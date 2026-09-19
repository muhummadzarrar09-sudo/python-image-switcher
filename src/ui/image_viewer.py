"""
Universal Image Viewer Panel V2.2 - Glassmorphism + Neon + Comparison Slider
Local & Offline UX improvements
"""

import os
import io
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Optional

COLORS = {
    "bg": "#0a0a0a",
    "card": "#1a1a1a",
    "card2": "#252525",
    "border": "#2a2a2a",
    "neon": "#4ade80",
    "text_dim": "#888888",
    "red": "#f87171",
}

class ImageViewerPanel(ctk.CTkFrame):
    def __init__(self, master, title: str = "Viewer", width: int = 400, height: int = 400, **kwargs):
        super().__init__(master, **kwargs)
        self.title = title
        self.configure(fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], corner_radius=12)
        self.image_path: Optional[str] = None
        self.pil_image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.zoom = 1.0
        self.original_size = (0,0)
        self.comparison_ratio = 0.5  # For comparison slider
        self.comparison_mode = False
        self.other_image = None  # For comparison

        # Header - neon accent
        header = ctk.CTkFrame(self, fg_color=COLORS["card2"], height=40, corner_radius=10)
        header.pack(fill="x", padx=2, pady=2)
        header.pack_propagate(False)

        left_h = ctk.CTkFrame(header, fg_color="transparent")
        left_h.pack(side="left", padx=12, pady=5, fill="y")

        dot_color = COLORS["neon"] if "Original" in title or "OLD" in title else "#60a5fa" if "NEW" in title or "Converted" in title else COLORS["neon"]
        self.dot = ctk.CTkLabel(left_h, text="●", font=ctk.CTkFont(size=12), text_color=dot_color)
        self.dot.pack(side="left", padx=(0,6))

        self.title_label = ctk.CTkLabel(left_h, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color="#e5e5e5")
        self.title_label.pack(side="left")

        self.info_label = ctk.CTkLabel(header, text="No image", font=ctk.CTkFont(size=10), text_color=COLORS["text_dim"])
        self.info_label.pack(side="right", padx=12)

        # Canvas area
        self.canvas_frame = ctk.CTkFrame(self, fg_color="#111", corner_radius=8)
        self.canvas_frame.pack(fill="both", expand=True, padx=4, pady=2)

        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg="#0f0f0f", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)

        # Controls - glass
        ctrl = ctk.CTkFrame(self, fg_color=COLORS["card2"], height=44, corner_radius=10)
        ctrl.pack(fill="x", padx=2, pady=2)
        ctrl.pack_propagate(False)

        self.zoom_out_btn = ctk.CTkButton(ctrl, text="−", width=32, height=28, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], hover_color="#333", command=lambda: self.set_zoom(self.zoom/1.2))
        self.zoom_out_btn.pack(side="left", padx=4, pady=6)

        self.zoom_label = ctk.CTkLabel(ctrl, text="100%", width=50, font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["neon"])
        self.zoom_label.pack(side="left", padx=2)

        self.zoom_in_btn = ctk.CTkButton(ctrl, text="+", width=32, height=28, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], hover_color="#333", command=lambda: self.set_zoom(self.zoom*1.2))
        self.zoom_in_btn.pack(side="left", padx=4, pady=6)

        self.fit_btn = ctk.CTkButton(ctrl, text="Fit", width=50, height=28, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], hover_color="#333", command=self.fit_to_view)
        self.fit_btn.pack(side="left", padx=8)

        self.btn_100 = ctk.CTkButton(ctrl, text="100%", width=50, height=28, fg_color=COLORS["card"], border_width=1, border_color=COLORS["border"], hover_color="#333", command=lambda: self.set_zoom(1.0))
        self.btn_100.pack(side="left", padx=2)

        # Comparison toggle (only for dual viewer, but we add here for flexibility)
        self.compare_btn = ctk.CTkButton(ctrl, text="◫ Compare", width=80, height=28, fg_color="transparent", border_width=1, border_color=COLORS["border"], hover_color="#333", command=self.toggle_comparison)
        self.compare_btn.pack(side="right", padx=4, pady=6)

        # Metadata label
        self.meta_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=10), text_color="#aaa", anchor="w", justify="left")
        self.meta_label.pack(fill="x", padx=10, pady=6)

        # Bind mouse wheel zoom
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)
        self.canvas.bind("<Button-5>", self.on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self.on_pan_start)
        self.canvas.bind("<B1-Motion>", self.on_pan_move)
        self._pan_start = None
        self._canvas_offset = [0,0]

        self.bind("<Configure>", lambda e: self.fit_to_view() if self.pil_image else None)

    def load_image(self, path: str, info: dict = None):
        self.image_path = path
        self._canvas_offset = [0,0]

        if not os.path.exists(path):
            self.show_error(f"File not found: {path}")
            return

        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".svg", ".svgz"):
                try:
                    import cairosvg
                    png_bytes = cairosvg.svg2png(url=path, scale=2.0)
                    self.pil_image = Image.open(io.BytesIO(png_bytes))
                except Exception as e:
                    self.pil_image = Image.new("RGBA", (400,400), (40,40,40,255))
                    print(f"SVG render error: {e}")
            elif ext == ".pdf":
                try:
                    from src.converter.svg_handler import render_pdf_first_page
                    import tempfile
                    tmp = tempfile.mktemp(suffix=".png")
                    render_pdf_first_page(path, tmp, scale=2)
                    self.pil_image = Image.open(tmp)
                except Exception as e:
                    self.pil_image = Image.new("RGBA", (400,400), (40,40,40,255))
                    print(f"PDF render error: {e}")
            else:
                self.pil_image = Image.open(path)
                if getattr(self.pil_image, "is_animated", False):
                    self.pil_image.seek(0)
                self.pil_image = self.pil_image.copy()

            self.original_size = self.pil_image.size
            self.fit_to_view()

            if info:
                size_kb = info.get("size_bytes",0)/1024
                meta = f"{info.get('width')}x{info.get('height')} • {info.get('format')} • {info.get('mode')} • {size_kb:.1f} KB"
                if info.get("has_alpha"):
                    meta += " • Alpha"
                if info.get("is_animated"):
                    meta += f" • Animated ({info.get('frames')} frames)"
                self.info_label.configure(text=meta)
                detailed = f"{os.path.basename(path)} • {info.get('width')}x{info.get('height')} | {info.get('mode')} | Alpha: {info.get('has_alpha')} | Frames: {info.get('frames')}"
                self.meta_label.configure(text=detailed)
            else:
                self.info_label.configure(text=f"{self.pil_image.size[0]}x{self.pil_image.size[1]} • {self.pil_image.mode}")
                self.meta_label.configure(text=f"{os.path.basename(path)}")

        except Exception as e:
            self.show_error(str(e))

    def show_error(self, msg: str):
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width()//2 or 200, self.canvas.winfo_height()//2 or 200,
                                text=f"⚠\n{msg}", fill=COLORS["red"], font=("Arial", 12), justify="center", width=300)
        self.info_label.configure(text="Error")
        self.meta_label.configure(text=msg)

    def show_placeholder(self, text: str = "No image"):
        # V3.2 - Product empty state: glass card + neon accent + premium typography
        self.pil_image = None
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 380
        h = self.canvas.winfo_height() or 380
        card_w = min(w-60, 340)
        card_h = 220
        cx, cy = w//2, h//2 - 10
        self.canvas.create_rectangle(cx-card_w//2+4, cy-card_h//2+4, cx+card_w//2+4, cy+card_h//2+4, fill="#000000", outline="", stipple="gray50")
        self.canvas.create_rectangle(cx-card_w//2, cy-card_h//2, cx+card_w//2, cy+card_h//2, fill="#1a1a1d", outline="#2a2a2e", width=1)
        icon_text = "🖼️"
        if "📂" in text or "Drop" in text:
            icon_text = "📂"
        elif "✨" in text or "Converted" in text:
            icon_text = "✨"
        elif "OLD" in text:
            icon_text = "◫"
        elif "NEW" in text:
            icon_text = "◩"
        self.canvas.create_text(cx, cy-50, text=icon_text, fill="#2a2a2a", font=("Segoe UI Emoji", 56))
        self.canvas.create_oval(cx-3, cy-90, cx+3, cy-84, fill="#4ade80", outline="")
        lines = text.split("\n")
        title = lines[0] if lines else text
        subtitle = "\n".join(lines[1:]) if len(lines)>1 else ""
        self.canvas.create_text(cx, cy+5, text=title, fill="#f5f5f7", font=("Segoe UI", 15, "bold"), justify="center", width=card_w-30)
        if subtitle:
            short_sub = subtitle[:90]
            self.canvas.create_text(cx, cy+35, text=short_sub, fill="#4ade80", font=("Segoe UI", 11, "bold"), justify="center", width=card_w-30)
        hint = "Drop image • Ctrl+O • F11 • 100% offline"
        self.canvas.create_rectangle(cx-110, h-45, cx+110, h-20, fill="#161618", outline="#232326", width=1)
        self.canvas.create_text(cx, h-32, text=hint, fill="#666", font=("Segoe UI", 9, "bold"), justify="center")
        self.info_label.configure(text=title[:50], font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"))
        self.meta_label.configure(text=subtitle[:80], font=ctk.CTkFont(size=11, family="Segoe UI"))

    def set_zoom(self, zoom: float):
        self.zoom = max(0.1, min(8.0, zoom))
        self.zoom_label.configure(text=f"{int(self.zoom*100)}%")
        self.render()

    def fit_to_view(self):
        if not self.pil_image:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            cw, ch = 380, 380
        iw, ih = self.pil_image.size
        if iw==0 or ih==0:
            return
        scale = min(cw/iw, ch/ih) * 0.85
        self.zoom = scale
        self._canvas_offset = [0,0]
        self.zoom_label.configure(text=f"{int(self.zoom*100)}%")
        self.render()

    def render(self):
        if not self.pil_image:
            return
        self.canvas.delete("all")
        self.draw_checkerboard()

        iw, ih = self.pil_image.size
        nw = int(iw * self.zoom)
        nh = int(ih * self.zoom)
        if nw<=0 or nh<=0:
            return
        try:
            resized = self.pil_image.resize((nw, nh), Image.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(resized)
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            x = cw//2 + self._canvas_offset[0]
            y = ch//2 + self._canvas_offset[1]

            if self.comparison_mode and self.other_image:
                # Comparison mode: show other image clipped
                try:
                    other_resized = self.other_image.resize((nw, nh), Image.LANCZOS)
                    self.tk_other = ImageTk.PhotoImage(other_resized)
                    # Draw other image first (full)
                    self.canvas.create_image(x, y, image=self.tk_other, anchor="center")
                    # Then draw this image clipped to ratio
                    clip_w = int(nw * self.comparison_ratio)
                    if clip_w > 0:
                        # Create clipped version
                        cropped = resized.crop((0, 0, clip_w, nh))
                        self.tk_clipped = ImageTk.PhotoImage(cropped)
                        clip_x = x - nw//2 + clip_w//2
                        self.canvas.create_image(clip_x, y, image=self.tk_clipped, anchor="center")
                        # Divider line
                        div_x = x - nw//2 + clip_w
                        self.canvas.create_line(div_x, y - nh//2, div_x, y + nh//2, fill=COLORS["neon"], width=2)
                        # Handle
                        self.canvas.create_oval(div_x-8, y-20, div_x+8, y+20, fill=COLORS["neon"], outline="")
                        self.canvas.create_text(div_x, y, text="◂▸", fill="#000", font=("Arial", 8))
                except Exception as e:
                    print(f"Comparison render error: {e}")
                    self.canvas.create_image(x, y, image=self.tk_image, anchor="center")
            else:
                self.canvas.create_image(x, y, image=self.tk_image, anchor="center")
        except Exception as e:
            print(f"Render error: {e}")

    def draw_checkerboard(self):
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw<10:
            cw=400
        if ch<10:
            ch=400
        size = 16
        colors = ["#1a1a1a", "#222222"]
        has_alpha = self.pil_image and self.pil_image.mode in ("RGBA","LA","PA")
        if not has_alpha:
            self.canvas.configure(bg="#0f0f0f")
            return
        for y in range(0, ch, size):
            for x in range(0, cw, size):
                col = colors[(x//size + y//size) % 2]
                self.canvas.create_rectangle(x, y, x+size, y+size, fill=col, outline="")

    def on_mousewheel(self, event):
        if event.num == 5 or event.delta < 0:
            self.set_zoom(self.zoom/1.1)
        else:
            self.set_zoom(self.zoom*1.1)

    def on_pan_start(self, event):
        # If in comparison mode and near divider, start dragging divider
        if self.comparison_mode:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            if self.pil_image:
                iw, ih = self.pil_image.size
                nw = int(iw * self.zoom)
                x = cw//2 + self._canvas_offset[0]
                div_x = x - nw//2 + int(nw * self.comparison_ratio)
                if abs(event.x - div_x) < 15:
                    self._dragging_divider = True
                    return
        self._pan_start = (event.x, event.y)
        self._dragging_divider = False

    def on_pan_move(self, event):
        if getattr(self, '_dragging_divider', False) and self.comparison_mode:
            cw = self.canvas.winfo_width()
            if self.pil_image:
                iw, _ = self.pil_image.size
                nw = int(iw * self.zoom)
                x = cw//2 + self._canvas_offset[0]
                left = x - nw//2
                ratio = (event.x - left) / nw if nw > 0 else 0.5
                self.comparison_ratio = max(0.0, min(1.0, ratio))
                self.render()
                return

        if self._pan_start:
            dx = event.x - self._pan_start[0]
            dy = event.y - self._pan_start[1]
            self._canvas_offset[0] += dx
            self._canvas_offset[1] += dy
            self._pan_start = (event.x, event.y)
            self.render()

    def toggle_comparison(self):
        self.comparison_mode = not self.comparison_mode
        if self.comparison_mode:
            self.compare_btn.configure(fg_color=COLORS["neon"], text_color="#000", text="◫ Comparing")
        else:
            self.compare_btn.configure(fg_color="transparent", text_color="#e5e5e5", text="◫ Compare")
        self.render()

    def set_comparison_images(self, img1, img2):
        """Set images for comparison mode"""
        self.pil_image = img1
        self.other_image = img2
        self.comparison_mode = True
        self.compare_btn.configure(fg_color=COLORS["neon"], text_color="#000", text="◫ Comparing")
        self.fit_to_view()

class DualViewer(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure((0,1), weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self.left = ImageViewerPanel(self, title="OLD / Original")
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0,6), pady=2)

        self.right = ImageViewerPanel(self, title="NEW / Converted")
        self.right.grid(row=0, column=1, sticky="nsew", padx=(6,0), pady=2)

        # Comparison slider for dual viewer
        self.compare_frame = ctk.CTkFrame(self, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#2a2a2a")
        self.compare_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=(6,2))
        self.compare_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.compare_frame, text="◫ Comparison Slider:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#888").grid(row=0, column=0, padx=12, pady=8, sticky="w")

        self.compare_slider = ctk.CTkSlider(self.compare_frame, from_=0, to=1, progress_color=COLORS["neon"], button_color=COLORS["neon"], command=self.on_compare_slide)
        self.compare_slider.set(0.5)
        self.compare_slider.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

        self.compare_label = ctk.CTkLabel(self.compare_frame, text="50% OLD / 50% NEW", font=ctk.CTkFont(size=10), text_color=COLORS["neon"])
        self.compare_label.grid(row=0, column=2, padx=12, pady=8)

        self.compare_mode = False

    def on_compare_slide(self, value):
        ratio = float(value)
        self.compare_label.configure(text=f"{int(ratio*100)}% OLD / {int((1-ratio)*100)}% NEW")
        # Update both viewers comparison ratio
        self.left.comparison_ratio = ratio
        self.right.comparison_ratio = ratio
        if self.left.pil_image and self.right.pil_image:
            # Enable comparison mode in left viewer showing right as other
            if not self.left.comparison_mode:
                self.left.comparison_mode = True
                self.left.other_image = self.right.pil_image
                self.left.compare_btn.configure(fg_color=COLORS["neon"], text_color="#000", text="◫ Comparing")
            self.left.render()

    def load_original(self, path: str, info: dict = None):
        self.left.load_image(path, info)

    def load_converted(self, path: str, info: dict = None):
        self.right.load_image(path, info)
        # Update comparison other image
        if self.left.pil_image:
            self.left.other_image = self.right.pil_image

    def clear(self):
        # V3.2 - Product empty states - glassmorphism + premium copy
        self.left.show_placeholder("📂 Drop your image\nDrag & drop • Ctrl+O to browse • F11 fullscreen • 100% local & offline")
        self.right.show_placeholder("✨ Awaiting conversion\nPick format → CONVERT → AI enhance 🤖 → 3D Studio 📦 • Pro Dark Studio")
        self.compare_slider.set(0.5)
        self.compare_label.configure(text="50% OLD / 50% NEW", font=ctk.CTkFont(size=12, weight="bold", family="Segoe UI"))
