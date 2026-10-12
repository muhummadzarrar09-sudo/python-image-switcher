import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from src.editor.batch import BatchSession
from src.editor.project import ProjectError, create_project, read_project


def test_protected_numbered_batch_survives_save_and_reopen(tmp_path):
    photos = [tmp_path / f"p{i}.jpg" for i in range(3)]
    for file in photos:
        file.write_bytes(b"source")
    batch = BatchSession()
    for photo in photos:
        batch.add_photo(str(photo))
    assert [p.number for p in batch.photos] == [1, 2, 3]
    batch.set_batch("brightness", 0.2)
    batch.edit_photo(2, "contrast", 0.4)
    batch.set_crop(2, (0.1, 0.2, 0.9, 0.8))
    assert batch.set_batch("brightness", 0.8) == [2]
    assert batch.effective_settings(1)["brightness"] == 0.8
    assert batch.effective_settings(2)["brightness"] == 0.2
    assert batch.effective_settings(2)["contrast"] == 0.4
    path = tmp_path / "session.isbatch"
    batch.save(str(path))
    restored = BatchSession.load(str(path))
    assert restored.excluded_numbers == [2]
    assert restored.effective_settings(2)["brightness"] == 0.2
    assert restored.get(2).crop == (0.1, 0.2, 0.9, 0.8)
    restored.remove_photo(1)
    assert restored.add_photo(str(photos[0])).number == 4
    restored.include_in_batch(2)
    assert restored.effective_settings(2)["brightness"] == 0.8


def test_batch_rejects_invalid_edits_and_crops(tmp_path):
    source = tmp_path / "p.png"
    source.write_bytes(b"source")
    batch = BatchSession()
    batch.add_photo(str(source))
    with pytest.raises(ValueError):
        batch.set_batch("unknown", 1)
    with pytest.raises(ValueError):
        batch.edit_photo(1, "exposure", float("nan"))
    with pytest.raises(ValueError):
        batch.set_crop(1, (0, 0, 2, 1))
    assert not batch.excluded_numbers


def test_portable_project_roundtrip_and_checksums(tmp_path):
    original = tmp_path / "camera.nef"
    master = tmp_path / "master.tiff"
    mask = tmp_path / "mask.png"
    original.write_bytes(b"RAW sample" * 100)
    master.write_bytes(b"lossless master" * 100)
    mask.write_bytes(b"corrected mask")
    destination = tmp_path / "edited.isphoto"
    project = create_project(str(destination), original=str(original), master=str(master),
                             mask=str(mask), photo_number=7, photo_id="stable-id",
                             edits={"exposure": 0.5, "crop": [0, 0, 1, 1]},
                             rights={"creator": "The actual creator"}, protected=True)
    assert project.manifest["photo_number"] == 7
    verified = read_project(str(destination))
    assert verified.manifest["rights"]["creator"] == "The actual creator"
    extracted = Path(verified.copy_original(str(tmp_path / "unpacked")))
    assert extracted.read_bytes() == original.read_bytes()
    assert Path(verified.copy_master(str(tmp_path / "unpacked"))).read_bytes() == master.read_bytes()
    with pytest.raises(FileExistsError):
        verified.copy_master(str(tmp_path / "unpacked"))


def test_tampering_with_asset_is_detected(tmp_path):
    original = tmp_path / "in.jpg"
    master = tmp_path / "out.png"
    original.write_bytes(b"original photo")
    master.write_bytes(b"image bytes")
    project_path = tmp_path / "photo.isphoto"
    create_project(str(project_path), original=str(original), master=str(master),
                   photo_number=1, photo_id="abc")
    # Repack with valid ZIP CRC but an asset that does not match our manifest SHA.
    modified = tmp_path / "bad.isphoto"
    with zipfile.ZipFile(project_path) as src, zipfile.ZipFile(modified, "w") as dst:
        for name in src.namelist():
            data = b"tampered image" if name == "assets/master" else src.read(name)
            dst.writestr(name, data, compress_type=zipfile.ZIP_STORED)
    with pytest.raises(ProjectError):
        read_project(str(modified))


def test_unsupported_version_and_excess_entries_rejected(tmp_path):
    original = tmp_path / "in.jpg"
    master = tmp_path / "out.png"
    original.write_bytes(b"original photo")
    master.write_bytes(b"image bytes")
    project_path = tmp_path / "photo.isphoto"
    create_project(str(project_path), original=str(original), master=str(master),
                   photo_number=1, photo_id="abc")
    modified = tmp_path / "version.isphoto"
    with zipfile.ZipFile(project_path) as src, zipfile.ZipFile(modified, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                manifest = json.loads(data)
                manifest["version"] = 999
                data = json.dumps(manifest).encode()
            dst.writestr(name, data)
    with pytest.raises(ProjectError, match="version"):
        read_project(str(modified))
