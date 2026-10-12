"""Generated JPG batch-edit render benchmark; no personal photos or disk export.

Exercises *the full-resolution render path* for numbered batch photos with
eligible exposure/contrast. It does NOT measure PNG/.isphoto encoding, Tk p95,
NEF, all adjustments or a real batch of 400 distinct camera photos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_editor import peak_memory_bytes  # noqa: E402
from src.editor.batch import BatchSession  # noqa: E402
from src.editor.gpu_preview import OpenCLPreview  # noqa: E402
from src.editor.render import render  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--size", default="2400x1600")
    args = parser.parse_args()
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
        if not (1 <= args.count <= 100 and 1 <= width * height <= 20_000_000
                and width > 0 and height > 0):
            raise ValueError
    except ValueError:
        parser.error("Count must be 1..100 and size WIDTHxHEIGHT up to 20 MP")
    with tempfile.TemporaryDirectory(prefix="image-switcher-batch-gpu-") as directory:
        path = Path(directory) / "generated.jpg"
        with Image.open(ROOT / "tests/fixtures/ui-camera.jpg") as original:
            original.resize((width, height), Image.Resampling.BICUBIC).save(path, quality=92)
        batch = BatchSession()
        for _ in range(args.count):
            batch.add_photo(str(path))
        batch.set_batch("exposure", .35)
        batch.set_batch("contrast", .2)
        cpu_seconds, gpu_seconds = [], []
        cpu_hashes, gpu_hashes = [], []
        try:
            accelerator = OpenCLPreview()
        except Exception as exc:
            print(json.dumps({"gpu_executed": False, "error": str(exc)}, indent=2))
            raise SystemExit(2) from None
        for photo in batch.photos:
            start = perf_counter()
            cpu, _, _ = render(photo, batch)
            cpu_seconds.append(perf_counter() - start)
            cpu_hashes.append(hashlib.sha256(cpu.tobytes()).hexdigest())
            del cpu
            start = perf_counter()
            accelerated, _, _ = render(photo, batch, accelerator=accelerator)
            gpu_seconds.append(perf_counter() - start)
            gpu_hashes.append(hashlib.sha256(accelerated.tobytes()).hexdigest())
            del accelerated
        gpu_used = accelerator.full_calls == args.count
        peak = peak_memory_bytes()
        report = {"fixture": "repeated generated JPG bytes as distinct numbered entries",
                  "count": args.count, "size": [width, height],
                  "gpu_device": accelerator.device_name, "gpu_executed_for_all": gpu_used,
                  "gpu_full_render_count": accelerator.full_calls,
                  "gpu_error": getattr(accelerator, "error", None),
                  "cpu_median_seconds": round(float(np.median(cpu_seconds)), 5),
                  "gpu_path_median_seconds": round(float(np.median(gpu_seconds)), 5),
                  "cpu_total_seconds": round(sum(cpu_seconds), 3),
                  "gpu_path_total_seconds": round(sum(gpu_seconds), 3),
                  "all_pixel_hashes_match": cpu_hashes == gpu_hashes,
                  "peak_process_mib": round(peak / 1024**2, 1) if peak is not None else None,
                  "note": "Includes full-size decode/adjustment only, not PNG/.isphoto writes, "
                          "ICC verification, NEF or 400 distinct photo I/O."}
        print(json.dumps(report, indent=2))
        if not gpu_used or cpu_hashes != gpu_hashes:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
