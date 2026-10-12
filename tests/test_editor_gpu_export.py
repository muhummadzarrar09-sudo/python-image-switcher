"""GPU batch export is opt-in per eligible recipe, exact or CPU-fallback."""
from __future__ import annotations

from pathlib import Path

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
    results = export_batch(batch, str(tmp_path / "gpu"), accelerator=accelerated)
    assert [number for number, _, _ in results] == [1, 2, 3]
    assert accelerated.full_calls == 2
    assert batch.get(2).protected
    for number, master, project in results:
        assert Path(project).exists()  # protected photo still has its project
        cpu, _, _ = render(batch.get(number), batch)
        with Image.open(master) as actual:
            assert np.array_equal(np.asarray(cpu), np.asarray(actual))


def test_failed_device_redoes_master_on_cpu_without_partial_output(tmp_path):
    source = tmp_path / "product.jpg"
    Image.new("RGB", (80, 65), (52, 117, 190)).save(source)
    batch = BatchSession()
    photo = batch.add_photo(str(source))
    batch.set_batch("exposure", .35)
    batch.set_batch("contrast", .2)
    gpu = FakeGPU(fail=True)
    outputs = export_batch(batch, str(tmp_path / "results"), accelerator=gpu)
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
