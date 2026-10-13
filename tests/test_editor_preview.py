"""Preview is small, coalesced and never changes full-resolution export."""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from PIL import Image

from src.editor.batch import BatchSession
from src.editor.preview import PreviewRenderer, PreviewRequest, mask_point, preview_label, process_preview
from scripts.probe_gpu import cpu_pixels
from src.editor.render import render


def test_nef_preview_label_never_claims_full_raw_pixels():
    assert "may use camera JPEG" in preview_label("photo.NEF", True)
    assert "may use camera JPEG" in preview_label("photo.NEF", False)
    assert preview_label("photo.jpg", True) == "Source preview"
    assert preview_label("photo.png", False) == "Edited preview"


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_mask_coordinate_mapping_ignores_matte_and_is_scale_invariant(scale):
    # Analogous to 100/125/150% Tk scaling: events and displayed bounds are
    # measured in the same coordinate system, independent of actual OS DPI.
    bounds = tuple(v * scale for v in (30, 20, 200, 100))
    assert mask_point(bounds, 130 * scale, 70 * scale) == (.5, .5)
    assert mask_point(bounds, 30 * scale, 20 * scale) == (0, 0)
    for x, y in [(29, 70), (230, 70), (130, 19), (130, 120)]:
        assert mask_point(bounds, x * scale, y * scale) is None
    assert mask_point((0, 0, 0, 10), 0, 5) is None


def test_preview_is_canvas_size_while_master_is_full_size(tmp_path):
    source = tmp_path / "wide.jpg"
    Image.new("RGB", (1800, 1200), (20, 50, 90)).save(source)
    batch = BatchSession()
    photo = batch.add_photo(str(source))
    original, _, _ = render(photo, batch)
    before = process_preview(PreviewRequest(1, photo, batch, True, (200, 130)))
    edited = process_preview(PreviewRequest(2, photo, batch, False, (200, 130)))
    assert original.size == (1800, 1200)
    assert before.width <= 200 and before.height <= 130
    assert edited.width <= 200 and edited.height <= 130
    assert np.array_equal(np.asarray(render(photo, batch)[0]), np.asarray(original))


def test_multi_picture_jpg_second_still_preview_is_not_first(tmp_path):
    source = tmp_path / "CSC0108.JPG"
    Image.new("RGB", (800, 600), "red").save(
        source, format="MPO", save_all=True,
        append_images=[Image.new("RGB", (800, 600), "blue")])
    batch = BatchSession()
    photo = batch.add_photo(str(source), frame_index=1)
    for before in (True, False):
        image = process_preview(PreviewRequest(1, photo, batch, before, (240, 160)))
        assert image.getpixel((image.width//2, image.height//2))[2] > 240
        assert image.width <= 240 and image.height <= 160


def test_gpu_opt_in_uses_preview_only_and_falls_back_on_driver_failure(tmp_path, monkeypatch):
    from src.editor import preview as preview_module

    source = tmp_path / "color.png"
    Image.new("RGB", (160, 120), (105, 75, 55)).save(source)
    batch = BatchSession()
    photo = batch.add_photo(str(source))
    batch.set_batch("exposure", .35)
    batch.set_batch("contrast", .2)
    request = PreviewRequest(1, photo, batch, False, (100, 80))
    cpu = process_preview(request)

    class FakeGPU:
        device_name = "fake test GPU"

        def __init__(self):
            self.calls = 0
            self.failed = False

        def apply(self, image, exposure, contrast):
            assert (exposure, contrast) == (.35, .2)
            self.calls += 1
            return Image.fromarray(cpu_pixels(np.asarray(image)))

    monkeypatch.setenv("IMAGE_SWITCHER_GPU", "auto")
    monkeypatch.setattr(preview_module, "OpenCLPreview", FakeGPU)
    worker = PreviewRenderer()
    try:
        deadline = time.monotonic() + 4
        while worker.gpu_status == "checking" and time.monotonic() < deadline:
            time.sleep(.005)
        assert worker.gpu_status == "GPU ready: fake test GPU"
        worker.submit(request)
        deadline = time.monotonic() + 4
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.result()
            time.sleep(.005)
        assert result is not None and result[2] is None and result[3] is True
        assert np.array_equal(np.asarray(result[1]), np.asarray(cpu))
    finally:
        worker.close()

    def driver_down():
        raise RuntimeError("driver unavailable")

    monkeypatch.setattr(preview_module, "OpenCLPreview", driver_down)
    worker = PreviewRenderer()
    try:
        deadline = time.monotonic() + 4
        while worker.gpu_status == "checking" and time.monotonic() < deadline:
            time.sleep(.005)
        worker.submit(request)
        deadline = time.monotonic() + 4
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.result()
            time.sleep(.005)
        assert result is not None and result[2] is None and result[3] is False
        assert worker.gpu_error == "driver unavailable"
        assert np.array_equal(np.asarray(result[1]), np.asarray(cpu))
    finally:
        worker.close()
    # Startup initializes the GPU even if the current recipe cannot use it;
    # an unsupported Sharpness recipe still renders on CPU.
    monkeypatch.setattr(preview_module, "OpenCLPreview", FakeGPU)
    batch.set_batch("sharpness", .4)
    worker = PreviewRenderer()
    try:
        deadline = time.monotonic() + 4
        while worker.gpu_status == "checking" and time.monotonic() < deadline:
            time.sleep(.005)
        worker.submit(PreviewRequest(2, photo, batch, False, (100, 80)))
        deadline = time.monotonic() + 4
        result = None
        while result is None and time.monotonic() < deadline:
            result = worker.result()
            time.sleep(.005)
        assert result is not None and result[2] is None and result[3] is False
        assert worker.gpu_error is None
    finally:
        worker.close()
    # Explicit opt-out does not even initialize an OpenCL context.
    monkeypatch.setenv("IMAGE_SWITCHER_GPU", "off")
    monkeypatch.setattr(preview_module, "OpenCLPreview", driver_down)
    worker = PreviewRenderer()
    try:
        assert worker.gpu_status == "CPU (GPU off)"
        assert worker.gpu_error is None
    finally:
        worker.close()
    # No preview-only optimization may change the full-resolution export path.
    assert render(photo, batch)[0].size == (160, 120)


def test_only_latest_request_survives_slow_worker(tmp_path):
    started = threading.Event()
    release = threading.Event()
    observed = []

    def processor(request):
        observed.append(request.generation)
        if request.generation == 1:
            started.set()
            assert release.wait(5)
        return Image.new("RGB", (10, 10), (request.generation, 0, 0))

    batch = BatchSession()
    source = tmp_path / "p.png"
    Image.new("RGB", (10, 10)).save(source)
    photo = batch.add_photo(str(source))
    worker = PreviewRenderer(processor)
    try:
        worker.submit(PreviewRequest(1, photo, batch, False, (10, 10)))
        assert started.wait(2)
        for generation in range(2, 25):
            worker.submit(PreviewRequest(generation, photo, batch, False, (10, 10)))
        release.set()
        deadline = time.monotonic() + 5
        result = None
        while time.monotonic() < deadline:
            result = worker.result()
            if result is not None:
                break
            time.sleep(.01)
        assert result is not None and result[0] == 24 and result[1].getpixel((0, 0)) == (24, 0, 0)
        assert observed == [1, 24]  # queued intermediate slider updates are skipped
    finally:
        release.set()
        worker.close()
