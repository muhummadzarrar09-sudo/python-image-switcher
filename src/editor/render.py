"""Still-photo rendering and explicitly lossless master export.

NEF is decoded with LibRaw/rawpy to 16-bit RGB and written with tifffile;
JPG/PNG and other static Pillow formats are processed at their decoded depth.
No lossy JPG export occurs through this module. Automatic subject segmentation
and signed credentials are intentionally NOT implied by this renderer.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageCms

from .batch import BatchSession, Photo

STILL_EXTENSIONS = {".nef", ".jpg", ".jpeg", ".mpo", ".png", ".tif", ".tiff",
                    ".webp", ".bmp", ".avif", ".heic", ".heif"}
MAX_RENDER_PIXELS = 100_000_000  # bounded resource use, not a silent resize


class PhotoRenderError(ValueError):
    pass


def _check_depth(path: str, image: Image.Image) -> None:
    """Refuse precision/color spaces that this renderer cannot preserve yet."""
    ext = Path(path).suffix.lower()
    if ext in (".avif", ".heic", ".heif"):
        raise PhotoRenderError("HEIC/AVIF bit depth and color management are not yet validated for fidelity-safe editing")
    if image.mode in ("I;16", "I;16B", "I;16L", "I", "F", "CMYK"):
        raise PhotoRenderError("High-bit-depth or CMYK photo cannot be preserved by this renderer yet")
    if ext == ".png":
        with open(path, "rb") as source:
            header = source.read(25)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 25 and header[24] > 8:
            raise PhotoRenderError("16-bit PNG editing is not supported without precision loss")
    if ext in (".tif", ".tiff"):
        bits = getattr(image, "tag_v2", {}).get(258, (8,))
        if isinstance(bits, int):
            bits = (bits,)
        if any(bit > 8 for bit in bits):
            raise PhotoRenderError("16-bit TIFF editing is not supported without precision loss")


def _choose_still(image: Image.Image, ext: str, frame_index: int | None) -> None:
    """MPOs are collections of JPEG *stills*, not an animation to truncate.

    Require an explicit index for MPO so callers such as background replacement
    cannot silently use only its primary still. Everything else remains strictly
    single-frame (no GIF/WebP animation or first-page TIFF fallback).
    """
    frames = getattr(image, "n_frames", 1)
    if image.format == "MPO" and ext in (".jpg", ".jpeg", ".mpo"):
        if type(frames) is not int or frames < 1:
            raise PhotoRenderError("Invalid multi-picture JPEG")
        if frame_index is None:
            if frames > 1:
                raise PhotoRenderError("Multi-picture JPEG contains several stills; add it to the batch to keep every photo")
            frame_index = 0
        if type(frame_index) is not int or not 0 <= frame_index < frames:
            raise PhotoRenderError("Invalid multi-picture JPEG still index")
        image.seek(frame_index)
    elif getattr(image, "is_animated", False) or frames != 1:
        raise PhotoRenderError("Animated/multipage files are outside the still-photo editor")
    elif frame_index not in (None, 0) or isinstance(frame_index, bool):
        raise PhotoRenderError("Single still photo has no other frame")


def still_photo_frames(path: str) -> range:
    """Identify each importable JPEG still without guessing a primary frame."""
    ext = Path(path).suffix.lower()
    if ext not in STILL_EXTENSIONS:
        raise PhotoRenderError("Unsupported still-photo extension")
    if ext == ".nef":
        return range(1)
    try:
        with Image.open(path) as image:
            if image.format == "MPO" and ext in (".jpg", ".jpeg", ".mpo"):
                frames = getattr(image, "n_frames", 0)
                if type(frames) is not int or frames < 1:
                    raise PhotoRenderError("Invalid multi-picture JPEG")
                return range(frames)
            _choose_still(image, ext, None)
            return range(1)
    except PhotoRenderError:
        raise
    except Exception as exc:
        raise PhotoRenderError(f"Cannot read still photo: {exc}") from exc


def _open_source(path: str, *, preview: bool = False,
                 frame_index: int | None = None) -> tuple[Image.Image | np.ndarray, bytes | None, bool]:
    ext = Path(path).suffix.lower()
    if ext not in STILL_EXTENSIONS:
        raise PhotoRenderError(f"{ext or 'Unknown file'} is not a supported still-photo extension")
    if ext == ".nef":
        if frame_index not in (None, 0) or isinstance(frame_index, bool):
            raise PhotoRenderError("NEF contains one editable still")
        try:
            import rawpy
        except ImportError as exc:
            raise PhotoRenderError("NEF support needs rawpy/LibRaw installed") from exc
        try:
            with rawpy.imread(path) as raw:
                if preview:
                    try:
                        thumb = raw.extract_thumb()
                        if thumb.format == rawpy.ThumbFormat.JPEG:
                            with Image.open(io.BytesIO(thumb.data)) as image:
                                return ImageOps.exif_transpose(image).convert("RGB"), None, False
                        return Image.fromarray(thumb.data).convert("RGB"), None, False
                    except Exception:
                        pass
                # RawPy defaults to output sRGB; we embed an sRGB profile on TIFF export.
                pixels = raw.postprocess(output_bps=16, no_auto_bright=True, use_camera_wb=True)
                return pixels, None, True
        except Exception as exc:
            raise PhotoRenderError(f"Cannot decode this NEF camera/compression: {exc}") from exc
    try:
        with Image.open(path) as image:
            _choose_still(image, ext, frame_index)
            if image.width * image.height > MAX_RENDER_PIXELS:
                raise PhotoRenderError("Photo exceeds the current safe processing size")
            _check_depth(path, image)
            profile = image.info.get("icc_profile")
            if preview:
                image.thumbnail((1400, 1000), Image.Resampling.LANCZOS)
            image = ImageOps.exif_transpose(image)
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            return image.convert("RGBA" if has_alpha else "RGB"), profile, False
    except PhotoRenderError:
        raise
    except Exception as exc:
        raise PhotoRenderError(f"Cannot read still photo: {exc}") from exc


def source_info(path: str, *, frame_index: int | None = None) -> dict:
    """Validate still-photo intake and report source dimensions, not thumbnail size."""
    ext = Path(path).suffix.lower()
    if ext not in STILL_EXTENSIONS:
        raise PhotoRenderError("Unsupported still-photo extension")
    if ext == ".nef":
        _open_source(path, preview=True, frame_index=frame_index)  # validate LibRaw
        import rawpy
        with rawpy.imread(path) as raw:
            return {"size": (raw.sizes.width, raw.sizes.height), "raw": True}
    try:
        with Image.open(path) as image:
            _choose_still(image, ext, frame_index)
            if image.width * image.height > MAX_RENDER_PIXELS:
                raise PhotoRenderError("Photo exceeds the current safe processing size")
            _check_depth(path, image)
            return {"size": image.size, "raw": False}
    except PhotoRenderError:
        raise
    except Exception as exc:
        raise PhotoRenderError(f"Cannot read still photo: {exc}") from exc


def _mask_from_strokes(photo: Photo, size: tuple[int, int]) -> Image.Image:
    # A blank manual mask deliberately does NOT pretend to be auto-segmentation.
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    w, h = size
    for stroke in photo.mask_strokes:
        x, y = round(stroke["x"] * w), round(stroke["y"] * h)
        radius = max(1, round(stroke["radius"] * min(w, h)))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=255 if stroke["add_background"] else 0)
    return mask


def render(photo: Photo, batch: BatchSession, *, preview: bool = False) -> tuple[Image.Image | np.ndarray, bytes | None, bool]:
    """Render a full-res image, or an explicitly downsampled UI preview.

    Return (image, source ICC, 16-bit RAW). Non-RAW outputs are Pillow images;
    16-bit NEF outputs are RGB uint16 ndarrays (never coerced to 8 bits).
    """
    image, profile, raw = _open_source(photo.source, preview=preview, frame_index=photo.frame_index)
    values = batch.effective_settings(photo.number)
    if raw:
        pixels = image
        if pixels.shape[0] * pixels.shape[1] > MAX_RENDER_PIXELS:
            raise PhotoRenderError("NEF exceeds the current safe processing size")
        if photo.crop:
            x0, y0, x1, y1 = photo.crop
            h, w = pixels.shape[:2]
            pixels = pixels[round(y0*h):round(y1*h), round(x0*w):round(x1*w)]
        if photo.rotation:
            pixels = np.rot90(pixels, photo.rotation // 90)
        if photo.flip_horizontal:
            pixels = np.fliplr(pixels)
        if photo.background or photo.mask_strokes:
            raise PhotoRenderError("16-bit NEF background masking is not yet implemented; no downgraded export was written")
        depth = 65535
        data = pixels.astype(np.float32) / depth
    else:
        if photo.crop:
            x0, y0, x1, y1 = photo.crop
            w, h = image.size
            image = image.crop((round(x0*w), round(y0*h), round(x1*w), round(y1*h)))
        if photo.rotation:
            image = image.rotate(photo.rotation, expand=True)
        if photo.flip_horizontal:
            image = ImageOps.mirror(image)
        data = np.asarray(image).astype(np.float32) / 255.0
        depth = 255
    color = data[:, :, :3]
    if values["exposure"]:
        color *= 2.0 ** values["exposure"]
    if values["brightness"]:
        color += values["brightness"] * 0.5
    if values["contrast"]:
        color[:] = (color - 0.5) * (1 + values["contrast"]) + 0.5
    luminance = color.mean(axis=2, keepdims=True)
    if values["highlights"]:
        color += values["highlights"] * np.maximum(0, luminance - 0.5) * 0.9
    if values["shadows"]:
        color += values["shadows"] * np.maximum(0, 0.5 - luminance) * 0.9
    if values["saturation"]:
        color[:] = luminance + (color - luminance) * (1 + values["saturation"])
    color[:, :, 0] += values["warmth"] * 0.12 + values["tint"] * 0.07
    color[:, :, 2] -= values["warmth"] * 0.12 - values["tint"] * 0.07
    color[:, :, 1] -= values["tint"] * 0.07
    if values["vignette"]:
        h, w = color.shape[:2]
        yy, xx = np.ogrid[-1:1:complex(h), -1:1:complex(w)]
        falloff = np.minimum(1, (xx*xx + yy*yy) * 0.65)[:, :, None]
        color *= 1 - values["vignette"] * falloff * 0.75
    np.clip(color, 0, 1, out=color)
    if values["sharpness"]:
        # Unsharp mask in the current float32 working depth, including 16-bit RAW.
        padded = np.pad(color, ((1, 1), (1, 1), (0, 0)), mode="edge")
        blurred = (color + padded[:-2, 1:-1] + padded[2:, 1:-1]
                   + padded[1:-1, :-2] + padded[1:-1, 2:]) / 5
        color[:] = np.clip(color + (color - blurred) * values["sharpness"], 0, 1)
    if raw:
        return np.round(color * depth).astype(np.uint16), profile, True
    out = Image.fromarray(np.round(data * depth).astype(np.uint8),
                          "RGBA" if data.shape[2] == 4 else "RGB")
    if photo.background:
        mode = photo.background.get("mode")
        if mode not in ("blur", "remove", "color", "image"):
            raise PhotoRenderError("Unknown background effect")
        mask = _mask_from_strokes(photo, out.size).filter(ImageFilter.GaussianBlur(1))
        base = out.convert("RGBA")
        if mode == "blur":
            amount = float(photo.background.get("intensity", 8))
            effect = base.filter(ImageFilter.GaussianBlur(max(0, min(50, amount))))
        elif mode == "remove":
            alpha = ImageOps.invert(mask)
            base.putalpha(Image.fromarray(np.minimum(np.asarray(base.getchannel("A")),
                                                       np.asarray(alpha)).astype(np.uint8)))
            return base, profile, False
        elif mode == "color":
            effect = Image.new("RGBA", out.size, photo.background.get("color", "#ffffff"))
        else:
            bg_path = photo.background.get("source")
            if not bg_path:
                raise PhotoRenderError("Replacement image is missing")
            if source_info(bg_path)["raw"]:
                raise PhotoRenderError("NEF replacement requires 16-bit compositing, not yet implemented")
            # Check original dimensions before any preview-only thumbnail operation.
            bg_w, bg_h = source_info(bg_path)["size"]
            if not preview and (bg_w < out.width or bg_h < out.height):
                raise PhotoRenderError("Replacement image would be upscaled; choose a larger image")
            replacement, _, _ = _open_source(bg_path, preview=preview)
            replacement = replacement.convert("RGBA")
            effect = ImageOps.fit(replacement, out.size, Image.Resampling.LANCZOS)
        result = Image.composite(effect, base, mask)
        return result, profile, False
    return out, profile, False


def export_lossless(photo: Photo, batch: BatchSession, path: str) -> str:
    """Save atomically to an explicit lossless PNG/TIFF; never emit JPEG."""
    ext = Path(path).suffix.lower()
    if ext not in (".png", ".tif", ".tiff"):
        raise PhotoRenderError("Lossless master must be PNG or TIFF")
    image, profile, raw = render(photo, batch)
    if raw and ext != ".tiff" and ext != ".tif":
        raise PhotoRenderError("16-bit NEF master currently requires TIFF")
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=parent, prefix=".render-", suffix=ext,
                                         delete=False) as out:
            temporary = out.name
        if raw:
            import tifffile
            # rawpy postprocess returns sRGB; use standard sRGB ICC when available.
            icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            tifffile.imwrite(temporary, image, photometric="rgb", compression="deflate",
                             extratags=[(34675, "B", len(icc), icc, False)])
        else:
            kwargs = {"icc_profile": profile} if profile else {}
            if ext == ".png":
                image.save(temporary, format="PNG", compress_level=6, **kwargs)
            else:
                image.save(temporary, format="TIFF", compression="tiff_lzw", **kwargs)
        os.replace(temporary, path)
        return path
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
