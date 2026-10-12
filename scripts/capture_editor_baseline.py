"""Capture reproducible *actual Windows* editor states for MUH-45.

By default this uses an AI-generated camera test image, NOT a signed-off real
photo baseline. Pass --photo later to test local photos; generated screenshots
and source paths are private and are never added to Git automatically.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import sys
import traceback


def window_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x"))
        if width < 1000 or height < 700:
            raise ValueError
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Window size must be WIDTHxHEIGHT, at least 1000x700") from exc


def bounds(widget) -> dict[str, int]:
    return {"x": widget.winfo_rootx(), "y": widget.winfo_rooty(),
            "width": widget.winfo_width(), "height": widget.winfo_height()}


def dpi_for_window(widget) -> int | None:
    if sys.platform != "win32":
        return None
    try:
        from ctypes import windll
        return int(windll.user32.GetDpiForWindow(widget.winfo_id()))
    except (AttributeError, OSError):
        return None  # older Windows versions do not expose GetDpiForWindow


def run(photos: list[Path], output: Path, size: tuple[int, int], wait_ms: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Capture the baseline on Windows 11, not in Linux CI")
    # Delay desktop imports until after platform and CLI checks. Direct script
    # invocation puts scripts/ rather than the repository root on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import customtkinter as ctk
    from PIL import ImageGrab
    from src.editor.render import source_info
    from src.editor.window import EditorWindow, ExportOptions

    for photo in photos:
        if not photo.is_file():
            raise FileNotFoundError(photo)
        source_info(str(photo))
    output.mkdir(parents=True, exist_ok=True)
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    editor = EditorWindow(root)
    # CTk's geometry API accepts logical units and scales them internally;
    # the comparison viewport is specified in *physical* client pixels.
    scale = editor._get_window_scaling()
    editor.geometry(f"{round(size[0] / scale)}x{round(size[1] / scale)}")
    editor.update()
    meta: dict = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "requested_window": {"width": size[0], "height": size[1]},
        "dpi_for_window": dpi_for_window(editor),
        "tk_pixels_per_point": float(root.tk.call("tk", "scaling")),
        "ctk_window_scaling": float(editor._get_window_scaling()),
        "source_names": [p.name for p in photos],  # never store full private source paths
        "fixture_only": all(p.resolve() == (Path(__file__).resolve().parents[1] / "tests/fixtures/ui-camera.jpg")
                            for p in photos),
        "states": {},
        "notes": "Real OS capture; fixture/photo and approval must be recorded separately. "
                 "No source pixels or AI-generated mockup are treated as ground truth.",
    }
    dialog = None
    popups: dict[str, object] = {}
    states: list[tuple[str, object]] = []

    def populate():
        # Two numbered entries even when a single real reference image is supplied.
        first = editor.batch.add_photo(str(photos[0]))
        editor.batch.add_photo(str(photos[1] if len(photos) > 1 else photos[0]))
        editor.select(first.number)

    def protect():
        editor.scope.set("Selected")
        editor.sync_sliders()
        editor.change_value("contrast", .25)
        editor.scope.set("Batch")
        editor.sync_sliders()
        assert editor.selected_photo().protected

    def crop():
        editor.open_crop_tools()
        popups["crop-tools"] = editor.crop_window

    def background():
        editor.close_crop_tools()
        editor.open_background_tools()
        popups["background-tools"] = editor.background_window

    def export():
        nonlocal dialog
        editor.close_background_tools()
        dialog = ExportOptions(editor)
        popups["export-overlay"] = dialog

    states.extend([("empty-editor", lambda: None), ("populated-editor", populate),
                   ("protected-batch", protect), ("crop-tools", crop),
                   ("background-tools", background), ("export-overlay", export)])

    def save_metadata():
        (output / "capture.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    def capture(index: int):
        nonlocal dialog
        if index == len(states):
            if dialog and dialog.winfo_exists():
                dialog.close()
            editor.destroy()
            root.destroy()
            return
        name, setup = states[index]
        try:
            setup()
            editor.update_idletasks()
            editor.after(wait_ms, lambda: screenshot(index, name))
        except Exception:
            traceback.print_exc()
            meta["error"] = f"Failed to prepare {name}"
            save_metadata()
            root.destroy()
            raise

    def screenshot(index: int, name: str):
        try:
            rect = bounds(editor)  # Tk client-area coordinates; titlebar/taskbar excluded
            bbox = (rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            image.save(output / f"{name}.png")
            state = {"editor_client": rect, "image_pixels": list(image.size),
                     "selected_number": editor.current,
                     "protected_numbers": editor.batch.excluded_numbers,
                     "scope": editor.scope.get()}
            for key in ("header", "toolbar", "sidebar", "workspace", "panel", "canvas"):
                widget = getattr(editor, key, None)
                if widget:
                    state[key] = bounds(widget)
            popup = popups.get(name)
            if popup and popup.winfo_exists():
                popup_rect = bounds(popup)
                state["popup"] = popup_rect
                popup_bbox = (popup_rect["x"], popup_rect["y"],
                              popup_rect["x"] + popup_rect["width"],
                              popup_rect["y"] + popup_rect["height"])
                ImageGrab.grab(bbox=popup_bbox, all_screens=True).save(output / f"{name}-popup.png")
            meta["states"][name] = state
            save_metadata()
            print(f"Captured {name}: {image.width}x{image.height}")
            editor.after(100, lambda: capture(index + 1))
        except Exception:
            traceback.print_exc()
            meta["error"] = f"Failed to capture {name}"
            save_metadata()
            root.destroy()
            raise

    editor.after(wait_ms, lambda: capture(0))
    root.mainloop()
    if "error" in meta or len(meta["states"]) != len(states):
        raise RuntimeError(f"Incomplete capture; see {output / 'capture.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", type=Path, action="append",
                        help="Optional real local photo (repeat for a second image). If omitted, "
                             "uses the labeled AI-generated camera test fixture, NOT a sign-off baseline.")
    parser.add_argument("--output", type=Path, default=Path("ui-captures") / "windows-11",
                        help="Ignored local directory for screenshots and measurement JSON")
    parser.add_argument("--window", type=window_size, default=(1456, 766),
                        help="Target Tk client dimensions WIDTHxHEIGHT (default 1456x766)")
    parser.add_argument("--wait-ms", type=int, default=900,
                        help="Delay after each state before screenshot (at least 300 ms)")
    args = parser.parse_args()
    if args.wait_ms < 300:
        parser.error("--wait-ms must be at least 300")
    photos = args.photo or [Path(__file__).resolve().parents[1] / "tests/fixtures/ui-camera.jpg"]
    run(photos, args.output, args.window, args.wait_ms)


if __name__ == "__main__":
    main()
