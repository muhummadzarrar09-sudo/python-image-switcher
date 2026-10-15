"""Probe correctness on CPU; actual GPU execution is a user-hardware gate."""
from __future__ import annotations

import numpy as np
from PIL import Image

from scripts.probe_gpu import CONTRAST, EXPOSURE, cpu_pixels, fixture, gpu_devices
from src.editor.batch import BatchSession
from src.editor.render import render


def test_cpu_probe_matches_export_math_on_generated_png(tmp_path):
    source = fixture(49, 38)
    path = tmp_path / "generated.png"
    Image.fromarray(source).save(path)
    batch = BatchSession()
    photo = batch.add_photo(str(path))
    batch.set_batch("exposure", EXPOSURE)
    batch.set_batch("contrast", CONTRAST)
    expected, _, _ = render(photo, batch)
    assert np.array_equal(cpu_pixels(source), np.asarray(expected))


def test_device_selection_never_treats_cpu_opencl_as_gpu():
    class Platform:
        def get_devices(self, device_type):
            assert device_type == 42
            return ["GPU"]

    class CL:
        class device_type:
            GPU = 42

        @staticmethod
        def get_platforms():
            return [Platform()]

    assert gpu_devices(CL) == ["GPU"]
    assert fixture(9, 8).shape == (8, 9, 3)
