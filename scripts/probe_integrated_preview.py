"""Compare automatically initialized GPU editor preview vs CPU on generated JPG fixture.

Source-checkout diagnostic, not a bundled installer feature. Never reads a
private photo or writes a master. Results are local; please share the JSON.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter, sleep

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.editor.batch import BatchSession  # noqa: E402
from src.editor.preview import PreviewRenderer, PreviewRequest  # noqa: E402


def measure(photo, batch, *, gpu: bool, repeats: int = 5) -> dict:
    os.environ["IMAGE_SWITCHER_GPU"] = "auto" if gpu else "off"
    worker = PreviewRenderer()
    samples = []
    image = None
    used = False
    try:
        if gpu:
            deadline = perf_counter() + 30
            while worker.gpu_status == "checking" and perf_counter() < deadline:
                sleep(.01)
        for generation in range(1, repeats + 2):
            start = perf_counter()
            worker.submit(PreviewRequest(generation, photo, batch, False, (1200, 800)))
            deadline = start + 30
            while perf_counter() < deadline:
                result = worker.result()
                if result and result[0] == generation:
                    if result[2]:
                        raise RuntimeError(result[2])
                    image = result[1]
                    used = result[3]
                    break
                sleep(.001)
            else:
                raise TimeoutError("Preview took longer than 30 seconds")
            if generation > 1:  # warmup includes context/kernel/JPEG setup
                samples.append(perf_counter() - start)
        return {"gpu_used": used, "gpu_error": worker.gpu_error,
                "median_seconds": round(float(np.median(samples)), 5),
                "size": list(image.size),
                "sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                "pixels": np.asarray(image).copy()}
    finally:
        worker.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="image-switcher-preview-") as directory:
        source = Path(directory) / "generated.jpg"
        with Image.open(ROOT / "tests/fixtures/ui-camera.jpg") as fixture:
            fixture.resize((2400, 1600), Image.Resampling.BICUBIC).save(source, quality=92)
        batch = BatchSession()
        photo = batch.add_photo(str(source))
        batch.set_batch("exposure", .35)
        batch.set_batch("contrast", .2)
        cpu = measure(photo, batch, gpu=False)
        gpu = measure(photo, batch, gpu=True)
    diff = np.abs(cpu["pixels"].astype(np.int16) - gpu["pixels"].astype(np.int16))
    for sample in (cpu, gpu):
        del sample["pixels"]
    print(json.dumps({"fixture": "checked-in AI sample enlarged to 2400x1600 JPG",
                      "preview_size": [1200, 800], "cpu": cpu, "gpu_auto": gpu,
                      "max_channel_difference": int(diff.max()),
                      "differing_channel_count": int(np.count_nonzero(diff)),
                      "total_channels": int(diff.size),
                      "export_gpu_enabled": False,
                      "note": "Measures complete preview rendering (including JPEG draft/decode and worker wait), "
                              "not Tk drawing, NEF, ICC, Sharpness or packaging."}, indent=2))
    if not gpu["gpu_used"] or int(diff.max()) > 1:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
