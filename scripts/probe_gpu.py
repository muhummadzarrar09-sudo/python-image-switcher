"""Opt-in OpenCL hardware probe for MUH-56; does NOT accelerate the editor.

Runs a representative 8-bit exposure/contrast operation on generated pixels,
measuring transfer + kernel + readback on a REAL GPU device and comparing with
the current CPU math. No photo, network request, hardware ID or username used.
Install pyopencl only for this diagnostic; it is NOT an editor dependency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

# Direct script execution places scripts/ rather than the checkout on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.editor.gpu_preview import KERNEL, gpu_devices  # noqa: E402

# Same arithmetic/order and round-to-even as src/editor/render.py for these two
# sliders. An isolated diagnostic is NOT sufficient to enable GPU export.
EXPOSURE = .35
CONTRAST = .2


def cpu_pixels(source: np.ndarray) -> np.ndarray:
    data = source.astype(np.float32)
    data /= 255
    data *= 2.0 ** EXPOSURE
    data[:] = (data - .5) * (1 + CONTRAST) + .5
    np.clip(data, 0, 1, out=data)
    data *= 255
    np.rint(data, out=data)
    return data.astype(np.uint8)


def fixture(width: int, height: int) -> np.ndarray:
    """Deterministic textured RGB test input without requiring a personal photo."""
    y, x = np.indices((height, width), dtype=np.uint32)
    return np.stack(((x * 17 + y * 3) % 256, (x * 5 + y * 19) % 256,
                     (x * 7 + y * 11) % 256), axis=-1).astype(np.uint8)


def probe(width: int, height: int, repeats: int = 5) -> dict:
    import pyopencl as cl  # optional; do not load it in the app or installer

    devices = gpu_devices(cl)
    if not devices:
        raise RuntimeError("OpenCL has no GPU device; the editor remains CPU-only")
    # Both the RTX 4070 and Iris Xe can expose OpenCL. Prefer the NVIDIA GPU,
    # while allowing a GPU from another vendor if NVIDIA's runtime is absent.
    device = next((d for d in devices if "NVIDIA" in d.vendor.upper()), devices[0])
    context = cl.Context(devices=[device])
    queue = cl.CommandQueue(context, properties=cl.command_queue_properties.PROFILING_ENABLE)
    program = cl.Program(context, KERNEL).build()
    kernel = cl.Kernel(program, "exposure_contrast")
    source = fixture(width, height)
    flat = np.ascontiguousarray(source.reshape(-1))
    cpu_samples = []
    for _ in range(repeats):
        start = perf_counter()
        expected = cpu_pixels(source)
        cpu_samples.append(perf_counter() - start)
    output = np.empty_like(flat)
    mem = cl.mem_flags
    input_buffer = cl.Buffer(context, mem.READ_ONLY, flat.nbytes)
    output_buffer = cl.Buffer(context, mem.WRITE_ONLY, flat.nbytes)
    gpu_samples, kernel_samples = [], []
    for index in range(repeats + 1):
        start = perf_counter()
        cl.enqueue_copy(queue, input_buffer, flat, is_blocking=False)
        event = kernel(queue, (flat.size,), None, input_buffer, output_buffer,
                       np.float32(2 ** EXPOSURE), np.float32(1 + CONTRAST),
                       np.int32(flat.size))
        cl.enqueue_copy(queue, output, output_buffer, is_blocking=True)
        elapsed = perf_counter() - start  # includes device transfer and sync
        if index:  # first run is warmup, including driver initialization
            gpu_samples.append(elapsed)
            kernel_samples.append((event.profile.end - event.profile.start) / 1e9)
    delta = np.abs(expected.astype(np.int16).reshape(-1) - output.astype(np.int16))
    return {"gpu_executed": True, "editor_gpu_enabled": False,
            "selected_device": {"name": device.name, "vendor": device.vendor,
                                "driver": device.driver_version,
                                "reported_global_mem_gib": round(device.global_mem_size / (1024 ** 3), 2)},
            "size": [width, height], "repeats": repeats,
            "cpu_median_seconds": round(float(np.median(cpu_samples)), 5),
            "gpu_transfer_kernel_readback_median_seconds": round(float(np.median(gpu_samples)), 5),
            "gpu_kernel_only_median_seconds": round(float(np.median(kernel_samples)), 5),
            "max_channel_difference": int(delta.max()),
            "differing_channel_count": int(np.count_nonzero(delta)),
            "total_channels": int(delta.size),
            "note": "Diagnostic math only, NOT an editor acceleration or export-parity claim. "
                    "GPU results include transfers; decode, Sharpness, ICC, Tk and export remain CPU."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", default="2400x1600", help="Generated image WIDTHxHEIGHT, max 12 megapixels")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    try:
        width, height = (int(part) for part in args.size.lower().split("x"))
        if not (width > 0 and height > 0 and width * height <= 12_000_000 and 1 <= args.repeats <= 20):
            raise ValueError
    except ValueError:
        parser.error("Use --size WIDTHxHEIGHT up to 12 MP and --repeats 1..20")
    try:
        print(json.dumps(probe(width, height, args.repeats), indent=2))
    except Exception as exc:
        # Missing package, broken driver or compiler are diagnostics, not a
        # reason to break the mandatory CPU-only editor on the user's PC.
        print(json.dumps({"gpu_executed": False, "editor_gpu_enabled": False,
                          "error": str(exc), "error_type": type(exc).__name__}, indent=2))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
