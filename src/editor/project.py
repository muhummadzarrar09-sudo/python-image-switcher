"""Self-contained `.isphoto` project files, version 1.

A .isphoto is a lossless container, not a new codec or a universal C2PA format.
All data lives under fixed archive names. No archive entry is ever extracted by
zipfile.extract(); content is streamed and verified before use.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

VERSION = 1
MAX_MANIFEST = 2 * 1024 * 1024
MAX_ENTRIES = 5
MAX_TOTAL_BYTES = 200 * 1024**3  # safety ceiling, never silently truncate
CHUNK = 1024 * 1024


class ProjectError(ValueError):
    """Malformed, unsupported, or damaged photo project."""


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while block := source.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def _safe_filename(name: str) -> str:
    # Windows files may contain backslashes even when run on Linux.
    name = name.replace("\\", "/").split("/")[-1]
    if not name or name in (".", "..") or "\x00" in name:
        raise ProjectError("Invalid stored filename")
    return name


@dataclass(frozen=True)
class PhotoProject:
    path: str
    manifest: dict

    @property
    def photo_number(self) -> int:
        return self.manifest["photo_number"]

    def copy_original(self, directory: str) -> str:
        return self._copy_entry("original", directory)

    def copy_master(self, directory: str) -> str:
        return self._copy_entry("master", directory)

    def copy_background(self, directory: str) -> str | None:
        if "background" not in self.manifest["files"]:
            return None
        return self._copy_entry("background", directory)

    def _copy_entry(self, key: str, directory: str) -> str:
        file_info = self.manifest["files"][key]
        os.makedirs(directory, exist_ok=True)
        destination = os.path.join(directory, _safe_filename(file_info["filename"]))
        if os.path.exists(destination):
            raise FileExistsError(f"Refusing to overwrite {destination}")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".isphoto-",
                                             delete=False) as out:
                temporary = out.name
                with zipfile.ZipFile(self.path) as archive, archive.open(file_info["entry"]) as source:
                    digest = hashlib.sha256()
                    count = 0
                    while block := source.read(CHUNK):
                        count += len(block)
                        if count > file_info["size"]:
                            raise ProjectError("Archive entry changed while extracting")
                        digest.update(block)
                        out.write(block)
                if count != file_info["size"] or digest.hexdigest() != file_info["sha256"]:
                    raise ProjectError("Damaged project entry")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, destination)
            return destination
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def create_project(path: str, *, original: str, master: str, photo_number: int,
                   photo_id: str, edits: dict | None = None, rights: dict | None = None,
                   mask: str | None = None, background: str | None = None,
                   protected: bool = False) -> PhotoProject:
    """Atomically write a portable original + lossless master + edit recipe.

    Standard standalone exports remain necessary for other applications.
    C2PA, when available, belongs on the *inner final master* and is not
    implied by a manifest SHA-256 checksum.
    """
    if type(photo_number) is not int or photo_number < 1 or not isinstance(photo_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", photo_id):
        raise ValueError("A stable positive photo number and safe ID are required")
    if Path(master).suffix.lower() not in (".png", ".tif", ".tiff"):
        raise ValueError("Project master must be a lossless PNG or TIFF")
    sources = {"original": original, "master": master}
    if mask is not None:
        sources["mask"] = mask
    if background is not None:
        sources["background"] = background
    if any(not os.path.isfile(p) for p in sources.values()):
        raise FileNotFoundError("A project input file is missing")
    if sum(os.path.getsize(p) for p in sources.values()) > MAX_TOTAL_BYTES:
        raise ProjectError("Project exceeds safety size limit")
    files = {}
    for key, source in sources.items():
        files[key] = {"entry": f"assets/{key}", "filename": _safe_filename(os.path.basename(source)),
                      "size": os.path.getsize(source), "sha256": _sha256_file(source)}
    manifest = {"type": "ImageSwitcherPhoto", "version": VERSION, "photo_number": photo_number,
                "photo_id": photo_id, "protected": bool(protected), "edits": edits or {},
                "rights": rights or {}, "files": files}
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(manifest_bytes) > MAX_MANIFEST:
        raise ProjectError("Project metadata is too large")
    destination = os.path.abspath(path)
    if Path(destination).suffix.lower() != ".isphoto":
        raise ValueError("Project path must end in .isphoto")
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=parent, prefix=".isphoto-", suffix=".tmp",
                                         delete=False) as out:
            temporary = out.name
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            archive.writestr("manifest.json", manifest_bytes, compress_type=zipfile.ZIP_DEFLATED)
            for key, source in sources.items():
                # Images are already compressed or lossless; store without any re-encoding.
                archive.write(source, files[key]["entry"], compress_type=zipfile.ZIP_STORED)
        read_project(temporary)  # read-back verification before publishing
        # Atomic no-overwrite publication on the same volume. A subsequent save
        # must choose a new path; never silently replace an existing project.
        os.link(temporary, destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return PhotoProject(destination, manifest)


def read_project(path: str) -> PhotoProject:
    """Verify all members' names, sizes and SHA-256 without extracting."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(infos) > MAX_ENTRIES or len(names) != len(set(names)) or "manifest.json" not in names:
                raise ProjectError("Invalid project entries")
            if archive.getinfo("manifest.json").file_size > MAX_MANIFEST:
                raise ProjectError("Manifest exceeds safety limit")
            with archive.open("manifest.json") as stream:
                manifest = json.load(stream)
            if not isinstance(manifest, dict):
                raise ProjectError("Invalid project manifest")
            if manifest.get("type") != "ImageSwitcherPhoto" or manifest.get("version") != VERSION:
                raise ProjectError("Unsupported photo project version")
            if type(manifest.get("photo_number")) is not int or manifest["photo_number"] < 1:
                raise ProjectError("Invalid photo number")
            if not isinstance(manifest.get("photo_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", manifest["photo_id"]):
                raise ProjectError("Invalid photo ID")
            files = manifest.get("files", {})
            if not isinstance(files, dict) or not {"original", "master"} <= files.keys():
                raise ProjectError("Missing original or master")
            if set(files) - {"original", "master", "mask", "background"}:
                raise ProjectError("Unknown asset")
            if set(names) != {"manifest.json"} | {f"assets/{key}" for key in files}:
                raise ProjectError("Unexpected archive entries")
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                raise ProjectError("Project exceeds safety limit")
            for key, item in files.items():
                if not isinstance(item, dict) or item.get("entry") != f"assets/{key}" or type(item.get("size")) is not int:
                    raise ProjectError("Invalid asset entry")
                _safe_filename(item["filename"])
                info = archive.getinfo(item["entry"])
                if info.file_size != item["size"] or item["size"] < 0:
                    raise ProjectError("Incorrect asset size")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise ProjectError("Compressed assets are unsupported")
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    while block := stream.read(CHUNK):
                        digest.update(block)
                if digest.hexdigest() != item["sha256"]:
                    raise ProjectError("Asset checksum mismatch")
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, RuntimeError, json.JSONDecodeError, OSError) as exc:
        raise ProjectError(f"Invalid or damaged photo project: {exc}") from exc
    return PhotoProject(os.path.abspath(path), manifest)
