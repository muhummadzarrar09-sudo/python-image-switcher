"""Desktop UI for numbered, non-destructive still-photo batches.

Adjustments are visible as named sliders. Crop/background controls live in their
own editing tools, while export settings appear only after clicking Export.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
from pathlib import Path
from queue import Empty, Full, Queue
import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageColor, ImageTk

from .batch import BatchSession, EDIT_FIELDS
from .gpu_preview import OpenCLPreview, eligible_export
from .preview import PreviewRenderer, PreviewRequest, mask_point, preview_label
from .render import STILL_EXTENSIONS, edited_size, source_info, still_photo_frames, _open_source
from .workflow import export_batch, import_project, plan_export
from .version import ALPHA_VERSION
from .window_geometry import place_popup


def _thumbnail_pixels(path: str, frame_index: int) -> Image.Image:
    """Decode a tiny still in a worker; CTkImage creation stays on the UI thread."""
    background = Image.new("RGBA", (104, 61), "#343943")
    image, _, _ = _open_source(path, preview=True, frame_index=frame_index,
                               preview_size=(104, 61))
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


RAIL_PAGE_SIZE = 48  # bound Tk widget count, independent of batch size
THUMB_CACHE_LIMIT = 192  # four rail pages of small decoded thumbnails


class EditorWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title(f"Image Switcher | Still Photo Editor {ALPHA_VERSION}")
        # CTk scales geometry/minsize in logical units. Keep the minimum in
        # physical pixels across display scales instead of turning a 1000x700
        # request into an unavoidable 1500x1050 window at 150%.
        scale = self._get_window_scaling()
        self.geometry(f"{round(1456 / scale)}x{round(766 / scale)}")
        self.minsize(round(960 / scale), round(640 / scale))
        self.batch = BatchSession()
        self.session_path: str | None = None
        self.current: int | None = None
        self.busy = False
        self.importing = False
        self.import_dialog: ImportProgress | None = None
        self._import_queue: Queue | None = None
        self._import_cancel: threading.Event | None = None
        self._import_closing = threading.Event()
        self._import_errors: list[str] = []
        self._import_job = None
        self._export_queue: Queue | None = None
        self._export_poll_job = None
        self.brush_add = True
        self.mask_painting = False
        self.crop_window: CropTools | None = None
        self.background_window: BackgroundTools | None = None
        self._preview_image = None
        self._thumbnail_cache: OrderedDict[str, ctk.CTkImage] = OrderedDict()
        self._tiles: dict[str, tuple[ctk.CTkFrame, ctk.CTkButton, ctk.CTkLabel]] = {}
        self._tile_states: dict[str, tuple[bool, bool, str]] = {}
        self._rail_page = 0
        self.view_mode = ctk.StringVar(value="After")
        self._canvas_bounds = (0, 0, 0, 0)
        self._resize_job = None
        self._preview_renderer = PreviewRenderer()
        self._preview_generation = 0
        self._preview_job = None
        self._preview_poll_job = None
        self._gpu_status_job = None
        self._displayed_number: int | None = None
        self._displayed_generation = -1
        self._syncing_sliders = False
        self.sliders: dict[str, ctk.CTkSlider] = {}
        self.value_labels: dict[str, ctk.CTkLabel] = {}
        self.scope = ctk.StringVar(value="Batch")
        self.configure(fg_color="#16181c")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Two groups share one row on roomy displays and stack on narrow/high
        # DPI clients. Never let Tk's packer silently collapse an action.
        header = self.header = self.toolbar = ctk.CTkFrame(
            self, height=48, fg_color="#1c1e22", corner_radius=0)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_propagate(False)
        header_left = ctk.CTkFrame(header, height=48, fg_color="transparent")
        header_right = ctk.CTkFrame(header, height=48, fg_color="transparent")
        header_left.pack(side="left")
        header_right.pack(side="right")
        ctk.CTkLabel(header_left, text="IS", width=29, height=29, fg_color="#19539a",
                     corner_radius=5, font=ctk.CTkFont(size=14, weight="bold")).pack(
                         side="left", padx=(10, 7), pady=8)
        self._brand_icon = header_left.winfo_children()[0]
        self._brand_label = ctk.CTkLabel(header_left, text="Image Switcher", text_color="#f3f5f9",
                                          font=ctk.CTkFont(size=15, weight="bold"))
        self._brand_label.pack(side="left", padx=(0, 8))
        self._brand_visible = True
        for text, width, action in (("Add", 56, self.add_files), ("Open", 56, self.open_session),
                                    ("Save", 56, self.save_session), ("Project", 67, self.open_project),
                                    ("Crop", 56, self.open_crop_tools),
                                    ("Background", 91, self.open_background_tools)):
            ctk.CTkButton(header_left, text=text, command=action, height=30, width=width,
                          fg_color="#30343a", hover_color="#424b56", corner_radius=5,
                          font=ctk.CTkFont(size=11)).pack(side="left", padx=2, pady=8)
        ctk.CTkButton(header_right, text="Export", width=104, height=32, fg_color="#2468b9",
                      hover_color="#337dd2", command=self.export).pack(side="right", padx=(3, 10))
        ctk.CTkSegmentedButton(header_right, variable=self.scope, values=["Selected", "Batch"],
                               width=130, height=30, selected_color="#205da7",
                               selected_hover_color="#286cbe", command=lambda _: self.sync_sliders()).pack(
                                   side="right", padx=(2, 6))
        ctk.CTkLabel(header_right, text="Scope", text_color="#abb3bd",
                     font=ctk.CTkFont(size=11)).pack(side="right", padx=3)
        ctk.CTkButton(header_right, text="Unlock", command=self.unlock, width=64, height=30,
                      fg_color="#30343a", hover_color="#424b56",
                      font=ctk.CTkFont(size=11)).pack(side="right", padx=3)
        self._header_left = header_left
        self._header_right = header_right
        self._header_wrapped = False
        header.bind("<Configure>", self._layout_header)

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
        rail_nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        rail_nav.pack(fill="x", padx=5, pady=(3, 1))
        self.prev_page = ctk.CTkButton(rail_nav, text="‹", width=32, height=26,
                                       command=lambda: self.change_rail_page(-1))
        self.prev_page.pack(side="left")
        self.page_label = ctk.CTkLabel(rail_nav, text="0 / 0", width=80,
                                       text_color="#b9c3cf", font=ctk.CTkFont(size=10))
        self.page_label.pack(side="left", expand=True)
        self.next_page = ctk.CTkButton(rail_nav, text="›", width=32, height=26,
                                       command=lambda: self.change_rail_page(1))
        self.next_page.pack(side="right")
        self.gpu_state_label = ctk.CTkLabel(sidebar, text="GPU: checking…", text_color="#aab0b9",
                                            wraplength=150, font=ctk.CTkFont(size=10))
        self.gpu_state_label.pack(pady=(2, 0))
        ctk.CTkLabel(sidebar, text="Protected edits stay in batch",
                     text_color="#aab0b9", wraplength=155, font=ctk.CTkFont(size=10)).pack(pady=7)

        workspace = self.workspace = ctk.CTkFrame(self, fg_color="#17191d", corner_radius=0)
        workspace.grid(row=1, column=1, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=1)
        # Tk Canvas defaults to a ~394px requested width, which forces the
        # adjustments outside a 1000px physical client at 150% scaling.
        # The weighted grid expands this small request when space is available.
        self.canvas = tk.Canvas(workspace, width=120, height=120,
                                bg="#17191d", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.canvas.bind("<Button-1>", self.paint_mask)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        footer = self.footer = ctk.CTkFrame(workspace, height=50, fg_color="#1b1e23", corner_radius=0)
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_propagate(False)  # labels must not enlarge the workspace column
        self.status = ctk.CTkLabel(footer, text="Add still photos to begin", anchor="w",
                                   text_color="#aab0b9", font=ctk.CTkFont(size=11))
        self.status.pack(side="left", padx=15, fill="x", expand=True)
        self.footer_hint = ctk.CTkLabel(footer, text="Fit preview · original-size master on export",
                                        text_color="#858e9b", font=ctk.CTkFont(size=10))
        self.footer_hint.pack(side="right", padx=(5, 15))
        self.footer_view = ctk.CTkSegmentedButton(footer, variable=self.view_mode,
                                                  values=["Before", "After"], width=138, height=30,
                                                  selected_color="#205da7", command=lambda _: self.show_current())
        self.footer_view.pack(side="right", padx=5, pady=8)
        footer.bind("<Configure>", self._layout_footer)

        panel = self.panel = ctk.CTkScrollableFrame(self, width=295, fg_color="#21252b", corner_radius=0)
        panel.grid(row=1, column=2, sticky="nsew")
        self.panel_heading = ctk.CTkLabel(panel, text="ADJUSTMENTS", anchor="w",
                                           text_color="#c9ced7", font=ctk.CTkFont(size=11, weight="bold"))
        self.panel_heading.pack(fill="x", padx=12, pady=(12, 10))
        self.panel_view = ctk.CTkSegmentedButton(panel, variable=self.view_mode,
                                                 values=["Before", "After"], width=138, height=30,
                                                 selected_color="#205da7", command=lambda _: self.show_current())
        self._compact_footer = False
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
        self._poll_gpu_status()

    def _layout_footer(self, event):
        # CTkFrame.bind attaches to its internal Tk canvas, not the frame.
        if event.widget != self.footer._canvas:
            return
        compact = event.width < 500
        if compact == self._compact_footer:
            return
        self._compact_footer = compact
        if compact:
            self.footer_hint.pack_forget()
            self.footer_view.pack_forget()
            self.panel_view.pack(fill="x", padx=12, pady=(0, 8), after=self.panel_heading)
        else:
            self.panel_view.pack_forget()
            self.footer_hint.pack(side="right", padx=(5, 15))
            self.footer_view.pack(side="right", padx=5, pady=8)

    def _layout_header(self, event):
        if event.widget != self.header._canvas:
            return
        show_brand = event.width >= 1100
        if show_brand != self._brand_visible:
            if show_brand:
                self._brand_label.pack(side="left", after=self._brand_icon, padx=(0, 8))
            else:
                self._brand_label.pack_forget()
            self._brand_visible = show_brand
        needed = self._header_left.winfo_reqwidth() + self._header_right.winfo_reqwidth() + 8
        wrap = event.width < needed
        if wrap == self._header_wrapped:
            return
        self._header_wrapped = wrap
        self._header_left.pack_forget()
        self._header_right.pack_forget()
        if wrap:
            self._header_left.pack(side="top", anchor="w")
            self._header_right.pack(side="top", anchor="e")
        else:
            self._header_left.pack(side="left")
            self._header_right.pack(side="right")
        self.header.configure(height=96 if wrap else 48)

    def _poll_gpu_status(self):
        status = self._preview_renderer.gpu_status
        self.gpu_state_label.configure(text=status)
        self._gpu_status_job = self.after(250 if status == "checking" else 1500,
                                          self._poll_gpu_status)

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
        # The worker cannot decode hundreds of photos ahead of the UI and
        # retain all their Pillow images while the progress window catches up.
        self._import_queue = Queue(maxsize=24)
        self._import_errors = []
        self._import_total = len(paths)
        self._import_processed = 0
        self._import_added = 0
        self.import_dialog = ImportProgress(self, len(paths), self._import_cancel)
        self.status.configure(text=f"Preparing {len(paths)} selected file(s)…")
        thread = threading.Thread(target=self._import_worker,
                                  args=(tuple(paths), self._import_queue, self._import_cancel,
                                        self._import_closing), daemon=True)
        thread.start()
        self._import_job = self.after(50, self._drain_import)

    @staticmethod
    def _import_worker(paths, results: Queue, cancel: threading.Event,
                       closing: threading.Event | None = None):
        closing = closing or threading.Event()

        def send(item):
            while not closing.is_set():
                try:
                    results.put(item, timeout=.1)
                    return
                except Full:
                    pass  # keep only a small, bounded queue of decoded stills

        try:
            for path in paths:
                if cancel.is_set() or closing.is_set():
                    break
                try:
                    frames = []
                    for index in still_photo_frames(path):
                        if cancel.is_set() or closing.is_set():
                            break
                        source_info(path, frame_index=index)
                        frames.append((index, _thumbnail_pixels(path, index)))
                    if not cancel.is_set() and not closing.is_set():
                        send((path, frames, None))
                except Exception as exc:
                    send((path, [], str(exc)))
        finally:
            send((None, [], None))

    def _drain_import(self):
        self._import_job = None
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
                        self._remember_thumbnail(photo.id, ctk.CTkImage(
                            light_image=image, dark_image=image, size=(104, 61)))
                        self.current = photo.number
                        self._import_added += 1
                self.import_dialog.show_progress(self._import_processed, self._import_added,
                                                  Path(path).name)
        except Empty:
            pass
        if not done:
            self._import_job = self.after(50, self._drain_import)
            return
        canceled = self._import_cancel.is_set()
        self.import_dialog.progress_text.configure(text="Updating thumbnail rail…")
        self.import_dialog.update_idletasks()
        if self.current is not None:
            self._rail_page = (len(self.batch.photos) - 1) // RAIL_PAGE_SIZE
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

    def _remember_thumbnail(self, photo_id: str, image: ctk.CTkImage):
        self._thumbnail_cache[photo_id] = image
        self._thumbnail_cache.move_to_end(photo_id)
        while len(self._thumbnail_cache) > THUMB_CACHE_LIMIT:
            self._thumbnail_cache.popitem(last=False)

    def thumbnail(self, photo):
        """Keep a bounded LRU of small rail images; never cache full frames."""
        if photo.id not in self._thumbnail_cache:
            try:
                rgb = _thumbnail_pixels(photo.source, photo.frame_index)
            except Exception:
                rgb = Image.new("RGB", (104, 61), "#343943")
            self._remember_thumbnail(photo.id, ctk.CTkImage(light_image=rgb, dark_image=rgb,
                                                              size=(104, 61)))
        else:
            self._thumbnail_cache.move_to_end(photo.id)
        return self._thumbnail_cache[photo.id]

    def refresh_list(self):
        """Retain visible tiles; never create 400+ Tk widget trees at once."""
        total = len(self.batch.photos)
        pages = (total + RAIL_PAGE_SIZE - 1) // RAIL_PAGE_SIZE
        self._rail_page = min(self._rail_page, max(0, pages - 1))
        visible = self.batch.photos[self._rail_page * RAIL_PAGE_SIZE:
                                    (self._rail_page + 1) * RAIL_PAGE_SIZE]
        live = {photo.id for photo in visible}
        for photo_id in set(self._tiles) - live:
            self._tiles.pop(photo_id)[0].destroy()
            self._tile_states.pop(photo_id, None)
        # A small LRU avoids repeated camera decode for recent pages without
        # retaining one Pillow/CTkImage forever for every batch entry.
        all_ids = {photo.id for photo in self.batch.photos}
        for photo_id in set(self._thumbnail_cache) - all_ids:
            self._thumbnail_cache.pop(photo_id, None)
        self.batch_count.configure(text=str(total))
        self.page_label.configure(text=f"{self._rail_page + 1} / {pages}" if pages else "0 / 0")
        self.prev_page.configure(state="normal" if self._rail_page > 0 else "disabled")
        self.next_page.configure(state="normal" if self._rail_page + 1 < pages else "disabled")
        for photo in visible:
            if photo.id not in self._tiles:
                tile = ctk.CTkFrame(self.items, height=84, corner_radius=4,
                                    fg_color="#282c32")
                tile.pack(fill="x", pady=3)
                tile.pack_propagate(False)
                ctk.CTkLabel(tile, text=str(photo.number), width=23, height=21,
                             corner_radius=3, fg_color="#101317", text_color="#e0e5ed",
                             font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 2))
                thumbnail_column = ctk.CTkFrame(tile, fg_color="transparent")
                thumbnail_column.pack(side="left", fill="y")
                button = ctk.CTkButton(thumbnail_column, text="", image=self.thumbnail(photo),
                                       width=104, height=61, border_width=0,
                                       border_color="#5195e9", fg_color="#30353c",
                                       hover_color="#375273", corner_radius=3,
                                       command=lambda n=photo.number: self.select(n))
                button.pack()
                caption = ctk.CTkLabel(thumbnail_column, text="", width=104, height=18,
                                       anchor="w", text_color="#abb3bd",
                                       font=ctk.CTkFont(size=9))
                caption.pack()
                self._tiles[photo.id] = (tile, button, caption)
            selected = photo.number == self.current
            state = (selected, photo.protected, Path(photo.source).stem[:11])
            if self._tile_states.get(photo.id) != state:
                tile, button, caption = self._tiles[photo.id]
                tile.configure(fg_color="#23446b" if selected else "#282c32")
                button.configure(border_width=2 if selected else 0)
                caption.configure(text=("LOCKED · " if photo.protected else "") + state[2],
                                  text_color="#8dc0ff" if photo.protected else "#abb3bd")
                self._tile_states[photo.id] = state
        if self.batch.photos:
            self.status.configure(text=f"{len(self.batch.photos)} photos · protected: {self.batch.excluded_numbers} · full batch includes all")
        else:
            self.status.configure(text="Add still photos to begin")

    def change_rail_page(self, delta: int):
        pages = (len(self.batch.photos) + RAIL_PAGE_SIZE - 1) // RAIL_PAGE_SIZE
        self._rail_page = max(0, min(self._rail_page + delta, pages - 1))
        self.refresh_list()
        self.items._parent_canvas.yview_moveto(0)

    def select(self, number: int):
        self.close_crop_tools()
        self.close_background_tools()
        self.current = number
        self._rail_page = next(i // RAIL_PAGE_SIZE for i, photo in enumerate(self.batch.photos)
                               if photo.number == number)
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
            if Path(self.selected_photo().source).suffix.lower() == ".nef":
                raise ValueError("16-bit NEF background masking is not available; no edit was made")
            if self.background_window and self.background_window.winfo_exists():
                self.background_window.lift()
                self.background_window.focus_force()
            else:
                self.background_window = BackgroundTools(self)
                self.mask_painting = True
            self._sync_mask_status()
        except Exception as exc:
            self.error(exc)

    def close_background_tools(self):
        self.mask_painting = False
        self.canvas.configure(cursor="")
        if self.background_window and self.background_window.winfo_exists():
            self.background_window.destroy()
        self.background_window = None

    def _mask_state(self) -> tuple[bool, str]:
        """Painting is armed only for the current, valid After image and tool."""
        if (not self.mask_painting or not self.background_window
                or not self.background_window.winfo_exists()):
            return False, "Open Background to edit the manual mask."
        if self.busy or self.importing:
            return False, "Wait for the current operation to finish."
        try:
            photo = self.selected_photo()
        except (ValueError, KeyError):
            return False, "Choose a numbered photo first."
        if not Path(photo.source).is_file():
            return False, "Source photo is missing; restore it before painting."
        if self.view_mode.get() != "After":
            return False, "Select After to paint the manual mask."
        if not photo.background:
            return False, "Choose a background effect before painting."
        if (self._displayed_number != photo.number
                or self._displayed_generation != self._preview_generation
                or not self._canvas_bounds[2] or not self._canvas_bounds[3]):
            return False, "Waiting for this photo's updated preview…"
        return True, f"Mask ready · {len(photo.mask_strokes)} stroke(s). Click photo to paint; Erase corrects mistakes."

    def _sync_mask_status(self):
        ready, text = self._mask_state()
        self.canvas.configure(cursor="crosshair" if ready else "")
        if self.background_window and self.background_window.winfo_exists():
            self.background_window.mask_status.configure(text=text,
                                                          text_color="#a7d6ff" if ready else "#d2b889")
        return ready

    def set_background(self, mode: str, *, color: str = "#ffffff", source: str | None = None):
        photo = self.selected_photo()
        if mode != "none" and Path(photo.source).suffix.lower() == ".nef":
            raise ValueError("16-bit NEF background masking is not available; the photo was not changed")
        if mode == "image":
            if not source:
                raise ValueError("Choose a replacement image")
            replacement = source_info(source)
            if replacement["raw"]:
                raise ValueError("NEF replacement requires 16-bit compositing, not yet implemented")
            target_width, target_height = edited_size(photo)
            bg_width, bg_height = replacement["size"]
            if bg_width < target_width or bg_height < target_height:
                raise ValueError("Replacement image would be upscaled; choose a larger image")
            settings = {"mode": mode, "source": source}
        elif mode in ("blur", "remove", "color"):
            if mode == "color":
                ImageColor.getrgb(color)  # fail before changing the edit recipe
            settings = {"mode": mode, "color": color}
        elif mode == "none":
            settings = {}
        else:
            raise ValueError("Unknown background mode")
        if settings == photo.background:
            self._sync_mask_status()
            return  # choosing the existing mode is not a new protected edit
        self.batch.protect(photo.number)
        photo.background = settings
        self.refresh_list()
        self.show_current()

    def clear_mask(self):
        photo = self.selected_photo()
        if not photo.mask_strokes:
            return  # an empty mask is not a per-photo edit or a protection change
        self.batch.protect(photo.number)
        photo.mask_strokes.clear()
        self.refresh_list()
        self.show_current()

    def undo_mask_stroke(self):
        photo = self.selected_photo()
        if not photo.mask_strokes:
            return
        photo.mask_strokes.pop()
        self.show_current()

    def paint_mask(self, event):
        # A pending crop, rotation, resize or selection invalidates the old
        # displayed rectangle. Never map clicks through stale image bounds.
        if not self._sync_mask_status():
            return
        try:
            photo = self.selected_photo()
            point = mask_point(self._canvas_bounds, event.x, event.y)
            if point is None:
                return
            self.batch.add_mask_stroke(photo.number, *point, .035, add_background=self.brush_add)
            self.refresh_list()
            self.show_current()
        except Exception as exc:
            self.error(exc)

    def on_canvas_resize(self, _event):
        # Tk has already changed the widget dimensions here, but the old
        # displayed image bounds still belong to the previous size. Disarm
        # immediately; a delayed preview alone leaves a 150 ms paint window.
        self._displayed_generation = -1
        self._sync_mask_status()
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self.show_current)

    def show_current(self):
        """Schedule the latest canvas-size preview, without blocking Tk."""
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self._preview_generation += 1
        self._sync_mask_status()  # disarm clicks before a new crop/selection/preview starts
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
            self._preview_job = None
        canvas_w = max(100, self.canvas.winfo_width())
        canvas_h = max(100, self.canvas.winfo_height())
        if self.current is None:
            self._preview_image = None
            self._displayed_number = None
            self._displayed_generation = -1
            self._canvas_bounds = (0, 0, 0, 0)
            self.canvas.delete("all")
            self.canvas.create_text(canvas_w//2, canvas_h//2, text="Add still photos to begin",
                                    fill="#888", font=("Arial", 16))
            return
        if self._displayed_number != self.current:
            self.canvas.delete("all")
            self._canvas_bounds = (0, 0, 0, 0)
            self.canvas.create_text(canvas_w//2, canvas_h//2, text="Rendering preview…",
                                    fill="#abb3bd", font=("Arial", 13))
        # A single slider drag can send dozens of events. Keep only its final
        # value and retain the previous visible preview until the new one lands.
        self._preview_job = self.after(75, self._submit_preview)

    def _submit_preview(self):
        self._preview_job = None
        if self.current is None:
            return
        try:
            photo = deepcopy(self.selected_photo())
            settings = BatchSession(photos=[photo], batch_settings=dict(self.batch.batch_settings))
            request = PreviewRequest(self._preview_generation, photo, settings,
                                     self.view_mode.get() == "Before",
                                     (max(1, self.canvas.winfo_width()-20),
                                      max(1, self.canvas.winfo_height()-20)))
            self._preview_renderer.submit(request)
            if self._preview_poll_job is None:
                self._preview_poll_job = self.after(40, self._poll_preview)
        except Exception as exc:
            self._show_preview_error(str(exc))

    def _poll_preview(self):
        self._preview_poll_job = None
        if self.current is None:
            return
        result = self._preview_renderer.result()
        if result is None or result[0] != self._preview_generation:
            self._preview_poll_job = self.after(40, self._poll_preview)
            return
        _, image, error, gpu_used = result
        if error:
            self._show_preview_error(error)
            return
        try:
            canvas_w = max(100, self.canvas.winfo_width())
            canvas_h = max(100, self.canvas.winfo_height())
            image.thumbnail((canvas_w-20, canvas_h-20), Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
            width, height = image.size
            left, top = (canvas_w-width)//2, (canvas_h-height)//2
            self._canvas_bounds = (left, top, width, height)
            self.canvas.delete("all")
            self.canvas.create_image(left, top, anchor="nw", image=self._preview_image)
            photo = self.selected_photo()
            self._displayed_number = photo.number
            self._displayed_generation = self._preview_generation
            self._sync_mask_status()
            state = "Protected" if photo.protected else "Batch"
            kind = preview_label(photo.source, self.view_mode.get() == "Before")
            if gpu_used:
                kind += " · experimental GPU"
            self.status.configure(text=f"#{photo.number:04d} · {state} · {kind} · {Path(photo.source).name[:28]}")
        except Exception as exc:
            self._show_preview_error(str(exc))

    def _show_preview_error(self, error: str):
        self._displayed_generation = -1
        self._canvas_bounds = (0, 0, 0, 0)
        self._sync_mask_status()
        self.canvas.delete("all")
        if self.current is not None and not Path(self.selected_photo().source).is_file():
            number = self.current
            self.canvas.create_text(max(1, self.canvas.winfo_width()) // 2,
                                    max(1, self.canvas.winfo_height()) // 2,
                                    fill="#e4bd83", font=("Arial", 14), justify="center",
                                    text=f"Photo #{number:04d} source is missing\n"
                                         "Restore the original file, then reselect this photo.")
            self.status.configure(text=f"#{number:04d} · Source missing · restore the original and reselect")
        else:
            self.canvas.create_text(10, 20, anchor="nw", fill="orange", text=error[:105])
            self.status.configure(text=f"Preview failed: {error[:80]}")

    def destroy(self):
        # Workers never call Tk. Invalidate pending previews before destroying
        # the canvas so a late result cannot draw into a dead widget.
        self._import_closing.set()
        if self._import_cancel:
            self._import_cancel.set()
        self._preview_renderer.close()
        for job in (self._preview_job, self._preview_poll_job, self._resize_job,
                    self._import_job, self._gpu_status_job, self._export_poll_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        super().destroy()

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
                for tile, _, _ in self._tiles.values():
                    tile.destroy()
                self._tiles.clear()
                self._tile_states.clear()
                self._thumbnail_cache.clear()
                self.session_path = path
                self.current = self.batch.photos[0].number if self.batch.photos else None
                self._rail_page = 0
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
                self._rail_page = (len(self.batch.photos) - 1) // RAIL_PAGE_SIZE
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
        self._sync_mask_status()
        self._export_directory = directory
        count = len(snapshot.photos) if numbers is None else len(numbers)
        self.status.configure(text=f"Exporting 0/{count} numbered photos, including protected edits…")
        self._export_queue = Queue()  # small progress records, never decoded images

        def work():
            accelerator = None
            gpu_error = None
            if (os.environ.get("IMAGE_SWITCHER_GPU", "auto").lower() != "off"
                    and any(eligible_export(photo, snapshot) for photo in snapshot.photos
                            if numbers is None or photo.number in numbers)):
                try:
                    accelerator = OpenCLPreview()
                except Exception as exc:
                    gpu_error = str(exc)  # CPU fallback, no exports lost
            gpu_numbers, cpu_numbers = [], []

            def on_exported(number, done, total, used_gpu):
                (gpu_numbers if used_gpu else cpu_numbers).append(number)
                self._export_queue.put(("progress", number, done, (total, used_gpu)))

            try:
                results = export_batch(snapshot, directory, numbers=numbers,
                                       accelerator=accelerator, on_exported=on_exported)
                report_path, warning = None, None
                try:
                    # A per-number record is more useful than a readiness label
                    # or a long truncated popup for batches of 400+ photos.
                    fd, report_path = tempfile.mkstemp(prefix="batch-gpu-usage-", suffix=".json",
                                                        dir=directory)
                    with os.fdopen(fd, "w", encoding="utf-8") as output:
                        json.dump({"total_exported": len(results),
                                   "gpu_adjusted_photo_numbers": gpu_numbers,
                                   "cpu_photo_numbers": cpu_numbers,
                                   "gpu_device": getattr(accelerator, "device_name", None),
                                   "gpu_error": getattr(accelerator, "error", gpu_error),
                                   "scope": "8-bit RGB exposure/contrast color math only; "
                                            "decode and PNG/TIFF/.isphoto writing use CPU"}, output, indent=2)
                        output.write("\n")
                except OSError as exc:
                    warning = f"Could not save GPU usage report: {exc}"
                    if report_path:
                        try:
                            os.unlink(report_path)
                        except OSError:
                            pass
                    report_path = None
                self._export_queue.put(("done", len(results), gpu_numbers, (report_path, warning)))
            except Exception as exc:
                self._export_queue.put(("error", exc, None, None))
        threading.Thread(target=work, daemon=True).start()
        self._export_poll_job = self.after(80, self._poll_export)

    def _poll_export(self):
        self._export_poll_job = None
        for _ in range(20):
            try:
                kind, first, second, third = self._export_queue.get_nowait()
            except Empty:
                break
            if kind == "progress":
                total, used_gpu = third
                self.status.configure(text=f"Exported {second}/{total} · photo #{first:04d} "
                                           f"({'GPU color math' if used_gpu else 'CPU'})")
            elif kind == "done":
                report_path, warning = third
                details = f"\nGPU usage by photo number: {report_path}" if report_path else ""
                if warning:
                    details += f"\n{warning}"
                self.done(f"Exported {first} lossless masters + .isphoto projects to "
                          f"{self._export_directory}; GPU-adjusted {len(second)}/{first} photos"
                          f"{details}")
                return
            elif kind == "error":
                self.failed(first)
                return
        self._export_poll_job = self.after(80, self._poll_export)

    def done(self, message):
        self.busy = False
        self._sync_mask_status()
        self.status.configure(text=message)
        messagebox.showinfo("Export complete", message, parent=self)

    def failed(self, exc):
        self.busy = False
        self._sync_mask_status()
        self.error(exc)


class _EscapeClosableTool(ctk.CTkToplevel):
    """Make Escape reach native entries and CTk canvas-backed child controls."""

    def _install_escape(self, close):
        # A Toplevel binding is not inherited by focused entry/button widgets.
        # Scope the class binding to this window only; never bind_all globally.
        self._escape_tag = f"ImageSwitcherToolEscape{id(self)}"
        self._escape_close = close
        self.bind_class(self._escape_tag, "<Escape>", self._close_on_escape)

        def tag_tree(widget):
            widget.bindtags((self._escape_tag, *widget.bindtags()))
            for child in widget.winfo_children():
                tag_tree(child)

        tag_tree(self)

    def _close_on_escape(self, _event):
        self._escape_close()
        return "break"

    def destroy(self):
        # The parent editor may destroy a tool without using its Close action.
        tag = getattr(self, "_escape_tag", None)
        if tag:
            self.unbind_class(tag, "<Escape>")
            self._escape_tag = None
        super().destroy()


class CropTools(_EscapeClosableTool):
    """Non-export editing tools, separate from the adjustment sliders."""
    def __init__(self, editor: EditorWindow):
        super().__init__(editor)
        self.editor = editor
        self.title("Crop / orientation")
        place_popup(self, editor, 375, 305)
        self.resizable(False, False)
        self.transient(editor)
        self.configure(fg_color="#25282d")
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
        ctk.CTkButton(self, text="Close", fg_color="#3c444e",
                      command=editor.close_crop_tools).pack(pady=(8, 4))
        self._install_escape(editor.close_crop_tools)


class BackgroundTools(_EscapeClosableTool):
    """Non-modal so the user can paint directly on the canvas behind it."""
    def __init__(self, editor: EditorWindow):
        super().__init__(editor)
        self.editor = editor
        self.title("Background / manual mask")
        place_popup(self, editor, 410, 435)
        self.resizable(False, False)
        self.transient(editor)
        self.configure(fg_color="#25282d")
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
        mask_actions = ctk.CTkFrame(self, fg_color="transparent")
        mask_actions.pack(pady=4)
        ctk.CTkButton(mask_actions, text="Undo last stroke", width=135, fg_color="#3c444e",
                      command=editor.undo_mask_stroke).pack(side="left", padx=4)
        ctk.CTkButton(mask_actions, text="Clear mask", width=120, fg_color="#3c444e",
                      command=editor.clear_mask).pack(side="left", padx=4)
        self.mask_status = ctk.CTkLabel(self, text="Choose a background effect before painting.",
                                        wraplength=360, text_color="#d2b889", justify="center")
        self.mask_status.pack(padx=15, pady=(6, 2))
        ctk.CTkLabel(self, text="Manual mask only · no automatic subject selection.\n"
                     "Closing this tool stops painting; edits remain in the batch.",
                     text_color="#b3bdc9", justify="center").pack(pady=(0, 5))
        ctk.CTkButton(self, text="Close tool", width=120, fg_color="#3c444e",
                      command=editor.close_background_tools).pack(pady=(0, 8))
        self._install_escape(editor.close_background_tools)

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
        self.bind("<Escape>", lambda _event: self.close())
        self.shade = None
        try:
            shade = ctk.CTkToplevel(editor)
            self.shade = shade
            shade.overrideredirect(True)
            shade.configure(fg_color="#000000")
            shade.attributes("-alpha", 0.42)
            # Shade has CTk geometry scaling too; editor bounds are already
            # physical pixels, so do not multiply the dimmed surface by DPI.
            shade_scale = shade._get_window_scaling()
            shade.geometry(f"{round(editor.winfo_width() / shade_scale)}x"
                           f"{round(editor.winfo_height() / shade_scale)}+"
                           f"{editor.winfo_rootx()}+{editor.winfo_rooty()}")
            shade.lift(editor)
            self.shade = shade
        except tk.TclError:
            if self.shade and self.shade.winfo_exists():
                self.shade.destroy()
            self.shade = None  # platform cannot dim: modal must still work
        place_popup(self, editor, 530, 575)
        self.configure(fg_color="#25282d")
        self.lift(self.shade if self.shade else editor)

        ctk.CTkLabel(self, text="Export photos", anchor="w",
                     font=ctk.CTkFont(size=19, weight="bold")).pack(fill="x", padx=26, pady=(18, 14))
        ctk.CTkLabel(self, text="Destination", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x", padx=26)
        path_row = ctk.CTkFrame(self, fg_color="transparent")
        path_row.pack(fill="x", padx=24, pady=(5, 12))
        self.folder = ctk.StringVar()
        self.folder_entry = ctk.CTkEntry(path_row, textvariable=self.folder,
                                         placeholder_text="Choose an export folder",
                                         width=365, fg_color="#1d2025")
        self.folder_entry.pack(side="left", padx=(0, 8))
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
        # Tk's child bindtags do not inherit the Toplevel's Escape binding.
        # Register a tag on every existing CTk/native descendant so Escape
        # closes this modal from radios, buttons, checkboxes AND native entries.
        # A unique tag avoids changing another window's key bindings.
        self._escape_tag = f"ImageSwitcherExportEscape{id(self)}"
        self.bind_class(self._escape_tag, "<Escape>", self._close_on_escape)
        ctk.CTkLabel(self, text="No signed credential or watermark. Rights are stored in .isphoto only.",
                     text_color="#d6a773", font=ctk.CTkFont(size=10)).pack(padx=25, pady=(0, 7))
        ctk.CTkLabel(self, text="Existing output names stop export; files are never overwritten.",
                     text_color="#bbc4cf", font=ctk.CTkFont(size=11)).pack(padx=25, pady=(0, 5))
        self.preflight_status = ctk.CTkLabel(self, text="", text_color="#ffc188",
                                              wraplength=475, font=ctk.CTkFont(size=11))
        self.preflight_status.pack(fill="x", padx=25, pady=(0, 3))
        self.folder.trace_add("write", lambda *_: self.preflight_status.configure(text=""))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(anchor="e", padx=25, pady=(4, 14))
        ctk.CTkButton(actions, text="Cancel", width=100, fg_color="#363d47",
                      command=self.close).pack(side="left", padx=(0, 9))
        ctk.CTkButton(actions, text="Export now", width=115, fg_color="#1e64b8",
                      command=self.confirm).pack(side="left")
        self._tag_descendants_for_escape(self)
        self.after_idle(self._grab_when_visible)

    def _tag_descendants_for_escape(self, widget):
        tags = widget.bindtags()
        if self._escape_tag not in tags:
            widget.bindtags((self._escape_tag, *tags))
        for child in widget.winfo_children():
            self._tag_descendants_for_escape(child)

    def _close_on_escape(self, _event):
        self.close()
        return "break"

    def _grab_when_visible(self):
        if self.winfo_exists():
            try:
                self.lift(self.shade if self.shade and self.shade.winfo_exists() else self.editor)
                self.grab_set()
                self.creator.focus_set()
            except tk.TclError:
                self.after(50, self._grab_when_visible)

    def browse(self):
        destination = filedialog.askdirectory(parent=self, title="Choose folder for numbered master/project pairs")
        if destination:
            self.folder.set(destination)
        # Windows native folder choosers can return focus to the dimmed editor.
        # Return it to the live export dialog without changing its fields.
        if self.winfo_exists():
            self.after_idle(self._grab_when_visible)

    def confirm(self):
        destination = self.folder.get().strip()
        numbers = [self.editor.current] if self.selection.get().startswith("Selected photo") else None
        try:
            # Refuse existing names while the user can still correct this
            # dialog. The worker repeats the check and publishes exclusively.
            plan_export(self.editor.batch, destination, numbers)
        except FileExistsError:
            self.preflight_status.configure(text="Output name already exists. Choose another folder or export only the selected photo.")
            self.folder_entry.focus_set()
            return
        except (ValueError, OSError) as exc:
            self.preflight_status.configure(text=str(exc)[:170])
            self.folder_entry.focus_set()
            return
        rights = {"creator": self.creator.get().strip(), "copyright_notice": self.notice.get().strip()}
        self.close()
        self.editor.begin_export(destination, rights, numbers)

    def close(self):
        if not self.winfo_exists():
            return
        if self.grab_current() == self:
            self.grab_release()
        self.destroy()
        if self.editor.winfo_exists():
            self.editor.focus_set()

    def destroy(self):
        # Also run when the parent editor is destroyed with the dialog open.
        tag = getattr(self, "_escape_tag", None)
        if tag:
            self.unbind_class(tag, "<Escape>")
            self._escape_tag = None
        if getattr(self, "shade", None) and self.shade.winfo_exists():
            self.shade.destroy()
        super().destroy()
