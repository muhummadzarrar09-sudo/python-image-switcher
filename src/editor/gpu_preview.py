"""Optional OpenCL RGB exposure/contrast for previews and guarded batch export.

No import of pyopencl at module load, no GPU requirement on CPU-only machines.
Exports use it only after exact per-recipe 8-bit parity preflight; NEF and other
adjustments stay on CPU. Full-size GPU transfers are tiled to bound VRAM use.
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
    if (exposure != 1.0f) value *= exposure;
    if (contrast != 1.0f) value = (value - 0.5f) * contrast + 0.5f;
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


def eligible_export(photo: Photo, batch: BatchSession) -> bool:
    """Only simple 8-bit color edits are eligible; masters never lose precision."""
    values = batch.effective_settings(photo.number)
    return (Path(photo.source).suffix.lower() != ".nef"
            and (values["exposure"] != 0 or values["contrast"] != 0)
            and all(value == 0 for field, value in values.items()
                    if field not in ("exposure", "contrast"))
            and not photo.background and not photo.mask_strokes)


class OpenCLPreview:
    """One worker-owned GPU context and reusable bounded device buffers."""

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
        self.full_calls = 0
        self.failed = False
        self._parity: dict[tuple[float, float], bool] = {}

    def _transform(self, image: Image.Image, exposure: float, contrast: float,
                   *, tile_pixels: int) -> Image.Image:
        if image.mode != "RGB":
            raise ValueError("OpenCL color path requires 8-bit RGB")
        flat = np.ascontiguousarray(np.asarray(image)).reshape(-1)
        result = np.empty_like(flat)
        tile_channels = tile_pixels * 3
        for start in range(0, flat.size, tile_channels):
            source = flat[start:start + tile_channels]
            if source.nbytes > self._capacity:
                self._input = self.cl.Buffer(self.context, self.cl.mem_flags.READ_ONLY, source.nbytes)
                self._output = self.cl.Buffer(self.context, self.cl.mem_flags.WRITE_ONLY, source.nbytes)
                self._capacity = source.nbytes
            self.cl.enqueue_copy(self.queue, self._input, source, is_blocking=False)
            self.kernel(self.queue, (source.size,), None, self._input, self._output,
                        np.float32(2 ** exposure), np.float32(1 + contrast),
                        np.int32(source.size))
            # For device -> NumPy, PyOpenCL derives the byte count from this
            # exact-sized host slice (not the reusable device buffer capacity).
            self.cl.enqueue_copy(self.queue, result[start:start + source.size], self._output,
                                 is_blocking=True)
        return Image.fromarray(result.reshape(image.height, image.width, 3), "RGB")

    def apply(self, image: Image.Image, exposure: float, contrast: float) -> Image.Image:
        if image.width * image.height > 1_400_000:
            raise ValueError("GPU preview accepts canvas-size RGB only")
        result = self._transform(image, exposure, contrast, tile_pixels=1_400_000)
        self.calls += 1
        return result

    def _check_exact_parity(self, exposure: float, contrast: float) -> None:
        key = (exposure, contrast)
        if key not in self._parity:
            # For this color-only kernel each channel is independent; the 256
            # possible uint8 input values cover every output of an 8-bit RGB
            # photo for one recipe. Check before writing *any* exported master.
            values = np.arange(256, dtype=np.uint8)
            ramp = np.repeat(values[:, None], 3, axis=1).reshape(1, 256, 3)
            reference = ramp.astype(np.float32)
            reference /= 255
            if exposure:
                reference *= 2.0 ** exposure
            if contrast:
                reference[:] = (reference - 0.5) * (1 + contrast) + 0.5
            np.clip(reference, 0, 1, out=reference)
            reference *= 255
            np.rint(reference, out=reference)
            gpu = self._transform(Image.fromarray(ramp, "RGB"), exposure, contrast,
                                  tile_pixels=256)
            self._parity[key] = np.array_equal(np.asarray(gpu), reference.astype(np.uint8))
        if not self._parity[key]:
            raise ValueError("GPU arithmetic differs from CPU for this recipe")

    def apply_full(self, image: Image.Image, exposure: float, contrast: float) -> Image.Image:
        self._check_exact_parity(exposure, contrast)
        result = self._transform(image, exposure, contrast, tile_pixels=1_000_000)
        self.full_calls += 1
        return result
