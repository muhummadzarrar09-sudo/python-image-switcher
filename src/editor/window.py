"""Desktop UI for numbered, non-destructive still-photo batches.

Adjustments are visible as named sliders. Crop/background controls live in their
own editing tools, while export settings appear only after clicking Export.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageColor, ImageTk

from .batch import BatchSession, EDIT_FIELDS
from .render import STILL_EXTENSIONS, render, source_info
from .workflow import export_batch, import_project
from .version import ALPHA_VERSION


class EditorWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"Image Switcher | Still Photo Editor {ALPHA_VERSION}")
        self.geometry("1240x840")
        self.minsize(1000, 700)
        self.batch = BatchSession()
        self.session_path: str | None = None
        self.current: int | None = None
        self.busy = False
        self.brush_add = True
        self.mask_painting = False
        self.crop_window: CropTools | None = None
        self.background_window: BackgroundTools | None = None
        self._preview_image = None
        self._canvas_bounds = (0, 0, 0, 0)
        self._resize_job = None
        self._syncing_sliders = False
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self.value_labels: dict[str, ctk.CTkLabel] = {}
        self.scope = ctk.StringVar(value="Batch")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(self)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(6, 2))
        for text, action in (("Add photos", self.add_files), ("Open batch", self.open_session),
                             ("Save batch", self.save_session), ("Open .isphoto", self.open_project),
                             ("Crop / rotate", self.open_crop_tools),
                             ("Background / mask", self.open_background_tools),
                             ("Export...", self.export)):
            ctk.CTkButton(bar, text=text, command=action, width=112).pack(side="left", padx=3, pady=5)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 3))
        ctk.CTkLabel(controls, text="Adjust:").pack(side="left", padx=(5, 3))
        ctk.CTkOptionMenu(controls, variable=self.scope, values=["Batch", "Selected photo (protect)"],
                          width=205, command=lambda _: self.sync_sliders()).pack(side="left", padx=4)
        ctk.CTkButton(controls, text="Unlock selected", width=115, fg_color="#555",
                      command=self.unlock).pack(side="left", padx=6)
        self.status = ctk.CTkLabel(controls, text="Add still photos to begin", anchor="w")
        self.status.pack(side="left", padx=10, fill="x", expand=True)

        sidebar = ctk.CTkFrame(self, width=225)
        sidebar.grid(row=2, column=0, sticky="nsew", padx=(8, 4), pady=4)
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="NUMBERED BATCH", font=ctk.CTkFont(weight="bold")).pack(pady=8)
        self.items = ctk.CTkScrollableFrame(sidebar, width=204)
        self.items.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(sidebar, text="Locked = individual edits preserved;\nstill included in full-batch export.",
                     text_color="#c2c2c2", justify="left").pack(pady=8)

        self.canvas = tk.Canvas(self, width=680, height=540, bg="#171717", highlightthickness=0)
        self.canvas.grid(row=2, column=1, sticky="nsew", padx=4, pady=4)
        self.canvas.bind("<Button-1>", self.paint_mask)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        panel = ctk.CTkScrollableFrame(self, width=272)
        panel.grid(row=2, column=2, sticky="ns", padx=(4, 8), pady=4)
        ctk.CTkLabel(panel, text="ADJUSTMENTS", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(8, 12))
        # No category selector: every edit setting and its value is directly visible.
        for field, (low, high) in EDIT_FIELDS.items():
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=(0, 13))
            header = ctk.CTkFrame(row, fg_color="transparent")
            header.pack(fill="x")
            ctk.CTkLabel(header, text=field.replace("_", " ").title(), anchor="w",
                         font=ctk.CTkFont(size=13)).pack(side="left")
            label = ctk.CTkLabel(header, text="0.00", anchor="e", width=46, text_color="#aaa")
            label.pack(side="right")
            slider = ctk.CTkSlider(row, from_=low, to=high, number_of_steps=200,
                                   command=lambda value, key=field: self.change_value(key, value))
            slider.pack(fill="x", pady=(5, 0))
            self.sliders[field] = slider
            self.value_labels[field] = label
        self.sync_sliders()
        self.refresh_list()
        self.show_current()

    def error(self, exc):
        messagebox.showerror("Photo editor", str(exc), parent=self)
        self.status.configure(text=str(exc)[:100])

    def add_files(self):
        paths = filedialog.askopenfilenames(parent=self, title="Choose still photos",
                                           filetypes=[("Still photos", " ".join("*" + ext for ext in sorted(STILL_EXTENSIONS))),
                                                      ("All files", "*.*")])
        errors = []
        for path in paths:
            try:
                source_info(path)
                self.current = self.batch.add_photo(path).number
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        if paths:
            self.close_crop_tools()
            self.close_background_tools()
            self.refresh_list()
            self.sync_sliders()
            self.show_current()
        if errors:
            self.error("\n".join(errors[:8]))

    def refresh_list(self):
        for child in self.items.winfo_children():
            child.destroy()
        for photo in self.batch.photos:
            marker = "🔒" if photo.protected else "•"
            color = "#bd7c34" if photo.protected else ("#3476a8" if photo.number == self.current else "#333")
            ctk.CTkButton(self.items, text=f"#{photo.number:04d} {marker} {Path(photo.source).name[:17]}",
                          fg_color=color, anchor="w", command=lambda n=photo.number: self.select(n)).pack(fill="x", pady=2)
        if self.batch.photos:
            self.status.configure(text=f"{len(self.batch.photos)} photos | protected: {self.batch.excluded_numbers} | all export")
        else:
            self.status.configure(text="Add still photos to begin")

    def select(self, number: int):
        self.close_crop_tools()
        self.close_background_tools()
        self.current = number
        self.refresh_list()
        self.sync_sliders()
        self.show_current()

    def sync_sliders(self):
        self._syncing_sliders = True
        try:
            if self.scope.get() == "Batch" or self.current is None:
                values = self.batch.batch_settings
            else:
                values = self.batch.effective_settings(self.current)
            for field, slider in self.sliders.items():
                slider.set(values[field])
                self.value_labels[field].configure(text=f"{values[field]:+.2f}")
        finally:
            self._syncing_sliders = False

    def change_value(self, field: str, value: float):
        if self._syncing_sliders:
            return
        if self.scope.get() != "Batch" and self.current is None:
            self.status.configure(text="Select a numbered photo before making individual edits")
            self.sync_sliders()
            return
        try:
            if self.scope.get() == "Batch":
                self.batch.set_batch(field, value)
            else:
                photo = self.selected_photo()
                was_protected = photo.protected
                self.batch.edit_photo(photo.number, field, value)
                if not was_protected:
                    self.refresh_list()
            self.value_labels[field].configure(text=f"{value:+.2f}")
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def selected_photo(self):
        if self.current is None:
            raise ValueError("Choose a numbered photo first")
        return self.batch.get(self.current)

    def unlock(self):
        try:
            self.batch.include_in_batch(self.selected_photo().number)
            self.refresh_list()
            self.sync_sliders()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def open_crop_tools(self):
        try:
            self.selected_photo()
            if self.crop_window and self.crop_window.winfo_exists():
                self.crop_window.lift()
                self.crop_window.focus_force()
            else:
                self.crop_window = CropTools(self)
        except Exception as exc:
            self.error(exc)

    def close_crop_tools(self):
        if self.crop_window and self.crop_window.winfo_exists():
            self.crop_window.destroy()
        self.crop_window = None

    def apply_crop(self, text: str):
        try:
            box = tuple(float(x.strip()) / 100 for x in text.split(",")) if text.strip() else None
            self.batch.set_crop(self.selected_photo().number, box)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def rotate(self):
        try:
            photo = self.selected_photo()
            self.batch.set_rotation(photo.number, (photo.rotation + 90) % 360)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def flip(self):
        try:
            photo = self.selected_photo()
            self.batch.protect(photo.number)
            photo.flip_horizontal = not photo.flip_horizontal
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def open_background_tools(self):
        try:
            self.selected_photo()
            if self.background_window and self.background_window.winfo_exists():
                self.background_window.lift()
                self.background_window.focus_force()
            else:
                self.background_window = BackgroundTools(self)
                self.mask_painting = True
                self.canvas.configure(cursor="crosshair")
        except Exception as exc:
            self.error(exc)

    def close_background_tools(self):
        self.mask_painting = False
        self.canvas.configure(cursor="")
        if self.background_window and self.background_window.winfo_exists():
            self.background_window.destroy()
        self.background_window = None

    def set_background(self, mode: str, *, color: str = "#ffffff", source: str | None = None):
        photo = self.selected_photo()
        if mode == "image":
            if not source:
                raise ValueError("Choose a replacement image")
            source_info(source)
            settings = {"mode": mode, "source": source}
        elif mode in ("blur", "remove", "color"):
            if mode == "color":
                ImageColor.getrgb(color)  # fail before changing the edit recipe
            settings = {"mode": mode, "color": color}
        elif mode == "none":
            settings = {}
        else:
            raise ValueError("Unknown background mode")
        self.batch.protect(photo.number)
        photo.background = settings
        self.refresh_list()
        self.show_current()

    def clear_mask(self):
        photo = self.selected_photo()
        self.batch.protect(photo.number)
        photo.mask_strokes.clear()
        self.refresh_list()
        self.show_current()

    def paint_mask(self, event):
        if not self.mask_painting or self.current is None:
            return
        try:
            photo = self.selected_photo()
            if not photo.background:
                return
            left, top, width, height = self._canvas_bounds
            if not width or not (left <= event.x < left + width and top <= event.y < top + height):
                return
            self.batch.add_mask_stroke(photo.number, (event.x-left)/width, (event.y-top)/height,
                                       .035, add_background=self.brush_add)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def on_canvas_resize(self, _event):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self.show_current)

    def show_current(self):
        self._resize_job = None
        self.canvas.delete("all")
        canvas_w = max(100, self.canvas.winfo_width())
        canvas_h = max(100, self.canvas.winfo_height())
        if self.current is None:
            self._canvas_bounds = (0, 0, 0, 0)
            self.canvas.create_text(canvas_w//2, canvas_h//2, text="Add still photos to begin",
                                    fill="#888", font=("Arial", 16))
            return
        try:
            photo = self.selected_photo()
            image, _, _ = render(photo, self.batch, preview=True)
            if not isinstance(image, Image.Image):
                image = Image.fromarray((image / 257).astype("uint8"))
            image.thumbnail((canvas_w-20, canvas_h-20), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
            width, height = image.size
            left, top = (canvas_w-width)//2, (canvas_h-height)//2
            self._canvas_bounds = (left, top, width, height)
            self.canvas.create_image(left, top, anchor="nw", image=self._preview_image)
            self.canvas.create_text(8, 8, anchor="nw",
                                    text=f"#{photo.number:04d} {'PROTECTED' if photo.protected else 'BATCH'} | preview only",
                                    fill="white", font=("Arial", 12, "bold"))
        except Exception as exc:
            self._canvas_bounds = (0, 0, 0, 0)
            self.canvas.create_text(10, 20, anchor="nw", fill="orange", text=str(exc)[:105])

    def save_session(self):
        path = self.session_path or filedialog.asksaveasfilename(parent=self, defaultextension=".isbatch",
                                                                filetypes=[("Batch session", "*.isbatch")])
        if path:
            try:
                self.batch.save(path)
                self.session_path = path
                self.status.configure(text=f"Saved {path}")
            except Exception as exc:
                self.error(exc)

    def open_session(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Batch session", "*.isbatch")])
        if path:
            try:
                loaded = BatchSession.load(path)
                self.close_crop_tools()
                self.close_background_tools()
                self.batch = loaded
                self.session_path = path
                self.current = self.batch.photos[0].number if self.batch.photos else None
                self.refresh_list()
                self.sync_sliders()
                self.show_current()
            except Exception as exc:
                self.error(exc)

    def open_project(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Photo project", "*.isphoto")])
        if path:
            dest = filedialog.askdirectory(parent=self, title="Choose durable directory for imported original/master")
            if not dest:
                return
            try:
                self.close_crop_tools()
                self.close_background_tools()
                self.current = import_project(self.batch, path, dest).number
                self.refresh_list()
                self.sync_sliders()
                self.show_current()
            except Exception as exc:
                self.error(exc)

    def export(self):
        if self.busy:
            return
        if not self.batch.photos:
            self.error("Add still photos before exporting")
            return
        ExportOptions(self)

    def begin_export(self, directory: str, rights: dict, numbers: list[int] | None):
        if self.busy:
            return
        # A user may keep working while the worker renders. Export the exact
        # recipe that was approved in the dialog rather than mutable UI state.
        self.batch.rights = dict(rights)
        snapshot = deepcopy(self.batch)
        self.busy = True
        count = len(snapshot.photos) if numbers is None else len(numbers)
        self.status.configure(text=f"Exporting {count} numbered photo(s), with their manual edits...")

        def work():
            try:
                results = export_batch(snapshot, directory, numbers=numbers)
                self.after(0, lambda: self.done(f"Exported {len(results)} lossless masters + .isphoto projects to {directory}"))
            except Exception as exc:
                self.after(0, lambda exc=exc: self.failed(exc))
        threading.Thread(target=work, daemon=True).start()

    def done(self, message):
        self.busy = False
        self.status.configure(text=message)
        messagebox.showinfo("Export complete", message, parent=self)

    def failed(self, exc):
        self.busy = False
        self.error(exc)


class CropTools(ctk.CTkToplevel):
    """Non-export editing tools, separate from the adjustment sliders."""
    def __init__(self, editor: EditorWindow):
        super().__init__(editor)
        self.editor = editor
        self.title("Crop / orientation")
        self.geometry("350x260")
        self.resizable(False, False)
        self.transient(editor)
        self.protocol("WM_DELETE_WINDOW", editor.close_crop_tools)
        photo = editor.selected_photo()
        ctk.CTkLabel(self, text=f"Photo #{photo.number:04d} — crop / orientation",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(12, 6))
        ctk.CTkLabel(self, text="Crop x0, y0, x1, y1 (%) · blank resets crop").pack()
        self.crop = ctk.CTkEntry(self, placeholder_text="e.g. 5,5,95,95", width=300)
        self.crop.pack(pady=7)
        if photo.crop:
            self.crop.insert(0, ",".join(f"{v*100:g}" for v in photo.crop))
        ctk.CTkButton(self, text="Apply crop", command=lambda: editor.apply_crop(self.crop.get())).pack(pady=4)
        ctk.CTkButton(self, text="Rotate 90° left", command=editor.rotate).pack(pady=4)
        ctk.CTkButton(self, text="Flip horizontally", command=editor.flip).pack(pady=4)


class BackgroundTools(ctk.CTkToplevel):
    """Non-modal so the user can paint directly on the canvas behind it."""
    def __init__(self, editor: EditorWindow):
        super().__init__(editor)
        self.editor = editor
        self.title("Background / manual mask")
        self.geometry("390x375")
        self.resizable(False, False)
        self.transient(editor)
        self.protocol("WM_DELETE_WINDOW", editor.close_background_tools)
        photo = editor.selected_photo()
        ctk.CTkLabel(self, text=f"Photo #{photo.number:04d} — background",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(12, 6))
        self.effect = ctk.StringVar(value=photo.background.get("mode", "none"))
        ctk.CTkOptionMenu(self, variable=self.effect, values=["none", "blur", "remove", "color", "image"],
                          width=300, command=self.choose_mode).pack(pady=6)
        self.color = ctk.CTkEntry(self, width=300, placeholder_text="#ffffff")
        self.color.insert(0, photo.background.get("color", "#ffffff"))
        self.color.pack(pady=4)
        ctk.CTkButton(self, text="Apply color", command=self.apply_color).pack(pady=4)
        self.brush = ctk.StringVar(value="Paint background" if editor.brush_add else "Erase from mask")
        ctk.CTkOptionMenu(self, variable=self.brush, width=300,
                          values=["Paint background", "Erase from mask"],
                          command=lambda value: setattr(editor, "brush_add", value == "Paint background")).pack(pady=8)
        ctk.CTkButton(self, text="Clear mask strokes", fg_color="#555", command=editor.clear_mask).pack(pady=4)
        ctk.CTkLabel(self, text="While this tool is open, click the photo to paint.\n"
                     "Erase corrects mistakes; no automatic selection yet.",
                     text_color="#bbb", justify="center").pack(pady=6)

    def choose_mode(self, mode: str):
        try:
            if mode == "image":
                path = filedialog.askopenfilename(parent=self, title="Choose replacement image",
                                                  filetypes=[("Still photos", "*.png *.jpg *.jpeg *.tif *.tiff *.webp"),
                                                             ("All files", "*.*")])
                if not path:
                    self.effect.set(self.editor.selected_photo().background.get("mode", "none"))
                    return
                self.editor.set_background("image", source=path)
            else:
                self.editor.set_background(mode, color=self.color.get() or "#ffffff")
        except Exception as exc:
            self.effect.set(self.editor.selected_photo().background.get("mode", "none"))
            self.editor.error(exc)

    def apply_color(self):
        try:
            self.editor.set_background("color", color=self.color.get() or "#ffffff")
            self.effect.set("color")
        except Exception as exc:
            self.editor.error(exc)


class ExportOptions(ctk.CTkToplevel):
    """Nothing is exported until the user confirms this dedicated dialog."""
    def __init__(self, editor: EditorWindow):
        super().__init__(editor)
        self.editor = editor
        self.title("Export options")
        self.geometry("490x545")
        self.resizable(False, False)
        self.transient(editor)
        self.protocol("WM_DELETE_WINDOW", self.close)
        ctk.CTkLabel(self, text="EXPORT PHOTOS", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(14, 4))
        ctk.CTkLabel(self, text="Choose where and what to export. Nothing is written until Export now.",
                     text_color="#bbb", wraplength=455).pack(padx=15, pady=(0, 12))
        ctk.CTkLabel(self, text="Destination folder", anchor="w").pack(fill="x", padx=22)
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.pack(fill="x", padx=18, pady=5)
        self.folder = ctk.StringVar()
        ctk.CTkEntry(path_row, textvariable=self.folder, width=325).pack(side="left", padx=(0, 6))
        ctk.CTkButton(path_row, text="Browse", width=100, command=self.browse).pack(side="left")
        ctk.CTkLabel(self, text="Photos", anchor="w").pack(fill="x", padx=22, pady=(8, 0))
        self.selection = ctk.StringVar(value="Entire numbered batch (includes protected)")
        choices = [self.selection.get()]
        if editor.current is not None:
            choices.append(f"Selected photo #{editor.current:04d} only")
        ctk.CTkOptionMenu(self, variable=self.selection, values=choices, width=446).pack(pady=5)
        ctk.CTkLabel(self, text="Lossless master: PNG for 8-bit sources, 16-bit TIFF for NEF.\n"
                     "Every exported photo also gets an editable .isphoto copy.\n"
                     "Originals remain untouched; existing export names are never replaced.",
                     text_color="#b9d5e9", wraplength=440, justify="left").pack(padx=20, pady=(12, 8))
        ctk.CTkLabel(self, text="Project rights (declarations only)", anchor="w").pack(fill="x", padx=22)
        self.creator = ctk.CTkEntry(self, placeholder_text="Creator name (optional)", width=440)
        self.creator.pack(pady=(5, 4))
        self.creator.insert(0, editor.batch.rights.get("creator", ""))
        self.notice = ctk.CTkEntry(self, placeholder_text="Copyright notice (optional)", width=440)
        self.notice.pack(pady=4)
        self.notice.insert(0, editor.batch.rights.get("copyright_notice", ""))
        ctk.CTkLabel(self, text="Rights go in .isphoto only. No signed credentials or watermark yet.",
                     text_color="#e0ab71", wraplength=440).pack(padx=16, pady=7)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=(9, 12))
        ctk.CTkButton(actions, text="Cancel", width=135, fg_color="#555",
                      command=self.close).pack(side="left", padx=8)
        ctk.CTkButton(actions, text="Export now", width=145,
                      command=self.confirm).pack(side="left", padx=8)
        self.after_idle(self._grab_when_visible)

    def _grab_when_visible(self):
        if self.winfo_exists():
            try:
                self.grab_set()
            except tk.TclError:
                self.after(50, self._grab_when_visible)

    def browse(self):
        destination = filedialog.askdirectory(parent=self, title="Choose folder for numbered master/project pairs")
        if destination:
            self.folder.set(destination)

    def confirm(self):
        destination = self.folder.get().strip()
        if not destination:
            messagebox.showwarning("Choose a folder", "Select a destination folder first.", parent=self)
            return
        numbers = [self.editor.current] if self.selection.get().startswith("Selected photo") else None
        rights = {"creator": self.creator.get().strip(), "copyright_notice": self.notice.get().strip()}
        self.close()
        self.editor.begin_export(destination, rights, numbers)

    def close(self):
        if self.grab_current() == self:
            self.grab_release()
        self.destroy()
