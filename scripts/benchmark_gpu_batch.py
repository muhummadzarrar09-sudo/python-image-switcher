"""Generated JPG full-resolution batch render + optional lossless-export benchmark.

Exercises numbered batch photos with eligible exposure/contrast. By default
only render math/decode is timed; --write-exports also times and verifies the
real PNG/.isphoto workflow. Does not measure Tk p95, NEF, all adjustments or
a batch of 400 distinct camera photos. Never reads personal photos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from src.editor.workflow import export_batch  # noqa: E402


def _progress(stage: str, done: int, total: int) -> None:
    """Bounded, immediate status; stdout stays machine-readable JSON."""
    if done == 1 or done == total or done % max(1, total // 10) == 0:
        print(f"{stage}: {done}/{total} complete", file=sys.stderr, flush=True)


def _consume_master(directory: Path, number: int, source_stem: str) -> bytes:
    """Compare the decoded master, then remove this generated benchmark pair.

    Keep temporary disk use independent of batch length while still running
    export_batch on the complete numbered session (no user files are touched).
    """
    master = directory / f"{number:04d}-{source_stem}.png"
    project = directory / f"{number:04d}-{source_stem}.isphoto"
    with Image.open(master) as image:
        digest = hashlib.sha256(image.tobytes()).digest()
    os.unlink(master)
    os.unlink(project)
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--size", default="2400x1600")
    parser.add_argument("--write-exports", action="store_true",
                        help="also time real temporary PNG/.isphoto exports on CPU and GPU; uses disk space")
    args = parser.parse_args()
    try:
        width, height = (int(x) for x in args.size.lower().split("x"))
        if not (1 <= args.count <= 1000 and 1 <= width * height <= 20_000_000
                and width > 0 and height > 0):
            raise ValueError
    except ValueError:
        parser.error("Benchmark count must be 1..1000 and size WIDTHxHEIGHT up to 20 MP")
    print(f"Starting {args.count} numbered {width}x{height} renders (CPU then GPU per photo). "
          "Status goes to stderr; final JSON prints after all work.", file=sys.stderr, flush=True)
    if args.write_exports:
        print("Full-file export is enabled: two sequential CPU/GPU passes write PNG and "
              ".isphoto projects to a temporary folder. This can take minutes for "
              "hundreds of photos; completed test files are now verified and removed "
              "as it goes. Ctrl+C once to cancel and let temporary cleanup finish.",
              file=sys.stderr, flush=True)
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
        for index, photo in enumerate(batch.photos, 1):
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
            _progress("Full-resolution CPU/GPU renders", index, args.count)
        render_gpu_calls = accelerator.full_calls
        gpu_used = render_gpu_calls == args.count
        full_export = None
        if args.write_exports:
            cpu_dir, gpu_dir = (Path(directory) / "cpu-exports",
                                Path(directory) / "gpu-exports")
            cpu_master_hashes: dict[int, bytes] = {}
            cpu_validation_seconds = [0.0]

            def on_cpu_export(number, done, total, _used_gpu):
                started = perf_counter()
                cpu_master_hashes[number] = _consume_master(cpu_dir, number, path.stem)
                _progress("CPU PNG/.isphoto exports", done, total)
                cpu_validation_seconds[0] += perf_counter() - started

            start = perf_counter()
            cpu_outputs = export_batch(batch, str(cpu_dir), on_exported=on_cpu_export)
            cpu_export_seconds = perf_counter() - start - cpu_validation_seconds[0]
            gpu_export_numbers: list[int] = []
            mismatched_numbers: list[int] = []
            gpu_validation_seconds = [0.0]

            def on_gpu_export(number, done, total, used_gpu):
                started = perf_counter()
                if used_gpu:
                    gpu_export_numbers.append(number)
                if _consume_master(gpu_dir, number, path.stem) != cpu_master_hashes[number]:
                    mismatched_numbers.append(number)
                _progress("GPU-path PNG/.isphoto exports", done, total)
                gpu_validation_seconds[0] += perf_counter() - started

            start = perf_counter()
            gpu_outputs = export_batch(batch, str(gpu_dir), accelerator=accelerator,
                                       on_exported=on_gpu_export)
            gpu_export_seconds = perf_counter() - start - gpu_validation_seconds[0]
            full_export = {"gpu_adjusted_photo_numbers": gpu_export_numbers,
                           "cpu_total_seconds": round(cpu_export_seconds, 3),
                           "gpu_path_total_seconds": round(gpu_export_seconds, 3),
                           "all_master_pixel_hashes_match": not mismatched_numbers,
                           "master_and_project_count": len(gpu_outputs),
                           "note": "Times include full-batch PNG/.isphoto writes but exclude "
                                   "per-file pixel verification and cleanup. Generated files "
                                   "are deleted after verification to bound temporary disk use. "
                                   "Sequential passes have different disk cache conditions."}
        peak = peak_memory_bytes()
        report = {"fixture": "repeated generated JPG bytes as distinct numbered entries",
                  "count": args.count, "size": [width, height],
                  "gpu_device": accelerator.device_name, "gpu_executed_for_all": gpu_used,
                  "gpu_full_render_count": render_gpu_calls,
                  "gpu_error": getattr(accelerator, "error", None),
                  "cpu_median_seconds": round(float(np.median(cpu_seconds)), 5),
                  "gpu_path_median_seconds": round(float(np.median(gpu_seconds)), 5),
                  "cpu_total_seconds": round(sum(cpu_seconds), 3),
                  "gpu_path_total_seconds": round(sum(gpu_seconds), 3),
                  "all_pixel_hashes_match": cpu_hashes == gpu_hashes,
                  "peak_process_mib": round(peak / 1024**2, 1) if peak is not None else None,
                  "full_export": full_export,
                  "note": "Render timings include full-size decode/adjustment only. "
                          "Optional full_export includes PNG/.isphoto writes. "
                          "No ICC verification, NEF or distinct camera photo I/O."}
        print(json.dumps(report, indent=2))
        if (not gpu_used or cpu_hashes != gpu_hashes or
                (full_export is not None and
                 (not full_export["all_master_pixel_hashes_match"] or
                  full_export["master_and_project_count"] != args.count or
                  len(full_export["gpu_adjusted_photo_numbers"]) != args.count))):
            raise SystemExit(2)


if __name__ == "__main__":
    main()
