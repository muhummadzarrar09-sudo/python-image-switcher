"""Headless, generated-pixel report for the *installed* GPU-ready editor.

The normal app never writes this report; the explicit --gpu-report command does.
No personal photo is read or included in the output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from time import monotonic, sleep

import numpy as np
from PIL import Image

from .batch import BatchSession
from .gpu_preview import OpenCLPreview
from .preview import PreviewRenderer, PreviewRequest, process_preview
from .render import render
from .workflow import export_batch


def installed_gpu_report(path: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="image-switcher-device-check-") as directory:
        # Exercise a representative range of channel values, not a solid swatch.
        y, x = np.indices((256, 512), dtype=np.uint16)
        pixels = np.stack(((x + y) % 256, (x * 3 + y) % 256,
                           (x + y * 7) % 256), axis=-1).astype(np.uint8)
        source = Path(directory) / "generated.png"
        Image.fromarray(pixels).save(source)
        batch = BatchSession()
        photo = batch.add_photo(str(source))
        batch.set_batch("exposure", .35)
        batch.set_batch("contrast", .2)
        request = PreviewRequest(1, photo, batch, False, (512, 256))
        cpu = process_preview(request)
        worker = PreviewRenderer()
        try:
            deadline = monotonic() + 20
            while worker.gpu_status == "checking" and monotonic() < deadline:
                sleep(.02)
            worker.submit(request)
            result = None
            deadline = monotonic() + 20
            while monotonic() < deadline:
                result = worker.result()
                if result is not None:
                    break
                sleep(.01)
            if result is None:
                raise TimeoutError("Preview did not finish within 20 seconds")
            if result[2]:
                raise RuntimeError(result[2])
            gpu_image = result[1]
            delta = np.abs(np.asarray(cpu).astype(np.int16) -
                           np.asarray(gpu_image).astype(np.int16))
            # Exercise the same full-resolution batch/export path used by the
            # installed UI, not merely an isolated kernel or preview.
            accelerator = None
            gpu_export_error = None
            if worker.gpu_status.startswith("GPU ready"):
                try:
                    accelerator = OpenCLPreview()
                except Exception as exc:
                    gpu_export_error = str(exc)
            # Bigger than one million pixels: the installed-app check now
            # exercises multiple GPU transfer tiles, not only preview-sized
            # pixels. This is still a generated fixture, never a camera photo.
            export_source = Path(directory) / "generated-full.png"
            Image.fromarray(pixels).resize((2400, 1600), Image.Resampling.NEAREST).save(export_source)
            export_session = BatchSession()
            export_photo = export_session.add_photo(str(export_source))
            export_session.set_batch("exposure", .35)
            export_session.set_batch("contrast", .2)
            cpu_master, _, _ = render(export_photo, export_session)
            gpu_master, _, _ = render(export_photo, export_session, accelerator=accelerator)
            export_difference = np.abs(np.asarray(cpu_master).astype(np.int16) -
                                       np.asarray(gpu_master).astype(np.int16))
            output = Path(directory) / "exported"
            exported_gpu_numbers = []
            results = export_batch(export_session, str(output), accelerator=accelerator,
                                   on_exported=lambda number, _done, _total, used_gpu:
                                       exported_gpu_numbers.append(number) if used_gpu else None)
            if len(results) != 1:
                raise AssertionError("Diagnostic export did not retain its numbered photo")
            with Image.open(results[0][1]) as exported:
                exported_difference = np.abs(np.asarray(cpu_master).astype(np.int16) -
                                             np.asarray(exported).astype(np.int16))
            report = {"packaged": bool(getattr(sys, "frozen", False)),
                      "gpu_status": worker.gpu_status, "gpu_used_for_generated_preview": result[3],
                      "gpu_used_for_generated_export": bool(exported_gpu_numbers),
                      "gpu_adjusted_export_photo_numbers": exported_gpu_numbers,
                      "export_dimensions": [2400, 1600],
                      "gpu_export_error": getattr(accelerator, "error", gpu_export_error),
                      "gpu_error": worker.gpu_error,
                      "cpu_pixel_sha256": hashlib.sha256(cpu.tobytes()).hexdigest(),
                      "preview_pixel_sha256": hashlib.sha256(gpu_image.tobytes()).hexdigest(),
                      "max_channel_difference": int(delta.max()),
                      "differing_channel_count": int(np.count_nonzero(delta)),
                      "total_channels": int(delta.size),
                      "export_max_channel_difference": int(export_difference.max()),
                      "exported_png_max_channel_difference": int(exported_difference.max()),
                      "note": "Generated 512x256 preview and 2400x1600 numbered PNG export only. "
                              "No private photo, NEF, all-recipe parity or Tk responsiveness measured."}
        finally:
            worker.close()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
