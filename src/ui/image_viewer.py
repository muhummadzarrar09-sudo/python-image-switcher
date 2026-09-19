"""
Universal Image Viewer Panel - can view any file type, old vs new
"""
import os
import io
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Optional

class ImageViewerPanel(ctk.CTkFrame):
    def __init__(self, master, title: str = "Viewer", width: int = 400, height: int = 400, **kwargs):
        super().__init__(master, **kwargs)
        self.title = title
        self.configure(fg_color="#1a1a1a", border_width=1, border_color="#333")
        self.image_path: Optional[str] = None
        self.pil_image: Optional[Image.Image] = None
        self.tk_image: Optional[ImageTk.PhotoImage] = None
        self.zoom = 1.0
        self.original_size = (0,0)

        # Header
        header = ctk.CTkFrame(self, fg_color="#222", height=36)
        header.pack(fill="x", padx=1, pady=1)
        header.pack_propagate(False)

        self.title_label = ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=12, weight="bold"))
        self.title_label.pack(side="left", padx=10)

        self.info_label = ctk.CTkLabel(header, text="No image", font=ctk.CTkFont(size=10), text_color="#888")
        self.info_label.pack(side="right", padx=10)

        # Canvas area with checkerboard background
        self.canvas_frame = ctk.CTkFrame(self, fg_color="#111")
        self.canvas_frame.pack(fill="both", expand=True, padx=2, pady=2)

        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg="#111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Controls
        ctrl = ctk.CTkFrame(self, fg_color="#222", height=40)
        ctrl.pack(fill="x", padx=1, pady=1)
        ctrl.pack_propagate(False)

        self.zoom_out_btn = ctk.CTkButton(ctrl, text="−", width=30, height=28, command=lambda: self.set_zoom(self.zoom/1.2))
        self.zoom_out_btn.pack(side="left", padx=4, pady=4)

        self.zoom_label = ctk.CTkLabel(ctrl, text="100%", width=50, font=ctk.CTkFont(size=11))
        self.zoom_label.pack(side="left", padx=2)

        self.zoom_in_btn = ctk.CTkButton(ctrl, text="+", width=30, height=28, command=lambda: self.set_zoom(self.zoom*1.2))
        self.zoom_in_btn.pack(side="left", padx=4, pady=4)

        self.fit_btn = ctk.CTkButton(ctrl, text="Fit", width=50, height=28, fg_color="#333", command=self.fit_to_view)
        self.fit_btn.pack(side="left", padx=8)

        self.btn_100 = ctk.CTkButton(ctrl, text="100%", width=50, height=28, fg_color="#333", command=lambda: self.set_zoom(1.0))
        self.btn_100.pack(side="left", padx=2)

        # Metadata label
        self.meta_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=10), text_color="#aaa", anchor="w", justify="left")
        self.meta_label.pack(fill="x", padx=8, pady=4)

        # Bind mouse wheel zoom
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel)  # Linux
        self.canvas.bind("<Button-5>", self.on_mousewheel)
        # Pan drag
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
            # Try to load via our engine handling for vectors
            ext = os.path.splitext(path)[1].lower()
            if ext in (".svg", ".svgz"):
                # Render SVG to PNG for display
                try:
                    import cairosvg
                    png_bytes = cairosvg.svg2png(url=path, scale=2.0)
                    self.pil_image = Image.open(io.BytesIO(png_bytes))
                except Exception as e:
                    # Fallback placeholder
                    self.pil_image = Image.new("RGBA", (400,400), (40,40,40,255))
                    # Draw error text? just keep
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
                # For animated, take first frame
                if getattr(self.pil_image, "is_animated", False):
                    self.pil_image.seek(0)
                self.pil_image = self.pil_image.copy()  # detach from file

            self.original_size = self.pil_image.size
            self.fit_to_view()

            # Update info
            if info:
                size_kb = info.get("size_bytes",0)/1024
                meta = f"{info.get('width')}x{info.get('height')} • {info.get('format')} • {info.get('mode')} • {size_kb:.1f} KB"
                if info.get("has_alpha"):
                    meta += " • Alpha"
                if info.get("is_animated"):
                    meta += f" • Animated ({info.get('frames')} frames)"
                self.info_label.configure(text=meta)
                # Detailed meta label
                detailed = f"Path: {os.path.basename(path)}\nSize: {info.get('width')}x{info.get('height')} | Mode: {info.get('mode')} | Format: {info.get('format')} | Alpha: {info.get('has_alpha')} | Frames: {info.get('frames')}"
                self.meta_label.configure(text=detailed)
            else:
                self.info_label.configure(text=f"{self.pil_image.size[0]}x{self.pil_image.size[1]} • {self.pil_image.mode}")
                self.meta_label.configure(text=f"{os.path.basename(path)}")

        except Exception as e:
            self.show_error(str(e))

    def show_error(self, msg: str):
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width()//2 or 200, self.canvas.winfo_height()//2 or 200,
                                text=f"⚠\n{msg}", fill="#f87171", font=("Arial", 12), justify="center", width=300)
        self.info_label.configure(text="Error")
        self.meta_label.configure(text=msg)

    def show_placeholder(self, text: str = "No image"):
        self.pil_image = None
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width()//2 or 200, self.canvas.winfo_height()//2 or 200,
                                text=text, fill="#666", font=("Arial", 14))
        self.info_label.configure(text=text)
        self.meta_label.configure(text="")

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
        scale = min(cw/iw, ch/ih) * 0.9
        self.zoom = scale
        self._canvas_offset = [0,0]
        self.zoom_label.configure(text=f"{int(self.zoom*100)}%")
        self.render()

    def render(self):
        if not self.pil_image:
            return
        self.canvas.delete("all")
        # Checkerboard for transparency
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
            self.canvas.create_image(x, y, image=self.tk_image, anchor="center")
        except Exception as e:
            print(f"Render error: {e}")

    def draw_checkerboard(self):
        # Simple checkerboard background for transparency visualization
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw<10:
            cw=400
        if ch<10:
            ch=400
        size = 16
        colors = ["#222", "#2a2a2a"]
        # draw only if image has alpha
        has_alpha = self.pil_image and self.pil_image.mode in ("RGBA","LA","PA")
        if not has_alpha:
            self.canvas.configure(bg="#111")
            return
        for y in range(0, ch, size):
            for x in range(0, cw, size):
                col = colors[(x//size + y//size) % 2]
                self.canvas.create_rectangle(x, y, x+size, y+size, fill=col, outline="")

    def on_mousewheel(self, event):
        # Zoom with wheel
        if event.num == 5 or event.delta < 0:
            self.set_zoom(self.zoom/1.1)
        else:
            self.set_zoom(self.zoom*1.1)

    def on_pan_start(self, event):
        self._pan_start = (event.x, event.y)

    def on_pan_move(self, event):
        if self._pan_start:
            dx = event.x - self._pan_start[0]
            dy = event.y - self._pan_start[1]
            self._canvas_offset[0] += dx
            self._canvas_offset[1] += dy
            self._pan_start = (event.x, event.y)
            self.render()

class DualViewer(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure((0,1), weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.left = ImageViewerPanel(self, title="OLD / Original")
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0,4), pady=2)

        self.right = ImageViewerPanel(self, title="NEW / Converted")
        self.right.grid(row=0, column=1, sticky="nsew", padx=(4,0), pady=2)

        # Divider slider for comparison (optional)
        # Could add a slider that wipes

    def load_original(self, path: str, info: dict = None):
        self.left.load_image(path, info)

    def load_converted(self, path: str, info: dict = None):
        self.right.load_image(path, info)

    def clear(self):
        self.left.show_placeholder("Drop image or Browse")
        self.right.show_placeholder("Converted image will appear here")
