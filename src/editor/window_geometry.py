"""Physical Windows work-area placement for CTk popups.

CTk scales width/height but leaves +x+y as physical screen coordinates.
Keep the two coordinate systems separate; an off-screen popup can still
produce a valid-looking ImageGrab of pixels outside the usable display.
"""
from __future__ import annotations

import sys


def monitor_work_area(widget) -> dict[str, int] | None:
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
        monitor = user32.MonitorFromWindow(widget.winfo_id(), 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            area = info.rcWork
            return {"x": area.left, "y": area.top,
                    "width": area.right - area.left, "height": area.bottom - area.top}
    except (AttributeError, OSError, ValueError):
        pass
    return None


def popup_position(client: dict[str, int], size: tuple[int, int],
                   work_area: dict[str, int] | None) -> tuple[int, int]:
    """Center a physical client, then keep its client and titlebar visible."""
    width, height = size
    x = client["x"] + (client["width"] - width) // 2
    y = client["y"] + (client["height"] - height) // 2
    if work_area:
        left, top = work_area["x"] + 8, work_area["y"] + 35
        right = work_area["x"] + work_area["width"] - width - 8
        bottom = work_area["y"] + work_area["height"] - height - 8
        # If it genuinely cannot fit, don't invent an on-screen result: the
        # capture audit will report the unsupported monitor/popup combination.
        x = max(left, min(x, right))
        y = max(top, min(y, bottom))
    return x, y


def place_popup(popup, editor, width: int, height: int) -> None:
    scale = popup._get_window_scaling()
    client = {"x": editor.winfo_rootx(), "y": editor.winfo_rooty(),
              "width": editor.winfo_width(), "height": editor.winfo_height()}
    x, y = popup_position(client, (round(width * scale), round(height * scale)),
                          monitor_work_area(editor))
    popup.geometry(f"{width}x{height}+{x}+{y}")
