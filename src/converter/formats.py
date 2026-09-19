"""
Format Registry - Every image format with metadata for acceptance gate
"""
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ImageFormat:
    id: str  # canonical id
    exts: List[str]
    name: str
    category: str  # common_raster, lossless_raster, lossy_raster, modern_raster, vector, legacy_raster, animated
    mime: str
    pillow_format: Optional[str]  # None if not directly supported by Pillow
    supports_alpha: bool
    supports_animation: bool
    is_vector: bool
    is_lossless: bool
    can_read: bool
    can_write: bool
    requires_plugin: Optional[str]  # pip package
    description: str
    color_modes: List[str] = field(default_factory=lambda: ["RGB", "RGBA"])

# Comprehensive list - 50+ formats
FORMATS = [
    # === COMMON RASTER LOSSLESS ===
    ImageFormat("png", [".png"], "PNG", "common_raster", "image/png", "PNG", True, True, False, True, True, True, None, "Portable Network Graphics - lossless with transparency", ["RGB","RGBA","L","LA","P"]),
    ImageFormat("jpeg", [".jpg",".jpeg",".jpe",".jfif",".jif"], "JPEG", "common_raster", "image/jpeg", "JPEG", False, False, False, False, True, True, None, "Joint Photographic Experts Group - lossy photo format", ["RGB","L","CMYK"]),
    ImageFormat("webp", [".webp"], "WEBP", "modern_raster", "image/webp", "WEBP", True, True, False, False, True, True, None, "WebP - modern web format, lossy/lossless + animation", ["RGB","RGBA"]),
    ImageFormat("bmp", [".bmp",".dib"], "BMP", "common_raster", "image/bmp", "BMP", True, False, False, True, True, True, None, "Bitmap - uncompressed Windows bitmap", ["RGB","RGBA"]),
    ImageFormat("gif", [".gif"], "GIF", "animated", "image/gif", "GIF", True, True, False, True, True, True, None, "Graphics Interchange Format - 256 colors + animation", ["P","RGB","RGBA"]),
    ImageFormat("tiff", [".tiff",".tif"], "TIFF", "common_raster", "image/tiff", "TIFF", True, True, False, True, True, True, None, "Tagged Image File Format - high quality print", ["RGB","RGBA","CMYK","L"]),
    ImageFormat("ico", [".ico"], "ICO", "common_raster", "image/x-icon", "ICO", True, False, False, True, True, True, None, "Icon - multi-size icon container", ["RGB","RGBA"]),

    # === MODERN RASTER ===
    ImageFormat("avif", [".avif",".avifs"], "AVIF", "modern_raster", "image/avif", "AVIF", True, True, False, False, True, True, "pillow-avif-plugin", "AV1 Image File Format - next-gen ultra compressed", ["RGB","RGBA"]),
    ImageFormat("heif", [".heif"], "HEIF", "modern_raster", "image/heif", "HEIF", True, True, False, False, True, True, "pillow-heif", "High Efficiency Image File Format", ["RGB","RGBA"]),
    ImageFormat("heic", [".heic"], "HEIC", "modern_raster", "image/heic", "HEIF", True, True, False, False, True, True, "pillow-heif", "High Efficiency Image Coding - Apple photos", ["RGB","RGBA"]),
    ImageFormat("jxl", [".jxl"], "JPEG XL", "modern_raster", "image/jxl", "JXL", True, True, False, True, True, True, "pillow-jxl-plugin", "JPEG XL - future JPEG replacement", ["RGB","RGBA"]),
    ImageFormat("jp2", [".jp2",".j2k",".jpf",".jpx",".j2c"], "JPEG 2000", "modern_raster", "image/jp2", "JPEG2000", True, False, False, True, True, True, None, "JPEG 2000 - wavelet based high quality", ["RGB","RGBA","L"]),
    ImageFormat("hdr", [".hdr",".rgbe"], "HDR", "modern_raster", "image/vnd.radiance", "HDR", False, False, False, True, True, True, None, "Radiance HDR - high dynamic range", ["RGB"]),
    ImageFormat("exr", [".exr"], "OpenEXR", "modern_raster", "image/x-exr", "EXR", True, False, False, True, True, True, "OpenEXR", "OpenEXR - professional HDR VFX", ["RGB","RGBA"]),

    # === LEGACY / LESS COMMON RASTER (Pillow supported) ===
    ImageFormat("tga", [".tga",".icb",".vda",".vst"], "TGA", "legacy_raster", "image/x-tga", "TGA", True, False, False, True, True, True, None, "Truevision TGA - game textures", ["RGB","RGBA"]),
    ImageFormat("pcx", [".pcx"], "PCX", "legacy_raster", "image/x-pcx", "PCX", False, False, False, True, True, True, None, "PC Paintbrush Exchange", ["RGB","P"]),
    ImageFormat("ppm", [".ppm"], "PPM", "legacy_raster", "image/x-portable-pixmap", "PPM", False, False, False, True, True, True, None, "Portable Pixmap - color", ["RGB"]),
    ImageFormat("pgm", [".pgm"], "PGM", "legacy_raster", "image/x-portable-graymap", "PPM", False, False, False, True, True, True, None, "Portable Graymap - grayscale", ["L"]),
    ImageFormat("pbm", [".pbm"], "PBM", "legacy_raster", "image/x-portable-bitmap", "PPM", False, False, False, True, True, True, None, "Portable Bitmap - black & white", ["1"]),
    ImageFormat("pnm", [".pnm"], "PNM", "legacy_raster", "image/x-portable-anymap", "PPM", False, False, False, True, True, True, None, "Portable Anymap - PBM/PGM/PPM family", ["RGB","L","1"]),
    ImageFormat("sgi", [".sgi",".rgb",".rgba",".bw"], "SGI", "legacy_raster", "image/sgi", "SGI", True, False, False, True, True, True, None, "Silicon Graphics Image", ["RGB","RGBA","L"]),
    ImageFormat("xbm", [".xbm"], "XBM", "legacy_raster", "image/x-xbitmap", "XBM", False, False, False, True, True, True, None, "X11 Bitmap - monochrome", ["1"]),
    ImageFormat("xpm", [".xpm"], "XPM", "legacy_raster", "image/x-xpixmap", "XPM", True, False, False, True, True, True, None, "X11 Pixmap - color icon", ["RGB","RGBA"]),
    ImageFormat("icns", [".icns"], "ICNS", "legacy_raster", "image/x-icns", "ICNS", True, False, False, True, True, True, None, "Apple Icon Image", ["RGB","RGBA"]),
    ImageFormat("dds", [".dds"], "DDS", "legacy_raster", "image/x-dds", "DDS", True, False, False, False, True, True, None, "DirectDraw Surface - GPU textures", ["RGB","RGBA"]),
    ImageFormat("psd", [".psd"], "PSD", "legacy_raster", "image/vnd.adobe.photoshop", "PSD", True, False, False, True, True, False, None, "Photoshop Document - read only", ["RGB","RGBA","CMYK"]),
    ImageFormat("cur", [".cur"], "CUR", "legacy_raster", "image/x-icon", "CUR", True, False, False, True, True, True, None, "Windows Cursor", ["RGB","RGBA"]),
    ImageFormat("ftex", [".ftc",".ftu"], "FTEX", "legacy_raster", "image/x-ftex", "FTEX", True, False, False, True, True, True, None, "Texture File Format", ["RGB","RGBA"]),
    ImageFormat("im", [".im"], "IM", "legacy_raster", "image/x-im", "IM", False, False, False, True, True, True, None, "IFUNC Image Memory", ["RGB","L"]),
    ImageFormat("msp", [".msp"], "MSP", "legacy_raster", "image/x-msp", "MSP", False, False, False, True, True, True, None, "Microsoft Paint - legacy", ["1"]),
    ImageFormat("qoi", [".qoi"], "QOI", "modern_raster", "image/qoi", "QOI", True, False, False, True, True, True, "qoi", "Quite OK Image - fast lossless", ["RGB","RGBA"]),
    ImageFormat("blp", [".blp"], "BLP", "legacy_raster", "image/x-blp", "BLP", True, False, False, False, True, True, None, "Blizzard Mipmap - game texture", ["RGB","RGBA"]),

    # === VECTOR / MASTER ===
    ImageFormat("svg", [".svg"], "SVG", "vector", "image/svg+xml", None, True, False, True, True, True, True, "cairosvg", "Scalable Vector Graphics - resolution independent", ["RGB","RGBA"]),
    ImageFormat("svgz", [".svgz"], "SVGZ", "vector", "image/svg+xml", None, True, False, True, True, True, True, "cairosvg", "Compressed SVG - gzipped vector", ["RGB","RGBA"]),
    ImageFormat("pdf", [".pdf"], "PDF", "vector", "application/pdf", "PDF", True, False, True, True, True, True, "PyMuPDF", "Portable Document Format - vector pages", ["RGB","RGBA","CMYK"]),
    ImageFormat("eps", [".eps"], "EPS", "vector", "application/postscript", "EPS", True, False, True, True, True, True, None, "Encapsulated PostScript - print vector", ["RGB","CMYK"]),
    ImageFormat("ps", [".ps"], "PS", "vector", "application/postscript", "EPS", True, False, True, True, True, True, None, "PostScript - page description", ["RGB","CMYK"]),
    ImageFormat("ai", [".ai"], "AI", "vector", "application/postscript", None, True, False, True, True, True, False, None, "Adobe Illustrator - vector (read via PDF)", ["RGB","CMYK"]),
]

# Build lookup tables
EXT_TO_FORMAT = {}
ID_TO_FORMAT = {}
for fmt in FORMATS:
    ID_TO_FORMAT[fmt.id] = fmt
    for ext in fmt.exts:
        EXT_TO_FORMAT[ext.lower()] = fmt
        EXT_TO_FORMAT[ext.lower().lstrip('.')] = fmt

def get_format_by_ext(ext: str) -> ImageFormat | None:
    if not ext:
        return None
    ext = ext.lower().strip()
    if not ext.startswith('.'):
        ext = '.' + ext
    return EXT_TO_FORMAT.get(ext) or EXT_TO_FORMAT.get(ext.lstrip('.'))

def get_format_by_id(fid: str) -> ImageFormat | None:
    return ID_TO_FORMAT.get(fid.lower())

def all_formats():
    return FORMATS

def formats_by_category(cat: str):
    return [f for f in FORMATS if f.category == cat]

def searchable_formats(query: str = ""):
    q = query.lower().strip()
    if not q:
        return FORMATS
    results = []
    for f in FORMATS:
        hay = f"{f.id} {' '.join(f.exts)} {f.name} {f.description} {f.category} {f.mime}".lower()
        if q in hay:
            results.append(f)
    return results
