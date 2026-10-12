from pathlib import Path

import numpy as np
import pytest
from PIL import Image
import tifffile

from src.editor.batch import BatchSession
from src.editor.project import read_project
from src.editor.render import PhotoRenderError, export_lossless, render, source_info
from src.editor.workflow import export_batch, import_project


def sample(tmp_path):
    original = tmp_path / "camera.jpg"
    Image.new("RGB", (40, 30), (120, 80, 50)).save(original, quality=95)
    batch = BatchSession()
    photo = batch.add_photo(str(original))
    return batch, photo, original


def test_lossless_master_has_same_dimensions_and_changes_pixels(tmp_path):
    batch, photo, original = sample(tmp_path)
    batch.set_batch("exposure", 1)
    out = tmp_path / "master.png"
    export_lossless(photo, batch, str(out))
    with Image.open(out) as result, Image.open(original) as source:
        assert result.size == source.size
        assert result.getpixel((0, 0))[0] > source.getpixel((0, 0))[0]
    assert original.read_bytes() != out.read_bytes()
    with pytest.raises(PhotoRenderError, match="PNG or TIFF"):
        export_lossless(photo, batch, str(tmp_path / "lossy.jpg"))


def test_crop_rotate_preserves_numbered_exception_and_mask(tmp_path):
    batch, photo, _ = sample(tmp_path)
    batch.set_batch("brightness", 0.2)
    batch.set_crop(1, (0, 0, 0.5, 1))
    batch.set_rotation(1, 90)
    batch.set_batch("brightness", 0.9)
    assert batch.excluded_numbers == [1]
    assert batch.effective_settings(1)["brightness"] == 0.2
    out, _, _ = render(photo, batch)
    assert out.size == (30, 20)
    photo.background = {"mode": "color", "color": "#ff0000"}
    batch.add_mask_stroke(1, .5, .5, .4, add_background=True)
    out, _, _ = render(photo, batch)
    assert out.getpixel((15, 10))[0] >= 250
    assert out.getpixel((15, 10))[1] <= 10
    batch.add_mask_stroke(1, .5, .5, .2, add_background=False)
    out, _, _ = render(photo, batch)
    assert out.getpixel((15, 10))[1] > 10


def test_palette_transparency_is_preserved(tmp_path):
    palette = Image.new("P", (10, 10), 0)
    palette.putpalette([255, 0, 0, 0, 0, 255] + [0] * (256 * 3 - 6))
    palette.info["transparency"] = 0
    source = tmp_path / "transparent.png"
    palette.save(source)
    batch = BatchSession()
    batch.add_photo(str(source))
    output = tmp_path / "master.png"
    export_lossless(batch.photos[0], batch, str(output))
    with Image.open(output) as result:
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0))[3] == 0


def test_background_image_must_not_be_upscaled(tmp_path):
    batch, photo, _ = sample(tmp_path)
    small = tmp_path / "bg.png"
    Image.new("RGB", (5, 5), (255, 0, 0)).save(small)
    photo.background = {"mode": "image", "source": str(small)}
    batch.add_mask_stroke(1, .5, .5, .4, add_background=True)
    with pytest.raises(PhotoRenderError, match="upscaled"):
        render(photo, batch)
    Image.new("RGB", (100, 90), (255, 0, 0)).save(small)
    assert render(photo, batch)[0].size == (40, 30)


def test_batch_exports_every_photo_and_reopens_project(tmp_path):
    batch, photo, original = sample(tmp_path)
    second = tmp_path / "screenshot.png"
    Image.new("RGBA", (32, 28), (20, 40, 60, 80)).save(second)
    batch.add_photo(str(second))
    batch.edit_photo(1, "contrast", .5)
    batch.set_batch("exposure", .5)
    batch.rights["creator"] = "Declared creator"
    output = tmp_path / "export"
    results = export_batch(batch, str(output))
    assert [number for number, _, _ in results] == [1, 2]
    for _, master, project in results:
        with Image.open(master) as image:
            image.verify()
        assert read_project(project).manifest["rights"]["creator"] == "Declared creator"
    with pytest.raises(FileExistsError):
        export_batch(batch, str(output))
    restored = BatchSession()
    imported = import_project(restored, results[0][2], str(tmp_path / "imports"))
    assert imported.number == 1 and imported.protected
    assert Path(imported.source).read_bytes() == original.read_bytes()
    assert restored.effective_settings(1)["contrast"] == .5
    assert restored.effective_settings(1)["exposure"] == 0.0
    assert render(imported, restored)[0].size == (40, 30)


def test_project_embeds_supplied_background_for_portable_reedit(tmp_path):
    batch, photo, _ = sample(tmp_path)
    background = tmp_path / "replacement.png"
    Image.new("RGB", (80, 70), (200, 20, 30)).save(background)
    photo.background = {"mode": "image", "source": str(background)}
    batch.add_mask_stroke(photo.number, .5, .5, .2, add_background=True)
    projects = export_batch(batch, str(tmp_path / "output"))
    imported = BatchSession()
    restored = import_project(imported, projects[0][2], str(tmp_path / "imports"))
    assert Path(restored.background["source"]).read_bytes() == background.read_bytes()
    assert restored.mask_strokes == photo.mask_strokes
    assert np.array_equal(np.asarray(render(restored, imported)[0]), np.asarray(render(photo, batch)[0]))


def test_reject_16bit_source_instead_of_silent_8bit_conversion(tmp_path):
    path = tmp_path / "highbit.png"
    Image.fromarray(np.full((16, 12), 32768, dtype=np.uint16)).save(path)
    with pytest.raises(PhotoRenderError, match="16-bit|High-bit"):
        source_info(str(path))
    tiff = tmp_path / "highbit.tiff"
    tifffile.imwrite(tiff, np.full((16, 12, 3), 32000, dtype=np.uint16), photometric="rgb")
    with pytest.raises(PhotoRenderError, match="16-bit|High-bit"):
        source_info(str(tiff))


def test_reject_multiframe_instead_of_first_frame(tmp_path):
    path = tmp_path / "animated.webp"
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)
    with pytest.raises(PhotoRenderError, match="Animated/multipage"):
        source_info(str(path))


def test_nef_16bit_tiff_export_path_without_camera_fixture(tmp_path, monkeypatch):
    from src.editor import render as render_module
    batch, photo, _ = sample(tmp_path)
    photo.source = str(tmp_path / "photo.nef")
    pixels = np.full((12, 16, 3), 32000, dtype=np.uint16)
    monkeypatch.setattr(render_module, "_open_source", lambda *args, **kwargs: (pixels, None, True))
    path = tmp_path / "master.tiff"
    export_lossless(photo, batch, str(path))
    assert tifffile.imread(path).dtype == np.uint16
    assert np.array_equal(tifffile.imread(path), pixels)
    with pytest.raises(PhotoRenderError, match="requires TIFF"):
        export_lossless(photo, batch, str(tmp_path / "master.png"))
