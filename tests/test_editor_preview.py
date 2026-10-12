"""Preview is small, coalesced and never changes full-resolution export."""
from __future__ import annotations

import threading
import time

import numpy as np
from PIL import Image

from src.editor.batch import BatchSession
from src.editor.preview import PreviewRenderer, PreviewRequest, process_preview
from src.editor.render import render


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
