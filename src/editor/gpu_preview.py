"""Experimental *preview-only* OpenCL exposure/contrast for 8-bit RGB.

No import of pyopencl at module load, no GPU requirement on CPU-only machines.
Not used by full-resolution rendering, PNG/TIFF export or NEF processing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .batch import BatchSession, Photo

KERNEL = r"""
__kernel void exposure_contrast(__global const uchar *source,
                                __global uchar *output, const float exposure,
                                const float contrast, const int n) {
    int i = get_global_id(0);
    if (i >= n) return;
    float value = (float)source[i] / 255.0f;
    value *= exposure;
    value = (value - 0.5f) * contrast + 0.5f;
    output[i] = convert_uchar_sat_rte(clamp(value, 0.0f, 1.0f) * 255.0f);
}
"""


def gpu_devices(cl):
    """GPU only: an OpenCL CPU implementation is not hardware acceleration."""
    found = []
    for platform in cl.get_platforms():
        try:
            found.extend(platform.get_devices(device_type=cl.device_type.GPU))
        except cl.LogicError as exc:
            if exc.code != cl.status_code.DEVICE_NOT_FOUND:
                raise
    return found


def eligible(photo: Photo, batch: BatchSession) -> bool:
    """Conservative fast path; all other recipes keep the existing CPU preview."""
    values = batch.effective_settings(photo.number)
    return (Path(photo.source).suffix.lower() in (".jpg", ".jpeg", ".png")
            and (values["exposure"] != 0 or values["contrast"] != 0)
            and all(value == 0 for field, value in values.items()
                    if field not in ("exposure", "contrast"))
            and not (photo.crop or photo.rotation or photo.flip_horizontal
                     or photo.background or photo.mask_strokes))


class OpenCLPreview:
    """One worker-owned GPU context and bounded buffers for display-sized RGB."""

    def __init__(self):
        import pyopencl as cl  # optional; intentionally absent from required deps

        devices = gpu_devices(cl)
        if not devices:
            raise RuntimeError("No OpenCL GPU device")
        device = next((d for d in devices if "NVIDIA" in d.vendor.upper()), devices[0])
        self.cl = cl
        self.device_name = device.name
        self.context = cl.Context(devices=[device])
        self.queue = cl.CommandQueue(self.context)
        program = cl.Program(self.context, KERNEL).build()
        # Reuse the same kernel object (avoids repeated kernel retrieval/setup).
        self.kernel = cl.Kernel(program, "exposure_contrast")
        self._capacity = 0
        self._input = None
        self._output = None
        self.calls = 0

    def apply(self, image: Image.Image, exposure: float, contrast: float) -> Image.Image:
        if image.mode != "RGB" or image.width * image.height > 1_400_000:
            raise ValueError("GPU preview accepts canvas-size 8-bit RGB only")
        flat = np.ascontiguousarray(np.asarray(image)).reshape(-1)
        result = np.empty_like(flat)
        if flat.nbytes > self._capacity:
            # One input and one output buffer, reused while sizes stay small.
            self._input = self.cl.Buffer(self.context, self.cl.mem_flags.READ_ONLY, flat.nbytes)
            self._output = self.cl.Buffer(self.context, self.cl.mem_flags.WRITE_ONLY, flat.nbytes)
            self._capacity = flat.nbytes
        self.cl.enqueue_copy(self.queue, self._input, flat, is_blocking=False)
        self.kernel(self.queue, (flat.size,), None, self._input, self._output,
                    np.float32(2 ** exposure), np.float32(1 + contrast), np.int32(flat.size))
        self.cl.enqueue_copy(self.queue, result, self._output, is_blocking=True)
        self.calls += 1
        return Image.fromarray(result.reshape(image.height, image.width, 3), "RGB")
