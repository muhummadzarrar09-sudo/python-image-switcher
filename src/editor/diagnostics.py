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
from .preview import PreviewRenderer, PreviewRequest, process_preview


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
            report = {"packaged": bool(getattr(sys, "frozen", False)),
                      "gpu_status": worker.gpu_status, "gpu_used_for_generated_preview": result[3],
                      "gpu_error": worker.gpu_error,
                      "cpu_pixel_sha256": hashlib.sha256(cpu.tobytes()).hexdigest(),
                      "preview_pixel_sha256": hashlib.sha256(gpu_image.tobytes()).hexdigest(),
                      "max_channel_difference": int(delta.max()),
                      "differing_channel_count": int(np.count_nonzero(delta)),
                      "total_channels": int(delta.size),
                      "note": "Generated 512x256 PNG exposure/contrast only. No private photo, "
                              "full-resolution export or Tk responsiveness measured."}
        finally:
            worker.close()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
