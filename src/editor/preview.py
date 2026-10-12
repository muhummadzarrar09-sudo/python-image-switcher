"""Coalesced, size-bounded preview rendering with no Tk calls off the UI thread.

Only UI previews use this worker. Export still uses the original full-resolution
render and its own verified lossless save path.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from queue import Empty, Full, Queue
import threading

import numpy as np
from PIL import Image

from .batch import BatchSession, Photo
from .gpu_preview import OpenCLPreview, eligible
from .render import _open_source, render


@dataclass(frozen=True)
class PreviewRequest:
    generation: int
    photo: Photo
    batch: BatchSession
    before: bool
    size: tuple[int, int]


def process_preview(request: PreviewRequest, accelerator: OpenCLPreview | None = None) -> Image.Image:
    """Return a small display image; never edit, save or demote the source."""
    if request.before:
        image, _, _ = _open_source(request.photo.source, preview=True,
                                   frame_index=request.photo.frame_index, preview_size=request.size)
    else:
        image = None
        if accelerator is not None and not getattr(accelerator, "failed", False) and eligible(request.photo, request.batch):
            source, _, raw = _open_source(request.photo.source, preview=True,
                                          frame_index=request.photo.frame_index,
                                          preview_size=request.size)
            if not raw and isinstance(source, Image.Image) and source.mode == "RGB":
                values = request.batch.effective_settings(request.photo.number)
                try:
                    image = accelerator.apply(source, values["exposure"], values["contrast"])
                except Exception as exc:
                    # Driver failures are recoverable for previews; disable the
                    # backend for this worker and re-render on the known CPU path.
                    accelerator.failed = True
                    accelerator.error = str(exc)
        if image is None:
            image, _, _ = render(request.photo, request.batch, preview=True,
                                 preview_size=request.size)
    if not isinstance(image, Image.Image):
        # Some NEF files have no embedded JPEG; their uint16 demosaic is still
        # displayed as 8-bit, while full-resolution TIFF export stays uint16.
        image = Image.fromarray(np.right_shift(image, 8).astype(np.uint8))
    image.thumbnail(request.size, Image.Resampling.LANCZOS)
    return image


class PreviewRenderer:
    """Single worker, at most one pending request and one completed image."""

    def __init__(self, processor=process_preview):
        self._processor = processor
        self._pending: Queue[PreviewRequest | None] = Queue(maxsize=1)
        self._completed: Queue[tuple[int, Image.Image | None, str | None, bool]] = Queue(maxsize=1)
        self._stop = threading.Event()
        self._latest = 0
        self._gpu_opt_in = os.environ.get("IMAGE_SWITCHER_EXPERIMENTAL_GPU_PREVIEW") == "1"
        self._gpu_backend: OpenCLPreview | None = None
        self._gpu_disabled = False
        self.gpu_error: str | None = None
        self._worker = threading.Thread(target=self._run, name="editor-preview", daemon=True)
        self._worker.start()

    def submit(self, request: PreviewRequest) -> None:
        if self._stop.is_set():
            return
        self._latest = request.generation
        self._replace(self._pending, request)

    @staticmethod
    def _replace(queue: Queue, item) -> None:
        try:
            queue.put_nowait(item)
        except Full:
            try:
                queue.get_nowait()
            except Empty:
                pass
            queue.put_nowait(item)

    def result(self) -> tuple[int, Image.Image | None, str | None, bool] | None:
        try:
            return self._completed.get_nowait()
        except Empty:
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            request = self._pending.get()
            if request is None or self._stop.is_set():
                break
            if request.generation != self._latest:
                continue
            try:
                gpu_used = False
                if (self._processor is process_preview and self._gpu_opt_in
                        and not self._gpu_disabled and not request.before
                        and eligible(request.photo, request.batch)):
                    if self._gpu_backend is None:
                        try:
                            self._gpu_backend = OpenCLPreview()  # worker thread only
                        except Exception as exc:
                            self.gpu_error = str(exc)
                            self._gpu_disabled = True
                    previous_calls = self._gpu_backend.calls if self._gpu_backend else 0
                    image = process_preview(request, accelerator=self._gpu_backend)
                    gpu_used = bool(self._gpu_backend and self._gpu_backend.calls > previous_calls)
                    if self._gpu_backend and getattr(self._gpu_backend, "failed", False):
                        self.gpu_error = self._gpu_backend.error
                        self._gpu_disabled = True
                else:
                    image = self._processor(request)
                error = None
            except Exception as exc:
                image, error, gpu_used = None, str(exc), False
            if request.generation == self._latest and not self._stop.is_set():
                self._replace(self._completed, (request.generation, image, error, gpu_used))

    def close(self) -> None:
        self._stop.set()
        self._replace(self._pending, None)
