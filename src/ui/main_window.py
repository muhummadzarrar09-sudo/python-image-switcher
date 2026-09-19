"""
Main Window V3 - Pro Dark Studio Edition
Linear / Figma / Raycast inspired - Sidebar nav, glassmorphism, product-grade
"""

import os
import sys
import threading
import tempfile
from pathlib import Path
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

from src.converter.formats import get_format_by_id, get_format_by_ext, FORMATS
from src.converter.validator import validate_conversion
from src.converter.engine import ConversionEngine
from src.converter.batch_engine import BatchEngine
from src.converter.presets import PRESETS, get_preset_by_id, categories as preset_categories, get_presets_by_category
from src.converter.bg_remover import remove_background, is_rembg_available
from src.converter.upscaler import upscale_image, is_realesrgan_available
from src.ui.searchable_combobox import SearchableFormatDropdown
from src.ui.image_viewer import DualViewer
from src.utils.update_checker import check_for_updates_async, get_local_version
from src.utils.config import load_config, save_config, add_recent_file, add_recent_folder, update_setting
from src.ui.toast import init_toast_manager, toast_success, toast_error, toast_warning, toast_info

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# V3.1 Pro Dark Studio + Light Mode + Custom Titlebar + Animations
COLORS_DARK = {
    "bg": "#0a0a0b",
    "sidebar": "#111113",
    "sidebar_hover": "#1a1a1e",
    "card": "#161618",
    "card2": "#1e1e22",
    "card_hover": "#252529",
    "border": "#232326",
    "border_light": "#2a2a30",
    "neon": "#4ade80",
    "neon_hover": "#22c55e",
    "neon_dim": "#4ade8020",
    "neon_subtle": "#4ade8010",
    "text": "#e4e4e7",
    "text_dim": "#71717a",
    "text_faint": "#3f3f46",
    "red": "#f87171",
    "yellow": "#facc15",
    "blue": "#60a5fa",
}

COLORS_LIGHT = {
    "bg": "#f4f4f5",
    "sidebar": "#ffffff",
    "sidebar_hover": "#f4f4f5",
    "card": "#ffffff",
    "card2": "#f4f4f5",
    "card_hover": "#e4e4e7",
    "border": "#e4e4e7",
    "border_light": "#d4d4d8",
    "neon": "#16a34a",
    "neon_hover": "#15803d",
    "neon_dim": "#16a34a20",
    "neon_subtle": "#16a34a10",
    "text": "#18181b",
    "text_dim": "#71717a",
    "text_faint": "#a1a1aa",
    "red": "#ef4444",
    "yellow": "#eab308",
    "blue": "#3b82f6",
}

# Default to dark, will be updated by theme
COLORS = COLORS_DARK.copy()

class ImageSwitcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        # V3.1 Theme handling - light/dark
        self.current_theme = self.config.get("ui", {}).get("theme", "dark")
        global COLORS
        if self.current_theme == "light":
            COLORS = COLORS_LIGHT.copy()
            ctk.set_appearance_mode("light")
        else:
            COLORS = COLORS_DARK.copy()
            ctk.set_appearance_mode("dark")

        # V3.1 Custom Titlebar handling
        self.custom_titlebar_enabled = self.config.get("ui", {}).get("custom_titlebar", False)
        self.titlebar_drag_start = None

        self.title(f"Image Switcher V3.2 • Pro Dark Studio • Resizable + Acrylic + Ripple • Offline")
        w = self.config.get("window", {}).get("width", 1440)
        h = self.config.get("window", {}).get("height", 900)
        self.geometry(f"{w}x{h}")
        self.minsize(1280, 800)
        self.configure(fg_color=COLORS["bg"])

        self.engine = ConversionEngine()
        self.batch_engine = BatchEngine(max_workers=4)
        self.current_file: str | None = None
        self.current_info: dict | None = None
        self.converted_file: str | None = None
        self.last_target_id: str | None = None
        self.batch_items = []
        self.studio_photos = []
        self.studio_result = None

        self.is_fullscreen = False
        self.prev_geometry = None
        self.is_maximized_taskbar = False
        self.current_page = "Single"
        self.animating = False

        # V3 Grid: custom titlebar row 0 (if enabled), header row 1, main row 2 (sidebar col0 + content col1), status row 3
        # We'll adjust dynamically
        self.sidebar_width = self.config.get("ui", {}).get("sidebar_width", 260)
        self.grid_columnconfigure(0, weight=0, minsize=self.sidebar_width)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)  # custom titlebar
        self.grid_rowconfigure(1, weight=0)  # header
        self.grid_rowconfigure(2, weight=1)  # main
        self.grid_rowconfigure(3, weight=0)  # status

        if self.custom_titlebar_enabled:
            self._build_custom_titlebar()
            # Hide OS titlebar
            try:
                self.overrideredirect(True)
            except:
                pass

        self._build_header()
        self._build_sidebar()
        self._build_content()
        self._build_status_bar()

        self.toast_manager = init_toast_manager(self)
        self._restore_config()
        self._bind_shortcuts()
        self._init_drag_drop()

        # V3.1 Animations - add hover animations to buttons after build
        self.after(500, self._setup_animations)

        # V3.2 Acrylic blur + resizable sidebar + ripple
        self.acrylic_enabled = self.config.get("ui", {}).get("acrylic_blur", True)
        if self.acrylic_enabled:
            self.after(300, self._enable_acrylic_blur)

        if self.config.get("ui", {}).get("auto_check_updates", True):
            self.after(1500, self._check_updates)

        self.single_viewer.clear()

        if self.config.get("first_run"):
            self.after(1000, self._show_onboarding)

        self.after(200, self._ensure_taskbar_bounds)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(100, lambda: self._switch_page("Single"))

    def _build_custom_titlebar(self):
        # V3.1 Custom Titlebar - traffic lights, draggable, window controls
        titlebar = ctk.CTkFrame(self, height=32, fg_color=COLORS["sidebar"], corner_radius=0, border_width=0)
        titlebar.grid(row=0, column=0, columnspan=2, sticky="ew")
        titlebar.grid_propagate(False)
        titlebar.grid_columnconfigure(1, weight=1)
        self.custom_titlebar = titlebar

        # Traffic lights
        dots = ctk.CTkFrame(titlebar, fg_color="transparent")
        dots.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        close_btn = ctk.CTkButton(dots, text="●", width=12, height=12, corner_radius=6, fg_color="#ff5f56", hover_color="#ff5f56", text_color="#ff5f56", font=ctk.CTkFont(size=8), command=self._on_close)
        close_btn.pack(side="left", padx=2)
        min_btn = ctk.CTkButton(dots, text="●", width=12, height=12, corner_radius=6, fg_color="#ffbd2e", hover_color="#ffbd2e", text_color="#ffbd2e", font=ctk.CTkFont(size=8), command=lambda: self.iconify())
        min_btn.pack(side="left", padx=2)
        max_btn = ctk.CTkButton(dots, text="●", width=12, height=12, corner_radius=6, fg_color="#27c93f", hover_color="#27c93f", text_color="#27c93f", font=ctk.CTkFont(size=8), command=self._toggle_maximize_taskbar)
        max_btn.pack(side="left", padx=2)

        title_lbl = ctk.CTkLabel(titlebar, text="Image Switcher V3.2 • Pro Dark Studio • Resizable + Acrylic + Ripple + Light/Dark", font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"])
        title_lbl.grid(row=0, column=1, padx=20, sticky="w")

        # Right - theme + window controls
        right_tb = ctk.CTkFrame(titlebar, fg_color="transparent")
        right_tb.grid(row=0, column=2, padx=12, sticky="e")

        self.titlebar_theme_btn = ctk.CTkButton(right_tb, text="☀️" if self.current_theme=="dark" else "🌙", width=24, height=24, corner_radius=6, fg_color="transparent", hover_color=COLORS["card_hover"], font=ctk.CTkFont(size=12), command=self._toggle_theme)
        self.titlebar_theme_btn.pack(side="left", padx=2)

        # Draggable
        def start_drag(e):
            self.titlebar_drag_start = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())
        def on_drag(e):
            if self.titlebar_drag_start and not self.is_fullscreen and not self.is_maximized_taskbar:
                x = e.x_root - self.titlebar_drag_start[0]
                y = e.y_root - self.titlebar_drag_start[1]
                self.geometry(f"+{x}+{y}")
        titlebar.bind("<ButtonPress-1>", start_drag)
        titlebar.bind("<B1-Motion>", on_drag)
        title_lbl.bind("<ButtonPress-1>", start_drag)
        title_lbl.bind("<B1-Motion>", on_drag)

    def _enable_acrylic_blur(self):
        # V3.2 Acrylic blur - Windows 11 Mica/Acrylic via DWM
        try:
            if os.name != "nt":
                return False
            self.update_idletasks()
            hwnd = self.winfo_id()
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or hwnd
            except:
                hwnd = self.winfo_id()
            try:
                import ctypes
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                DWMWA_SYSTEMBACKDROP_TYPE = 38
                DWMSBT_MAINWINDOW = 2
                DWMSBT_TRANSIENTWINDOW = 3
                value = ctypes.c_int(1 if self.current_theme=="dark" else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
                try:
                    backdrop = ctypes.c_int(DWMSBT_MAINWINDOW if self.config.get("ui", {}).get("acrylic_type","mica")=="mica" else DWMSBT_TRANSIENTWINDOW)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
                    print(f"Acrylic/Mica enabled: {backdrop.value}")
                    return True
                except Exception as e:
                    print(f"Mica failed, trying blur: {e}")
                class ACCENTPOLICY(ctypes.Structure):
                    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int), ("GradientColor", ctypes.c_int), ("AnimationId", ctypes.c_int)]
                class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENTPOLICY)), ("SizeOfData", ctypes.c_size_t)]
                accent = ACCENTPOLICY()
                accent.AccentState = 4
                accent.AccentFlags = 0
                accent.GradientColor = 0x99000000 if self.current_theme=="dark" else 0x99FFFFFF
                accent.AnimationId = 0
                data = WINDOWCOMPOSITIONATTRIBDATA()
                data.Attribute = 19
                data.Data = ctypes.pointer(accent)
                data.SizeOfData = ctypes.sizeof(accent)
                ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
                return True
            except Exception as e:
                print(f"Acrylic blur failed: {e}")
                return False
        except Exception as e:
            print(f"Acrylic overall failed: {e}")
            return False

    def _build_header(self):
        # V3.1 Header with theme toggle + custom titlebar awareness
        header_row = 1 if self.custom_titlebar_enabled else 0
        header = ctk.CTkFrame(self, height=56, fg_color=COLORS["card"], corner_radius=0, border_width=0)
        header.grid(row=header_row, column=0, columnspan=2, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        self.header_frame = header

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, padx=20, pady=8, sticky="w")

        try:
            icon_path = Path(__file__).parent.parent.parent / "assets" / "icon-v2-3d.png"
            if not icon_path.exists():
                icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.png"
            if icon_path.exists():
                pil_icon = Image.open(icon_path).resize((32,32), Image.LANCZOS)
                self._logo_img = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(32,32))
                logo_lbl = ctk.CTkLabel(left, image=self._logo_img, text="")
                logo_lbl.pack(side="left", padx=(0,12))
        except Exception as e:
            print(f"Icon load failed: {e}")

        title_col = ctk.CTkFrame(left, fg_color="transparent")
        title_col.pack(side="left")

        title = ctk.CTkLabel(title_col, text="IMAGE SWITCHER", font=ctk.CTkFont(size=18, weight="bold", family="Segoe UI"), text_color=COLORS["text"])
        title.pack(anchor="w")
        subtitle = ctk.CTkLabel(title_col, text="Pro Dark Studio • V3.2 • Resizable • Acrylic • Ripple • Offline", font=ctk.CTkFont(size=10, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"])
        subtitle.pack(anchor="w")

        center = ctk.CTkFrame(header, fg_color="transparent")
        center.grid(row=0, column=1, padx=20, sticky="ew")

        ver = get_local_version()
        self.version_label = ctk.CTkLabel(center, text=f"v{ver}", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"])
        self.version_label.pack(side="left", padx=10)

        self.update_banner = ctk.CTkLabel(center, text="", font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), text_color=COLORS["neon"], cursor="hand2")
        self.update_banner.pack(side="left", padx=10)
        self.update_banner.bind("<Button-1>", lambda e: self._open_github())

        cmd_hint = ctk.CTkFrame(center, fg_color=COLORS["card2"], corner_radius=8, border_width=1, border_color=COLORS["border"])
        cmd_hint.pack(side="left", padx=20)
        ctk.CTkLabel(cmd_hint, text="⌘K", font=ctk.CTkFont(size=10, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(cmd_hint, text="Command", font=ctk.CTkFont(size=10, family="Segoe UI"), text_color=COLORS["text_dim"]).pack(side="left", padx=(0,8), pady=4)
        cmd_hint.bind("<Button-1>", lambda e: self._open_command_palette())
        for child in cmd_hint.winfo_children():
            child.bind("<Button-1>", lambda e: self._open_command_palette())

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=2, padx=16, sticky="e")

        self.fullscreen_btn = ctk.CTkButton(right, text="⛶ F11", width=64, height=32, corner_radius=8, fg_color=COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), command=self._toggle_fullscreen)
        self.fullscreen_btn.pack(side="left", padx=3)

        self.maximize_btn = ctk.CTkButton(right, text="🗖 Bounds", width=80, height=32, corner_radius=8, fg_color=COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), command=self._toggle_maximize_taskbar)
        self.maximize_btn.pack(side="left", padx=3)

        self.pinger_btn = ctk.CTkButton(right, text="🔔 Updates", width=90, height=32, corner_radius=8, fg_color=COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), command=self._check_updates_manual)
        self.pinger_btn.pack(side="left", padx=4)

        # V3.1 Theme toggle + Custom titlebar toggle + V3.2 Acrylic
        self.theme_btn = ctk.CTkButton(right, text="🌙" if self.current_theme=="dark" else "☀️", width=36, height=32, corner_radius=8, fg_color=COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=14), command=self._toggle_theme)
        self.theme_btn.pack(side="left", padx=3)

        self.titlebar_btn = ctk.CTkButton(right, text="🪟", width=36, height=32, corner_radius=8, fg_color=COLORS["card2"] if not self.custom_titlebar_enabled else COLORS["neon"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=14), command=self._toggle_custom_titlebar)
        self.titlebar_btn.pack(side="left", padx=3)

        self.acrylic_btn = ctk.CTkButton(right, text="✨", width=36, height=32, corner_radius=8, fg_color=COLORS["neon"] if getattr(self, 'acrylic_enabled', True) else COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=14), command=self._toggle_acrylic_blur)
        self.acrylic_btn.pack(side="left", padx=3)

        self.settings_btn = ctk.CTkButton(right, text="⚙️", width=36, height=32, corner_radius=8, fg_color=COLORS["card2"], hover_color=COLORS["sidebar_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=14), command=self.open_settings)
        self.settings_btn.pack(side="left", padx=4)

    def _build_sidebar(self):
        sidebar_row = 2 if self.custom_titlebar_enabled else 1
        # V3.2 Resizable sidebar
        self.sidebar_width = self.config.get("ui", {}).get("sidebar_width", 260)
        self.sidebar = ctk.CTkFrame(self, width=self.sidebar_width, fg_color=COLORS["sidebar"], corner_radius=0, border_width=0)
        self.sidebar.grid(row=sidebar_row, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, minsize=self.sidebar_width)

        # Resize handle - 4px at right edge
        self.sidebar_resize_handle = ctk.CTkFrame(self, width=4, fg_color="transparent", corner_radius=0, cursor="sb_h_double_arrow")
        self.sidebar_resize_handle.grid(row=sidebar_row, column=0, sticky="ns", padx=0)
        self.sidebar_resize_handle.place(relx=0, rely=0, relheight=1.0, x=self.sidebar_width-4, y=0, anchor="nw")
        # Use place for handle to be at edge
        self.sidebar_resize_handle.lift()

        def on_enter(e):
            self.sidebar_resize_handle.configure(fg_color=COLORS["border"])
        def on_leave(e):
            self.sidebar_resize_handle.configure(fg_color="transparent")
        def start_resize(e):
            self._resize_start_x = e.x_root
            self._resize_start_width = self.sidebar_width
        def do_resize(e):
            dx = e.x_root - self._resize_start_x
            new_w = self._resize_start_width + dx
            new_w = max(200, min(400, new_w))
            self.sidebar_width = new_w
            self.sidebar.configure(width=new_w)
            self.grid_columnconfigure(0, minsize=new_w)
            try:
                self.sidebar_resize_handle.place(x=new_w-4)
            except:
                pass
        def end_resize(e):
            try:
                self.config["ui"] = self.config.get("ui", {})
                self.config["ui"]["sidebar_width"] = self.sidebar_width
                save_config(self.config)
                toast_info(f"Sidebar: {self.sidebar_width}px")
            except:
                pass

        self.sidebar_resize_handle.bind("<Enter>", on_enter)
        self.sidebar_resize_handle.bind("<Leave>", on_leave)
        self.sidebar_resize_handle.bind("<ButtonPress-1>", start_resize)
        self.sidebar_resize_handle.bind("<B1-Motion>", do_resize)
        self.sidebar_resize_handle.bind("<ButtonRelease-1>", end_resize)

        search_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        search_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        search_frame.grid_columnconfigure(0, weight=1)

        search_btn = ctk.CTkButton(search_frame, text="🔍  Search or jump to...  ⌘K", height=36, corner_radius=10, fg_color=COLORS["card"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), anchor="w", command=self._open_command_palette)
        search_btn.grid(row=0, column=0, sticky="ew")

        nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        nav_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(nav_frame, text="CONVERT", font=ctk.CTkFont(size=10, weight="bold", family="Segoe UI"), text_color=COLORS["text_faint"]).grid(row=0, column=0, sticky="w", padx=8, pady=(8,4))

        self.nav_buttons = {}
        nav_items = [
            ("Single", "🖼️  Single", "Convert one image"),
            ("Batch", "🔥  Batch", "Convert folders"),
            ("Presets", "✨  Presets", "Instagram, Social, Web"),
            ("AI", "🤖  AI Tools", "BG Remover + Upscaler"),
            ("3D Studio", "📦  3D Studio", "Product 3D Maker"),
        ]

        for idx, (key, label, desc) in enumerate(nav_items, start=1):
            btn = ctk.CTkButton(nav_frame, text=label, height=40, corner_radius=10, fg_color="transparent", hover_color=COLORS["sidebar_hover"], border_width=0, font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), anchor="w", text_color=COLORS["text_dim"], command=lambda k=key: self._switch_page(k))
            btn.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
            self.nav_buttons[key] = btn

        sep = ctk.CTkFrame(nav_frame, height=1, fg_color=COLORS["border"], corner_radius=0)
        sep.grid(row=len(nav_items)+1, column=0, sticky="ew", padx=8, pady=12)

        ctk.CTkLabel(nav_frame, text="SYSTEM", font=ctk.CTkFont(size=10, weight="bold", family="Segoe UI"), text_color=COLORS["text_faint"]).grid(row=len(nav_items)+2, column=0, sticky="w", padx=8, pady=(0,4))

        self.nav_buttons["Tools"] = ctk.CTkButton(nav_frame, text="🔧  Tools", height=40, corner_radius=10, fg_color="transparent", hover_color=COLORS["sidebar_hover"], border_width=0, font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), anchor="w", text_color=COLORS["text_dim"], command=lambda: self._switch_page("Tools"))
        self.nav_buttons["Tools"].grid(row=len(nav_items)+3, column=0, sticky="ew", padx=4, pady=2)

        bottom_frame = ctk.CTkFrame(self.sidebar, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        bottom_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
        bottom_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bottom_frame, text="Offline • 100% Local", font=ctk.CTkFont(size=11, weight="bold", family="Segoe UI"), text_color=COLORS["neon"]).grid(row=0, column=0, sticky="w", padx=12, pady=(10,2))
        ctk.CTkLabel(bottom_frame, text="No tracking • No cloud", font=ctk.CTkFont(size=10, family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=1, column=0, sticky="w", padx=12, pady=(0,10))

        ctk.CTkLabel(self.sidebar, text="F11 Fullscreen • Shift+F11 Bounds • Ctrl+K Cmd • Ctrl+T Theme • Ctrl+Shift+A Acrylic • Drag resize", font=ctk.CTkFont(size=9, family="Segoe UI"), text_color=COLORS["text_faint"], wraplength=240, justify="left").grid(row=4, column=0, sticky="ew", padx=12, pady=8)

    def _build_content(self):
        content_row = 2 if self.custom_titlebar_enabled else 1
        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0, border_width=0)
        self.content.grid(row=content_row, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {}
        for page_name in ["Single", "Batch", "Presets", "AI", "3D Studio", "Tools"]:
            frame = ctk.CTkFrame(self.content, fg_color=COLORS["bg"], corner_radius=0)
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            self.pages[page_name] = frame

        self._build_single_page(self.pages["Single"])
        self._build_batch_page(self.pages["Batch"])
        self._build_presets_page(self.pages["Presets"])
        self._build_ai_page(self.pages["AI"])
        self._build_studio_page(self.pages["3D Studio"])
        self._build_tools_page(self.pages["Tools"])

    def _switch_page(self, page_name):
        # V3.1 with animation
        mapping = {
            "Batch 🔥": "Batch",
            "Presets ✨": "Presets",
            "AI 🤖": "AI",
            "3D Studio 📦": "3D Studio",
        }
        page_name = mapping.get(page_name, page_name)
        old_page = getattr(self, 'current_page', None)
        self.current_page = page_name

        # Animate if different
        if old_page and old_page != page_name:
            self._animate_page_switch(old_page, page_name)

        for key, btn in self.nav_buttons.items():
            if key == page_name:
                btn.configure(fg_color=COLORS["card2"], text_color=COLORS["text"], border_width=1, border_color=COLORS["border"])
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text_dim"], border_width=0)

        for name, frame in self.pages.items():
            if name == page_name:
                frame.tkraise()
                frame.grid()
            else:
                frame.grid_remove()

        self.tabs = type('obj', (object,), {'get': lambda: page_name, 'set': self._switch_page})()
        try:
            self.status_label.configure(text=f"{page_name} • F11 • Shift+F11 Bounds • Ctrl+K Cmd • Ctrl+T Theme • Ctrl+Shift+A Acrylic • {self.current_theme} • {self.sidebar_width}px sidebar • Offline")
        except:
            pass

    def _build_single_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        top_card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        top_card.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        top_card.grid_columnconfigure(1, weight=1)

        file_frame = ctk.CTkFrame(top_card, fg_color="transparent")
        file_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=20)
        file_frame.grid_columnconfigure(1, weight=1)

        self.file_label = ctk.CTkLabel(file_frame, text="No file selected — Drop image or Ctrl+O", font=ctk.CTkFont(size=14, weight="bold", family="Segoe UI"), anchor="w", text_color=COLORS["text"])
        self.file_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4)

        browse_btn = ctk.CTkButton(file_frame, text="Browse", width=120, height=40, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(weight="bold", family="Segoe UI", size=13), border_width=0, command=self.browse_file)
        browse_btn.grid(row=0, column=2, padx=8)

        self.drop_label = ctk.CTkLabel(file_frame, text="Drag & Drop anywhere • PNG JPG SVG WEBP HEIC AVIF • Offline 100% local • F11 fullscreen • Shift+F11 bounds", font=ctk.CTkFont(size=11, family="Segoe UI"), text_color=COLORS["text_dim"])
        self.drop_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=4, pady=(8,0))

        fmt_row = ctk.CTkFrame(top_card, fg_color="transparent")
        fmt_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=24, pady=(0,20))
        fmt_row.grid_columnconfigure((0,2), weight=1)

        self.source_dropdown = SearchableFormatDropdown(fmt_row, label_text="Source Format", width=360, on_select=self.on_source_selected)
        self.source_dropdown.grid(row=0, column=0, padx=8, sticky="ew")

        arrow_frame = ctk.CTkFrame(fmt_row, fg_color="transparent", width=60)
        arrow_frame.grid(row=0, column=1, padx=12)
        ctk.CTkLabel(arrow_frame, text="→", font=ctk.CTkFont(size=20, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).pack()
        ctk.CTkLabel(arrow_frame, text="TO", font=ctk.CTkFont(size=9, weight="bold", family="Segoe UI"), text_color=COLORS["text_faint"]).pack()

        self.target_dropdown = SearchableFormatDropdown(fmt_row, label_text="Target Format", width=360, on_select=self.on_target_selected)
        self.target_dropdown.grid(row=0, column=2, padx=8, sticky="ew")

        opts_card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        opts_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0,16))
        opts_card.grid_columnconfigure((1,3), weight=1)

        ctk.CTkLabel(opts_card, text="Quality", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=20, pady=16, sticky="w")
        self.quality_label = ctk.CTkLabel(opts_card, text="90", font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), text_color=COLORS["text"], width=32)
        self.quality_label.grid(row=0, column=0, padx=80, sticky="w")
        self.quality_slider = ctk.CTkSlider(opts_card, from_=1, to=100, number_of_steps=99, progress_color=COLORS["text"], button_color=COLORS["text"], button_hover_color=COLORS["neon"], command=self.on_quality_change)
        self.quality_slider.set(90)
        self.quality_slider.grid(row=0, column=1, padx=12, sticky="ew")

        ctk.CTkLabel(opts_card, text="Background", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=2, padx=20, sticky="e")
        self.bg_color_var = ctk.StringVar(value="white")
        self.bg_menu = ctk.CTkOptionMenu(opts_card, values=["white","black","transparent","red","green","blue","checker"], variable=self.bg_color_var, width=140, fg_color=COLORS["card2"], button_color=COLORS["card2"], button_hover_color=COLORS["card_hover"], dropdown_fg_color=COLORS["card2"], text_color=COLORS["text"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.bg_menu.grid(row=0, column=3, padx=20)

        resize_frame = ctk.CTkFrame(opts_card, fg_color="transparent")
        resize_frame.grid(row=1, column=0, columnspan=4, sticky="ew", padx=20, pady=(0,16))
        ctk.CTkLabel(resize_frame, text="Resize", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).pack(side="left", padx=4)
        self.width_entry = ctk.CTkEntry(resize_frame, placeholder_text="Width", width=90, fg_color=COLORS["card2"], border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.width_entry.pack(side="left", padx=8)
        ctk.CTkLabel(resize_frame, text="×", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.height_entry = ctk.CTkEntry(resize_frame, placeholder_text="Height", width=90, fg_color=COLORS["card2"], border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.height_entry.pack(side="left", padx=8)
        self.keep_aspect = ctk.CTkCheckBox(resize_frame, text="Keep original", font=ctk.CTkFont(size=12, family="Segoe UI"), fg_color=COLORS["text"], hover_color=COLORS["text_dim"], text_color=COLORS["text_dim"])
        self.keep_aspect.select()
        self.keep_aspect.pack(side="left", padx=16)

        self.single_viewer = DualViewer(parent)
        self.single_viewer.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0,20))

    def _build_batch_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        batch_top = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        batch_top.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        batch_top.grid_columnconfigure(1, weight=1)

        input_row = ctk.CTkFrame(batch_top, fg_color="transparent")
        input_row.grid(row=0, column=0, columnspan=3, sticky="ew", padx=24, pady=12)
        input_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(input_row, text="Input", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=8, sticky="w")
        self.batch_input_var = ctk.StringVar(value="No folder selected")
        self.batch_input_label = ctk.CTkLabel(input_row, textvariable=self.batch_input_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.batch_input_label.grid(row=0, column=1, padx=12, sticky="ew")
        ctk.CTkButton(input_row, text="Browse Folder", width=130, height=36, corner_radius=10, fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.browse_batch_input).grid(row=0, column=2, padx=6)
        ctk.CTkButton(input_row, text="Browse Files", width=120, height=36, corner_radius=10, fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.browse_batch_files).grid(row=0, column=3, padx=6)

        output_row = ctk.CTkFrame(batch_top, fg_color="transparent")
        output_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=24, pady=12)
        output_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(output_row, text="Output", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=8, sticky="w")
        self.batch_output_var = ctk.StringVar(value="Same as input (with _converted suffix)")
        self.batch_output_label = ctk.CTkLabel(output_row, textvariable=self.batch_output_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.batch_output_label.grid(row=0, column=1, padx=12, sticky="ew")
        ctk.CTkButton(output_row, text="Choose Output", width=130, height=36, corner_radius=10, fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.browse_batch_output).grid(row=0, column=2, padx=6)

        batch_opts = ctk.CTkFrame(batch_top, fg_color="transparent")
        batch_opts.grid(row=2, column=0, columnspan=3, sticky="ew", padx=24, pady=12)
        batch_opts.grid_columnconfigure((1,3,5), weight=1)

        ctk.CTkLabel(batch_opts, text="Target", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=8)
        self.batch_target_var = ctk.StringVar(value="webp")
        self.batch_target_menu = ctk.CTkOptionMenu(batch_opts, values=["png","jpg","webp","avif","bmp","tiff","gif","ico"], variable=self.batch_target_var, width=100, fg_color=COLORS["card2"], button_color=COLORS["card2"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.batch_target_menu.grid(row=0, column=1, padx=8, sticky="ew")

        ctk.CTkLabel(batch_opts, text="Quality", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=2, padx=8)
        self.batch_quality_slider = ctk.CTkSlider(batch_opts, from_=1, to=100, number_of_steps=99, width=120, progress_color=COLORS["text"], button_color=COLORS["text"], command=lambda v: self.batch_quality_label.configure(text=str(int(v))))
        self.batch_quality_slider.set(90)
        self.batch_quality_slider.grid(row=0, column=3, padx=8, sticky="ew")
        self.batch_quality_label = ctk.CTkLabel(batch_opts, text="90", width=32, text_color=COLORS["text"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"))
        self.batch_quality_label.grid(row=0, column=4, padx=8)

        self.batch_recursive = ctk.CTkCheckBox(batch_opts, text="Recursive", fg_color=COLORS["text"], font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"])
        self.batch_recursive.select()
        self.batch_recursive.grid(row=0, column=5, padx=12)

        self.batch_keep_struct = ctk.CTkCheckBox(batch_opts, text="Keep structure", fg_color=COLORS["text"], font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"])
        self.batch_keep_struct.select()
        self.batch_keep_struct.grid(row=0, column=6, padx=12)

        self.batch_overwrite = ctk.CTkCheckBox(batch_opts, text="Overwrite", fg_color=COLORS["text"], font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"])
        self.batch_overwrite.grid(row=0, column=7, padx=12)

        batch_mid = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        batch_mid.grid(row=1, column=0, sticky="ew", padx=20, pady=(0,16))
        batch_mid.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(batch_mid, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=20, pady=12)

        self.batch_scan_btn = ctk.CTkButton(btn_row, text="Scan Images", width=120, height=36, corner_radius=10, fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.scan_batch)
        self.batch_scan_btn.pack(side="left", padx=6)

        self.batch_convert_btn = ctk.CTkButton(btn_row, text="Convert All", width=140, height=36, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.start_batch_convert)
        self.batch_convert_btn.pack(side="left", padx=12)

        self.batch_stop_btn = ctk.CTkButton(btn_row, text="Stop", width=80, height=36, corner_radius=10, fg_color=COLORS["card2"], hover_color=COLORS["red"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self.stop_batch, state="disabled")
        self.batch_stop_btn.pack(side="left", padx=6)

        self.batch_progress = ctk.CTkProgressBar(btn_row, width=200, progress_color=COLORS["text"])
        self.batch_progress.set(0)
        self.batch_progress.pack(side="left", padx=20, fill="x", expand=True)

        self.batch_status_label = ctk.CTkLabel(btn_row, text="Ready", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"))
        self.batch_status_label.pack(side="left", padx=12)

        self.batch_list_frame = ctk.CTkScrollableFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self.batch_list_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0,20))

        self.batch_list_label = ctk.CTkLabel(self.batch_list_frame, text="No images scanned yet — choose input folder and click Scan", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.batch_list_label.pack(pady=40)

    def _build_presets_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        presets_header = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        presets_header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        ctk.CTkLabel(presets_header, text="Resize Presets", font=ctk.CTkFont(size=18, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(20,4))
        ctk.CTkLabel(presets_header, text="One-click presets for Instagram, Social, Web, Print, Discord — Applies to Single + Batch", font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"]).pack(anchor="w", padx=24, pady=(0,16))

        cat_frame = ctk.CTkFrame(presets_header, fg_color="transparent")
        cat_frame.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(cat_frame, text="Category", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).pack(side="left", padx=8)
        self.preset_cat_var = ctk.StringVar(value="all")
        cats = ["all"] + preset_categories()
        self.preset_cat_menu = ctk.CTkOptionMenu(cat_frame, values=cats, variable=self.preset_cat_var, width=160, fg_color=COLORS["card2"], button_color=COLORS["card2"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._filter_presets)
        self.preset_cat_menu.pack(side="left", padx=12)

        self.presets_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self.presets_scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,20))

        self._build_presets_list(PRESETS)

    def _build_ai_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        ai_header = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        ai_header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        ctk.CTkLabel(ai_header, text="AI Tools", font=ctk.CTkFont(size=18, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(20,4))
        ctk.CTkLabel(ai_header, text="Background Remover + Upscaler + Enhancer — Local fallback if models not installed", font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"], wraplength=700, justify="left").pack(anchor="w", padx=24, pady=(0,16))

        bg_frame = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        bg_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=12)
        bg_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bg_frame, text="Background Remover", font=ctk.CTkFont(size=14, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).grid(row=0, column=0, columnspan=3, sticky="w", padx=24, pady=(16,4))
        status_bg = "rembg installed" if is_rembg_available() else "rembg not installed — using fallback"
        ctk.CTkLabel(bg_frame, text=status_bg, font=ctk.CTkFont(size=11, family="Segoe UI"), text_color=COLORS["neon"] if is_rembg_available() else COLORS["yellow"]).grid(row=1, column=0, columnspan=3, sticky="w", padx=24)

        ctk.CTkLabel(bg_frame, text="Input", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=2, column=0, padx=24, pady=12, sticky="w")
        self.ai_bg_input_var = ctk.StringVar(value="No file")
        ctk.CTkLabel(bg_frame, textvariable=self.ai_bg_input_var, text_color=COLORS["text_dim"], width=400, anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=2, column=1, padx=12, sticky="ew")
        ctk.CTkButton(bg_frame, text="Browse", width=100, height=32, corner_radius=8, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._browse_ai_bg_input).grid(row=2, column=2, padx=12)

        ctk.CTkLabel(bg_frame, text="Output", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=3, column=0, padx=24, pady=12, sticky="w")
        self.ai_bg_output_var = ctk.StringVar(value="Will save as *_no_bg.png")
        ctk.CTkLabel(bg_frame, textvariable=self.ai_bg_output_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=3, column=1, padx=12, sticky="ew")

        btn_row_bg = ctk.CTkFrame(bg_frame, fg_color="transparent")
        btn_row_bg.grid(row=4, column=0, columnspan=3, sticky="ew", padx=24, pady=16)
        ctk.CTkButton(btn_row_bg, text="Remove Background", height=36, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self._run_bg_remover).pack(side="left", padx=6)
        self.ai_bg_status = ctk.CTkLabel(btn_row_bg, text="Ready", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"))
        self.ai_bg_status.pack(side="left", padx=16)

        up_frame = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        up_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=12)
        up_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(up_frame, text="AI Upscaler", font=ctk.CTkFont(size=14, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).grid(row=0, column=0, columnspan=3, sticky="w", padx=24, pady=(16,4))
        status_up = "Real-ESRGAN available" if is_realesrgan_available() else "Real-ESRGAN not installed — using LANCZOS+sharpen"
        ctk.CTkLabel(up_frame, text=status_up, font=ctk.CTkFont(size=11, family="Segoe UI"), text_color=COLORS["neon"] if is_realesrgan_available() else COLORS["yellow"]).grid(row=1, column=0, columnspan=3, sticky="w", padx=24)

        ctk.CTkLabel(up_frame, text="Input", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=2, column=0, padx=24, pady=12, sticky="w")
        self.ai_up_input_var = ctk.StringVar(value="No file")
        ctk.CTkLabel(up_frame, textvariable=self.ai_up_input_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=2, column=1, padx=12, sticky="ew")
        ctk.CTkButton(up_frame, text="Browse", width=100, height=32, corner_radius=8, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._browse_ai_up_input).grid(row=2, column=2, padx=12)

        ctk.CTkLabel(up_frame, text="Scale", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=3, column=0, padx=24, pady=12, sticky="w")
        self.ai_up_scale_var = ctk.StringVar(value="2x")
        ctk.CTkOptionMenu(up_frame, values=["2x","4x"], variable=self.ai_up_scale_var, width=120, fg_color=COLORS["card2"], button_color=COLORS["card2"], font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=3, column=1, sticky="w", padx=12)

        ctk.CTkLabel(up_frame, text="Output", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=4, column=0, padx=24, pady=12, sticky="w")
        self.ai_up_output_var = ctk.StringVar(value="Will save as *_upscaled.png")
        ctk.CTkLabel(up_frame, textvariable=self.ai_up_output_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=4, column=1, padx=12, sticky="ew")

        btn_row_up = ctk.CTkFrame(up_frame, fg_color="transparent")
        btn_row_up.grid(row=5, column=0, columnspan=3, sticky="ew", padx=24, pady=16)
        ctk.CTkButton(btn_row_up, text="Upscale", height=36, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self._run_upscaler).pack(side="left", padx=6)
        ctk.CTkButton(btn_row_up, text="Enhance Only", height=36, corner_radius=10, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._run_enhancer).pack(side="left", padx=8)
        self.ai_up_status = ctk.CTkLabel(btn_row_up, text="Ready", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"))
        self.ai_up_status.pack(side="left", padx=16)

    def _build_studio_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        studio_header = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        studio_header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        ctk.CTkLabel(studio_header, text="3D Product Studio", font=ctk.CTkFont(size=18, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(20,4))
        ctk.CTkLabel(studio_header, text="Personalised 3D Maker — AI auto-detects photos (1=depth, 4-8=box, 12+=turntable 360) — 100% Local", font=ctk.CTkFont(size=12, family="Segoe UI"), text_color=COLORS["text_dim"], wraplength=800, justify="left").pack(anchor="w", padx=24, pady=(0,16))

        studio_input = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        studio_input.grid(row=1, column=0, sticky="ew", padx=20, pady=12)
        studio_input.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(studio_input, text="Product Photos", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=24, pady=12, sticky="w")
        self.studio_input_var = ctk.StringVar(value="No photos selected — drop folder or select multiple")
        ctk.CTkLabel(studio_input, textvariable=self.studio_input_var, text_color=COLORS["text_dim"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=0, column=1, padx=12, sticky="ew")
        ctk.CTkButton(studio_input, text="Select Photos", width=120, height=32, corner_radius=8, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._browse_studio_photos).grid(row=0, column=2, padx=6)
        ctk.CTkButton(studio_input, text="Select Folder", width=120, height=32, corner_radius=8, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._browse_studio_folder).grid(row=0, column=3, padx=6)

        studio_opts = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        studio_opts.grid(row=2, column=0, sticky="ew", padx=20, pady=12)
        studio_opts.grid_columnconfigure((1,3,5), weight=1)

        ctk.CTkLabel(studio_opts, text="Mode", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), text_color=COLORS["text_dim"]).grid(row=0, column=0, padx=24, pady=12, sticky="w")
        self.studio_mode_var = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(studio_opts, values=["auto","turntable","box","cylinder","sphere","plane"], variable=self.studio_mode_var, width=140, fg_color=COLORS["card2"], button_color=COLORS["card2"], font=ctk.CTkFont(size=12, family="Segoe UI")).grid(row=0, column=1, padx=8, sticky="ew")

        self.studio_status = ctk.CTkLabel(studio_opts, text="Ready — drop photos", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12, family="Segoe UI"))
        self.studio_status.grid(row=0, column=2, columnspan=3, padx=12, sticky="ew")

        btn_row_studio = ctk.CTkFrame(studio_opts, fg_color="transparent")
        btn_row_studio.grid(row=1, column=0, columnspan=6, sticky="ew", padx=24, pady=12)

        ctk.CTkButton(btn_row_studio, text="Analyze Photos", width=140, height=36, corner_radius=10, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._analyze_studio).pack(side="left", padx=6)
        ctk.CTkButton(btn_row_studio, text="Build 3D Stage", width=160, height=36, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self._build_3d_stage).pack(side="left", padx=12)
        ctk.CTkButton(btn_row_studio, text="Open WebGL Viewer", width=150, height=36, corner_radius=10, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._open_studio_viewer).pack(side="left", padx=6)
        ctk.CTkButton(btn_row_studio, text="Open 360 Viewer", width=140, height=36, corner_radius=10, fg_color=COLORS["card2"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._open_360_viewer).pack(side="left", padx=6)

        self.studio_scroll = ctk.CTkScrollableFrame(parent, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self.studio_scroll.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0,20))

        ctk.CTkLabel(self.studio_scroll, text="No 3D studio yet — select product photos and click Analyze", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=12, family="Segoe UI")).pack(pady=40)

    def _build_tools_page(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        tools_card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=16, border_width=1, border_color=COLORS["border"])
        tools_card.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        tools_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tools_card, text="Tools & Utilities", font=ctk.CTkFont(size=18, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(20,8))

        pinger_frame = ctk.CTkFrame(tools_card, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        pinger_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(pinger_frame, text="Branches Pinger V3 — Latest arena branches", font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(16,4))
        ctk.CTkLabel(pinger_frame, text="Checks GitHub API /branches for all arena/feature/dev branches, finds latest by commit date. Watch: python tools/pinger.py --branches --watch", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"), wraplength=800, justify="left").pack(anchor="w", padx=20)

        pinger_btns = ctk.CTkFrame(pinger_frame, fg_color="transparent")
        pinger_btns.pack(fill="x", padx=20, pady=16)

        ctk.CTkButton(pinger_btns, text="Check Branches Now", width=160, height=36, corner_radius=10, fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"), command=self._check_updates_manual).pack(side="left", padx=6)
        ctk.CTkButton(pinger_btns, text="View Log", width=100, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._open_pinger_log).pack(side="left", padx=6)
        ctk.CTkButton(pinger_btns, text="Branches Log", width=120, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._open_branches_log).pack(side="left", padx=6)
        ctk.CTkButton(pinger_btns, text="pinger.py", width=100, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=lambda: self._open_file("tools/pinger.py")).pack(side="left", padx=6)

        self.branches_frame = ctk.CTkFrame(tools_card, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        self.branches_frame.pack(fill="x", padx=20, pady=12)
        ctk.CTkLabel(self.branches_frame, text="Branches — Latest arena by date", font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(16,4))
        self.branches_label = ctk.CTkLabel(self.branches_frame, text="No branches checked yet — click Check Branches Now\nV3 will fetch all remote branches via GitHub API /branches", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"), wraplength=800, justify="left")
        self.branches_label.pack(anchor="w", padx=20, pady=(0,16))

        ctx_frame = ctk.CTkFrame(tools_card, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        ctx_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(ctx_frame, text="Context Menu", font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(16,4))
        ctk.CTkLabel(ctx_frame, text="Right-click image → Convert with Image Switcher. Right-click folder → Batch convert. Install via install.ps1 -ContextMenu", text_color=COLORS["text_dim"], font=ctk.CTkFont(size=11, family="Segoe UI"), wraplength=600, justify="left").pack(anchor="w", padx=20, pady=(0,16))

        other_frame = ctk.CTkFrame(tools_card, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["border"])
        other_frame.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(other_frame, text="Other • F11 Fullscreen • Shift+F11 Bounds", font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(anchor="w", padx=20, pady=(16,4))
        row = ctk.CTkFrame(other_frame, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(row, text="Landing", width=100, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=lambda: self._open_file("website/index.html")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Mockup", width=100, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=lambda: self._open_file("mockups/ui-redesign-v2.png")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="README", width=90, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=lambda: self._open_file("README.md")).pack(side="left", padx=6)
        ctk.CTkButton(row, text="⛶ F11 Test", width=90, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._toggle_fullscreen).pack(side="left", padx=12)
        ctk.CTkButton(row, text="🗖 Bounds Test", width=110, height=36, corner_radius=10, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], font=ctk.CTkFont(size=12, family="Segoe UI"), command=self._toggle_maximize_taskbar).pack(side="left", padx=6)

    def _build_status_bar(self):
        status_row = 3 if self.custom_titlebar_enabled else 2
        bottom = ctk.CTkFrame(self, height=84, fg_color=COLORS["card"], corner_radius=0, border_width=1, border_color=COLORS["border"])
        bottom.grid(row=status_row, column=0, columnspan=2, sticky="ew")
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(1, weight=1)
        self.bottom_frame = bottom

        self.bounds_border = ctk.CTkFrame(self, height=4, fg_color=COLORS["neon"], corner_radius=0)

        self.status_label = ctk.CTkLabel(bottom, text="Ready — Drop anywhere • Ctrl+O • F11 Fullscreen • Shift+F11 Bounds • V3 Pro Dark • Offline", font=ctk.CTkFont(size=11, family="Segoe UI"), text_color=COLORS["text_dim"], anchor="w")
        self.status_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(10,2))

        self.convert_btn = ctk.CTkButton(bottom, text="Convert", width=160, height=40, corner_radius=10, font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"), fg_color=COLORS["text"], text_color=COLORS["bg"], hover_color=COLORS["neon"], command=self.convert_image, state="disabled")
        self.convert_btn.grid(row=1, column=0, padx=20, pady=8, sticky="w")

        self.save_btn = ctk.CTkButton(bottom, text="Save As...", width=110, height=36, corner_radius=10, font=ctk.CTkFont(size=12, family="Segoe UI"), fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], command=self.save_converted, state="disabled")
        self.save_btn.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        self.open_folder_btn = ctk.CTkButton(bottom, text="Open Folder", width=110, height=36, corner_radius=10, font=ctk.CTkFont(size=12, family="Segoe UI"), fg_color=COLORS["card2"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["border"], command=self.open_folder, state="disabled")
        self.open_folder_btn.grid(row=1, column=1, padx=130, pady=8, sticky="w")

        self.gate_info_label = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=11, family="Segoe UI"), text_color=COLORS["text_dim"], wraplength=500, justify="left")
        self.gate_info_label.grid(row=1, column=2, padx=20, sticky="e")

    def _open_command_palette(self):
        win = ctk.CTkToplevel(self)
        win.title("Command Palette — Ctrl+K")
        win.geometry("600x400")
        win.transient(self)
        win.grab_set()
        win.configure(fg_color=COLORS["card"])

        ctk.CTkLabel(win, text="Command Palette", font=ctk.CTkFont(size=16, weight="bold", family="Segoe UI"), text_color=COLORS["text"]).pack(pady=16)

        entry = ctk.CTkEntry(win, placeholder_text="Type a command or search...", width=540, height=40, corner_radius=10, fg_color=COLORS["card2"], border_color=COLORS["border"], font=ctk.CTkFont(size=13, family="Segoe UI"))
        entry.pack(padx=20, pady=8)
        entry.focus()

        scroll = ctk.CTkScrollableFrame(win, width=540, height=280, fg_color=COLORS["card2"], corner_radius=12)
        scroll.pack(padx=20, pady=12, fill="both", expand=True)

        commands = [
            ("🖼️  Go to Single", lambda: (self._switch_page("Single"), win.destroy())),
            ("🔥  Go to Batch", lambda: (self._switch_page("Batch"), win.destroy())),
            ("✨  Go to Presets", lambda: (self._switch_page("Presets"), win.destroy())),
            ("🤖  Go to AI Tools", lambda: (self._switch_page("AI"), win.destroy())),
            ("📦  Go to 3D Studio", lambda: (self._switch_page("3D Studio"), win.destroy())),
            ("🔧  Go to Tools", lambda: (self._switch_page("Tools"), win.destroy())),
            ("📁  Browse File (Ctrl+O)", lambda: (self.browse_file(), win.destroy())),
            ("🔄  Convert (Space)", lambda: (self.convert_image(), win.destroy())),
            ("💾  Save As (Ctrl+S)", lambda: (self.save_converted(), win.destroy())),
            ("⛶  Toggle Fullscreen (F11)", lambda: (self._toggle_fullscreen(), win.destroy())),
            ("🗖  Toggle Bounds (Shift+F11)", lambda: (self._toggle_maximize_taskbar(), win.destroy())),
            ("🌗  Toggle Theme (Ctrl+T) • Light/Dark", lambda: (self._toggle_theme(), win.destroy())),
            ("🪟  Toggle Custom Titlebar (Ctrl+Shift+T)", lambda: (self._toggle_custom_titlebar(), win.destroy())),
            ("✨  Toggle Acrylic Blur (Ctrl+Shift+A) • Mica", lambda: (self._toggle_acrylic_blur(), win.destroy())),
            ("↔️  Resize Sidebar • Drag handle at right edge", lambda: (toast_info("Drag the 4px handle at sidebar right edge • 200-400px"), win.destroy())),
            ("🔔  Check Updates", lambda: (self._check_updates_manual(), win.destroy())),
        ]

        def filter_cmds(*args):
            q = entry.get().lower()
            for w in scroll.winfo_children():
                w.destroy()
            for label, cmd in commands:
                if q in label.lower():
                    b = ctk.CTkButton(scroll, text=label, height=36, corner_radius=8, fg_color="transparent", hover_color=COLORS["card_hover"], anchor="w", font=ctk.CTkFont(size=12, family="Segoe UI"), command=cmd)
                    b.pack(fill="x", padx=4, pady=2)

        entry.bind("<KeyRelease>", filter_cmds)
        filter_cmds()

        def on_esc(e):
            win.destroy()
        win.bind("<Escape>", on_esc)
        entry.bind("<Escape>", on_esc)

    # ===== V3.1 THEME + CUSTOM TITLEBAR + ANIMATIONS =====
    def _toggle_theme(self):
        # Toggle light/dark
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        global COLORS
        if self.current_theme == "light":
            COLORS = COLORS_LIGHT.copy()
            ctk.set_appearance_mode("light")
            try:
                self.theme_btn.configure(text="☀️")
                if hasattr(self, 'titlebar_theme_btn'):
                    self.titlebar_theme_btn.configure(text="☀️")
            except:
                pass
        else:
            COLORS = COLORS_DARK.copy()
            ctk.set_appearance_mode("dark")
            try:
                self.theme_btn.configure(text="🌙")
                if hasattr(self, 'titlebar_theme_btn'):
                    self.titlebar_theme_btn.configure(text="🌙")
            except:
                pass

        # Apply to main frames
        try:
            self.configure(fg_color=COLORS["bg"])
            self.header_frame.configure(fg_color=COLORS["card"])
            self.sidebar.configure(fg_color=COLORS["sidebar"])
            self.content.configure(fg_color=COLORS["bg"])
            self.bottom_frame.configure(fg_color=COLORS["card"], border_color=COLORS["border"])
            if hasattr(self, 'custom_titlebar'):
                self.custom_titlebar.configure(fg_color=COLORS["sidebar"])
            # Update pages
            for frame in self.pages.values():
                frame.configure(fg_color=COLORS["bg"])
            toast_success(f"Theme: {self.current_theme} • Restart for full effect" if self.current_theme=="light" else f"Theme: {self.current_theme} • Pro Dark Studio")
        except Exception as e:
            print(f"Theme apply failed: {e}")

        # Save config
        try:
            self.config["ui"] = self.config.get("ui", {})
            self.config["ui"]["theme"] = self.current_theme
            save_config(self.config)
        except:
            pass

    def _toggle_custom_titlebar(self):
        # Toggle custom titlebar
        self.custom_titlebar_enabled = not self.custom_titlebar_enabled
        self.config["ui"] = self.config.get("ui", {})
        self.config["ui"]["custom_titlebar"] = self.custom_titlebar_enabled
        save_config(self.config)

        if self.custom_titlebar_enabled:
            # Enable custom
            try:
                self._build_custom_titlebar()
                self.overrideredirect(True)
                # Re-grid with new rows
                self.header_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
                self.sidebar.grid(row=2, column=0, sticky="nsew")
                self.content.grid(row=2, column=1, sticky="nsew")
                self.bottom_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
                self.titlebar_btn.configure(fg_color=COLORS["neon"])
                toast_success("Custom Titlebar ON • Traffic lights • Draggable")
            except Exception as e:
                print(f"Custom titlebar enable failed: {e}")
        else:
            # Disable custom
            try:
                self.overrideredirect(False)
                if hasattr(self, 'custom_titlebar'):
                    self.custom_titlebar.grid_forget()
                self.header_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
                self.sidebar.grid(row=1, column=0, sticky="nsew")
                self.content.grid(row=1, column=1, sticky="nsew")
                self.bottom_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
                self.titlebar_btn.configure(fg_color=COLORS["card2"])
                toast_info("Custom Titlebar OFF • OS titlebar restored")
            except Exception as e:
                print(f"Custom titlebar disable failed: {e}")

    def _toggle_acrylic_blur(self):
        # V3.2 Toggle acrylic blur
        self.acrylic_enabled = not getattr(self, 'acrylic_enabled', True)
        self.config["ui"] = self.config.get("ui", {})
        self.config["ui"]["acrylic_blur"] = self.acrylic_enabled
        save_config(self.config)
        try:
            if hasattr(self, 'acrylic_btn'):
                self.acrylic_btn.configure(fg_color=COLORS["neon"] if self.acrylic_enabled else COLORS["card2"])
        except:
            pass
        if self.acrylic_enabled:
            ok = self._enable_acrylic_blur()
            if ok:
                toast_success("Acrylic Blur ON • Mica/Blur enabled • Windows 11")
            else:
                toast_info("Acrylic Blur ON • Fallback: not supported on this OS")
        else:
            try:
                if os.name == "nt":
                    import ctypes
                    hwnd = self.winfo_id()
                    try:
                        hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
                    except:
                        pass
                    DWMWA_SYSTEMBACKDROP_TYPE = 38
                    DWMSBT_AUTO = 0
                    val = ctypes.c_int(DWMSBT_AUTO)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(val), ctypes.sizeof(val))
            except Exception as e:
                print(f"Disable acrylic failed: {e}")
            toast_info("Acrylic Blur OFF • Solid background")

    def _setup_animations(self):
        # V3.1 Animations - hover, page switch fade, button pulse + V3.2 ripple
        try:
            # Add hover animations to nav buttons
            for btn in self.nav_buttons.values():
                self._add_hover_animation(btn)
                self._add_ripple_animation(btn)

            # Add hover to header buttons
            for btn in [self.fullscreen_btn, self.maximize_btn, self.pinger_btn, self.theme_btn, self.titlebar_btn, self.acrylic_btn, self.settings_btn]:
                self._add_hover_animation(btn, subtle=True)
                self._add_ripple_animation(btn)

            # Add ripple to primary buttons
            for attr in ['convert_btn', 'batch_convert_btn', 'batch_scan_btn']:
                if hasattr(self, attr):
                    self._add_ripple_animation(getattr(self, attr))

            # Pulse convert button when ready
            if hasattr(self, 'convert_btn'):
                self._pulse_button(self.convert_btn)

        except Exception as e:
            print(f"Setup animations failed: {e}")

    def _add_ripple_animation(self, btn):
        # V3.2 Ripple micro-interaction - material style ripple on click
        try:
            def on_click(event):
                try:
                    x, y = event.x, event.y
                    w = btn.winfo_width()
                    h = btn.winfo_height()
                    max_size = max(w, h) * 1.5
                    ripple = ctk.CTkFrame(btn, width=10, height=10, corner_radius=100, fg_color=COLORS["neon"] if self.current_theme=="dark" else "#ffffff", border_width=0)
                    ripple.place(x=x-5, y=y-5)
                    def expand(size=10, opacity=1.0):
                        if size >= max_size:
                            try:
                                ripple.place_forget()
                                ripple.destroy()
                            except:
                                pass
                            return
                        try:
                            ripple.configure(width=size, height=size, corner_radius=size//2)
                            ripple.place(x=x-size//2, y=y-size//2)
                            self.after(16, lambda: expand(size+max_size//10, opacity-0.1))
                        except:
                            pass
                    expand()
                    try:
                        orig_h = btn.cget("height")
                        btn.configure(height=max(20, orig_h-2))
                        self.after(100, lambda: btn.configure(height=orig_h))
                    except:
                        pass
                except Exception as ex:
                    print(f"Ripple failed: {ex}")
            btn.bind("<ButtonPress-1>", on_click, add="+")
        except Exception as e:
            print(f"Add ripple failed: {e}")

    def _add_hover_animation(self, btn, subtle=False):
        # Simple hover scale animation via after
        orig_fg = btn.cget("fg_color")
        def on_enter(e):
            try:
                btn.configure(fg_color=COLORS["card_hover"] if subtle else COLORS["sidebar_hover"])
                # Slight scale effect via font weight
                if not subtle:
                    btn.configure(font=ctk.CTkFont(size=13, weight="bold", family="Segoe UI"))
            except:
                pass
        def on_leave(e):
            try:
                # Restore based on active state
                if btn in self.nav_buttons.values():
                    is_active = btn.cget("text_color") == COLORS["text"]
                    if is_active:
                        btn.configure(fg_color=COLORS["card2"])
                    else:
                        btn.configure(fg_color="transparent")
                else:
                    btn.configure(fg_color=orig_fg)
            except:
                pass
        try:
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
        except:
            pass

    def _pulse_button(self, btn, pulses=3):
        # Pulse animation for convert button
        try:
            count = [0]
            def pulse():
                if count[0] >= pulses*2:
                    btn.configure(fg_color=COLORS["text"] if self.current_theme=="dark" else COLORS["text"], text_color=COLORS["bg"])
                    return
                if count[0] % 2 == 0:
                    btn.configure(fg_color=COLORS["neon"], text_color="#000")
                else:
                    btn.configure(fg_color=COLORS["text"], text_color=COLORS["bg"])
                count[0] += 1
                self.after(300, pulse)
            # Only pulse if button is enabled and file loaded
            if self.current_file:
                self.after(500, pulse)
        except:
            pass

    def _animate_page_switch(self, old_page, new_page):
        # V3.1 Page switch fade animation
        if self.animating:
            return
        self.animating = True
        try:
            new_frame = self.pages.get(new_page)
            if new_frame:
                # Start slightly transparent/offset and animate in
                new_frame.tkraise()
                # Simple fade via after - we can't animate opacity in CTk, so we animate a subtle slide
                steps = 8
                def slide_in(step=0):
                    if step >= steps:
                        self.animating = False
                        return
                    # Could animate via padding or just delay
                    self.after(20, lambda: slide_in(step+1))
                slide_in()
            else:
                self.animating = False
        except:
            self.animating = False

    def _restore_config(self):
        """Restore last used settings from local config"""
        try:
            # Last target format
            last_target = self.config.get("last_target_format", "webp")
            if last_target:
                self.target_dropdown.set_selected_by_id(last_target)
                self.batch_target_var.set(last_target)

            # Last quality
            last_q = self.config.get("last_quality", 90)
            self.quality_slider.set(last_q)
            self.quality_label.configure(text=str(last_q))
            self.batch_quality_slider.set(last_q)
            self.batch_quality_label.configure(text=str(last_q))

            # Last bg
            last_bg = self.config.get("last_bg_color", "white")
            self.bg_color_var.set(last_bg)

            # Batch settings
            batch_cfg = self.config.get("batch", {})
            if batch_cfg.get("target"):
                self.batch_target_var.set(batch_cfg["target"])
            if batch_cfg.get("quality"):
                self.batch_quality_slider.set(batch_cfg["quality"])
                self.batch_quality_label.configure(text=str(batch_cfg["quality"]))

            # Recent files - show in file label hint
            recent = self.config.get("recent_files", [])
            if recent:
                self.drop_label.configure(text=f"Recent: {Path(recent[0]).name} • Drag & Drop anywhere • Ctrl+O • {len(recent)} recent")

        except Exception as e:
            print(f"Restore config failed: {e}")

    def _bind_shortcuts(self):
        """Keyboard shortcuts - offline UX + V2.4 F11 fullscreen + taskbar bounds"""
        # Ctrl+O - Open file
        self.bind("<Control-o>", lambda e: self.browse_file())
        self.bind("<Control-O>", lambda e: self.browse_file())
        # Ctrl+S - Save as
        self.bind("<Control-s>", lambda e: self.save_converted())
        self.bind("<Control-S>", lambda e: self.save_converted())
        # Ctrl+Shift+O - Open folder for batch
        self.bind("<Control-Shift-O>", lambda e: self.browse_batch_input())
        # Ctrl+Q - Quit
        self.bind("<Control-q>", lambda e: self._on_close())
        # Esc - Clear / close dropdowns OR exit fullscreen
        self.bind("<Escape>", lambda e: self._on_escape())
        # F11 - Fullscreen toggle (bounds around taskbar aware)
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        # Shift+F11 - Maximize respecting taskbar (zoomed, not covering taskbar)
        self.bind("<Shift-F11>", lambda e: self._toggle_maximize_taskbar())
        # Ctrl+1/2/3/4/5/6 - Switch tabs
        self.bind("<Control-1>", lambda e: self._switch_page("Single"))
        self.bind("<Control-2>", lambda e: self._switch_page("Batch"))
        self.bind("<Control-3>", lambda e: self._switch_page("Presets"))
        self.bind("<Control-4>", lambda e: self._switch_page("AI"))
        self.bind("<Control-5>", lambda e: self._switch_page("3D Studio"))
        self.bind("<Control-6>", lambda e: self._switch_page("Tools"))
        # Ctrl+K - Command Palette V3.1
        self.bind("<Control-k>", lambda e: self._open_command_palette())
        self.bind("<Control-K>", lambda e: self._open_command_palette())
        # Ctrl+T - Toggle Theme V3.1
        self.bind("<Control-t>", lambda e: self._toggle_theme())
        self.bind("<Control-T>", lambda e: self._toggle_theme())
        # Ctrl+Shift+T - Toggle Custom Titlebar V3.1
        self.bind("<Control-Shift-T>", lambda e: self._toggle_custom_titlebar())
        # Ctrl+Shift+A - Toggle Acrylic Blur V3.2
        self.bind("<Control-Shift-A>", lambda e: self._toggle_acrylic_blur())
        # F5 - Refresh / Scan batch
        self.bind("<F5>", lambda e: self.scan_batch() if self.current_page == "Batch" else None)
        # Space - Convert
        self.bind("<space>", lambda e: self.convert_image() if self.current_file else None)

    def _toggle_fullscreen(self):
        """F11 - True fullscreen (covers taskbar) - press Esc or F11 to exit - V2.5 with neon visual"""
        if not self.is_fullscreen:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    def _enter_fullscreen(self):
        self.prev_geometry = self.geometry()
        self.attributes("-fullscreen", True)
        self.is_fullscreen = True
        # V2.5 - Neon border visual for fullscreen
        try:
            self.bounds_border.configure(fg_color=COLORS["neon"])
            self.bounds_border.place(x=0, y=0, relwidth=1, height=6)
            self.bottom_frame.configure(border_color=COLORS["neon"], border_width=2)
            self.fullscreen_btn.configure(fg_color=COLORS["neon"], text_color="#000", border_color=COLORS["neon"])
        except:
            pass
        self.status_label.configure(text="Fullscreen - Press F11 or Esc to exit • Taskbar hidden • Neon border active • RHHHAAAAA")
        try:
            toast_info("Fullscreen ON - F11/Esc to exit - Neon border")
        except:
            pass

    def _exit_fullscreen(self):
        self.attributes("-fullscreen", False)
        self.is_fullscreen = False
        if self.prev_geometry:
            self.geometry(self.prev_geometry)
        # Remove neon border if not in bounds mode
        try:
            if not self.is_maximized_taskbar:
                self.bounds_border.place_forget()
                self.bottom_frame.configure(border_color=COLORS["border"], border_width=1)
                self.fullscreen_btn.configure(fg_color=COLORS["card2"], text_color=COLORS["text"], border_color=COLORS["border"])
        except:
            pass
        self.status_label.configure(text="Exited fullscreen - Window respects taskbar bounds • F11 for fullscreen • Shift+F11 for maximize")
        try:
            toast_success("Fullscreen OFF")
        except:
            pass
        # Ensure bounds respect taskbar after exit
        self.after(100, self._ensure_taskbar_bounds)

    def _toggle_maximize_taskbar(self):
        """Shift+F11 - Maximize but RESPECTS taskbar (bounds around taskbar) - V2.5 with neon border visual"""
        try:
            if not self.is_maximized_taskbar:
                self.prev_geometry = self.geometry()
                # Get work area (screen minus taskbar) on Windows
                work_area = self._get_work_area()
                if work_area:
                    x, y, w, h = work_area
                    self.geometry(f"{w}x{h}+{x}+{y}")
                else:
                    # Fallback - zoomed state respects taskbar on Windows
                    self.state("zoomed")
                self.is_maximized_taskbar = True
                # V2.5 - Visual neon border when in Bounds mode
                try:
                    self.bounds_border.configure(fg_color=COLORS["neon"])
                    self.bounds_border.place(x=0, y=0, relwidth=1, height=6)
                    self.bottom_frame.configure(border_color=COLORS["neon"], border_width=2)
                    self.maximize_btn.configure(fg_color=COLORS["neon"], text_color="#000", border_color=COLORS["neon"])
                except:
                    pass
                self.status_label.configure(text="Maximized respecting taskbar - NEON bounds active • Shift+F11 to restore • F11 true fullscreen")
                toast_success("Bounds Mode ON - Neon border - respects taskbar")
            else:
                self.state("normal")
                if self.prev_geometry:
                    self.geometry(self.prev_geometry)
                self.is_maximized_taskbar = False
                try:
                    self.bounds_border.place_forget()
                    self.bottom_frame.configure(border_color=COLORS["border"], border_width=1)
                    self.maximize_btn.configure(fg_color=COLORS["card2"], text_color=COLORS["text"], border_color=COLORS["border"])
                except:
                    pass
                self.status_label.configure(text="Restored - window bounded • Shift+F11 to maximize respecting taskbar")
                toast_info("Bounds Mode OFF - Restored")
        except Exception as e:
            print(f"Maximize taskbar failed: {e}")
            # Fallback to simple zoomed
            try:
                self.state("zoomed" if not self.is_maximized_taskbar else "normal")
                self.is_maximized_taskbar = not self.is_maximized_taskbar
                if self.is_maximized_taskbar:
                    self.bounds_border.place(x=0, y=0, relwidth=1, height=6)
                    self.bottom_frame.configure(border_color=COLORS["neon"], border_width=2)
                else:
                    self.bounds_border.place_forget()
            except:
                pass

    def _get_work_area(self):
        """Get work area (screen minus taskbar) - Windows API via ctypes, fallback to screen size"""
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                # Get work area
                SPI_GETWORKAREA = 0x0030
                rect = wintypes.RECT()
                ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
                x = rect.left
                y = rect.top
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                return (x, y, w, h)
            else:
                # Linux/Mac - use screen size minus small margin for taskbar/dock
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                # Assume taskbar 40px bottom
                return (0, 0, sw, sh-40)
        except Exception as e:
            print(f"Get work area failed: {e}")
            return None

    def _ensure_taskbar_bounds(self):
        """Ensure window is within work area (bounds around taskbar) - called on resize/move"""
        try:
            work_area = self._get_work_area()
            if not work_area:
                return
            wx, wy, ww, wh = work_area
            # Get current geometry
            self.update_idletasks()
            x = self.winfo_x()
            y = self.winfo_y()
            w = self.winfo_width()
            h = self.winfo_height()

            # Clamp to work area
            new_x = max(wx, min(x, wx + ww - 100))
            new_y = max(wy, min(y, wy + wh - 100))
            new_w = min(w, ww)
            new_h = min(h, wh)

            # Only adjust if out of bounds significantly
            if x < wx-50 or y < wy-50 or x + w > wx + ww + 50 or y + h > wy + wh + 50:
                self.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
        except Exception as e:
            print(f"Ensure bounds failed: {e}")

    def _on_escape(self):
        # If fullscreen, exit fullscreen first (F11 UX)
        if self.is_fullscreen:
            self._exit_fullscreen()
            return
        # Close dropdowns if open
        try:
            if self.source_dropdown.is_open:
                self.source_dropdown.close_dropdown()
                return
            if self.target_dropdown.is_open:
                self.target_dropdown.close_dropdown()
                return
        except:
            pass

    def _init_drag_drop(self):
        """Real drag & drop - tries windnd (Windows) and tkinterdnd2, fallback to visual"""
        # Try windnd for Windows - best offline, no extra window
        try:
            import windnd
            def on_drop(files):
                for f in files:
                    fp = f.decode('utf-8') if isinstance(f, bytes) else str(f)
                    if os.path.isdir(fp):
                        # Folder dropped -> batch mode
                        self.batch_input_var.set(fp)
                        self.batch_items = self.batch_engine.discover_images(fp, recursive=self.batch_recursive.get())
                        self._refresh_batch_list()
                        self._switch_page("Batch")
                        toast_success(f"Dropped folder: {len(self.batch_items)} images found")
                        self.batch_status_label.configure(text=f"Dropped folder - {len(self.batch_items)} images")
                    else:
                        # File dropped -> single mode
                        self.load_file(fp)
                        self._switch_page("Single")
                        toast_success(f"Dropped: {Path(fp).name}")
                    break  # Only first file/folder

            windnd.hook_dropfiles(self, func=on_drop)
            self.drop_label.configure(text="✅ Drag & Drop enabled (windnd) • Drop files/folders anywhere • Recent + Shortcuts • Offline")
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"windnd failed: {e}")

        # Try tkinterdnd2
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            # Need to have TkinterDnD root, but we are CTk - try to enable
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_dnd_drop)
            self.drop_label.configure(text="✅ Drag & Drop enabled (tkdnd) • Drop files anywhere • Offline")
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"tkdnd failed: {e}")

        # Fallback - no real DnD, but keep visual hint + recent
        self.drop_label.configure(text="💡 Tip: Drag & Drop needs windnd (pip install windnd) or use Ctrl+O • Recent files + offline • No cloud")

    def _on_dnd_drop(self, event):
        # For tkinterdnd2
        files = self.tk.splitlist(event.data)
        for fp in files:
            fp = fp.strip('{}')
            if os.path.isdir(fp):
                self.batch_input_var.set(fp)
                self.batch_items = self.batch_engine.discover_images(fp, recursive=True)
                self._refresh_batch_list()
                self._switch_page("Batch")
                toast_success(f"Dropped folder: {len(self.batch_items)} images")
            else:
                self.load_file(fp)
                self._switch_page("Single")
                toast_success(f"Dropped: {Path(fp).name}")
            break

    def _show_onboarding(self):
        """First-run onboarding - local, no cloud"""
        win = ctk.CTkToplevel(self)
        win.title("Welcome to Image Switcher V2.2 • Offline")
        win.geometry("650x500")
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text="🖼️ Welcome to Image Switcher V2.2", font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["neon"]).pack(pady=(20,10))
        ctk.CTkLabel(win, text="100% Local & Offline • No Cloud • RHHHAAAAA Edition", font=ctk.CTkFont(size=12), text_color=COLORS["text_dim"]).pack()

        txt = ctk.CTkTextbox(win, width=600, height=320, fg_color=COLORS["card"], font=ctk.CTkFont(size=12))
        txt.pack(padx=20, pady=20)
        txt.insert("0.0", f"""🎉 Welcome! Everything is LOCAL & OFFLINE suiiiiiii

✨ NEW V2.2 UX Improvements:
• Real Drag & Drop - drop files/folders anywhere (needs windnd: pip install windnd)
• Keyboard Shortcuts: Ctrl+O Open, Ctrl+S Save, Ctrl+Q Quit, Ctrl+1-5 Switch Tabs, Esc Close dropdowns, Space Convert, F5 Scan batch
• Recent Files - remembers last 10 files/folders (saved locally in {self.config.get('window',{})})
• Toast Notifications - no more annoying popups, auto-dismiss glass toasts
• Comparison Slider - in Dual Viewer, drag divider to wipe OLD vs NEW
• Settings Persistence - remembers last format, quality, bg color, output dir (100% local JSON)
• Better Empty States - helpful tips when no file loaded
• Batch Drag & Drop - drop folder onto Batch tab
• Presets Visual + Favorites
• AI Tools Before/After preview

📁 Config saved locally at:
{Path.home() / 'AppData' / 'Roaming' / 'ImageSwitcher' / 'config.json' if os.name=='nt' else Path.home() / '.config' / 'ImageSwitcher' / 'config.json'}

🔔 Pinger is offline-friendly:
• Works without internet (shows cached status)
• Checks GitHub only when online
• No tracking, no cloud

🖱️ Context Menu:
• Install with: install.ps1 -ContextMenu -FileAssociations
• Right-click image → Convert with Image Switcher
• Right-click folder → Convert images in folder

⚡ Quick Start:
1. Drop image or Ctrl+O
2. Select target format (searchable)
3. Press Space or Convert button
4. Save As Ctrl+S

💡 Tips:
• Try Presets ✨ tab for Instagram, Discord, Web sizes
• Try AI 🤖 tab for BG remover + Upscaler (pip install rembg for best quality)
• Batch 🔥 tab for folder conversion
• Tools tab for pinger + landing page

Enjoy offline converting! RHHHAAAAA
""")
        txt.configure(state="disabled")

        def close():
            win.destroy()
            # Save first_run = False
            self.config["first_run"] = False
            save_config(self.config)

        ctk.CTkButton(win, text="Let's Go RHHHAAAAA 🚀", fg_color=COLORS["neon"], text_color="#000", font=ctk.CTkFont(weight="bold"), command=close).pack(pady=10)

    def _on_close(self):
        # Save window size + settings
        try:
            # Save current settings
            if self.target_dropdown.get_selected():
                self.config["last_target_format"] = self.target_dropdown.get_selected().id
            self.config["last_quality"] = int(self.quality_slider.get())
            self.config["last_bg_color"] = self.bg_color_var.get()
            self.config["batch"] = {
                "target": self.batch_target_var.get(),
                "quality": int(self.batch_quality_slider.get()),
                "recursive": bool(self.batch_recursive.get()),
                "keep_structure": bool(self.batch_keep_struct.get()),
                "overwrite": bool(self.batch_overwrite.get()),
            }
            # Window size
            self.config["window"] = {
                "width": self.winfo_width(),
                "height": self.winfo_height(),
            }
            save_config(self.config)
        except Exception as e:
            print(f"Save config on close failed: {e}")

        self.destroy()

    # ===== LOGIC (same as before but with V2 polish) =====
    def browse_file(self):
        filetypes = [
            ("All Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff *.tif *.ico *.avif *.heif *.heic *.svg *.svgz *.pdf *.eps *.ps *.tga *.pcx *.ppm *.pgm *.pbm *.dds *.psd *.hdr *.exr *.jp2 *.j2k *.qoi"),
            ("Common", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
            ("Vector", "*.svg *.svgz *.pdf *.eps"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(title="Select Image", filetypes=filetypes)
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        self.current_file = path
        self.file_label.configure(text=f"📄 {path}", text_color=COLORS["text"])
        self.status_label.configure(text=f"Loading {os.path.basename(path)}...")

        # Add to recent + save config - local only
        try:
            add_recent_file(self.config, path)
            self.config["recent_files"] = self.config.get("recent_files", [])
            if path not in self.config["recent_files"]:
                self.config["recent_files"].insert(0, path)
                self.config["recent_files"] = self.config["recent_files"][:10]
        except:
            pass

        info = self.engine.get_image_info(path)
        self.current_info = info
        fmt = self.engine.detect_source_format(path)

        if fmt:
            self.source_dropdown.set_selected_by_id(fmt.id)
            self.update_target_gate(fmt, info)
        else:
            self.source_dropdown.main_btn.configure(text="Unknown format - select manually")
            self.target_dropdown.set_gate_results({})

        self.single_viewer.load_original(path, info)
        self.single_viewer.right.show_placeholder("Select target format and click CONVERT")
        self.convert_btn.configure(state="normal" if fmt else "disabled")
        self.status_label.configure(text=f"Loaded {info.get('width')}x{info.get('height')} {info.get('format')} | Ready to convert • {os.path.basename(path)}")

        # Toast instead of just status
        try:
            toast_success(f"Loaded {Path(path).name} • {info.get('width')}x{info.get('height')} {info.get('format')}")
        except:
            pass

    def update_target_gate(self, source_fmt, source_info):
        gate_map = {}
        has_alpha = source_info.get("has_alpha", False) if source_info else False
        is_anim = source_info.get("is_animated", False) if source_info else False
        for tgt in FORMATS:
            gate = validate_conversion(source_fmt, tgt, source_has_alpha=has_alpha, source_is_animated=is_anim)
            gate_map[tgt.id] = gate
        self.target_dropdown.set_gate_results(gate_map)

    def on_source_selected(self, fmt):
        if self.current_info:
            self.update_target_gate(fmt, self.current_info)
        else:
            gate_map = {}
            for tgt in FORMATS:
                gate = validate_conversion(fmt, tgt)
                gate_map[tgt.id] = gate
            self.target_dropdown.set_gate_results(gate_map)
        self.gate_info_label.configure(text=f"Source set to {fmt.id.upper()} - select target")
        self.convert_btn.configure(state="normal")

    def on_target_selected(self, fmt):
        self.last_target_id = fmt.id
        src_fmt = self.source_dropdown.get_selected()
        if src_fmt:
            gate = validate_conversion(src_fmt, fmt, source_has_alpha=self.current_info.get("has_alpha", False) if self.current_info else False, source_is_animated=self.current_info.get("is_animated", False) if self.current_info else False)
            txt = f"{gate.reason}"
            if gate.warnings:
                txt += " | " + " | ".join(gate.warnings[:2])
            color = COLORS["neon"] if gate.status=="green" else COLORS["yellow"] if gate.status=="yellow" else COLORS["red"]
            self.gate_info_label.configure(text=txt, text_color=color)
            self.convert_btn.configure(state="normal" if gate.allowed else "disabled")
            if not gate.allowed:
                self.status_label.configure(text=f"Blocked: {gate.reason}")
        else:
            self.gate_info_label.configure(text=f"Target: {fmt.id.upper()} - {fmt.description}")

    def on_quality_change(self, value):
        q = int(value)
        self.quality_label.configure(text=str(q))

    def convert_image(self):
        if not self.current_file:
            try:
                toast_warning("Select an image first (Ctrl+O)")
            except:
                pass
            messagebox.showwarning("No file", "Select an image first - Drag & Drop or Ctrl+O")
            return
        src_fmt = self.source_dropdown.get_selected()
        tgt_fmt = self.target_dropdown.get_selected()
        if not tgt_fmt:
            try:
                toast_warning("Select target format")
            except:
                pass
            messagebox.showwarning("No target", "Select target format from searchable dropdown")
            return
        if not src_fmt:
            src_fmt = self.engine.detect_source_format(self.current_file)
            if not src_fmt:
                try:
                    toast_error("Cannot detect source format")
                except:
                    pass
                messagebox.showerror("Error", "Cannot detect source format")
                return

        gate = validate_conversion(src_fmt, tgt_fmt, source_has_alpha=self.current_info.get("has_alpha", False), source_is_animated=self.current_info.get("is_animated", False))
        if not gate.allowed:
            try:
                toast_error(f"Blocked: {gate.reason}")
            except:
                pass
            messagebox.showerror("Blocked by Acceptance Gate", gate.reason)
            return

        # Save last used settings - local persistence
        try:
            update_setting("last_target_format", tgt_fmt.id)
            update_setting("last_quality", int(self.quality_slider.get()))
            update_setting("last_bg_color", self.bg_color_var.get())
        except:
            pass

        self.convert_btn.configure(state="disabled", text="Converting...")
        self.status_label.configure(text=f"Converting {src_fmt.id.upper()} -> {tgt_fmt.id.upper()}...")

        def do_convert():
            try:
                bg_str = self.bg_color_var.get()
                bg_map = {"white": (255,255,255), "black": (0,0,0), "red": (255,0,0), "green": (0,255,0), "blue": (0,0,255), "transparent": (255,255,255)}
                bg = bg_map.get(bg_str, (255,255,255))
                quality = int(self.quality_slider.get())
                resize = None
                if not self.keep_aspect.get():
                    try:
                        w = int(self.width_entry.get()) if self.width_entry.get().strip() else 0
                        h = int(self.height_entry.get()) if self.height_entry.get().strip() else 0
                        if w>0 and h>0:
                            resize = (w,h)
                    except:
                        pass

                ext = tgt_fmt.exts[0]
                temp_dir = tempfile.gettempdir()
                out_path = os.path.join(temp_dir, f"converted_{os.path.splitext(os.path.basename(self.current_file))[0]}{ext}")
                base, ex = os.path.splitext(out_path)
                counter = 1
                while os.path.exists(out_path):
                    out_path = f"{base}_{counter}{ex}"
                    counter+=1

                success, msg, extra = self.engine.convert(self.current_file, out_path, tgt_fmt.id, background_color=bg, quality=quality, resize=resize)

                def on_done():
                    if success:
                        self.converted_file = out_path
                        info = self.engine.get_image_info(out_path)
                        self.single_viewer.load_converted(out_path, info)
                        self.save_btn.configure(state="normal")
                        self.open_folder_btn.configure(state="normal")
                        self.status_label.configure(text=f"✅ {msg} - {os.path.basename(out_path)} | {info.get('width')}x{info.get('height')}")
                        self.gate_info_label.configure(text=f"Done: {src_fmt.id.upper()} -> {tgt_fmt.id.upper()} | {msg}")
                    else:
                        self.status_label.configure(text=f"❌ Failed: {msg}")
                        messagebox.showerror("Conversion failed", msg)
                    self.convert_btn.configure(state="normal", text="🔄 CONVERT")

                self.after(0, on_done)
            except Exception as e:
                def on_err():
                    self.status_label.configure(text=f"Error: {e}")
                    messagebox.showerror("Error", str(e))
                    self.convert_btn.configure(state="normal", text="🔄 CONVERT")
                self.after(0, on_err)

        threading.Thread(target=do_convert, daemon=True).start()

    def save_converted(self):
        if not self.converted_file or not os.path.exists(self.converted_file):
            messagebox.showwarning("No converted file", "Convert an image first")
            return
        tgt = self.target_dropdown.get_selected()
        ext = tgt.exts[0] if tgt else os.path.splitext(self.converted_file)[1]
        default_name = os.path.basename(self.converted_file)
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=default_name, filetypes=[(f"{tgt.id.upper()} files" if tgt else "Image", f"*{ext}"), ("All Files", "*.*")])
        if path:
            try:
                import shutil
                shutil.copy2(self.converted_file, path)
                self.status_label.configure(text=f"Saved to {path}")
                messagebox.showinfo("Saved", f"Saved to {path}")
            except Exception as e:
                messagebox.showerror("Save failed", str(e))

    def open_folder(self):
        if self.converted_file and os.path.exists(self.converted_file):
            folder = os.path.dirname(self.converted_file)
            try:
                os.startfile(folder)
            except:
                try:
                    import subprocess
                    subprocess.Popen(["xdg-open", folder])
                except:
                    messagebox.showinfo("Folder", folder)

    # ===== BATCH LOGIC =====
    def browse_batch_input(self):
        folder = filedialog.askdirectory(title="Select Input Folder with Images")
        if folder:
            self.batch_input_var.set(folder)
            if not self.batch_output_var.get() or "Same as input" in self.batch_output_var.get():
                self.batch_output_var.set(str(Path(folder) / "converted"))

    def browse_batch_files(self):
        files = filedialog.askopenfilenames(title="Select Images", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff *.svg *.avif *.heif *.heic"), ("All", "*.*")])
        if files:
            self.batch_items = list(files)
            self.batch_input_var.set(f"{len(files)} files selected")
            self._refresh_batch_list()

    def browse_batch_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.batch_output_var.set(folder)

    def scan_batch(self):
        input_path = self.batch_input_var.get()
        if "No folder" in input_path or "files selected" in input_path and not self.batch_items:
            # If files selected mode
            if self.batch_items:
                self._refresh_batch_list()
                self.batch_status_label.configure(text=f"Ready - {len(self.batch_items)} files")
                return
            messagebox.showwarning("No input", "Select input folder first")
            return

        if self.batch_items and "files selected" in input_path:
            # Already have files
            self._refresh_batch_list()
            return

        # Scan folder
        recursive = self.batch_recursive.get()
        try:
            sources = self.batch_engine.discover_images(input_path, recursive=recursive)
            self.batch_items = sources
            self._refresh_batch_list()
            self.batch_status_label.configure(text=f"Found {len(sources)} images")
        except Exception as e:
            messagebox.showerror("Scan failed", str(e))

    def _refresh_batch_list(self):
        for w in self.batch_list_frame.winfo_children():
            w.destroy()

        if not self.batch_items:
            lbl = ctk.CTkLabel(self.batch_list_frame, text="No images found", text_color=COLORS["text_dim"])
            lbl.pack(pady=20)
            return

        # Header
        header = ctk.CTkFrame(self.batch_list_frame, fg_color="transparent")
        header.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(header, text=f"{len(self.batch_items)} images - Target: {self.batch_target_var.get().upper()} - Quality: {int(self.batch_quality_slider.get())}", font=ctk.CTkFont(weight="bold"), text_color=COLORS["neon"]).pack(anchor="w")

        # List
        for i, src in enumerate(self.batch_items[:100]):  # Show first 100
            row = ctk.CTkFrame(self.batch_list_frame, fg_color=COLORS["card2"] if i%2==0 else COLORS["card"], corner_radius=6)
            row.pack(fill="x", padx=5, pady=2)
            ctk.CTkLabel(row, text=f"{i+1}. {os.path.basename(src)}", font=ctk.CTkFont(size=11), anchor="w", width=300).pack(side="left", padx=8, pady=4)
            ctk.CTkLabel(row, text=src, font=ctk.CTkFont(size=9), text_color=COLORS["text_dim"], anchor="w").pack(side="left", padx=5, fill="x", expand=True)

        if len(self.batch_items) > 100:
            ctk.CTkLabel(self.batch_list_frame, text=f"... and {len(self.batch_items)-100} more", text_color=COLORS["text_dim"]).pack(pady=5)

    def start_batch_convert(self):
        if not self.batch_items:
            messagebox.showwarning("No images", "Scan images first")
            return

        output = self.batch_output_var.get()
        if "Same as input" in output:
            # Use input folder + converted
            inp = self.batch_input_var.get()
            if os.path.isdir(inp):
                output = str(Path(inp) / "converted")
            else:
                output = str(Path(tempfile.gettempdir()) / "batch_converted")

        target = self.batch_target_var.get()
        quality = int(self.batch_quality_slider.get())
        keep_struct = self.batch_keep_struct.get()
        overwrite = self.batch_overwrite.get()

        # Prepare
        input_root = self.batch_input_var.get() if keep_struct and os.path.isdir(self.batch_input_var.get()) else None
        items = self.batch_engine.prepare_batch(self.batch_items, output, target, keep_structure=keep_struct, input_root=input_root)

        self.batch_convert_btn.configure(state="disabled")
        self.batch_stop_btn.configure(state="normal")
        self.batch_progress.set(0)
        self.batch_status_label.configure(text=f"Converting 0/{len(items)}...")

        def on_progress(item, current, total):
            def _ui():
                self.batch_progress.set(current/total)
                self.batch_status_label.configure(text=f"Converting {current}/{total} - {os.path.basename(item.source_path)}")
            self.after(0, _ui)

        def do_batch():
            try:
                result = self.batch_engine.convert_batch(items, target, quality=quality, overwrite=overwrite, on_progress=on_progress)
                def _done():
                    self.batch_progress.set(1.0)
                    self.batch_status_label.configure(text=f"Done: {result.succeeded} ok, {result.failed} failed, {result.skipped} skipped")
                    self.batch_convert_btn.configure(state="normal")
                    self.batch_stop_btn.configure(state="disabled")
                    self.status_label.configure(text=f"Batch done: {result.succeeded}/{result.total} converted to {target.upper()} in {output}")
                    messagebox.showinfo("Batch Complete", f"Total: {result.total}\nSucceeded: {result.succeeded}\nFailed: {result.failed}\nSkipped: {result.skipped}\n\nOutput: {output}")
                    # Refresh list with statuses
                    for w in self.batch_list_frame.winfo_children():
                        w.destroy()
                    for it in result.items:
                        color = COLORS["neon"] if it.status=="done" else COLORS["red"] if it.status=="failed" else COLORS["yellow"]
                        icon = "✓" if it.status=="done" else "✗" if it.status=="failed" else "↷"
                        row = ctk.CTkFrame(self.batch_list_frame, fg_color=COLORS["card2"], corner_radius=6)
                        row.pack(fill="x", padx=5, pady=1)
                        ctk.CTkLabel(row, text=f"{icon} {os.path.basename(it.source_path)} -> {os.path.basename(it.target_path)}", text_color=color, font=ctk.CTkFont(size=11), anchor="w").pack(side="left", padx=8)
                        ctk.CTkLabel(row, text=it.message, text_color=COLORS["text_dim"], font=ctk.CTkFont(size=9)).pack(side="left", padx=5)
                self.after(0, _done)
            except Exception as e:
                def _err():
                    messagebox.showerror("Batch failed", str(e))
                    self.batch_convert_btn.configure(state="normal")
                    self.batch_stop_btn.configure(state="disabled")
                self.after(0, _err)

        threading.Thread(target=do_batch, daemon=True).start()

    def stop_batch(self):
        self.batch_engine.stop()
        self.batch_status_label.configure(text="Stopping...")
        self.batch_stop_btn.configure(state="disabled")

    # ===== PINGER + UTILS =====
    # V2.5 - Branches aware updates, not just main
    def _check_updates(self):
        def cb(result):
            def _ui():
                # V2.5 - Show branches updates too + update branches label
                try:
                    branches = result.get("branches", [])
                    latest = result.get("latest_branch")
                    if branches:
                        txt = f"🌿 {len(branches)} branches • Latest arena: {latest['name'][:40] if latest else 'N/A'} {latest['sha'][:7] if latest else ''} • {latest.get('date','')[:10] if latest else ''}\n"
                        txt += "\n".join([f"{'➡️' if latest and b['name']==latest['name'] else '  '} {b['name'][:50]} : {b['sha']} {'(you)' if b['name']==result.get('local_branch') else ''}" for b in branches[:15]])
                        if hasattr(self, 'branches_label'):
                            self.branches_label.configure(text=txt)
                except Exception as e:
                    print(f"Branches label update failed: {e}")

                if result.get("has_update"):
                    if result.get("update_type") == "branch" and result.get("latest_branch"):
                        latest = result["latest_branch"]
                        self.update_banner.configure(text=f"🔔 Branch: {latest['name'][:30]} {latest['sha'][:7]} - {latest.get('message','')[:25]}")
                    else:
                        tag = result.get("release_tag") or result.get("remote_sha") or "update"
                        self.update_banner.configure(text=f"🔔 Update: {tag} • {len(result.get('branches',[]))} branches")
                    self.version_label.configure(text_color=COLORS["neon"])
                else:
                    branches = result.get("branches", [])
                    latest = result.get("latest_branch")
                    if latest:
                        self.update_banner.configure(text=f"✓ Up to date • {len(branches)} branches • latest {latest['name'][:18]} {latest['sha'][:7]} • main {result.get('remote_sha','')[:7]}")
                    else:
                        if result.get("remote_sha"):
                            self.update_banner.configure(text=f"✓ Up to date • main {result.get('remote_sha')[:7]} • {len(branches)} branches")
                        else:
                            self.update_banner.configure(text="")
            self.after(0, _ui)
        check_for_updates_async(cb)

    def _check_updates_manual(self):
        self.pinger_btn.configure(text="Checking...", state="disabled")
        self.update_banner.configure(text="Checking branches + main + releases...")

        def cb(result):
            def _ui():
                self.pinger_btn.configure(text="🔔 Updates", state="normal")
                branches = result.get("branches", [])
                latest = result.get("latest_branch")
                # Update branches label in Tools tab
                try:
                    if branches:
                        txt = f"🌿 {len(branches)} branches fetched • Latest arena: {latest['name'] if latest else 'N/A'} • You: {result.get('local_branch')}\n"
                        txt += f"Date: {latest.get('date','') if latest else ''} • Msg: {latest.get('message','')[:60] if latest else ''}\n\n"
                        txt += "\n".join([f"{'➡️ LATEST' if latest and b['name']==latest['name'] else '  '} {b['name'][:50]} : {b['sha']} {'(you)' if b['name']==result.get('local_branch') else ''}" for b in branches[:20]])
                        if hasattr(self, 'branches_label'):
                            self.branches_label.configure(text=txt, text_color=COLORS["neon"] if result.get("has_update") else COLORS["text"])
                except Exception as e:
                    print(f"Branches label manual update failed: {e}")

                if result.get("has_update"):
                    if result.get("update_type") == "branch" and latest:
                        self.update_banner.configure(text=f"🔔 Branch: {latest['name'][:30]}")
                        msg = f"Newer branch available:\n\nLatest arena branch: {latest['name']}\nSHA: {latest['sha']}\nDate: {latest.get('date','')}\nMsg: {latest.get('message','')}\n\nYou are on: {result.get('local_branch')} ({result.get('local_version')})\nBranches found: {len(branches)}\n\nRun: git fetch origin && git checkout {latest['name']}\n\nOr Tools tab -> Check Branches"
                        messagebox.showinfo("Branch Update Available", msg)
                    else:
                        tag = result.get("release_tag") or result.get("remote_sha")
                        self.update_banner.configure(text=f"🔔 Update: {tag}")
                        messagebox.showinfo("Update Available", f"New version: {tag}\n\n{result.get('remote_message','')}\n\nVisit: {result.get('release_url') or 'https://github.com/muhummadzarrar09-sudo/python-image-switcher'}\n\nOr run: python tools/pinger.py --branches")
                else:
                    if latest:
                        self.update_banner.configure(text=f"✓ Up to date • {len(branches)} branches • latest {latest['name'][:20]}")
                        branch_list = "\n".join([f"{b['name']}: {b['sha']}" for b in branches[:10]])
                        messagebox.showinfo("Up to date", f"You are on latest v{result.get('local_version')} ({result.get('local_branch')})\nMain: {result.get('remote_sha')}\n\nBranches ({len(branches)}):\n{branch_list}\n\nLatest arena: {latest['name']} {latest['sha']}\n\nRun: python tools/pinger.py --branches")
                    else:
                        self.update_banner.configure(text=f"✓ Up to date • {result.get('remote_sha','')[:7]}")
                        messagebox.showinfo("Up to date", f"You are on latest v{result.get('local_version')}\nMain: {result.get('remote_sha')}")
            self.after(0, _ui)
        check_for_updates_async(cb)

    def _open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/muhummadzarrar09-sudo/python-image-switcher")

    def _open_file(self, rel_path):
        p = Path(__file__).parent.parent.parent / rel_path
        if p.exists():
            try:
                os.startfile(str(p))
            except:
                messagebox.showinfo("File", str(p))
        else:
            messagebox.showwarning("Not found", f"{rel_path} not found")

    def _open_pinger_log(self):
        # Run pinger in a popup V2.5 branches
        win = ctk.CTkToplevel(self)
        win.title("Pinger Log V2.5 - Branches")
        win.geometry("700x500")
        txt = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Courier", size=11), fg_color=COLORS["card"])
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("0.0", "Running pinger V2.5 --branches ...\n")

        def run():
            import subprocess
            try:
                root = Path(__file__).parent.parent.parent
                result = subprocess.run([sys.executable, str(root / "tools" / "pinger.py"), "--branches"], capture_output=True, text=True, timeout=30, cwd=str(root))
                out = result.stdout + "\n" + result.stderr
                self.after(0, lambda: txt.insert("end", out))
            except Exception as e:
                self.after(0, lambda: txt.insert("end", f"Error: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _open_branches_log(self):
        # V2.5 - Show branches via pinger --branches
        win = ctk.CTkToplevel(self)
        win.title("Branches Log V2.5 - Latest arena")
        win.geometry("700x500")
        txt = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Courier", size=11), fg_color=COLORS["card"])
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("0.0", "Fetching branches via GitHub API /branches ...\n")

        def run():
            import subprocess
            try:
                root = Path(__file__).parent.parent.parent
                # Run update_checker directly to get branches
                result = subprocess.run([sys.executable, str(root / "tools" / "pinger.py"), "--branches", "--interval", "1"], capture_output=True, text=True, timeout=30, cwd=str(root))
                out = result.stdout + "\n" + result.stderr
                self.after(0, lambda: txt.insert("end", out))
            except Exception as e:
                self.after(0, lambda: txt.insert("end", f"Error: {e}"))

        threading.Thread(target=run, daemon=True).start()

    # ===== PRESETS LOGIC =====
    def _build_presets_list(self, presets_list):
        for w in self.presets_scroll.winfo_children():
            w.destroy()

        # Group by category
        cats = {}
        for p in presets_list:
            cats.setdefault(p.category, []).append(p)

        for cat, plist in cats.items():
            header = ctk.CTkFrame(self.presets_scroll, fg_color="transparent")
            header.pack(fill="x", padx=5, pady=(12,4))
            ctk.CTkLabel(header, text=cat.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["neon"]).pack(side="left")
            ctk.CTkLabel(header, text=f"{len(plist)} presets", font=ctk.CTkFont(size=10), text_color=COLORS["text_dim"]).pack(side="left", padx=10)

            for preset in plist:
                row = ctk.CTkFrame(self.presets_scroll, fg_color=COLORS["card2"], corner_radius=10, border_width=1, border_color=COLORS["border"])
                row.pack(fill="x", padx=5, pady=4)
                row.grid_columnconfigure(1, weight=1)

                # Info
                info_col = ctk.CTkFrame(row, fg_color="transparent")
                info_col.grid(row=0, column=0, padx=12, pady=8, sticky="w")

                ctk.CTkLabel(info_col, text=preset.name, font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w")
                ctk.CTkLabel(info_col, text=f"{preset.width}x{preset.height} • {preset.description}", font=ctk.CTkFont(size=10), text_color=COLORS["text_dim"]).pack(anchor="w")

                # Apply button
                ctk.CTkButton(row, text=f"Apply {preset.width}x{preset.height}", width=140, height=32, fg_color=COLORS["neon"], text_color="#000", font=ctk.CTkFont(weight="bold", size=11), command=lambda p=preset: self._apply_preset(p)).grid(row=0, column=1, padx=12, pady=8, sticky="e")

    def _filter_presets(self, cat):
        if cat == "all":
            self._build_presets_list(PRESETS)
        else:
            filtered = get_presets_by_category(cat)
            self._build_presets_list(filtered)

    def _apply_preset(self, preset):
        # Apply to Single tab resize entries
        if preset.width > 0 and preset.height > 0:
            self.width_entry.delete(0, 'end')
            self.width_entry.insert(0, str(preset.width))
            self.height_entry.delete(0, 'end')
            self.height_entry.insert(0, str(preset.height))
            self.keep_aspect.deselect()  # Use preset size

            # Switch to Single tab
            self._switch_page("Single")
            self.status_label.configure(text=f"Applied preset: {preset.name} {preset.width}x{preset.height} • {preset.description}")
            messagebox.showinfo("Preset Applied", f"{preset.name}\n{preset.width}x{preset.height}\n{preset.description}\n\nNow select image and convert!")
        else:
            # AI upscale presets
            if "upscale" in preset.id:
                scale = 2 if "2x" in preset.id else 4
                self.ai_up_scale_var.set(f"{scale}x")
                self._switch_page("AI")
                self.status_label.configure(text=f"AI Upscale preset {scale}x selected - go to AI tab")
                messagebox.showinfo("AI Preset", f"Upscale {scale}x selected. Go to AI tab and select image.")

    # ===== AI TOOLS LOGIC =====
    def _browse_ai_bg_input(self):
        path = filedialog.askopenfilename(title="Select Image for BG Removal", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")])
        if path:
            self.ai_bg_input_var.set(path)
            self.ai_bg_output_var.set(str(Path(path).parent / f"{Path(path).stem}_no_bg.png"))
            self.ai_bg_status.configure(text=f"Selected {Path(path).name}")

    def _browse_ai_up_input(self):
        path = filedialog.askopenfilename(title="Select Image for Upscale", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")])
        if path:
            self.ai_up_input_var.set(path)
            self.ai_up_output_var.set(str(Path(path).parent / f"{Path(path).stem}_upscaled.png"))
            self.ai_up_status.configure(text=f"Selected {Path(path).name}")

    def _run_bg_remover(self):
        input_path = self.ai_bg_input_var.get()
        if "No file" in input_path or not os.path.exists(input_path):
            messagebox.showwarning("No file", "Select input image first")
            return

        output_path = self.ai_bg_output_var.get()
        if "Will save" in output_path:
            output_path = str(Path(input_path).parent / f"{Path(input_path).stem}_no_bg.png")

        self.ai_bg_status.configure(text="Removing background... RHHH")

        def do():
            try:
                success, msg = remove_background(input_path, output_path)
                def done():
                    if success:
                        self.ai_bg_status.configure(text=f"✅ {msg}", text_color=COLORS["neon"])
                        self.status_label.configure(text=f"BG removed: {output_path}")
                        # Load in viewer
                        info = self.engine.get_image_info(output_path)
                        self.single_viewer.load_converted(output_path, info)
                        self._switch_page("Single")
                        messagebox.showinfo("BG Removed", f"{msg}\n\nSaved to: {output_path}")
                    else:
                        self.ai_bg_status.configure(text=f"❌ {msg}", text_color=COLORS["red"])
                        messagebox.showerror("Failed", msg)
                self.after(0, done)
            except Exception as e:
                self.after(0, lambda: self.ai_bg_status.configure(text=f"Error: {e}", text_color=COLORS["red"]))

        threading.Thread(target=do, daemon=True).start()

    def _run_upscaler(self):
        input_path = self.ai_up_input_var.get()
        if "No file" in input_path or not os.path.exists(input_path):
            messagebox.showwarning("No file", "Select input image first")
            return

        output_path = self.ai_up_output_var.get()
        if "Will save" in output_path:
            output_path = str(Path(input_path).parent / f"{Path(input_path).stem}_upscaled.png")

        scale_str = self.ai_up_scale_var.get()
        scale = 4 if "4x" in scale_str else 2

        self.ai_up_status.configure(text=f"Upscaling {scale}x... RHHH")

        def do():
            try:
                success, msg = upscale_image(input_path, output_path, scale=scale)
                def done():
                    if success:
                        self.ai_up_status.configure(text=f"✅ {msg}", text_color=COLORS["neon"])
                        self.status_label.configure(text=f"Upscaled: {output_path}")
                        info = self.engine.get_image_info(output_path)
                        self.single_viewer.load_converted(output_path, info)
                        self._switch_page("Single")
                        messagebox.showinfo("Upscaled", f"{msg}\n\nSaved to: {output_path}")
                    else:
                        self.ai_up_status.configure(text=f"❌ {msg}", text_color=COLORS["red"])
                        messagebox.showerror("Failed", msg)
                self.after(0, done)
            except Exception as e:
                self.after(0, lambda: self.ai_up_status.configure(text=f"Error: {e}", text_color=COLORS["red"]))

        threading.Thread(target=do, daemon=True).start()

    def _run_enhancer(self):
        input_path = self.ai_up_input_var.get()
        if "No file" in input_path or not os.path.exists(input_path):
            messagebox.showwarning("No file", "Select input image first")
            return

        output_path = str(Path(input_path).parent / f"{Path(input_path).stem}_enhanced.png")
        self.ai_up_status.configure(text="Enhancing...")

        def do():
            try:
                from src.converter.upscaler import enhance_image
                success, msg = enhance_image(input_path, output_path, enhance_factor=1.5)
                def done():
                    if success:
                        self.ai_up_status.configure(text=f"✅ {msg}", text_color=COLORS["neon"])
                        info = self.engine.get_image_info(output_path)
                        self.single_viewer.load_converted(output_path, info)
                        messagebox.showinfo("Enhanced", f"{msg}\n{output_path}")
                    else:
                        self.ai_up_status.configure(text=f"❌ {msg}", text_color=COLORS["red"])
                self.after(0, done)
            except Exception as e:
                self.after(0, lambda: self.ai_up_status.configure(text=f"Error: {e}"))

        threading.Thread(target=do, daemon=True).start()

    # ===== 3D STUDIO LOGIC - PERSONALISED 3D MAKER =====
    def _browse_studio_photos(self):
        files = filedialog.askopenfilenames(title="Select Product Photos (any number, AI will know what to do)", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All", "*.*")])
        if files:
            self.studio_photos = list(files)
            self.studio_input_var.set(f"{len(files)} photos selected")
            self.studio_status.configure(text=f"Selected {len(files)} photos - click Analyze")
            try:
                toast_success(f"3D Studio: {len(files)} photos selected")
            except:
                pass
            self._refresh_studio_preview()

    def _browse_studio_folder(self):
        folder = filedialog.askdirectory(title="Select Folder with Product Photos")
        if folder:
            try:
                from src.converter.product_3d import Product3DStudio
                studio = Product3DStudio()
                photos = studio.batch_engine.discover_images(folder, recursive=False) if hasattr(studio, 'batch_engine') else []
                # Fallback: use batch_engine from self
                if not photos:
                    photos = self.batch_engine.discover_images(folder, recursive=False)
                self.studio_photos = photos
                self.studio_input_var.set(f"{len(photos)} photos from {Path(folder).name}")
                self.studio_status.configure(text=f"Folder: {len(photos)} photos")
                toast_success(f"3D Studio folder: {len(photos)} photos")
                self._refresh_studio_preview()
            except Exception as e:
                messagebox.showerror("Failed", str(e))

    def _refresh_studio_preview(self):
        for w in self.studio_scroll.winfo_children():
            w.destroy()
        
        if not hasattr(self, 'studio_photos') or not self.studio_photos:
            ctk.CTkLabel(self.studio_scroll, text="No photos - select product photos", text_color=COLORS["text_dim"]).pack(pady=20)
            return

        header = ctk.CTkFrame(self.studio_scroll, fg_color="transparent")
        header.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(header, text=f"{len(self.studio_photos)} photos - Mode: {self.studio_mode_var.get()} - AI will auto-detect", font=ctk.CTkFont(weight="bold"), text_color=COLORS["neon"]).pack(anchor="w")

        # Show thumbnails (first 12)
        thumb_frame = ctk.CTkFrame(self.studio_scroll, fg_color="transparent")
        thumb_frame.pack(fill="x", padx=5, pady=5)

        for i, p in enumerate(self.studio_photos[:12]):
            try:
                row = ctk.CTkFrame(thumb_frame, fg_color=COLORS["card2"], corner_radius=8)
                row.pack(fill="x", padx=5, pady=2)
                ctk.CTkLabel(row, text=f"{i+1}. {Path(p).name}", font=ctk.CTkFont(size=11), width=300, anchor="w").pack(side="left", padx=8, pady=4)
                ctk.CTkLabel(row, text=p, font=ctk.CTkFont(size=9), text_color=COLORS["text_dim"], anchor="w").pack(side="left", padx=5, fill="x", expand=True)
            except:
                pass

        if len(self.studio_photos) > 12:
            ctk.CTkLabel(self.studio_scroll, text=f"... and {len(self.studio_photos)-12} more", text_color=COLORS["text_dim"]).pack()

        # Show last result if exists
        if hasattr(self, 'studio_result') and self.studio_result:
            res = self.studio_result
            result_frame = ctk.CTkFrame(self.studio_scroll, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["neon"])
            result_frame.pack(fill="x", padx=10, pady=15)

            ctk.CTkLabel(result_frame, text=f"📦 Last Build: {res.mode} - {res.shape} - {len(res.photos)} photos", font=ctk.CTkFont(weight="bold"), text_color=COLORS["neon"]).pack(anchor="w", padx=16, pady=(12,4))
            ctk.CTkLabel(result_frame, text=f"🎯 {res.suggestion.reason} (confidence {res.suggestion.confidence*100:.0f}%)", font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"], wraplength=700, justify="left").pack(anchor="w", padx=16)
            ctk.CTkLabel(result_frame, text=f"📁 Output: {res.output_dir}", font=ctk.CTkFont(size=10), text_color=COLORS["text_dim"]).pack(anchor="w", padx=16, pady=(4,12))

            exports_frame = ctk.CTkFrame(result_frame, fg_color="transparent")
            exports_frame.pack(fill="x", padx=16, pady=8)

            for fmt, path in res.exports.items():
                if os.path.exists(path):
                    row = ctk.CTkFrame(exports_frame, fg_color=COLORS["card"], corner_radius=8)
                    row.pack(fill="x", pady=2)
                    ctk.CTkLabel(row, text=f"{fmt.upper()}: {Path(path).name}", font=ctk.CTkFont(size=11), text_color=COLORS["neon"] if fmt in ["glb","html","html_360"] else COLORS["text_dim"]).pack(side="left", padx=10, pady=6)
                    ctk.CTkButton(row, text="Open", width=60, height=24, fg_color=COLORS["card2"], command=lambda p=path: self._open_file(p) if not p.endswith('.html') else self._open_html(p)).pack(side="right", padx=5)

    def _analyze_studio(self):
        if not hasattr(self, 'studio_photos') or not self.studio_photos:
            messagebox.showwarning("No photos", "Select product photos first")
            return

        self.studio_status.configure(text="Analyzing with AI auto-detect...")

        def do():
            try:
                from src.converter.product_3d import Product3DStudio
                studio = Product3DStudio()
                photos, suggestion = studio.analyze_photos(self.studio_photos)

                def done():
                    self.studio_status.configure(text=f"AI: {suggestion.shape} - {suggestion.reason} ({suggestion.confidence*100:.0f}%)")
                    # Show suggestion
                    for w in self.studio_scroll.winfo_children():
                        w.destroy()

                    sug_frame = ctk.CTkFrame(self.studio_scroll, fg_color=COLORS["card2"], corner_radius=12, border_width=1, border_color=COLORS["neon"])
                    sug_frame.pack(fill="x", padx=10, pady=10)

                    ctk.CTkLabel(sug_frame, text=f"🤖 AI Suggestion: {suggestion.shape.upper()}", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["neon"]).pack(anchor="w", padx=16, pady=(12,4))
                    ctk.CTkLabel(sug_frame, text=f"Reason: {suggestion.reason}", font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"], wraplength=700, justify="left").pack(anchor="w", padx=16)
                    ctk.CTkLabel(sug_frame, text=f"Confidence: {suggestion.confidence*100:.0f}% - Dimensions: {suggestion.dimensions}", font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w", padx=16)
                    ctk.CTkLabel(sug_frame, text=f"Best mapping: {list(suggestion.best_photos.keys())}", font=ctk.CTkFont(size=10), text_color=COLORS["text_dim"]).pack(anchor="w", padx=16, pady=(4,12))

                    # Show photos with views
                    for p in photos:
                        row = ctk.CTkFrame(self.studio_scroll, fg_color=COLORS["card2"] if "front" in p.view else COLORS["card"], corner_radius=6)
                        row.pack(fill="x", padx=5, pady=1)
                        angle_str = f"{p.angle:.0f}°" if p.angle is not None else "?"
                        ctk.CTkLabel(row, text=f"{angle_str} - {p.view} - {Path(p.path).name}", font=ctk.CTkFont(size=11)).pack(side="left", padx=8, pady=4)

                    toast_success(f"AI analyzed: {suggestion.shape} - {suggestion.confidence*100:.0f}%")

                self.after(0, done)
            except Exception as e:
                self.after(0, lambda: self.studio_status.configure(text=f"Analyze failed: {e}"))

        threading.Thread(target=do, daemon=True).start()

    def _build_3d_stage(self):
        if not hasattr(self, 'studio_photos') or not self.studio_photos:
            messagebox.showwarning("No photos", "Select product photos first")
            return

        mode = self.studio_mode_var.get()
        self.studio_status.configure(text=f"Building 3D stage ({mode})... RHHH")

        def do():
            try:
                from src.converter.product_3d import Product3DStudio
                studio = Product3DStudio()
                result = studio.create_studio(self.studio_photos, mode=mode)
                self.studio_result = result

                def done():
                    self.studio_status.configure(text=f"Built {result.mode} - {len(result.exports)} exports")
                    self._refresh_studio_preview()
                    toast_success(f"3D Studio built: {result.mode} - {len(result.exports)} exports - {result.output_dir}")
                    messagebox.showinfo("3D Studio Built", f"Mode: {result.mode}\nShape: {result.shape}\nPhotos: {len(result.photos)}\n\nExports:\n" + "\n".join([f"{k}: {Path(v).name}" for k,v in result.exports.items() if os.path.exists(v)]) + f"\n\nOutput: {result.output_dir}")

                self.after(0, done)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.after(0, lambda: self.studio_status.configure(text=f"Build failed: {e}"))

        threading.Thread(target=do, daemon=True).start()

    def _open_studio_viewer(self):
        if not hasattr(self, 'studio_result') or not self.studio_result:
            messagebox.showwarning("No build", "Build 3D stage first")
            return

        html = self.studio_result.exports.get("html")
        if html and os.path.exists(html):
            self._open_html(html)
        else:
            messagebox.showwarning("No viewer", "HTML viewer not found - check output folder")

    def _open_360_viewer(self):
        if not hasattr(self, 'studio_result') or not self.studio_result:
            messagebox.showwarning("No build", "Build 3D stage first - need 8+ photos for 360")
            return

        html = self.studio_result.exports.get("html_360")
        if html and os.path.exists(html):
            self._open_html(html)
        else:
            # Try to find any 360 viewer
            out = Path(self.studio_result.output_dir)
            candidates = list(out.glob("viewer_360.html")) + list(out.glob("**/viewer_360.html"))
            if candidates:
                self._open_html(str(candidates[0]))
            else:
                messagebox.showwarning("No 360", "360 viewer needs 8+ photos - you have %d" % len(self.studio_result.photos))

    def _open_html(self, path):
        import webbrowser
        try:
            # For local HTML, use file://
            webbrowser.open(f"file://{Path(path).absolute()}")
            toast_success(f"Opened {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Failed", str(e))

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Settings - Image Switcher V2")
        win.geometry("600x500")
        win.transient(self)
        ctk.CTkLabel(win, text="Settings & About V2 • RHHHAAAAA Edition", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["neon"]).pack(pady=10)
        txt = ctk.CTkTextbox(win, width=560, height=400, fg_color=COLORS["card"], font=ctk.CTkFont(family="Courier", size=11))
        txt.pack(padx=10, pady=10)
        ver = get_local_version()
        txt.insert("0.0", f"""Image Switcher V2 - RHHHAAAAA Edition v{ver}

NEW IN V2:
✓ Glassmorphism UI with neon #4ade80 accents
✓ Batch Mode - convert folders, keep structure, multithreaded
✓ Explorer Context Menu - right-click image/folder
✓ Main Branch Pinger - tools/pinger.py + .ps1 + in-app checker
✓ New 3D Icon + Landing Page
✓ V2 Mockup in mockups/ui-redesign-v2.png

Features (V1):
- 50+ formats: PNG JPEG WEBP BMP GIF TIFF ICO AVIF HEIF HEIC SVG PDF etc
- Searchable dropdown with acceptance gate (green/yellow/red)
- Dual viewer OLD vs NEW with checkerboard, zoom/pan, metadata
- SVG raster/vector master
- Quality slider, background picker, resize

Batch Mode:
- Select folder or multiple files
- Choose target format + quality
- Recursive, keep structure, overwrite toggle
- Progress bar + stop button
- Output: converted/ subfolder or custom

Pinger:
- python tools/pinger.py (Python)
- powershell -File tools/pinger.ps1 (PowerShell)
- Watch mode: --watch --interval 60
- In-app: header banner + Tools tab

Context Menu:
- Install with: install.ps1 -ContextMenu -FileAssociations
- Adds: Right-click image -> Convert with Image Switcher
- Adds: Right-click folder -> Convert images in folder

Current file: {self.current_file or 'None'}
Converted: {self.converted_file or 'None'}
Batch items: {len(self.batch_items)}

Build:
python build_exe.py --onefile
powershell -File install.ps1 -ContextMenu -FileAssociations -Force

GitHub: https://github.com/muhummadzarrar09-sudo/python-image-switcher
""")
        txt.configure(state="disabled")
