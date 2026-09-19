"""
Test conversion without GUI - demonstrates acceptance gate + engine for all formats
"""
import os, tempfile
from PIL import Image
from src.converter.engine import ConversionEngine
from src.converter.formats import FORMATS, get_format_by_id
from src.converter.validator import validate_conversion

def create_sample_images(tmpdir):
    # Create sample PNG with alpha
    png_path = os.path.join(tmpdir, "sample.png")
    img = Image.new("RGBA", (400,300), (0,0,0,0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([0,0,400,300], fill=(74,222,128,255))
    draw.ellipse([50,50,350,250], fill=(255,100,100,200))
    draw.text((150,130), "PNG Sample", fill=(0,0,0,255))
    img.save(png_path)
    
    # Create SVG
    svg_path = os.path.join(tmpdir, "sample.svg")
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
  <rect width="400" height="300" fill="#4ade80"/>
  <circle cx="200" cy="150" r="100" fill="#ff6467" opacity="0.8"/>
  <text x="150" y="160" font-family="Arial" font-size="24" fill="black">SVG Sample</text>
</svg>'''
    with open(svg_path, 'w') as f:
        f.write(svg_content)
    
    # Create JPEG
    jpg_path = os.path.join(tmpdir, "sample.jpg")
    img2 = Image.new("RGB", (400,300), (100,150,255))
    draw2 = ImageDraw.Draw(img2)
    draw2.text((150,130), "JPG Sample", fill=(255,255,255))
    img2.save(jpg_path, quality=90)
    
    return [png_path, svg_path, jpg_path]

def test_matrix():
    print("=== Testing Acceptance Gate Matrix ===")
    src_ids = ["png", "jpeg", "svg", "webp", "gif"]
    tgt_ids = ["png", "jpeg", "webp", "svg", "pdf", "bmp", "gif", "avif"]
    for src_id in src_ids:
        src = get_format_by_id(src_id)
        if not src:
            continue
        print(f"\n--- {src_id.upper()} as source ---")
        for tgt_id in tgt_ids:
            tgt = get_format_by_id(tgt_id)
            if not tgt:
                continue
            gate = validate_conversion(src, tgt, source_has_alpha=True, source_is_animated=False)
            print(f"  {src_id:>5} -> {tgt_id:<5} : {gate.status:6} allowed={gate.allowed} | {gate.reason[:50]}")

def test_conversions():
    tmp = tempfile.mkdtemp(prefix="img_test_")
    print(f"\n=== Testing Actual Conversions in {tmp} ===")
    samples = create_sample_images(tmp)
    engine = ConversionEngine()
    
    tests = [
        (samples[0], "jpeg", "PNG->JPEG with alpha -> white bg"),
        (samples[0], "webp", "PNG->WEBP"),
        (samples[0], "bmp", "PNG->BMP"),
        (samples[0], "gif", "PNG->GIF (256 colors)"),
        (samples[0], "svg", "PNG->SVG (embed)"),
        (samples[0], "pdf", "PNG->PDF"),
        (samples[1], "png", "SVG->PNG (rasterize)"),
        (samples[1], "jpeg", "SVG->JPEG"),
        (samples[1], "pdf", "SVG->PDF"),
        (samples[2], "png", "JPEG->PNG"),
        (samples[2], "webp", "JPEG->WEBP"),
    ]
    
    success_count = 0
    for src_path, tgt_id, desc in tests:
        tgt = get_format_by_id(tgt_id)
        ext = tgt.exts[0]
        dst_path = os.path.join(tmp, f"converted_{os.path.basename(src_path).split('.')[0]}_{tgt_id}{ext}")
        success, msg, extra = engine.convert(src_path, dst_path, tgt_id, quality=90)
        status = "✅" if success else "❌"
        print(f"{status} {desc}: {msg} -> {os.path.basename(dst_path)} exists={os.path.exists(dst_path)}")
        if success:
            success_count += 1
            info = engine.get_image_info(dst_path)
            print(f"   Info: {info['width']}x{info['height']} {info['format']} {info['mode']} size={info['size_bytes']} bytes")
    
    print(f"\n=== Results: {success_count}/{len(tests)} conversions succeeded ===")
    print(f"All files in: {tmp}")

if __name__ == "__main__":
    test_matrix()
    test_conversions()
