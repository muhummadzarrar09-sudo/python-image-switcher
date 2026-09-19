"""
SVG and Vector handling - rasterize vector to raster, and embed raster in vector
"""
import base64
import io
import os
from typing import Tuple, Optional

def rasterize_svg(svg_path: str, output_path: Optional[str] = None, scale: float = 2.0, background_color: str = "transparent") -> Tuple[bytes, int, int]:
    """
    Convert SVG to PNG bytes using cairosvg if available, else fallback
    Returns (png_bytes, width, height)
    """
    # Try cairosvg first
    try:
        import cairosvg
        with open(svg_path, 'rb') as f:
            svg_data = f.read()
        png_bytes = cairosvg.svg2png(bytestring=svg_data, scale=scale, background_color=background_color if background_color != "transparent" else None)
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        w, h = img.size
        if output_path:
            with open(output_path, 'wb') as out:
                out.write(png_bytes)
        return png_bytes, w, h
    except Exception as e_cairo:
        # Try PyMuPDF as fallback for SVG
        try:
            import fitz
            # PyMuPDF can render SVG via converting to PDF? Try open as image
            # For SVG, we can create a placeholder using fitz
            doc = fitz.open(svg_path)
            if len(doc) > 0:
                page = doc[0]
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat, alpha=True)
                png_bytes = pix.tobytes("png")
                from PIL import Image
                img = Image.open(io.BytesIO(png_bytes))
                w, h = img.size
                if output_path:
                    with open(output_path, 'wb') as out:
                        out.write(png_bytes)
                doc.close()
                return png_bytes, w, h
            doc.close()
        except Exception:
            pass

        # Final fallback: generate placeholder PNG with text
        try:
            from PIL import Image, ImageDraw
            w, h = int(400*scale), int(400*scale)
            bg = (255,255,255,0) if background_color=="transparent" else (255,255,255,255)
            img = Image.new("RGBA", (w,h), bg)
            draw = ImageDraw.Draw(img)
            draw.rectangle([10,10,w-10,h-10], outline=(100,100,100,255), width=2)
            draw.text((20,20), f"SVG: {os.path.basename(svg_path)}", fill=(0,0,0,255))
            draw.text((20,40), f"Cairo missing: {str(e_cairo)[:80]}", fill=(200,0,0,255))
            draw.text((20,60), "Install: pip install cairosvg", fill=(0,0,200,255))
            # Draw a simple representation
            draw.ellipse([w//4, h//4, w*3//4, h*3//4], fill=(74,222,128,180), outline=(0,0,0,255), width=2)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            if output_path:
                with open(output_path, 'wb') as out:
                    out.write(png_bytes)
            return png_bytes, w, h
        except Exception as e:
            raise RuntimeError(f"SVG rasterization failed: {e_cairo} | fallback also failed: {e}")

def raster_to_svg(raster_path: str, svg_output_path: str, embed: bool = True, title: str = "Converted Image"):
    """
    Convert raster image to SVG by embedding as base64
    """
    from PIL import Image
    img = Image.open(raster_path)
    w, h = img.size

    if embed:
        # Read file and base64 encode
        with open(raster_path, 'rb') as f:
            data = f.read()
        # Detect mime
        ext = os.path.splitext(raster_path)[1].lower()
        mime_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
        }
        mime = mime_map.get(ext, 'image/png')
        # If not PNG, convert to PNG for embedding to preserve quality
        if mime != 'image/png':
            # Convert to PNG in memory
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            data = buf.getvalue()
            mime = 'image/png'

        b64 = base64.b64encode(data).decode('utf-8')
        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <title>{title}</title>
  <image width="{w}" height="{h}" xlink:href="data:{mime};base64,{b64}" href="data:{mime};base64,{b64}"/>
</svg>
'''
    else:
        # Link mode (not embedded)
        svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}">
  <title>{title}</title>
  <image width="{w}" height="{h}" xlink:href="{os.path.basename(raster_path)}"/>
</svg>
'''
    with open(svg_output_path, 'w', encoding='utf-8') as out:
        out.write(svg_content)
    return svg_output_path

def raster_to_pdf(raster_path: str, pdf_output_path: str):
    from PIL import Image
    img = Image.open(raster_path)
    if img.mode in ("RGBA", "LA"):
        # PDF doesn't support alpha well, composite on white
        bg = Image.new("RGB", img.size, (255,255,255))
        if img.mode == "RGBA":
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.save(pdf_output_path, "PDF", resolution=100.0)
    return pdf_output_path

def render_pdf_first_page(pdf_path: str, png_output_path: str, scale: int = 2):
    """
    Render first page of PDF to PNG for preview
    Tries PyMuPDF, then pdf2image, then fails gracefully
    """
    # Try PyMuPDF
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=True)
        pix.save(png_output_path)
        doc.close()
        return png_output_path
    except ImportError:
        pass
    except Exception:
        pass

    # Try pdf2image
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=200)
        if images:
            images[0].save(png_output_path, "PNG")
            return png_output_path
    except Exception:
        pass

    raise RuntimeError("PDF preview needs PyMuPDF (pip install PyMuPDF) or pdf2image")
