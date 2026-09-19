"""
Toast Notifications - Local UX, no popups
Glassmorphism + Neon, auto-dismiss, stackable
"""

import customtkinter as ctk
from typing import Optional
import threading
import time

COLORS = {
    "bg": "#1a1a1a",
    "border": "#2a2a2a",
    "neon": "#4ade80",
    "red": "#f87171",
    "yellow": "#facc15",
    "blue": "#60a5fa",
}

class ToastManager:
    def __init__(self, master):
        self.master = master
        self.toasts = []
        self.container = None
        self._ensure_container()

    def _ensure_container(self):
        if self.container and self.container.winfo_exists():
            return
        # Top-right container
        self.container = ctk.CTkFrame(self.master, fg_color="transparent")
        self.container.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=80)
        self.container.lift()

    def show(self, message: str, type: str = "info", duration: int = 3000):
        """
        Show toast
        type: info, success, warning, error
        duration: ms
        """
        self._ensure_container()

        colors = {
            "info": COLORS["bg"],
            "success": "#1a2e1a",
            "warning": "#2e2a1a",
            "error": "#2e1a1a",
        }
        border_colors = {
            "info": COLORS["border"],
            "success": COLORS["neon"],
            "warning": COLORS["yellow"],
            "error": COLORS["red"],
        }
        icons = {
            "info": "💬",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }

        toast = ctk.CTkFrame(self.container, fg_color=colors.get(type, COLORS["bg"]), 
                             border_width=1, border_color=border_colors.get(type, COLORS["border"]),
                             corner_radius=12, width=320)
        toast.pack(pady=5, fill="x", padx=5)

        # Content
        content = ctk.CTkFrame(toast, fg_color="transparent")
        content.pack(fill="x", padx=12, pady=10)

        icon = ctk.CTkLabel(content, text=icons.get(type, "💬"), font=ctk.CTkFont(size=14))
        icon.pack(side="left", padx=(0,8))

        msg = ctk.CTkLabel(content, text=message, font=ctk.CTkFont(size=11), wraplength=250, justify="left", anchor="w")
        msg.pack(side="left", fill="x", expand=True)

        close = ctk.CTkButton(content, text="✕", width=20, height=20, fg_color="transparent", hover_color="#333", command=lambda: self._remove(toast))
        close.pack(side="right", padx=5)

        self.toasts.append(toast)

        # Auto-dismiss
        def auto_remove():
            time.sleep(duration/1000)
            try:
                self.master.after(0, lambda: self._remove(toast))
            except:
                pass

        threading.Thread(target=auto_remove, daemon=True).start()

        return toast

    def _remove(self, toast):
        try:
            if toast in self.toasts:
                self.toasts.remove(toast)
            if toast.winfo_exists():
                toast.destroy()
        except:
            pass

    def success(self, msg, duration=3000):
        return self.show(msg, "success", duration)

    def error(self, msg, duration=4000):
        return self.show(msg, "error", duration)

    def warning(self, msg, duration=3500):
        return self.show(msg, "warning", duration)

    def info(self, msg, duration=3000):
        return self.show(msg, "info", duration)

# Global helper for easy use
_toast_manager = None

def init_toast_manager(master):
    global _toast_manager
    _toast_manager = ToastManager(master)
    return _toast_manager

def get_toast_manager():
    return _toast_manager

def toast_success(msg, duration=3000):
    if _toast_manager:
        return _toast_manager.success(msg, duration)

def toast_error(msg, duration=4000):
    if _toast_manager:
        return _toast_manager.error(msg, duration)

def toast_warning(msg, duration=3500):
    if _toast_manager:
        return _toast_manager.warning(msg, duration)

def toast_info(msg, duration=3000):
    if _toast_manager:
        return _toast_manager.info(msg, duration)
