"""Measure first full render wall time and process peak memory with a test photo.

Uses a temporary enlarged version of tests/fixtures/ui-camera.jpg. No personal
photo or large fixture is written to the repository. Windows/Linux results are
hardware-dependent and do NOT measure GPU acceleration or Tk responsiveness.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def peak_memory_bytes() -> int | None:
    if sys.platform == "win32":
        from ctypes import wintypes

        class ProcessCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = ProcessCounters()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (
            wintypes.HANDLE, ctypes.POINTER(ProcessCounters), wintypes.DWORD)
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize)
        return None
    if sys.platform.startswith("linux"):
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    return None


def run_one(path: str, mode: str) -> dict:
    from src.editor.batch import BatchSession
    from src.editor.render import render
    batch = BatchSession()
    photo = batch.add_photo(path)
    if mode == "adjusted":
        for key, value in (("exposure", .35), ("contrast", .2), ("sharpness", .4)):
            batch.set_batch(key, value)
    started = perf_counter()
    image, _, _ = render(photo, batch)
    elapsed = perf_counter() - started
    peak = peak_memory_bytes()
    return {"mode": mode, "size": list(image.shape[1::-1]) if not isinstance(image, Image.Image)
            else list(image.size), "seconds": round(elapsed, 3),
            "peak_process_mib": round(peak / 1024**2, 1) if peak is not None else None,
            "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", default="2400x1600", help="Synthetic test image size WIDTHxHEIGHT")
    parser.add_argument("--worker", nargs=2, metavar=("PATH", "MODE"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, str(ROOT))
        print(json.dumps(run_one(*args.worker)))
        return
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
        if width < 1 or height < 1 or width * height > 20_000_000:
            raise ValueError
    except ValueError:
        parser.error("--size must be WIDTHxHEIGHT up to 20 megapixels (safe benchmark allocation)")
    with tempfile.TemporaryDirectory(prefix="image-switcher-bench-") as directory:
        path = Path(directory) / "sample.jpg"
        with Image.open(ROOT / "tests/fixtures/ui-camera.jpg") as source:
            source.resize((width, height), Image.Resampling.BICUBIC).save(path, quality=92)
        results = []
        for mode in ("identity", "adjusted"):
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                      "--worker", str(path), mode], check=True,
                                     capture_output=True, text=True, cwd=ROOT)
            results.append(json.loads(process.stdout))
    print(json.dumps({"fixture": "AI-generated camera JPEG", "size": [width, height],
                      "gpu_used": False, "samples": results}, indent=2))


if __name__ == "__main__":
    main()
