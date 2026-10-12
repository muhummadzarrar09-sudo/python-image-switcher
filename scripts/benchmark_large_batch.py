"""Windows-only 421+ generated JPG import/RAM/UI diagnostic (no private photos).

This stresses numbered import, bounded queue and paged rail. Synthetic JPGs do
NOT stand in for camera NEF/JPG decode, SSD latency or full-batch export.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_editor import peak_memory_bytes  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=421)
    args = parser.parse_args()
    if not 401 <= args.count <= 800:
        parser.error("--count must be 401..800 (bounded diagnostic)")
    if sys.platform != "win32":
        parser.error("Use the Windows 11 Tk editor for this UI/RAM diagnostic")
    import customtkinter as ctk
    from PIL import Image
    from src.editor.window import EditorWindow, RAIL_PAGE_SIZE

    with tempfile.TemporaryDirectory(prefix="image-switcher-421-") as directory:
        source = Path(directory) / "generated.jpg"
        with Image.open(ROOT / "tests/fixtures/ui-camera.jpg") as fixture:
            fixture.resize((1600, 1200), Image.Resampling.BICUBIC).save(source, quality=90)
        # Distinct numbered paths; hardlinks avoid storing 421 identical JPGs.
        # This tests UI/queue/RAM, not varied disks or camera codecs.
        paths = []
        for number in range(1, args.count + 1):
            path = Path(directory) / f"fixture-{number:04d}.jpg"
            try:
                path.hardlink_to(source)
            except OSError:
                shutil.copyfile(source, path)
            paths.append(str(path))
        root = ctk.CTk()
        root.withdraw()
        editor = EditorWindow(root)
        try:
            root.update()
            start = monotonic()
            editor.start_import(paths)
            queue_peak = 0
            deadline = start + 180
            while editor.importing and monotonic() < deadline:
                root.update()
                queue_peak = max(queue_peak, editor._import_queue.qsize())
                sleep(.01)
            if editor.importing:
                raise TimeoutError("Synthetic batch import did not finish in 180 seconds")
            elapsed = monotonic() - start
            if len(editor.batch.photos) != args.count or len(editor._tiles) > RAIL_PAGE_SIZE:
                raise AssertionError("Missing numbered still or unbounded thumbnail rail")
            peak = peak_memory_bytes()
            report = {"fixture": "421+ generated 1600x1200 JPGs with separate paths (hardlinked bytes)",
                      "count": args.count, "seconds": round(elapsed, 2),
                      "peak_process_mib": round(peak / 1024**2, 1) if peak is not None else None,
                      "peak_pending_file_results": queue_peak,
                      "import_queue_limit": editor._import_queue.maxsize,
                      "mounted_rail_tiles": len(editor._tiles),
                      "rail_tile_limit": RAIL_PAGE_SIZE,
                      "gpu_status": editor._preview_renderer.gpu_status,
                      "note": "Generated JPG paths only; no private photo, NEF, full-size batch export, "
                              "Tk p95 latency or varied-file I/O measured."}
            print(json.dumps(report, indent=2))
        finally:
            editor.destroy()
            root.destroy()


if __name__ == "__main__":
    main()
