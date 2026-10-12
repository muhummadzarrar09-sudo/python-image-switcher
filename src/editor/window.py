"""Desktop UI for numbered, non-destructive still-photo batches.

This deliberately remains separate from the legacy anything-to-anything converter.
All Tk widgets are updated on the UI thread; exports run off-thread.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from .batch import BatchSession, EDIT_FIELDS
from .render import PhotoRenderError, STILL_EXTENSIONS, render, source_info
from .workflow import export_batch, import_project
from .version import ALPHA_VERSION


class EditorWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"Image Switcher | Still Photo Editor {ALPHA_VERSION}")
        self.geometry("1240x840")
        self.minsize(1000, 700)
        self.batch = BatchSession()
        self.session_path = None
        self.current = None
        self.busy = False
        self.brush_add = True
        self._preview_image = None
        self._canvas_bounds = (0, 0, 0, 0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(self)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=6)
        for text, action in (("Add still photos", self.add_files), ("Open .isbatch", self.open_session),
                             ("Save .isbatch", self.save_session), ("Open .isphoto", self.open_project),
                             ("Export batch", self.export)):
            ctk.CTkButton(bar, text=text, command=action, width=130).pack(side="left", padx=4, pady=5)
        self.status = ctk.CTkLabel(bar, text="Originals stay untouched; exports are PNG/TIFF plus .isphoto")
        self.status.pack(side="left", padx=10)

        sidebar = ctk.CTkFrame(self, width=245)
        sidebar.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="NUMBERED BATCH", font=ctk.CTkFont(weight="bold")).pack(pady=8)
        self.items = ctk.CTkScrollableFrame(sidebar, width=220)
        self.items.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(sidebar, text="Locked = manual edits preserved;\nstill included in export.",
                     text_color="#c2c2c2", justify="left").pack(pady=8)
        self.canvas = tk.Canvas(self, width=780, height=540, bg="#171717", highlightthickness=0)
        self.canvas.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        self.canvas.bind("<Button-1>", self.paint_mask)
        panel = ctk.CTkScrollableFrame(self, width=295)
        panel.grid(row=1, column=2, sticky="ns", padx=(4, 8), pady=4)
        ctk.CTkLabel(panel, text="PHOTO EDITS", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=8)
        self.scope = ctk.StringVar(value="Batch")
        ctk.CTkOptionMenu(panel, values=["Batch", "Selected photo (protect)"],
                          variable=self.scope, command=lambda _: self.select_field(self.field.get())).pack(fill="x", padx=8)
        ctk.CTkLabel(panel, text="Protected photos ignore later batch sliders", text_color="#aaa").pack()
        self.field = ctk.StringVar(value="exposure")
        ctk.CTkOptionMenu(panel, variable=self.field, values=list(EDIT_FIELDS),
                          command=self.select_field).pack(fill="x", padx=8, pady=8)
        self.value_label = ctk.CTkLabel(panel, text="exposure: 0")
        self.value_label.pack()
        self.slider = ctk.CTkSlider(panel, command=self.change_value)
        self.slider.pack(fill="x", padx=10, pady=8)
        ctk.CTkButton(panel, text="Unlock selected for batch", command=self.unlock).pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(panel, text="CROP / ORIENTATION", font=ctk.CTkFont(weight="bold")).pack(pady=(18, 5))
        ctk.CTkLabel(panel, text="Crop x0,y0,x1,y1 in % (0 to 100)").pack()
        self.crop = ctk.CTkEntry(panel, placeholder_text="e.g. 5,5,95,95")
        self.crop.pack(fill="x", padx=8)
        ctk.CTkButton(panel, text="Apply crop / blank = reset", command=self.apply_crop).pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(panel, text="Rotate 90° left", command=self.rotate).pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(panel, text="Flip horizontally", command=self.flip).pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(panel, text="BACKGROUND (manual mask)", font=ctk.CTkFont(weight="bold")).pack(pady=(18, 5))
        self.effect = ctk.StringVar(value="none")
        ctk.CTkOptionMenu(panel, variable=self.effect, values=["none", "blur", "remove", "color", "image"],
                          command=self.set_background).pack(fill="x", padx=8)
        self.color = ctk.CTkEntry(panel, placeholder_text="#ffffff")
        self.color.insert(0, "#ffffff")
        self.color.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(panel, text="Set color / choose image", command=self.pick_background).pack(fill="x", padx=8)
        self.brush = ctk.StringVar(value="Paint background")
        ctk.CTkOptionMenu(panel, variable=self.brush, values=["Paint background", "Erase from mask"],
                          command=lambda value: setattr(self, "brush_add", value == "Paint background")).pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(panel, text="Click photo to paint; erase corrects mistakes.\nNo automatic subject detection yet.",
                     text_color="#bbb", justify="left").pack(pady=3)
        ctk.CTkLabel(panel, text="PROJECT RIGHTS (declared, not signed)",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(18, 5))
        self.creator = ctk.CTkEntry(panel, placeholder_text="Creator name (optional)")
        self.creator.pack(fill="x", padx=8)
        self.notice = ctk.CTkEntry(panel, placeholder_text="Copyright notice (optional)")
        self.notice.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(panel, text="Rights here stay in .isphoto only.\nNo C2PA signature or persistent watermark yet.",
                     text_color="#e0ab71", justify="left").pack(pady=8)
        self.select_field("exposure")
        self.refresh_list()

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
        self.refresh_list()
        self.show_current()
        if errors:
            self.error("\n".join(errors[:8]))

    def refresh_list(self):
        for child in self.items.winfo_children():
            child.destroy()
        for photo in self.batch.photos:
            state = "🔒" if photo.protected else "•"
            color = "#bd7c34" if photo.protected else ("#3476a8" if photo.number == self.current else "#333")
            ctk.CTkButton(self.items, text=f"#{photo.number:04d} {state} {Path(photo.source).name[:19]}",
                          fg_color=color, anchor="w", command=lambda n=photo.number: self.select(n)).pack(fill="x", pady=2)
        self.status.configure(text=f"{len(self.batch.photos)} photos | protected: {self.batch.excluded_numbers} | all included in export")

    def select(self, number):
        self.current = number
        self.refresh_list()
        self.select_field(self.field.get())
        self.show_current()

    def select_field(self, field):
        lo, hi = EDIT_FIELDS[field]
        self.slider.configure(from_=lo, to=hi, number_of_steps=200)
        if self.scope.get() == "Batch" or self.current is None:
            value = self.batch.batch_settings[field]
        else:
            value = self.batch.effective_settings(self.current)[field]
        self.slider.set(value)
        self.value_label.configure(text=f"{field}: {value:.2f}")

    def change_value(self, value):
        field = self.field.get()
        self.value_label.configure(text=f"{field}: {value:.2f}")
        try:
            if self.scope.get() == "Batch":
                self.batch.set_batch(field, value)
            elif self.current is not None:
                self.batch.edit_photo(self.current, field, value)
            self.refresh_list()
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
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def apply_crop(self):
        try:
            text = self.crop.get().strip()
            box = tuple(float(x.strip()) / 100 for x in text.split(",")) if text else None
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

    def set_background(self, value):
        try:
            photo = self.selected_photo()
            if value == "image":
                path = filedialog.askopenfilename(parent=self, title="Choose replacement image")
                if not path:
                    self.effect.set(photo.background.get("mode", "none"))
                    return
                source_info(path)
                photo.background = {"mode": "image", "source": path}
            elif value == "none":
                photo.background = {}
            else:
                photo.background = {"mode": value, "color": self.color.get() or "#ffffff"}
            self.batch.protect(photo.number)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def pick_background(self):
        self.set_background(self.effect.get())

    def paint_mask(self, event):
        try:
            photo = self.selected_photo()
            left, top, w, h = self._canvas_bounds
            if not w or not (left <= event.x < left + w and top <= event.y < top + h):
                return
            self.batch.add_mask_stroke(photo.number, (event.x-left)/w, (event.y-top)/h,
                                       .035, add_background=self.brush_add)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def show_current(self):
        self.canvas.delete("all")
        if self.current is None:
            self._canvas_bounds = (0, 0, 0, 0)
            return
        try:
            photo = self.selected_photo()
            image, _, raw = render(photo, self.batch, preview=True)
            if not isinstance(image, Image.Image):
                image = Image.fromarray((image / 257).astype("uint8"))
            image.thumbnail((780, 540), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
            w, h = image.size
            left, top = (780-w)//2, (540-h)//2
            self._canvas_bounds = (left, top, w, h)
            self.canvas.create_image(left, top, anchor="nw", image=self._preview_image)
            self.canvas.create_text(8, 8, anchor="nw", text=f"#{photo.number:04d} {'PROTECTED' if photo.protected else 'BATCH'} | preview only",
                                    fill="white", font=("Arial", 12, "bold"))
        except Exception as exc:
            self._canvas_bounds = (0, 0, 0, 0)
            self.canvas.create_text(10, 20, anchor="nw", fill="orange", text=str(exc)[:105])

    def save_session(self):
        path = self.session_path or filedialog.asksaveasfilename(parent=self, defaultextension=".isbatch",
                                                                filetypes=[("Batch session", "*.isbatch")])
        if path:
            try:
                self.batch.rights = {"creator": self.creator.get(), "copyright_notice": self.notice.get()}
                self.batch.save(path)
                self.session_path = path
                self.status.configure(text=f"Saved {path}")
            except Exception as exc:
                self.error(exc)

    def open_session(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Batch session", "*.isbatch")])
        if path:
            try:
                self.batch = BatchSession.load(path)
                self.session_path = path
                self.current = self.batch.photos[0].number if self.batch.photos else None
                self.creator.delete(0, "end")
                self.creator.insert(0, self.batch.rights.get("creator", ""))
                self.notice.delete(0, "end")
                self.notice.insert(0, self.batch.rights.get("copyright_notice", ""))
                self.refresh_list()
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
                self.current = import_project(self.batch, path, dest).number
                self.refresh_list()
                self.show_current()
            except Exception as exc:
                self.error(exc)

    def export(self):
        if self.busy or not self.batch.photos:
            return
        dest = filedialog.askdirectory(parent=self, title="Empty folder for numbered lossless masters and projects")
        if not dest:
            return
        self.batch.rights = {"creator": self.creator.get(), "copyright_notice": self.notice.get()}
        self.busy = True
        self.status.configure(text="Exporting every numbered photo, including protected edits...")

        def work():
            try:
                results = export_batch(self.batch, dest)
                self.after(0, lambda: self.done(f"Exported {len(results)} PNG/TIFF masters + .isphoto projects to {dest}"))
            except Exception as exc:
                self.after(0, lambda exc=exc: self.failed(exc))
        threading.Thread(target=work, daemon=True).start()

    def done(self, message):
        self.busy = False
        self.status.configure(text=message)
        messagebox.showinfo("Batch exported", message, parent=self)

    def failed(self, exc):
        self.busy = False
        self.error(exc)
