"""GPU batch export is opt-in per eligible recipe, exact or CPU-fallback."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
from PIL import Image

from src.editor.batch import BatchSession
from src.editor.gpu_preview import OpenCLPreview
from src.editor.render import render
from src.editor.workflow import export_batch


def reference(image, exposure, contrast):
    data = np.asarray(image).astype(np.float32)
    data /= 255
    if exposure:
        data *= 2 ** exposure
    if contrast:
        data[:] = (data - .5) * (1 + contrast) + .5
    np.clip(data, 0, 1, out=data)
    data *= 255
    np.rint(data, out=data)
    return Image.fromarray(data.astype(np.uint8), "RGB")


class FakeGPU:
    def __init__(self, fail=False):
        self.full_calls = 0
        self.device_name = "test double, not a GPU"
        self.failed = False
        self.fail = fail
        self.error = None

    def apply_full(self, image, exposure, contrast):
        if self.fail:
            raise RuntimeError("lost device while copying pixels")
        self.full_calls += 1
        return reference(image, exposure, contrast)


def test_batch_exports_gpu_eligible_and_cpu_protected_with_pixel_parity(tmp_path):
    batch = BatchSession()
    for number in range(3):
        source = tmp_path / f"subject-{number}.png"
        Image.new("RGB", (64, 48), (number * 30 + 20, 80, 170)).save(source)
        batch.add_photo(str(source))
    batch.edit_photo(2, "brightness", .3)  # protected, not GPU eligible
    batch.set_batch("exposure", .35)
    batch.set_batch("contrast", .2)
    accelerated = FakeGPU()
    usage = []
    results = export_batch(batch, str(tmp_path / "gpu"), accelerator=accelerated,
                           on_exported=lambda number, done, total, gpu:
                               usage.append((number, done, total, gpu)))
    assert [number for number, _, _ in results] == [1, 2, 3]
    assert usage == [(1, 1, 3, True), (2, 2, 3, False), (3, 3, 3, True)]
    assert accelerated.full_calls == 2
    assert batch.get(2).protected
    for number, master, project in results:
        assert Path(project).exists()  # protected photo still has its project
        cpu, _, _ = render(batch.get(number), batch)
        with Image.open(master) as actual:
            assert np.array_equal(np.asarray(cpu), np.asarray(actual))


def test_421_distinct_generated_photos_keep_protected_numbers_and_bounded_outputs(tmp_path):
    # Structural >400-photo test with tiny distinct fixtures and a TEST DOUBLE.
    # This is not a real GPU benchmark or evidence about camera I/O/latency.
    batch = BatchSession()
    for index in range(421):
        source = tmp_path / f"distinct-{index:04d}.png"
        Image.new("RGB", (20, 16), (index % 256, (index * 3) % 256, (index * 7) % 256)).save(source)
        photo = batch.add_photo(str(source))
        if index % 7 == 0:
            batch.edit_photo(photo.number, "brightness", .1)  # explicit protected CPU route
    batch.set_batch("exposure", .35)
    batch.set_batch("contrast", .2)
    gpu = FakeGPU()
    output = tmp_path / "full-batch"
    used_gpu, used_cpu = [], []

    def consume(number, done, total, accelerated):
        assert total == 421 and number == done
        photo = batch.get(number)
        master = output / f"{number:04d}-distinct-{number-1:04d}.png"
        project = output / f"{number:04d}-distinct-{number-1:04d}.isphoto"
        assert len(list(output.glob("*.png"))) == 1  # completed pairs never pile up
        assert len(list(output.glob("*.isphoto"))) == 1
        expected, _, _ = render(photo, batch)
        with Image.open(master) as actual:
            assert np.array_equal(np.asarray(actual), np.asarray(expected))
        from src.editor.project import read_project
        assert read_project(str(project)).manifest["protected"] == photo.protected
        (used_gpu if accelerated else used_cpu).append(number)
        master.unlink()
        project.unlink()

    results = export_batch(batch, str(output), accelerator=gpu, on_exported=consume)
    assert len(results) == 421
    assert [row[0] for row in results] == list(range(1, 422))
    assert used_cpu == [number for number in range(1, 422) if (number - 1) % 7 == 0]
    assert used_gpu == [number for number in range(1, 422) if (number - 1) % 7 != 0]
    assert gpu.full_calls == len(used_gpu)
    assert not list(output.iterdir())


def test_failed_device_redoes_master_on_cpu_without_partial_output(tmp_path):
    source = tmp_path / "product.jpg"
    Image.new("RGB", (80, 65), (52, 117, 190)).save(source)
    batch = BatchSession()
    photo = batch.add_photo(str(source))
    batch.set_batch("exposure", .35)
    batch.set_batch("contrast", .2)
    gpu = FakeGPU(fail=True)
    usage = []
    outputs = export_batch(batch, str(tmp_path / "results"), accelerator=gpu,
                           on_exported=lambda number, _done, _total, used:
                               usage.append((number, used)))
    assert usage == [(1, False)]
    assert gpu.failed and "lost device" in gpu.error and gpu.full_calls == 0
    expected, _, _ = render(photo, batch)
    with Image.open(outputs[0][1]) as master:
        assert np.array_equal(np.asarray(master), np.asarray(expected))
    assert Path(outputs[0][2]).is_file()


def test_byte_complete_recipe_preflight_rejects_mismatching_gpu():
    backend = OpenCLPreview.__new__(OpenCLPreview)
    backend._parity = {}
    backend._transform = lambda *_args, **_kwargs: Image.new("RGB", (256, 1), "black")
    with pytest.raises(ValueError, match="differs from CPU"):
        backend._check_exact_parity(.35, .2)
    assert backend._parity[(.35, .2)] is False


def test_full_export_benchmark_measures_numbered_masters(tmp_path, monkeypatch, capsys):
    from scripts import benchmark_gpu_batch

    monkeypatch.setattr(benchmark_gpu_batch, "OpenCLPreview", FakeGPU)
    consumed = []
    real_consume = benchmark_gpu_batch._consume_master

    def check_bounded_files(directory, number, source_stem):
        # The CPU/GPU export folders must not grow linearly with batch count.
        assert len(list(directory.glob("*.png"))) == 1
        assert len(list(directory.glob("*.isphoto"))) == 1
        consumed.append((directory.name, number))
        return real_consume(directory, number, source_stem)

    monkeypatch.setattr(benchmark_gpu_batch, "_consume_master", check_bounded_files)
    monkeypatch.setattr(sys, "argv", ["benchmark_gpu_batch.py", "--count", "3",
                                  "--size", "320x240", "--write-exports"])
    benchmark_gpu_batch.main()
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert "CPU PNG/.isphoto exports: 3/3 complete" in output.err
    assert "GPU-path PNG/.isphoto exports: 3/3 complete" in output.err
    assert consumed == [("cpu-exports", n) for n in (1, 2, 3)] + [
        ("gpu-exports", n) for n in (1, 2, 3)]
    assert report["count"] == 3
    assert report["gpu_full_render_count"] == 3
    assert report["all_pixel_hashes_match"]
    assert report["full_export"]["gpu_adjusted_photo_numbers"] == [1, 2, 3]
    assert report["full_export"]["all_master_pixel_hashes_match"]
    assert report["full_export"]["master_and_project_count"] == 3
