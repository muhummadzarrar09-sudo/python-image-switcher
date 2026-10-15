"""Persistent, non-destructive numbered photo batches.

An individually edited photo is protected as a whole: its batch defaults are
snapshotted at the time of the first edit, so later batch changes cannot leak
into it. Protection does not remove it from the batch or export.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

EDIT_FIELDS = {
    "brightness": (-1.0, 1.0),
    "exposure": (-4.0, 4.0),
    "contrast": (-1.0, 1.0),
    "highlights": (-1.0, 1.0),
    "shadows": (-1.0, 1.0),
    "vignette": (-1.0, 1.0),
    "saturation": (-1.0, 1.0),
    "warmth": (-1.0, 1.0),
    "tint": (-1.0, 1.0),
    "sharpness": (0.0, 2.0),
}
DEFAULTS = {name: 0.0 for name in EDIT_FIELDS}


def _check_setting(key: str, value: float) -> float:
    if key not in EDIT_FIELDS:
        raise ValueError(f"Unknown editing field: {key}")
    value = float(value)
    lo, hi = EDIT_FIELDS[key]
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def _atomic_json(path: str, data: dict) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent,
                                         prefix=".isbatch-", suffix=".tmp", delete=False) as out:
            name = out.name
            json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@dataclass
class Photo:
    number: int
    source: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    protected: bool = False
    frozen_batch: dict[str, float] = field(default_factory=dict)
    overrides: dict[str, float] = field(default_factory=dict)
    crop: tuple[float, float, float, float] | None = None  # normalized x0,y0,x1,y1
    rotation: int = 0  # counterclockwise degrees
    flip_horizontal: bool = False
    background: dict = field(default_factory=dict)
    mask_strokes: list[dict] = field(default_factory=list)
    rights: dict = field(default_factory=dict)
    frame_index: int = 0  # MPO JPEG still number; 0 for ordinary single-photo files


@dataclass
class BatchSession:
    photos: list[Photo] = field(default_factory=list)
    batch_settings: dict[str, float] = field(default_factory=lambda: dict(DEFAULTS))
    next_number: int = 1
    rights: dict = field(default_factory=dict)
    version: int = 1

    def add_photo(self, path: str, *, frame_index: int = 0) -> Photo:
        path = str(Path(path).expanduser().resolve())
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        if type(frame_index) is not int or frame_index < 0:
            raise ValueError("Invalid still-photo frame index")
        photo = Photo(number=self.next_number, source=path, frame_index=frame_index)
        self.photos.append(photo)
        self.next_number += 1
        return photo

    def get(self, number: int) -> Photo:
        for photo in self.photos:
            if photo.number == number:
                return photo
        raise KeyError(f"No photo #{number}")

    def protect(self, number: int) -> None:
        photo = self.get(number)
        if not photo.protected:
            photo.frozen_batch = dict(self.batch_settings)
            photo.protected = True

    def include_in_batch(self, number: int) -> None:
        """Explicitly rejoin future batch edits; per-photo overrides remain."""
        photo = self.get(number)
        photo.protected = False
        photo.frozen_batch = {}

    def edit_photo(self, number: int, key: str, value: float) -> None:
        value = _check_setting(key, value)
        self.protect(number)
        self.get(number).overrides[key] = value

    def set_batch(self, key: str, value: float) -> list[int]:
        """Update batch defaults; return stable numbers excluded from this edit."""
        self.batch_settings[key] = _check_setting(key, value)
        return self.excluded_numbers

    @property
    def excluded_numbers(self) -> list[int]:
        return [p.number for p in self.photos if p.protected]

    def effective_settings(self, number: int) -> dict[str, float]:
        photo = self.get(number)
        base = photo.frozen_batch if photo.protected else self.batch_settings
        return {**DEFAULTS, **base, **photo.overrides}

    def set_crop(self, number: int, box: tuple[float, float, float, float] | None) -> None:
        if box is not None:
            if len(box) != 4 or not all(math.isfinite(x) for x in box):
                raise ValueError("Invalid crop box")
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("Crop must be within the image")
        self.protect(number)
        self.get(number).crop = tuple(box) if box is not None else None

    def set_rotation(self, number: int, degrees: int) -> None:
        if degrees not in (0, 90, 180, 270):
            raise ValueError("Rotation must be 0, 90, 180 or 270")
        self.protect(number)
        self.get(number).rotation = degrees

    def add_mask_stroke(self, number: int, x: float, y: float, radius: float, *, add_background: bool) -> None:
        if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < radius <= 1):
            raise ValueError("Mask coordinates must be normalized")
        self.protect(number)
        self.get(number).mask_strokes.append({"x": x, "y": y, "radius": radius,
                                              "add_background": bool(add_background)})

    def remove_photo(self, number: int) -> None:
        self.photos.remove(self.get(number))  # number is never reused

    def save(self, path: str) -> None:
        from dataclasses import asdict
        _atomic_json(path, asdict(self))

    @classmethod
    def load(cls, path: str) -> "BatchSession":
        with open(path, encoding="utf-8") as inp:
            data = json.load(inp)
        if data.get("version") != 1:
            raise ValueError("Unsupported batch version")
        photos = [Photo(**{**entry, "crop": tuple(entry["crop"]) if entry.get("crop") else None})
                  for entry in data["photos"]]
        if len({p.number for p in photos}) != len(photos) or any(p.number < 1 for p in photos):
            raise ValueError("Invalid or duplicate photo numbers")
        if data["next_number"] <= max((p.number for p in photos), default=0):
            raise ValueError("Invalid next photo number")
        settings = {key: _check_setting(key, val) for key, val in data["batch_settings"].items()}
        for photo in photos:
            if type(photo.frame_index) is not int or photo.frame_index < 0:
                raise ValueError("Invalid still-photo frame index")
            for mapping in (photo.frozen_batch, photo.overrides):
                for key, val in mapping.items():
                    _check_setting(key, val)
            if photo.crop is not None:
                x0, y0, x1, y1 = photo.crop
                if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                    raise ValueError("Invalid crop")
        return cls(photos=photos, batch_settings={**DEFAULTS, **settings},
                   next_number=data["next_number"], rights=data.get("rights", {}))
