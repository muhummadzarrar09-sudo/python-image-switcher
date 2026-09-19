# Python Image Switcher - Complete App Plan

## Vision
A professional desktop app that converts ANY image type to ANY other image type, with intelligent compatibility gating, searchable conversion selector, and dual viewer (old vs new). Handles raster, vector (SVG), animated, and modern formats. Builds as a real Windows EXE + Setup Installer.

---

## 1. Supported Formats Registry (45+)

### Core Raster (Pillow Native)
- JPEG / JPG, PNG, WEBP, BMP, GIF, TIFF/TIF, ICO, PPM, PGM, PBM, PNM, PCX, TGA, SGI, XBM, XPM, ICNS, IM, MSP, SPIDER, DIB, PALM, XBM, XV Thumbnails

### Modern Raster (Plugins)
- AVIF (via pillow-avif or pillow>=10.1), HEIF, HEIC (via pillow-heif), JPEG2000 (JP2, J2K, JPF, JPX), DDS (limited), QOI (via plugin), JXL (JPEG XL experimental)

### Vector / Master
- SVG, SVGZ, PDF, EPS, PS

### Meta / Professional
- PSD (read-only via Pillow), HDR, EXR (limited), CUR (cursor), FLI/FLC (autodesk), FTEX, GBR, etc.

Each format definition contains:
```python
{
  id: "png",
  exts: [".png"],
  name: "Portable Network Graphics",
  pillow_format: "PNG",
  category: "raster_lossless",
  mime: "image/png",
  supports_alpha: True,
  supports_animation: True (APNG),
  is_vector: False,
  is_lossy: False,
  can_read: True,
  can_write: True,
  requires_plugin: None
}
```

## 2. Acceptance Gate - Conversion Matrix Logic

The "acceptance gate" validates every source -> target pair.

### Rules:
1. **Vector -> Raster (SVG/PDF/EPS -> PNG/JPG etc)**
   - Allowed: YES, via CairoSVG / Ghostscript rasterization
   - Needs: cairosvg for SVG, PyMuPDF or pdf2image for PDF, Pillow for EPS
   - Warning if target doesn't support alpha -> composite on background

2. **Raster -> Vector**
   - Allowed: YES, but two modes:
     - Mode A (Master Wrap): Embed raster as base64 inside SVG (100% fidelity, not true vector)
     - Mode B (Trace): Potrace/autotrace to trace edges (experimental, optional dep)
   - Default to Wrap for safety

3. **Raster -> Raster**
   - Pillow handles most
   - Gate checks:
     - Alpha: Source has alpha, target=JPEG? -> require background color or warn composite on white
     - Animation: GIF/WEBP animated -> static target? -> extract first frame or all frames?
     - Color Mode: CMYK -> RGB conversion warning
     - HDR/16-bit -> 8-bit downgrade warning

4. **Transparency Handling**
   - If src has alpha and dst doesn't: Show color picker for background

5. **Quality Settings**
   - JPEG/WEBP/AVIF/HEIC: quality slider 1-100
   - PNG: compression level
   - GIF: colors, dithering

Matrix is computed at runtime, not hardcoded, so adding new format auto-updates.

UI shows:
- GREEN: Full support
- YELLOW: Supported with conversion loss (alpha, animation, quality)
- RED: Not supported / needs plugin / impossible

## 3. Searchable Dropdown Inside

Not a plain combobox. Custom widget:
- Click to open panel
- Top: Search Entry (filters as you type, fuzzy match on ext, name, mime)
- Middle: Scrollable list grouped by category: Common, Modern, Vector, Legacy
- Each row shows: Icon, Format Name, Extension, Compatibility Dot (green/yellow/red), Description
- Bottom: Info bar explaining why incompatible if red
- Keyboard nav: Arrow keys, Enter to select

Two instances:
- Source format (auto-detected but can override)
- Target format (filtered by acceptance gate based on source)

Search examples: typing "trans" shows PNG, WEBP, AVIF, GIF, SVG... typing "jpg" filters to JPEG, typing "vector" shows SVG group.

## 4. Viewer Panel - Universal Viewer

Dual panel layout:
- LEFT: OLD / Original image
- RIGHT: NEW / Converted image (or placeholder before conversion)

Each viewer:
- Canvas with checkerboard background (for transparency)
- Zoom: Fit, 100%, 25-400% slider, mouse wheel zoom
- Pan: Drag to pan when zoomed
- Metadata overlay: WxH, file size, format, color mode, DPI, has alpha, animated frames
- For SVG: renders to bitmap for preview but keeps vector data
- For ANY file: tries Pillow -> cairosvg -> pdf -> fallback to icon + info
- Comparison slider mode: drag divider to wipe between old/new
- Info bar: shows conversion warnings

## 5. Conversion Engine

`engine.py` flow:
1. Load source (Pillow, cairosvg, etc)
2. Validate via `validator.py` acceptance gate
3. Apply pre-processing: alpha composite if needed, mode conversion, resize if requested
4. Convert:
   - if vector->raster: render SVG at desired resolution (scale factor)
   - if raster->vector: embed or trace
   - if raster->raster: Pillow save with params
5. Save to temp for preview, then final output
6. Return metadata for viewer

Handles:
- Single file
- Batch folder (future)
- Preserve metadata option (EXIF)

## 6. App UI Layout (CustomTkinter)

```
[Header: Logo + Title + Settings]
[Drop Zone: Drag & Drop or Browse - shows file path + auto-detected format]
[Format Selectors Row: Source (searchable) -> Arrow -> Target (searchable) + Quality Settings]
[Viewer Row: Left Original | Divider Slider | Right Converted]
[Controls: Convert Button, Save As, Open Folder, Swap Formats]
[Log / Status Bar]
```

Theme: Dark modern, rounded corners, icons.

## 7. EXE & Setup Build

### PyInstaller Build
- `build_exe.py` creates:
  - One-dir build (fast start) for dev
  - One-file build (single EXE) for release
- Includes hidden imports: PIL, customtkinter, cairosvg, pillow_heif, etc.
- Bundles assets, icons

### Windows Installer (Inno Setup)
- `installer.iss` script creates real Setup.exe
- Steps:
  - Welcome page, license, install dir
  - Creates Start Menu shortcut, Desktop shortcut
  - Associates image formats optionally (open with)
  - Uninstaller

### Cross-platform
- For Mac/Linux: PyInstaller works, installer via DMG / .deb instructions in README

Build command:
```
pip install -r requirements.txt
python build_exe.py --onefile
# Then compile installer.iss with Inno Setup Compiler
```

## 8. File Structure
```
python-image-switcher/
├── src/
│   ├── app.py (entry point)
│   ├── converter/
│   │   ├── formats.py (45+ formats registry)
│   │   ├── validator.py (acceptance gate)
│   │   ├── engine.py (core conversion)
│   │   └── svg_handler.py
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── searchable_combobox.py
│   │   └── image_viewer.py
│   └── utils/
│       └── helpers.py
├── assets/
│   └── icon.ico, logo.png
├── requirements.txt
├── build_exe.py
├── installer.iss
├── PLAN.md (this)
└── README.md
```

## 9. Dependencies
- customtkinter (modern UI)
- Pillow >=10.0 (core)
- cairosvg (SVG -> PNG)
- pillow-heif (HEIC/HEIF)
- pillow-avif-plugin or pillow[avif]
- PyMuPDF or pdf2image (PDF rendering, optional)
- potracer? (optional vector trace)
- pyinstaller (build)

## 10. Future Extensions
- Batch conversion
- Resize / compress presets (Instagram, Web, Print)
- AI upscaling
- Right-click context menu integration
```

