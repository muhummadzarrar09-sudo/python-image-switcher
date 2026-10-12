"""Batch export of individually numbered projects and lossless open images."""
from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import re
import shutil
import tempfile

from .batch import BatchSession, Photo
from .project import create_project, read_project
from .render import export_lossless, PhotoRenderError


def export_batch(batch: BatchSession, directory: str, *, numbers: list[int] | None = None,
                 accelerator=None, on_exported=None) -> list[tuple[int, str, str]]:
    """Export all numbered photos (including protected), or an explicit selection.

    Masters are PNG for decoded 8-bit photos and RGB 16-bit TIFF for NEF.
    Returns [(stable number, master path, project path)]. On failure, already
    exported photos remain; the raised error identifies the failed operation.
    """
    if numbers is None:
        photos = batch.photos
    else:
        if not numbers or len(set(numbers)) != len(numbers):
            raise ValueError("Choose distinct numbered photos to export")
        selected = set(numbers)
        photos = [photo for photo in batch.photos if photo.number in selected]
        if len(photos) != len(numbers):
            raise ValueError("An export number is not in this batch")
    if not photos:
        raise ValueError("Add still photos before exporting")
    os.makedirs(directory, exist_ok=True)
    directory = os.path.abspath(directory)
    plans = []
    for photo in photos:
        basename = re.sub(r"[^\w.-]+", "_", Path(photo.source).stem)[:80] or "photo"
        stem = f"{photo.number:04d}-{basename}"
        extension = ".tiff" if Path(photo.source).suffix.lower() == ".nef" else ".png"
        master = os.path.join(directory, stem + extension)
        project = os.path.join(directory, stem + ".isphoto")
        if master == os.path.abspath(photo.source) or os.path.exists(master) or os.path.exists(project):
            raise FileExistsError(f"Refusing to overwrite {master} or {project}")
        plans.append((photo, master, project))
    result = []
    for photo, master, project in plans:
        with tempfile.TemporaryDirectory(dir=directory, prefix=".export-") as staging:
            staged = os.path.join(staging, os.path.basename(master))
            export_lossless(photo, batch, staged, accelerator=accelerator)
            recipe = asdict(photo)
            # Portable: original/background are in archive; strip machine-local paths.
            recipe.pop("source")
            if recipe["background"].get("source"):
                recipe["background"]["source"] = "embedded"
            # Exclusive same-volume publication of identical bytes. If the
            # verified project fails, remove this photo's master again.
            os.link(staged, master)
            try:
                create_project(project, original=photo.source, master=master,
                               photo_number=photo.number, photo_id=photo.id,
                               edits={"photo": recipe, "effective_settings": batch.effective_settings(photo.number)},
                               rights={**batch.rights, **photo.rights},
                               background=photo.background.get("source"), protected=photo.protected)
            except Exception:
                os.unlink(master)
                raise
        result.append((photo.number, master, project))
        if on_exported is not None:
            on_exported(photo.number, len(result), len(plans))
    return result


def import_project(batch: BatchSession, path: str, directory: str) -> Photo:
    """Verify an .isphoto and extract its original/background into a durable folder.

    The caller chooses this extraction directory; do not use an ephemeral temp
    path for sources referenced by a saved .isbatch session.
    """
    project = read_project(path)
    target = os.path.join(directory, f"photo-{project.photo_number}-{project.manifest['photo_id'][:12]}")
    if os.path.exists(target):
        raise FileExistsError(f"Project extraction directory already exists: {target}")
    os.makedirs(target)
    photo = None
    try:
        original = project.copy_original(os.path.join(target, "original"))
        background = project.copy_background(os.path.join(target, "background"))
        project.copy_master(os.path.join(target, "master"))
        recipe = project.manifest.get("edits", {})
        saved = recipe.get("photo", {})
        frame_index = saved.get("frame_index", 0)
        if type(frame_index) is not int or frame_index < 0:
            raise ValueError("Invalid saved still-photo frame index")
        # Validate the indexed original before adding it to the session.
        from .render import source_info
        source_info(original, frame_index=frame_index)
        photo = batch.add_photo(original, frame_index=frame_index)
        old_number = project.photo_number
        if old_number not in {p.number for p in batch.photos if p is not photo}:
            photo.number = old_number
            batch.next_number = max(batch.next_number, old_number + 1)
        for key in ("overrides", "frozen_batch", "crop", "rotation", "flip_horizontal", "mask_strokes", "background"):
            if key in saved:
                setattr(photo, key, tuple(saved[key]) if key == "crop" and saved[key] else saved[key])
        if background:
            photo.background["source"] = background
        photo.protected = True  # project edits must be protected from future batch changes
        photo.frozen_batch = dict(recipe.get("effective_settings", {}))
        photo.id = project.manifest["photo_id"]
        photo.rights = dict(project.manifest.get("rights", {}))
        return photo
    except Exception:
        if photo is not None and photo in batch.photos:
            batch.photos.remove(photo)
        shutil.rmtree(target)
        raise
