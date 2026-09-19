"""
Main Window - Full App UI with dual viewer, searchable dropdowns, acceptance gate
"""
import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
import tempfile
from PIL import Image

from src.converter.formats import get_format_by_id, get_format_by_ext, FORMATS, all_formats
from src.converter.validator import validate_conversion, get_compatible_targets
from src.converter.engine import ConversionEngine
from src.ui.searchable_combobox import SearchableFormatDropdown
from src.ui.image_viewer import DualViewer

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ImageSwitcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Python Image Switcher - Universal Converter")
        self.geometry("1300x850")
        self.minsize(1100, 700)

        self.engine = ConversionEngine()
        self.current_file: str | None = None
        self.current_info: dict | None = None
        self.converted_file: str | None = None
        self.last_target_id: str | None = None

        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ===== HEADER =====
        header = ctk.CTkFrame(self, height=60, fg_color="#1e1e1e", corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkLabel(header, text="🖼️ IMAGE SWITCHER", font=ctk.CTkFont(size=20, weight="bold"), text_color="#4ade80")
        logo.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        subtitle = ctk.CTkLabel(header, text="Convert ANY format to ANY format • SVG Raster/Vector • 50+ formats • Acceptance Gate", font=ctk.CTkFont(size=11), text_color="#888")
        subtitle.grid(row=0, column=1, padx=10, sticky="w")

        self.settings_btn = ctk.CTkButton(header, text="⚙️ Settings", width=100, height=32, fg_color="#333", command=self.open_settings)
        self.settings_btn.grid(row=0, column=2, padx=10)

        # ===== TOP CONTROLS: File drop + format selectors =====
        top = ctk.CTkFrame(self, fg_color="#252525", corner_radius=8)
        top.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        top.grid_columnconfigure(1, weight=1)

        # File select area
        file_frame = ctk.CTkFrame(top, fg_color="transparent")
        file_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        file_frame.grid_columnconfigure(1, weight=1)

        self.file_label = ctk.CTkLabel(file_frame, text="No file selected", font=ctk.CTkFont(size=12), anchor="w", text_color="#aaa")
        self.file_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4)

        browse_btn = ctk.CTkButton(file_frame, text="📁 Browse Image", width=140, command=self.browse_file)
        browse_btn.grid(row=0, column=2, padx=4)

        # Drag & Drop hint
        self.drop_label = ctk.CTkLabel(file_frame, text="Drag & Drop any image here (PNG, JPG, SVG, WEBP, HEIC, AVIF, TIFF, GIF, etc) - Viewer supports ANY file type", font=ctk.CTkFont(size=10), text_color="#666")
        self.drop_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=4, pady=2)

        # Format selectors row
        fmt_row = ctk.CTkFrame(top, fg_color="transparent")
        fmt_row.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0,10))
        fmt_row.grid_columnconfigure((0,2), weight=1)

        # Source format dropdown (auto-detected)
        self.source_dropdown = SearchableFormatDropdown(fmt_row, label_text="Source Format (auto-detected)", width=340, on_select=self.on_source_selected)
        self.source_dropdown.grid(row=0, column=0, padx=5, sticky="ew")

        arrow = ctk.CTkLabel(fmt_row, text="➡️", font=ctk.CTkFont(size=24))
        arrow.grid(row=0, column=1, padx=10)

        # Target format dropdown with gate
        self.target_dropdown = SearchableFormatDropdown(fmt_row, label_text="Target Format (searchable + gate)", width=340, on_select=self.on_target_selected)
        self.target_dropdown.grid(row=0, column=2, padx=5, sticky="ew")

        # Quality / Options row
        opts = ctk.CTkFrame(top, fg_color="transparent")
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        opts.grid_columnconfigure((0,1,2,3), weight=1)

        # Quality slider
        self.quality_label = ctk.CTkLabel(opts, text="Quality: 90", font=ctk.CTkFont(size=11))
        self.quality_label.grid(row=0, column=0, padx=5, sticky="w")
        self.quality_slider = ctk.CTkSlider(opts, from_=1, to=100, number_of_steps=99, command=self.on_quality_change)
        self.quality_slider.set(90)
        self.quality_slider.grid(row=0, column=1, padx=5, sticky="ew")

        # Background color for alpha
        self.bg_label = ctk.CTkLabel(opts, text="Background for transparency:", font=ctk.CTkFont(size=11))
        self.bg_label.grid(row=0, column=2, padx=5, sticky="e")
        self.bg_color_var = ctk.StringVar(value="white")
        self.bg_menu = ctk.CTkOptionMenu(opts, values=["white","black","transparent","red","green","blue","checker"], variable=self.bg_color_var, width=140)
        self.bg_menu.grid(row=0, column=3, padx=5)

        # Resize options
        resize_frame = ctk.CTkFrame(opts, fg_color="transparent")
        resize_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=5)
        ctk.CTkLabel(resize_frame, text="Resize (optional):", font=ctk.CTkFont(size=11)).pack(side="left", padx=5)
        self.width_entry = ctk.CTkEntry(resize_frame, placeholder_text="Width", width=80)
        self.width_entry.pack(side="left", padx=5)
        ctk.CTkLabel(resize_frame, text="x").pack(side="left")
        self.height_entry = ctk.CTkEntry(resize_frame, placeholder_text="Height", width=80)
        self.height_entry.pack(side="left", padx=5)
        self.keep_aspect = ctk.CTkCheckBox(resize_frame, text="Keep original size", font=ctk.CTkFont(size=11))
        self.keep_aspect.select()
        self.keep_aspect.pack(side="left", padx=15)

        # ===== VIEWER =====
        self.viewer = DualViewer(self)
        self.viewer.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0,10))

        # ===== BOTTOM CONTROLS =====
        bottom = ctk.CTkFrame(self, height=70, fg_color="#1e1e1e", corner_radius=0)
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.grid_propagate(False)
        bottom.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(bottom, text="Ready - Select an image to start", font=ctk.CTkFont(size=11), text_color="#888", anchor="w")
        self.status_label.grid(row=0, column=0, columnspan=3, sticky="ew", padx=15, pady=5)

        self.convert_btn = ctk.CTkButton(bottom, text="🔄 CONVERT", width=180, height=40, font=ctk.CTkFont(size=14, weight="bold"),
                                         fg_color="#4ade80", text_color="#000", hover_color="#22c55e",
                                         command=self.convert_image, state="disabled")
        self.convert_btn.grid(row=1, column=0, padx=15, pady=5, sticky="w")

        self.save_btn = ctk.CTkButton(bottom, text="💾 Save As...", width=140, height=36, fg_color="#333", command=self.save_converted, state="disabled")
        self.save_btn.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        self.open_folder_btn = ctk.CTkButton(bottom, text="📂 Open Folder", width=130, height=36, fg_color="#333", command=self.open_folder, state="disabled")
        self.open_folder_btn.grid(row=1, column=1, padx=150, pady=5, sticky="w")

        self.gate_info_label = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=10), text_color="#aaa", wraplength=500, justify="left")
        self.gate_info_label.grid(row=1, column=2, padx=15, sticky="e")

        # Drag and drop support via tkinter
        self.drop_target_register = self.register_drop()
        self.viewer.clear()

    def register_drop(self):
        # Simple file drop handling for Windows via tkinter dnd? We'll use bind for <Drop>
        try:
            # For CTk, we can bind to root
            self.bind("<Button-1>", lambda e: None)  # placeholder
            # Use tkdnd if available, else just rely on browse
            # We'll add a hidden file drop via event
            return None
        except:
            return None

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
        self.file_label.configure(text=f"📄 {path}", text_color="#fff")
        self.status_label.configure(text=f"Loading {os.path.basename(path)}...")

        # Detect format
        info = self.engine.get_image_info(path)
        self.current_info = info
        fmt = self.engine.detect_source_format(path)

        if fmt:
            self.source_dropdown.set_selected_by_id(fmt.id)
            # Update target gate
            self.update_target_gate(fmt, info)
        else:
            self.source_dropdown.main_btn.configure(text="Unknown format - select manually")
            # Show all targets as possible
            self.target_dropdown.set_gate_results({})

        # Load in viewer
        self.viewer.load_original(path, info)
        self.viewer.right.show_placeholder("Select target format and click CONVERT")
        self.convert_btn.configure(state="normal" if fmt else "disabled")
        self.status_label.configure(text=f"Loaded {info.get('width')}x{info.get('height')} {info.get('format')} | Ready to convert")

    def update_target_gate(self, source_fmt, source_info):
        # Build gate map for all formats
        gate_map = {}
        has_alpha = source_info.get("has_alpha", False) if source_info else False
        is_anim = source_info.get("is_animated", False) if source_info else False
        for tgt in FORMATS:
            gate = validate_conversion(source_fmt, tgt, source_has_alpha=has_alpha, source_is_animated=is_anim)
            gate_map[tgt.id] = gate
        self.target_dropdown.set_gate_results(gate_map)

    def on_source_selected(self, fmt):
        # When user manually changes source, recalc gate
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
        # Show gate info
        src_fmt = self.source_dropdown.get_selected()
        if src_fmt:
            gate = validate_conversion(src_fmt, fmt, 
                                       source_has_alpha=self.current_info.get("has_alpha", False) if self.current_info else False,
                                       source_is_animated=self.current_info.get("is_animated", False) if self.current_info else False)
            txt = f"{gate.reason}"
            if gate.warnings:
                txt += " | " + " | ".join(gate.warnings[:2])
            color = "#4ade80" if gate.status=="green" else "#facc15" if gate.status=="yellow" else "#f87171"
            self.gate_info_label.configure(text=txt, text_color=color)
            # Enable convert if allowed
            self.convert_btn.configure(state="normal" if gate.allowed else "disabled")
            if not gate.allowed:
                self.status_label.configure(text=f"Blocked: {gate.reason}")
        else:
            self.gate_info_label.configure(text=f"Target: {fmt.id.upper()} - {fmt.description}")

    def on_quality_change(self, value):
        q = int(value)
        self.quality_label.configure(text=f"Quality: {q}")

    def convert_image(self):
        if not self.current_file:
            messagebox.showwarning("No file", "Select an image first")
            return
        src_fmt = self.source_dropdown.get_selected()
        tgt_fmt = self.target_dropdown.get_selected()
        if not tgt_fmt:
            messagebox.showwarning("No target", "Select target format from searchable dropdown")
            return
        if not src_fmt:
            # try detect again
            src_fmt = self.engine.detect_source_format(self.current_file)
            if not src_fmt:
                messagebox.showerror("Error", "Cannot detect source format")
                return

        # Gate check
        gate = validate_conversion(src_fmt, tgt_fmt, 
                                   source_has_alpha=self.current_info.get("has_alpha", False),
                                   source_is_animated=self.current_info.get("is_animated", False))
        if not gate.allowed:
            messagebox.showerror("Blocked by Acceptance Gate", gate.reason)
            return

        self.convert_btn.configure(state="disabled", text="Converting...")
        self.status_label.configure(text=f"Converting {src_fmt.id.upper()} -> {tgt_fmt.id.upper()}...")

        # Run in thread
        def do_convert():
            try:
                # Determine background
                bg_str = self.bg_color_var.get()
                bg_map = {
                    "white": (255,255,255),
                    "black": (0,0,0),
                    "red": (255,0,0),
                    "green": (0,255,0),
                    "blue": (0,0,255),
                    "transparent": (255,255,255),  # fallback white if needed
                }
                bg = bg_map.get(bg_str, (255,255,255))

                quality = int(self.quality_slider.get())

                # Resize
                resize = None
                if not self.keep_aspect.get():
                    try:
                        w = int(self.width_entry.get()) if self.width_entry.get().strip() else 0
                        h = int(self.height_entry.get()) if self.height_entry.get().strip() else 0
                        if w>0 and h>0:
                            resize = (w,h)
                    except:
                        pass

                # Output temp file
                ext = tgt_fmt.exts[0]
                temp_dir = tempfile.gettempdir()
                out_path = os.path.join(temp_dir, f"converted_{os.path.splitext(os.path.basename(self.current_file))[0]}{ext}")
                # Ensure unique
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
                        self.viewer.load_converted(out_path, info)
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
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=default_name,
                                            filetypes=[(f"{tgt.id.upper()} files" if tgt else "Image", f"*{ext}"), ("All Files", "*.*")])
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
                os.startfile(folder)  # Windows
            except:
                try:
                    import subprocess
                    subprocess.Popen(["xdg-open", folder])
                except:
                    messagebox.showinfo("Folder", folder)

    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Settings - Image Switcher")
        win.geometry("500x400")
        win.transient(self)
        ctk.CTkLabel(win, text="Settings & About", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        txt = ctk.CTkTextbox(win, width=460, height=300)
        txt.pack(padx=10, pady=10)
        txt.insert("0.0", f"""Python Image Switcher v1.0

Features:
- 50+ formats supported
- Searchable dropdown with acceptance gate
- Dual viewer (old vs new)
- SVG rasterization and embedding
- Alpha handling with background picker
- Quality control

Formats:
Common: PNG, JPEG, WEBP, BMP, GIF, TIFF, ICO
Modern: AVIF, HEIF, HEIC, JPEG XL, JPEG2000, HDR, EXR
Legacy: TGA, PCX, PPM, SGI, XBM, XPM, etc
Vector: SVG, SVGZ, PDF, EPS, PS

Acceptance Gate:
Green = fully compatible
Yellow = compatible with loss (alpha, animation, quality)
Red = blocked

Dependencies:
- Pillow, customtkinter, cairosvg, pillow-heif, pillow-avif

Build EXE:
python build_exe.py --onefile
Then use installer.iss with Inno Setup to make Setup.exe

Current file: {self.current_file or 'None'}
Converted: {self.converted_file or 'None'}
""")
        txt.configure(state="disabled")
