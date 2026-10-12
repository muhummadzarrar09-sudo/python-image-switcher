"""Coalesced, size-bounded preview rendering with no Tk calls off the UI thread.

Only UI previews use this worker. Export still uses the original full-resolution
render and its own verified lossless save path.
"""
from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
import threading

import numpy as np
from PIL import Image

from .batch import BatchSession, Photo
from .render import _open_source, render


@dataclass(frozen=True)
class PreviewRequest:
    generation: int
    photo: Photo
    batch: BatchSession
    before: bool
    size: tuple[int, int]


def process_preview(request: PreviewRequest) -> Image.Image:
    """Return a small display image; never edit, save or demote the source."""
    if request.before:
        image, _, _ = _open_source(request.photo.source, preview=True,
                                   frame_index=request.photo.frame_index, preview_size=request.size)
    else:
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
        self._completed: Queue[tuple[int, Image.Image | None, str | None]] = Queue(maxsize=1)
        self._stop = threading.Event()
        self._latest = 0
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

    def result(self) -> tuple[int, Image.Image | None, str | None] | None:
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
                image = self._processor(request)
                error = None
            except Exception as exc:
                image, error = None, str(exc)
            if request.generation == self._latest and not self._stop.is_set():
                self._replace(self._completed, (request.generation, image, error))

    def close(self) -> None:
        self._stop.set()
        self._replace(self._pending, None)
