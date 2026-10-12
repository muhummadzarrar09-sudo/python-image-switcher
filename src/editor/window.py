"""Desktop UI for numbered, non-destructive still-photo batches.

Adjustments are visible as named sliders. Crop/background controls live in their
own editing tools, while export settings appear only after clicking Export.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageColor, ImageTk

from .batch import BatchSession, EDIT_FIELDS
from .render import STILL_EXTENSIONS, render, source_info, still_photo_frames, _open_source
from .workflow import export_batch, import_project
from .version import ALPHA_VERSION


def _thumbnail_pixels(path: str, frame_index: int) -> Image.Image:
    """Decode a tiny still in a worker; CTkImage creation stays on the UI thread."""
    background = Image.new("RGBA", (104, 61), "#343943")
    image, _, _ = _open_source(path, preview=True, frame_index=frame_index)
    if not isinstance(image, Image.Image):
        image = Image.fromarray((image / 257).astype("uint8"))
    image = image.convert("RGBA")
    image.thumbnail((104, 61), Image.Resampling.LANCZOS)
    background.alpha_composite(image, ((104-image.width)//2, (61-image.height)//2))
    return background.convert("RGB")


class ImportProgress(ctk.CTkToplevel):
    """Progress for background intake. Cancel stops after the current file."""

    def __init__(self, editor, total: int, cancel: threading.Event):
        super().__init__(editor)
        self.title("Adding still photos")
        self.geometry("430x190")
        self.resizable(False, False)
        self.transient(editor)
        self.configure(fg_color="#25282d")
        self._cancel = cancel
        self.editor_total = total
        self.protocol("WM_DELETE_WINDOW", self.request_cancel)
        x = editor.winfo_rootx() + max(0, (editor.winfo_width() - 430)//2)
        y = editor.winfo_rooty() + max(0, (editor.winfo_height() - 190)//2)
        self.geometry(f"430x190+{x}+{y}")
        ctk.CTkLabel(self, text="Adding still photos", anchor="w",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(fill="x", padx=22, pady=(16, 5))
        self.progress_text = ctk.CTkLabel(self, text=f"Checking 0 of {total} files…",
                                          anchor="w", text_color="#c8d0dc")
        self.progress_text.pack(fill="x", padx=22)
        self.bar = ctk.CTkProgressBar(self, width=382, height=10)
        self.bar.pack(padx=22, pady=(12, 6))
        self.bar.set(0)
        self.filename = ctk.CTkLabel(self, text="Checking image data…", anchor="w",
                                      text_color="#9da8b6", font=ctk.CTkFont(size=11))
        self.filename.pack(fill="x", padx=22)
        self.cancel_button = ctk.CTkButton(self, text="Stop importing", width=110,
                                            fg_color="#3c444e", command=self.request_cancel)
        self.cancel_button.pack(anchor="e", padx=22, pady=(3, 10))
        self.after_idle(self._focus)

    def _focus(self):
        if self.winfo_exists():
            try:
                self.lift()
                self.grab_set()
            except tk.TclError:
                self.after(50, self._focus)  # allow the native window to become viewable

    def show_progress(self, processed: int, added: int, name: str):
        self.progress_text.configure(text=f"Checked {processed}/{self.editor_total} files · {added} photo(s) added")
        self.filename.configure(text=name[:55])
        self.bar.set(processed / self.editor_total)

    def request_cancel(self):
        self._cancel.set()
        self.progress_text.configure(text="Stopping after the current file…")
        self.cancel_button.configure(state="disabled")

    def close(self):
        if self.grab_current() == self:
            self.grab_release()
        self.destroy()


class EditorWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"Image Switcher | Still Photo Editor {ALPHA_VERSION}")
        self.geometry("1456x766")
        self.minsize(1000, 700)
        self.batch = BatchSession()
        self.session_path: str | None = None
        self.current: int | None = None
        self.busy = False
        self.importing = False
        self.import_dialog: ImportProgress | None = None
        self._import_queue: Queue | None = None
        self._import_cancel: threading.Event | None = None
        self._import_errors: list[str] = []
        self.brush_add = True
        self.mask_painting = False
        self.crop_window: CropTools | None = None
        self.background_window: BackgroundTools | None = None
        self._preview_image = None
        self._thumbnail_cache: dict[str, ctk.CTkImage] = {}
        self.view_mode = ctk.StringVar(value="After")
        self._canvas_bounds = (0, 0, 0, 0)
        self._resize_job = None
        self._syncing_sliders = False
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self.value_labels: dict[str, ctk.CTkLabel] = {}
        self.scope = ctk.StringVar(value="Batch")
        self.configure(fg_color="#16181c")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Single compact chrome row; every action here is a working command.
        # Keep its width bounded at the 1000px minimum instead of placing a
        # second full-width toolbar between the photo and the title.
        header = self.header = self.toolbar = ctk.CTkFrame(
            self, height=48, fg_color="#1c1e22", corner_radius=0)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_propagate(False)
        ctk.CTkLabel(header, text="IS", width=29, height=29, fg_color="#19539a",
                     corner_radius=5, font=ctk.CTkFont(size=14, weight="bold")).pack(
                         side="left", padx=(10, 7), pady=8)
        ctk.CTkLabel(header, text="Image Switcher", text_color="#f3f5f9",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left", padx=(0, 8))
        for text, width, action in (("Add", 56, self.add_files), ("Open", 56, self.open_session),
                                    ("Save", 56, self.save_session), ("Project", 67, self.open_project),
                                    ("Crop", 56, self.open_crop_tools),
                                    ("Background", 91, self.open_background_tools)):
            ctk.CTkButton(header, text=text, command=action, height=30, width=width,
                          fg_color="#30343a", hover_color="#424b56", corner_radius=5,
                          font=ctk.CTkFont(size=11)).pack(side="left", padx=2, pady=8)
        ctk.CTkButton(header, text="Export", width=104, height=32, fg_color="#2468b9",
                      hover_color="#337dd2", command=self.export).pack(side="right", padx=(3, 10))
        ctk.CTkSegmentedButton(header, variable=self.scope, values=["Selected", "Batch"],
                               width=130, height=30, selected_color="#205da7",
                               selected_hover_color="#286cbe", command=lambda _: self.sync_sliders()).pack(
                                   side="right", padx=(2, 6))
        ctk.CTkLabel(header, text="Scope", text_color="#abb3bd",
                     font=ctk.CTkFont(size=11)).pack(side="right", padx=3)
        ctk.CTkButton(header, text="Unlock", command=self.unlock, width=64, height=30,
                      fg_color="#30343a", hover_color="#424b56",
                      font=ctk.CTkFont(size=11)).pack(side="right", padx=3)

        sidebar = self.sidebar = ctk.CTkFrame(self, width=164, fg_color="#1f2227", corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        rail_top = ctk.CTkFrame(sidebar, fg_color="transparent")
        rail_top.pack(fill="x", padx=10, pady=(12, 6))
        ctk.CTkLabel(rail_top, text="PHOTOS", anchor="w", text_color="#c8cdd6",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.batch_count = ctk.CTkLabel(rail_top, text="0", width=27, height=23,
                                        corner_radius=7, fg_color="#343a43")
        self.batch_count.pack(side="right")
        self.items = ctk.CTkScrollableFrame(sidebar, width=138, fg_color="transparent")
        self.items.pack(fill="both", expand=True, padx=3, pady=2)
        ctk.CTkLabel(sidebar, text="Protected edits stay in batch",
                     text_color="#aab0b9", wraplength=155, font=ctk.CTkFont(size=10)).pack(pady=7)

        workspace = self.workspace = ctk.CTkFrame(self, fg_color="#17191d", corner_radius=0)
        workspace.grid(row=1, column=1, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(workspace, bg="#17191d", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.canvas.bind("<Button-1>", self.paint_mask)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        footer = ctk.CTkFrame(workspace, height=50, fg_color="#1b1e23", corner_radius=0)
        footer.grid(row=1, column=0, sticky="ew")
        self.status = ctk.CTkLabel(footer, text="Add still photos to begin", anchor="w",
                                   text_color="#aab0b9", font=ctk.CTkFont(size=11))
        self.status.pack(side="left", padx=15, fill="x", expand=True)
        ctk.CTkLabel(footer, text="Fit preview · full resolution on export", text_color="#858e9b",
                     font=ctk.CTkFont(size=10)).pack(side="right", padx=(5, 15))
        ctk.CTkSegmentedButton(footer, variable=self.view_mode, values=["Before", "After"],
                               width=138, height=30, selected_color="#205da7",
                               command=lambda _: self.show_current()).pack(side="right", padx=5, pady=8)

        panel = self.panel = ctk.CTkScrollableFrame(self, width=295, fg_color="#21252b", corner_radius=0)
        panel.grid(row=1, column=2, sticky="nsew")
        ctk.CTkLabel(panel, text="ADJUSTMENTS", anchor="w", text_color="#c9ced7",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(fill="x", padx=12, pady=(12, 10))
        # Real capabilities only: do not create fake Whites/Clarity/Denoise
        # controls simply because the AI mockup drew them.
        for field, (low, high) in EDIT_FIELDS.items():
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(0, 10))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=field.replace("_", " ").title(), anchor="w",
                         width=80, font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w", padx=(0, 5))
            slider = ctk.CTkSlider(row, from_=low, to=high, number_of_steps=200, width=120, height=14,
                                   button_length=14, progress_color="#2764a9", fg_color="#434850",
                                   command=lambda value, key=field: self.change_value(key, value))
            slider.grid(row=0, column=1, sticky="ew")
            label = ctk.CTkLabel(row, text="+0.00", anchor="e", width=45,
                                 font=ctk.CTkFont(size=10), text_color="#bbc1cc")
            label.grid(row=0, column=2, padx=(7, 0))
            self.sliders[field] = slider
            self.value_labels[field] = label
        self.sync_sliders()
        self.refresh_list()
        self.show_current()

    def error(self, exc):
        messagebox.showerror("Photo editor", str(exc), parent=self)
        self.status.configure(text=str(exc)[:100])

    def add_files(self):
        if self.importing or self.busy:
            return
        paths = filedialog.askopenfilenames(parent=self, title="Choose still photos",
                                           filetypes=[("Still photos", " ".join("*" + ext for ext in sorted(STILL_EXTENSIONS))),
                                                      ("All files", "*.*")])
        if paths:
            self.start_import(paths)

    def start_import(self, paths):
        """Validate/decode off the UI thread; add numbered photos on Tk's thread."""
        if self.importing or self.busy or not paths:
            return
        self.close_crop_tools()
        self.close_background_tools()
        self.importing = True
        self._import_cancel = threading.Event()
        self._import_queue = Queue()
        self._import_errors = []
        self._import_total = len(paths)
        self._import_processed = 0
        self._import_added = 0
        self.import_dialog = ImportProgress(self, len(paths), self._import_cancel)
        self.status.configure(text=f"Preparing {len(paths)} selected file(s)…")
        thread = threading.Thread(target=self._import_worker,
                                  args=(tuple(paths), self._import_queue, self._import_cancel), daemon=True)
        thread.start()
        self.after(50, self._drain_import)

    @staticmethod
    def _import_worker(paths, results: Queue, cancel: threading.Event):
        try:
            for path in paths:
                if cancel.is_set():
                    break
                try:
                    frames = []
                    for index in still_photo_frames(path):
                        if cancel.is_set():
                            break
                        source_info(path, frame_index=index)
                        frames.append((index, _thumbnail_pixels(path, index)))
                    if not cancel.is_set():
                        results.put((path, frames, None))
                except Exception as exc:
                    results.put((path, [], str(exc)))
        finally:
            results.put((None, [], None))

    def _drain_import(self):
        done = False
        try:
            # Bound UI-thread work per tick so progress/cancel stays responsive
            # even when a fast validation thread queues hundreds of files.
            for _ in range(12):
                path, frames, error = self._import_queue.get_nowait()
                if path is None:
                    done = True
                    break
                self._import_processed += 1
                if error:
                    self._import_errors.append(f"{Path(path).name}: {error}")
                else:
                    for index, image in frames:
                        photo = self.batch.add_photo(path, frame_index=index)
                        self._thumbnail_cache[photo.id] = ctk.CTkImage(
                            light_image=image, dark_image=image, size=(104, 61))
                        self.current = photo.number
                        self._import_added += 1
                self.import_dialog.show_progress(self._import_processed, self._import_added,
                                                  Path(path).name)
        except Empty:
            pass
        if not done:
            self.after(50, self._drain_import)
            return
        canceled = self._import_cancel.is_set()
        self.import_dialog.progress_text.configure(text="Updating thumbnail rail…")
        self.import_dialog.update_idletasks()
        self.refresh_list()
        self.sync_sliders()
        self.show_current()
        self.importing = False
        self.import_dialog.close()
        self.import_dialog = None
        self.status.configure(text=(f"{'Stopped' if canceled else 'Finished'}: "
                                    f"{self._import_added} photo(s) added from "
                                    f"{self._import_processed}/{self._import_total} file(s); "
                                    f"{len(self._import_errors)} failed"))
        if self._import_errors:
            first = "\n".join(self._import_errors[:3])
            extra = f"\n…and {len(self._import_errors)-3} more." if len(self._import_errors) > 3 else ""
            messagebox.showwarning("Some still photos were not added",
                                   f"{len(self._import_errors)} file(s) could not be read.\n\n"
                                   f"{first}{extra}\n\nSuccessfully added photos remain in the batch.", parent=self)

    def thumbnail(self, photo):
        """Cache a small original preview; never re-render full-resolution photos for the rail."""
        if photo.id not in self._thumbnail_cache:
            try:
                rgb = _thumbnail_pixels(photo.source, photo.frame_index)
            except Exception:
                rgb = Image.new("RGB", (104, 61), "#343943")
            self._thumbnail_cache[photo.id] = ctk.CTkImage(light_image=rgb, dark_image=rgb,
                                                            size=(104, 61))
        return self._thumbnail_cache[photo.id]

    def refresh_list(self):
        for child in self.items.winfo_children():
            child.destroy()
        self.batch_count.configure(text=str(len(self.batch.photos)))
        for photo in self.batch.photos:
            selected = photo.number == self.current
            tile = ctk.CTkFrame(self.items, height=84, corner_radius=4,
                                fg_color="#23446b" if selected else "#282c32")
            tile.pack(fill="x", pady=3)
            tile.pack_propagate(False)
            ctk.CTkLabel(tile, text=str(photo.number), width=23, height=21,
                         corner_radius=3, fg_color="#101317", text_color="#e0e5ed",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
            thumbnail_column = ctk.CTkFrame(tile, fg_color="transparent")
            thumbnail_column.pack(side="left", fill="y")
            ctk.CTkButton(thumbnail_column, text="", image=self.thumbnail(photo),
                          width=104, height=61, border_width=2 if selected else 0,
                          border_color="#5195e9", fg_color="#30353c",
                          hover_color="#375273", corner_radius=3,
                          command=lambda n=photo.number: self.select(n)).pack()
            ctk.CTkLabel(thumbnail_column,
                         text=("LOCKED · " if photo.protected else "") + Path(photo.source).stem[:11],
                         width=104, height=18, anchor="w", text_color="#8dc0ff" if photo.protected else "#abb3bd",
                         font=ctk.CTkFont(size=9)).pack()
        if self.batch.photos:
            self.status.configure(text=f"{len(self.batch.photos)} photos · protected: {self.batch.excluded_numbers} · full batch includes all")
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
        if not self.mask_painting or self.current is None or self.view_mode.get() != "After":
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
            before = self.view_mode.get() == "Before"
            if before:
                image, _, _ = _open_source(photo.source, preview=True, frame_index=photo.frame_index)
            else:
                image, _, _ = render(photo, self.batch, preview=True)
            if not isinstance(image, Image.Image):
                image = Image.fromarray((image / 257).astype("uint8"))
            image.thumbnail((canvas_w-20, canvas_h-20), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
            width, height = image.size
            left, top = (canvas_w-width)//2, (canvas_h-height)//2
            self._canvas_bounds = (left, top, width, height)
            self.canvas.create_image(left, top, anchor="nw", image=self._preview_image)
            state = "🔒 Protected" if photo.protected else "Batch"
            kind = "Source preview" if before else "Edited preview"
            self.status.configure(text=f"#{photo.number:04d} · {state} · {kind} · {Path(photo.source).name[:28]}")
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
                self._thumbnail_cache.clear()
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
        if self.busy or self.importing:
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
        ctk.CTkLabel(self, text="Select After, then click the photo to paint.\n"
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
        self.title("Export photos")
        self.resizable(False, False)
        self.transient(editor)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.shade = None
        try:
            shade = ctk.CTkToplevel(editor)
            self.shade = shade
            shade.overrideredirect(True)
            shade.configure(fg_color="#000000")
            shade.attributes("-alpha", 0.42)
            shade.geometry(f"{editor.winfo_width()}x{editor.winfo_height()}+"
                           f"{editor.winfo_rootx()}+{editor.winfo_rooty()}")
            shade.lift(editor)
            self.shade = shade
        except tk.TclError:
            if self.shade and self.shade.winfo_exists():
                self.shade.destroy()
            self.shade = None  # platform cannot dim: modal must still work
        width, height = 530, 575
        x = editor.winfo_rootx() + max(0, (editor.winfo_width()-width)//2)
        y = editor.winfo_rooty() + max(0, (editor.winfo_height()-height)//2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.configure(fg_color="#25282d")
        self.lift(self.shade if self.shade else editor)

        ctk.CTkLabel(self, text="Export photos", anchor="w",
                     font=ctk.CTkFont(size=19, weight="bold")).pack(fill="x", padx=26, pady=(18, 14))
        ctk.CTkLabel(self, text="Destination", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=26)
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.pack(fill="x", padx=24, pady=(5, 12))
        self.folder = ctk.StringVar()
        ctk.CTkEntry(path_row, textvariable=self.folder, placeholder_text="Choose an export folder",
                     width=365, fg_color="#1d2025").pack(side="left", padx=(0, 8))
        ctk.CTkButton(path_row, text="Browse", width=95, command=self.browse,
                      fg_color="#363d47").pack(side="left")

        ctk.CTkLabel(self, text="Export scope", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=26)
        self.selection = ctk.StringVar(value="Entire numbered batch (includes protected)")
        ctk.CTkRadioButton(self, text="Entire numbered batch (includes protected)",
                           variable=self.selection, value="Entire numbered batch (includes protected)").pack(anchor="w", padx=29, pady=(6, 4))
        if editor.current is not None:
            ctk.CTkRadioButton(self, text=f"Selected photo #{editor.current:04d} only",
                               variable=self.selection, value=f"Selected photo #{editor.current:04d} only").pack(anchor="w", padx=29, pady=(0, 12))
        else:
            ctk.CTkLabel(self, text="Select a photo to enable single-photo export.",
                         text_color="#939ca8", anchor="w").pack(fill="x", padx=56, pady=(0, 12))

        ctk.CTkLabel(self, text="Format", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=26)
        ctk.CTkLabel(self, text="Lossless PNG (8-bit)  /  16-bit TIFF (NEF) — automatic",
                     fg_color="#1d2025", corner_radius=6, anchor="w", height=32,
                     text_color="#d2d9e3").pack(fill="x", padx=25, pady=(4, 3))
        ctk.CTkLabel(self, text="The decoded JPG cannot regain detail discarded by the source.",
                     text_color="#aab3be", anchor="w", font=ctk.CTkFont(size=10)).pack(fill="x", padx=27, pady=(0, 11))
        self.project_included = ctk.IntVar(value=1)
        ctk.CTkCheckBox(self, text="Include .isphoto project and untouched original",
                        variable=self.project_included, state="disabled", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=28, pady=(0, 12))

        ctk.CTkLabel(self, text="Project rights (unsigned declarations)", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=26)
        self.creator = ctk.CTkEntry(self, placeholder_text="Creator name (optional)", width=480,
                                    fg_color="#1d2025")
        self.creator.pack(padx=25, pady=(5, 4))
        self.creator.insert(0, editor.batch.rights.get("creator", ""))
        self.notice = ctk.CTkEntry(self, placeholder_text="Copyright notice (optional)", width=480,
                                   fg_color="#1d2025")
        self.notice.pack(padx=25, pady=(0, 8))
        self.notice.insert(0, editor.batch.rights.get("copyright_notice", ""))
        ctk.CTkLabel(self, text="No signed credential or watermark. Rights are stored in .isphoto only.",
                     text_color="#d6a773", font=ctk.CTkFont(size=10)).pack(padx=25, pady=(0, 7))
        ctk.CTkLabel(self, text="Existing output names stop export; files are never overwritten.",
                     text_color="#bbc4cf", font=ctk.CTkFont(size=11)).pack(padx=25, pady=(0, 7))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(anchor="e", padx=25, pady=(4, 14))
        ctk.CTkButton(actions, text="Cancel", width=100, fg_color="#363d47",
                      command=self.close).pack(side="left", padx=(0, 9))
        ctk.CTkButton(actions, text="Export now", width=115, fg_color="#1e64b8",
                      command=self.confirm).pack(side="left")
        self.after_idle(self._grab_when_visible)

    def _grab_when_visible(self):
        if self.winfo_exists():
            try:
                self.lift(self.shade if self.shade and self.shade.winfo_exists() else self.editor)
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
        if self.shade and self.shade.winfo_exists():
            self.shade.destroy()
        self.destroy()
