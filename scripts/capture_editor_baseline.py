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
import time
import traceback


def window_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in value.lower().split("x"))
        if width < 960 or height < 640:
            raise ValueError
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Window size must be WIDTHxHEIGHT, at least 960x640") from exc


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


def monitor_work_area(widget) -> dict[str, int] | None:
    """Win32 visible work area for this window, excluding taskbar/docked bars."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = (("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD))

        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = (wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromWindow(widget.winfo_id(), 2)  # nearest monitor
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        area = info.rcWork
        return {"x": area.left, "y": area.top,
                "width": area.right - area.left, "height": area.bottom - area.top}
    except (AttributeError, OSError, ValueError):
        return None


def run(photos: list[Path], output: Path, size: tuple[int, int], wait_ms: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Capture the baseline on Windows 11, not in Linux CI")
    # Delay desktop imports until after platform and CLI checks. Direct script
    # invocation puts scripts/ rather than the repository root on sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import customtkinter as ctk
    from PIL import Image, ImageGrab
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
    work_area = monitor_work_area(editor)
    geometry = f"{round(size[0] / scale)}x{round(size[1] / scale)}"
    if (work_area and work_area["width"] >= size[0] + 16
            and work_area["height"] >= size[1] + 55):
        # CTk scales dimensions, not +x+y. Give the OS titlebar and taskbar
        # room instead of accepting a partially off-screen default placement.
        geometry += f"+{work_area['x'] + 8}+{work_area['y'] + 8}"
    editor.geometry(geometry)
    editor.update()
    meta: dict = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "requested_window": {"width": size[0], "height": size[1]},
        "dpi_for_window": dpi_for_window(editor),
        "monitor_probe_attempted": True,
        "monitor_work_area": monitor_work_area(editor),
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

    def missing_source():
        # A disposable copy, never the user's source. The numbered entry must
        # remain visible with a repair instruction when its file disappears.
        missing = output / "temporarily-missing.jpg"
        Image.new("RGB", (64, 48), "#456789").save(missing)
        temporary = editor.batch.add_photo(str(missing))
        editor.select(temporary.number)  # cache its rail tile before removal
        missing.unlink()
        editor.show_current()

    def protect():
        editor.batch.remove_photo(editor.current)  # discard only the disposable #0003
        editor.select(1)
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

    def background_before():
        editor.view_mode.set("Before")
        editor.show_current()
        popups["background-before"] = editor.background_window

    def background_rejected():
        editor.view_mode.set("After")
        editor.show_current()
        # Use a generated, undersized still; rejecting it must not alter the
        # numbered photo or claim an upscaled export is lossless.
        small = output / "undersized-replacement.png"
        Image.new("RGB", (8, 8), "#26405c").save(small)
        before = dict(editor.selected_photo().background)
        try:
            editor.set_background("image", source=str(small))
        except ValueError as exc:
            meta["background_rejection"] = str(exc)
            editor.status.configure(text=f"Replacement rejected: {exc}")
        else:
            raise AssertionError("Undersized background was accepted")
        finally:
            small.unlink(missing_ok=True)
        assert editor.selected_photo().background == before
        popups["background-rejected"] = editor.background_window

    def background_ready():
        editor.set_background("color", color="#26405c")
        popups["background-ready"] = editor.background_window

    def export():
        nonlocal dialog
        editor.close_background_tools()
        dialog = ExportOptions(editor)
        popups["export-overlay"] = dialog

    states.extend([("empty-editor", lambda: None), ("populated-editor", populate),
                   ("missing-source", missing_source), ("protected-batch", protect), ("crop-tools", crop),
                   ("background-tools", background), ("background-before", background_before),
                   ("background-rejected", background_rejected),
                   ("background-ready", background_ready), ("export-overlay", export)])

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
            deadline = time.monotonic() + max(10, wait_ms / 1000 + 8)
            editor.after(wait_ms, lambda: screenshot(index, name, deadline))
        except Exception:
            traceback.print_exc()
            meta["error"] = f"Failed to prepare {name}"
            save_metadata()
            root.destroy()
            raise

    def screenshot(index: int, name: str, deadline: float):
        try:
            # Screenshot only a completed current preview. An arbitrary timer
            # could otherwise capture a stale photo or "Rendering preview…"
            # under a slower driver/NEF decoder and still report success.
            if name == "missing-source":
                ready = "Source missing" in editor.status.cget("text")
            else:
                ready = (editor.current is None or
                         editor._displayed_generation == editor._preview_generation)
            if not ready:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Timed out waiting for {name} preview/error state")
                editor.after(100, lambda: screenshot(index, name, deadline))
                return
            rect = bounds(editor)  # Tk client-area coordinates; titlebar/taskbar excluded
            bbox = (rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            image.save(output / f"{name}.png")
            state = {"editor_client": rect, "image_pixels": list(image.size),
                     "selected_number": editor.current,
                     "protected_numbers": editor.batch.excluded_numbers,
                     "scope": editor.scope.get(),
                     "source_missing": name == "missing-source" and
                                       not Path(editor.selected_photo().source).exists()}
            if editor.background_window and editor.background_window.winfo_exists():
                state["mask_status"] = editor.background_window.mask_status.cget("text")
                state["background_mode"] = editor.selected_photo().background.get("mode", "none")
            for key in ("header", "toolbar", "sidebar", "workspace", "panel", "canvas"):
                widget = getattr(editor, key, None)
                if widget:
                    state[key] = bounds(widget)
            state["header_actions"] = [bounds(widget) for widget in editor.header.winfo_children()
                                       if isinstance(widget, (ctk.CTkButton, ctk.CTkSegmentedButton))]
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
