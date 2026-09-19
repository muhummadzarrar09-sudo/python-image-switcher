"""
Core Conversion Engine - handles all raster/vector conversions with acceptance gate
"""
import os
import io
import tempfile
from typing import Optional, Tuple, Dict, Any
from PIL import Image, UnidentifiedImageError

from .formats import ImageFormat, get_format_by_ext, get_format_by_id, ID_TO_FORMAT
from .validator import validate_conversion, GateResult
from .svg_handler import rasterize_svg, raster_to_svg, raster_to_pdf

# Try to enable extra plugins
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

try:
    import pillow_avif  # noqa
except ImportError:
    try:
        # Pillow >=10.1 has AVIF built-in
        pass
    except:
        pass

class ConversionEngine:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="img_switch_")

    def detect_source_format(self, file_path: str) -> Optional[ImageFormat]:
        ext = os.path.splitext(file_path)[1].lower()
        fmt = get_format_by_ext(ext)
        if fmt:
            return fmt
        # Try to open with PIL to guess
        try:
            with Image.open(file_path) as im:
                pil_fmt = im.format
                # Map PIL format to our registry
                for f in ID_TO_FORMAT.values():
                    if f.pillow_format == pil_fmt:
                        return f
        except:
            pass
        # Check SVG by content
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as fh:
                head = fh.read(1024)
                if '<svg' in head.lower():
                    return get_format_by_id('svg')
        except:
            pass
        return None

    def get_image_info(self, file_path: str) -> Dict[str, Any]:
        """Get metadata for viewer panel"""
        info = {
            "path": file_path,
            "exists": os.path.exists(file_path),
            "size_bytes": 0,
            "width": 0,
            "height": 0,
            "format": "unknown",
            "mode": "unknown",
            "has_alpha": False,
            "is_animated": False,
            "frames": 1,
            "dpi": None,
            "error": None
        }
        if not os.path.exists(file_path):
            info["error"] = "File not found"
            return info
        try:
            info["size_bytes"] = os.path.getsize(file_path)
        except:
            pass

        ext = os.path.splitext(file_path)[1].lower()
        fmt = get_format_by_ext(ext)
        if fmt and fmt.is_vector:
            # Vector handling
            info["format"] = fmt.id.upper()
            info["mode"] = "vector"
            info["has_alpha"] = True
            # Try to get dimensions via XML parsing (no cairo needed)
            if fmt.id in ("svg", "svgz"):
                try:
                    import xml.etree.ElementTree as ET
                    # Handle gzipped svgz
                    if file_path.lower().endswith('.svgz'):
                        import gzip
                        with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                            content = f.read(4096)
                            # quick parse
                            import re
                            # Try to find width/height/viewBox via regex if XML parse fails on partial
                            w_match = re.search(r'width=["\']([^"\']+)["\']', content)
                            h_match = re.search(r'height=["\']([^"\']+)["\']', content)
                            vb_match = re.search(r'viewBox=["\']([^"\']+)["\']', content)
                            def parse_dim(s):
                                if not s:
                                    return 0
                                s = str(s).replace('px','').strip()
                                try:
                                    return int(float(s))
                                except:
                                    return 0
                            if w_match and h_match:
                                info["width"] = parse_dim(w_match.group(1))
                                info["height"] = parse_dim(h_match.group(1))
                            if (info["width"]==0 or info["height"]==0) and vb_match:
                                parts = vb_match.group(1).split()
                                if len(parts)==4:
                                    info["width"] = parse_dim(parts[2])
                                    info["height"] = parse_dim(parts[3])
                            if info["width"]==0:
                                info["width"]=512
                            if info["height"]==0:
                                info["height"]=512
                            return info
                    tree = ET.parse(file_path)
                    root = tree.getroot()
                    w = root.get('width', '0')
                    h = root.get('height', '0')
                    def parse_dim(s):
                        s = str(s).replace('px','').strip()
                        try:
                            return int(float(s))
                        except:
                            return 0
                    info["width"] = parse_dim(w)
                    info["height"] = parse_dim(h)
                    if info["width"]==0 or info["height"]==0:
                        vb = root.get('viewBox')
                        if vb:
                            parts = vb.split()
                            if len(parts)==4:
                                info["width"] = parse_dim(parts[2])
                                info["height"] = parse_dim(parts[3])
                    if info["width"]==0:
                        info["width"]=512
                    if info["height"]==0:
                        info["height"]=512
                except Exception as e:
                    # Don't set error for info, just default size
                    if info["width"]==0:
                        info["width"]=512
                    if info["height"]==0:
                        info["height"]=512
            return info

        # Raster via PIL
        try:
            with Image.open(file_path) as im:
                info["width"], info["height"] = im.size
                info["format"] = im.format or ext.strip('.').upper()
                info["mode"] = im.mode
                info["has_alpha"] = im.mode in ("RGBA","LA","PA") or (im.mode=="P" and "transparency" in im.info)
                info["is_animated"] = getattr(im, "is_animated", False)
                info["frames"] = getattr(im, "n_frames", 1)
                if "dpi" in im.info:
                    info["dpi"] = im.info["dpi"]
        except UnidentifiedImageError:
            info["error"] = "Cannot identify image file"
        except Exception as e:
            info["error"] = str(e)
        return info

    def convert(self, source_path: str, target_path: str, target_format_id: str, 
                background_color: Tuple[int,int,int] = (255,255,255),
                quality: int = 90,
                scale_factor: float = 2.0,
                resize: Optional[Tuple[int,int]] = None) -> Tuple[bool, str, Dict]:
        """
        Main conversion method
        Returns (success, message, info)
        """
        if not os.path.exists(source_path):
            return False, "Source file not found", {}

        source_fmt = self.detect_source_format(source_path)
        target_fmt = get_format_by_id(target_format_id)

        if not source_fmt:
            return False, "Cannot detect source format", {}
        if not target_fmt:
            return False, f"Unknown target format {target_format_id}", {}

        # Validate via acceptance gate
        src_info = self.get_image_info(source_path)
        gate = validate_conversion(source_fmt, target_fmt, 
                                   source_has_alpha=src_info.get("has_alpha", False),
                                   source_is_animated=src_info.get("is_animated", False))

        if not gate.allowed:
            return False, f"Conversion blocked: {gate.reason}", {"gate": gate}

        try:
            # === VECTOR -> RASTER ===
            if source_fmt.is_vector and not target_fmt.is_vector:
                if source_fmt.id in ("svg", "svgz"):
                    # Rasterize SVG to PNG first in temp
                    temp_png = os.path.join(self.temp_dir, "rasterized.png")
                    bg = None
                    if gate.needs_background:
                        bg = f"rgb({background_color[0]},{background_color[1]},{background_color[2]})"
                    png_bytes, w, h = rasterize_svg(source_path, temp_png, scale=scale_factor, background_color=bg or "transparent")
                    # Now convert that PNG to target
                    return self._convert_raster_to_raster(temp_png, target_path, target_fmt, background_color, quality, resize)
                elif source_fmt.id == "pdf":
                    # Render PDF first page
                    temp_png = os.path.join(self.temp_dir, "pdf_render.png")
                    try:
                        from .svg_handler import render_pdf_first_page
                        render_pdf_first_page(source_path, temp_png, scale=int(scale_factor))
                        return self._convert_raster_to_raster(temp_png, target_path, target_fmt, background_color, quality, resize)
                    except Exception as e:
                        return False, f"PDF rendering failed: {e}. Install PyMuPDF", {}
                else:
                    return False, f"Vector format {source_fmt.id} rasterization not yet implemented", {}

            # === RASTER -> VECTOR ===
            elif not source_fmt.is_vector and target_fmt.is_vector:
                if target_fmt.id in ("svg", "svgz"):
                    raster_to_svg(source_path, target_path, embed=True)
                    return True, f"Embedded raster in SVG", {"gate": gate}
                elif target_fmt.id == "pdf":
                    raster_to_pdf(source_path, target_path)
                    return True, f"Converted to PDF", {"gate": gate}
                else:
                    return False, f"Raster -> {target_fmt.id} not implemented", {}

            # === VECTOR -> VECTOR ===
            elif source_fmt.is_vector and target_fmt.is_vector:
                # For now, rasterize then embed, or copy if same
                if source_fmt.id == target_fmt.id:
                    import shutil
                    shutil.copy2(source_path, target_path)
                    return True, "Copied (same format)", {"gate": gate}
                # SVG -> PDF via cairosvg
                if source_fmt.id in ("svg","svgz") and target_fmt.id == "pdf":
                    try:
                        import cairosvg
                        cairosvg.svg2pdf(url=source_path, write_to=target_path)
                        return True, "SVG -> PDF converted", {"gate": gate}
                    except Exception as e:
                        return False, f"SVG->PDF failed: {e}", {}
                # Fallback: rasterize then embed
                temp_png = os.path.join(self.temp_dir, "vec2vec.png")
                png_bytes, w, h = rasterize_svg(source_path, temp_png, scale=scale_factor)
                if target_fmt.id in ("svg","svgz"):
                    raster_to_svg(temp_png, target_path)
                elif target_fmt.id == "pdf":
                    raster_to_pdf(temp_png, target_path)
                return True, f"Vector {source_fmt.id} -> {target_fmt.id} via raster intermediate", {"gate": gate}

            # === RASTER -> RASTER ===
            else:
                return self._convert_raster_to_raster(source_path, target_path, target_fmt, background_color, quality, resize)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Conversion error: {e}", {"gate": gate, "exception": str(e)}

    def _convert_raster_to_raster(self, src_path: str, dst_path: str, target_fmt: ImageFormat,
                                  bg_color: Tuple[int,int,int], quality: int, resize: Optional[Tuple[int,int]]) -> Tuple[bool,str,Dict]:
        try:
            with Image.open(src_path) as im:
                # Handle animation: take first frame for static targets
                if getattr(im, "is_animated", False) and not target_fmt.supports_animation:
                    im.seek(0)
                
                # Resize if requested
                if resize and resize[0]>0 and resize[1]>0:
                    im = im.resize(resize, Image.LANCZOS)

                # Handle alpha if target doesn't support it
                if (im.mode in ("RGBA","LA") or (im.mode=="P" and "transparency" in im.info)) and not target_fmt.supports_alpha:
                    # Composite on background
                    if im.mode == "RGBA":
                        background = Image.new("RGB", im.size, bg_color)
                        background.paste(im, mask=im.split()[-1])
                        im = background
                    elif im.mode == "LA":
                        background = Image.new("RGB", im.size, bg_color)
                        background.paste(im, mask=im.split()[-1])
                        im = background
                    elif im.mode == "P":
                        im = im.convert("RGBA")
                        background = Image.new("RGB", im.size, bg_color)
                        background.paste(im, mask=im.split()[-1])
                        im = background
                    else:
                        im = im.convert("RGB")

                # Ensure mode compatible with target
                if target_fmt.id in ("jpeg","jpg") and im.mode in ("RGBA","LA","P"):
                    im = im.convert("RGB")
                if target_fmt.id == "bmp" and im.mode == "RGBA":
                    # BMP supports RGBA in Pillow but not all viewers, keep
                    pass

                # Save params
                save_kwargs = {}
                pil_format = target_fmt.pillow_format

                if not pil_format:
                    return False, f"Target {target_fmt.id} has no Pillow saver", {}

                if pil_format == "JPEG":
                    save_kwargs["quality"] = quality
                    save_kwargs["optimize"] = True
                    if im.mode != "RGB":
                        im = im.convert("RGB")
                elif pil_format == "PNG":
                    save_kwargs["optimize"] = True
                    # compress_level 0-9 derived from quality? Use 6 default
                    save_kwargs["compress_level"] = max(0, min(9, 9 - quality//15))
                elif pil_format == "WEBP":
                    save_kwargs["quality"] = quality
                    save_kwargs["method"] = 4
                    if im.mode not in ("RGB","RGBA"):
                        im = im.convert("RGBA" if target_fmt.supports_alpha else "RGB")
                elif pil_format in ("TIFF","TIF"):
                    save_kwargs["compression"] = "tiff_lzw"
                elif pil_format == "GIF":
                    # Quantize if needed
                    if im.mode not in ("P","L"):
                        im = im.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=256)
                elif pil_format in ("HEIF","AVIF","JXL"):
                    save_kwargs["quality"] = quality

                # Ensure directory exists
                os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)

                # Handle multi-frame? For now save first frame or all if animated target supports
                if getattr(im, "is_animated", False) and target_fmt.supports_animation:
                    # Save all frames
                    frames = []
                    try:
                        for i in range(im.n_frames):
                            im.seek(i)
                            frames.append(im.copy())
                        if frames:
                            first = frames[0]
                            first.save(dst_path, format=pil_format, save_all=True, append_images=frames[1:], loop=0, **save_kwargs)
                        else:
                            im.save(dst_path, format=pil_format, **save_kwargs)
                    except Exception:
                        # fallback to first frame
                        im.seek(0)
                        im.save(dst_path, format=pil_format, **save_kwargs)
                else:
                    im.save(dst_path, format=pil_format, **save_kwargs)

                return True, f"Converted to {target_fmt.id.upper()}", {"gate": validate_conversion(get_format_by_ext(os.path.splitext(src_path)[1]) or target_fmt, target_fmt)}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Raster conversion failed: {e}", {}
