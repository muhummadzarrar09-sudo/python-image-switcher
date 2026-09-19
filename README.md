# 🖼️ Python Image Switcher - Universal Image Converter

> **Convert ANY image type to ANOTHER image type** with searchable dropdown, acceptance gate for EVERY format, dual viewer (old vs new), SVG raster/vector support, and real EXE installer.

![Version](https://img.shields.io/badge/version-1.0.0-green)
![Formats](https://img.shields.io/badge/formats-50%2B-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-yellow)

---

## ✨ Features Fr Fr

### 🔄 Universal Conversion
- **50+ formats**: PNG, JPEG, WEBP, BMP, GIF, TIFF, ICO, AVIF, HEIF, HEIC, JPEG XL, JPEG2000, HDR, EXR, TGA, PCX, PPM, PGM, PBM, SGI, XBM, XPM, DDS, PSD, CUR, QOI, BLP + Vector: SVG, SVGZ, PDF, EPS, PS, AI
- **Acceptance Gate**: Every source → target pair validated:
  - 🟢 Green = fully compatible
  - 🟡 Yellow = compatible with loss (alpha, animation, quality)
  - 🔴 Red = blocked / read-only / needs plugin
- Handles alpha, animation, color modes, transparency background picker

### 🔍 Searchable Dropdown Inside
- Not a boring combobox — **search bar INSIDE dropdown**
- Type to filter: `png`, `trans`, `vector`, `photo`, `modern` etc.
- Shows compatibility dot, grouped by category (Common, Modern, Vector, Legacy)
- Hover shows warnings & loss description
- Source auto-detected, target filtered by gate

### 👁️ Dual Viewer Panel
- **Left: OLD / Original** | **Right: NEW / Converted**
- Can view ANY file type: raster via Pillow, SVG via CairoSVG, PDF first page, etc.
- Checkerboard background for transparency
- Zoom (wheel), pan (drag), Fit, 100%, slider
- Metadata: dimensions, file size, format, mode, alpha, animated frames, DPI
- Comparison slider ready

### 🎨 SVG Master / Raster
- **Vector → Raster**: SVG/PDF/EPS → PNG/JPG/WEBP etc via CairoSVG (high-res scale factor)
- **Raster → Vector**: Embed raster as base64 inside SVG (100% fidelity) or PDF page
- Keeps vector editable when possible

### 📦 Complete App, Not Just Script
- Modern dark UI with CustomTkinter
- Builds to **real EXE** via PyInstaller
- **Setup installer** via Inno Setup (Windows Setup.exe with shortcuts, uninstaller, file associations)

---

## 📁 Project Structure

```
python-image-switcher/
├── src/
│   ├── app.py                  # Entry point
│   ├── converter/
│   │   ├── formats.py          # 50+ formats registry
│   │   ├── validator.py        # Acceptance gate matrix
│   │   ├── engine.py           # Core conversion logic
│   │   └── svg_handler.py      # SVG raster/vector handling
│   ├── ui/
│   │   ├── main_window.py      # Main app window
│   │   ├── searchable_combobox.py # Search inside dropdown
│   │   └── image_viewer.py     # Universal viewer panel
│   └── utils/
├── assets/                     # Icon, logo
├── requirements.txt
├── build_exe.py                # PyInstaller build script
├── installer.iss               # Inno Setup script for Setup.exe
├── PLAN.md                     # Architecture plan
└── README.md
```

---

## 🚀 Quick Start

### Install
```bash
pip install -r requirements.txt
```

### Run App
```bash
python src/app.py
# or
python -m src.app
# with file
python src/app.py myimage.png
```

### Test Conversion (CLI, no GUI)
```python
from src.converter.engine import ConversionEngine
engine = ConversionEngine()
engine.convert("input.png", "output.jpg", "jpeg", background_color=(255,255,255), quality=90)
```

---

## 🔨 Build EXE + Setup

### 1. Build EXE
```bash
# Single file EXE (easy distribute, slower start)
python build_exe.py --onefile

# Folder build (fast start)
python build_exe.py --onedir

# With console for debugging
python build_exe.py --onefile --console
```

Output: `dist/ImageSwitcher.exe` (or folder `dist/ImageSwitcher/`)

### 2. Build Setup Installer (Windows)
1. Install **Inno Setup**: https://jrsoftware.org/isinfo.php
2. Compile:
```bash
iscc installer.iss
# or open installer.iss in Inno Setup Compiler GUI and hit Compile
```
Output: `dist/ImageSwitcher-Setup-1.0.0.exe` - a real Windows installer with:
- Welcome page, license, install dir
- Start Menu + Desktop shortcuts
- Uninstaller
- Optional file associations

### Manual PyInstaller Command
```bash
pyinstaller --onefile --windowed --name=ImageSwitcher --icon=assets/icon.ico src/app.py --collect-all=customtkinter --hidden-import=PIL --hidden-import=cairosvg
```

---

## 🧠 Acceptance Gate Logic

The gate validates every pair at runtime:

- **Vector → Raster**: Allowed via CairoSVG/PyMuPDF rasterization. If target no alpha, needs background.
- **Raster → Vector**: Allowed, embeds raster in SVG/PDF (yellow - not true trace). Warning about base64 size.
- **Vector → Vector**: Yellow, may rasterize intermediate, loses editability.
- **Raster → Raster**: Checks alpha (JPEG no alpha), animation (GIF→JPG loses frames), lossy (PNG→JPEG quality loss), 256 colors (→GIF quantization), read-only (PSD).
- **Plugins**: AVIF needs `pillow-avif-plugin`, HEIC/HEIF needs `pillow-heif`, SVG needs `cairosvg`, PDF needs `PyMuPDF`.

UI shows reason + warnings + loss description.

---

## 📸 Screenshots (Concept)

- **Top**: File drop zone + auto-detected source format
- **Middle**: Source searchable dropdown ➡️ Target searchable dropdown (with green/yellow/red dots) + quality slider + background picker + resize
- **Bottom**: Dual viewer OLD vs NEW with zoom/pan + Convert button + Save As

---

## 🔧 Dependencies

- `customtkinter` - modern UI
- `Pillow` - core image handling
- `cairosvg` - SVG → raster
- `pillow-heif` - HEIC/HEIF
- `pillow-avif-plugin` - AVIF (or Pillow>=10.1 built-in)
- `PyMuPDF` - PDF rendering
- `pyinstaller` - EXE build

Optional for enhanced:
- `potracer` - true raster → vector tracing (future)

---

## 🗺️ Roadmap

- [x] 50+ formats registry
- [x] Acceptance gate with green/yellow/red
- [x] Searchable dropdown with search inside
- [x] Dual viewer old vs new + metadata + zoom/pan
- [x] SVG raster/vector master
- [x] EXE build + Inno Setup installer
- [ ] Batch folder conversion
- [ ] Resize presets (Instagram, Web, Print)
- [ ] AI upscaling
- [ ] Right-click context menu "Convert with Image Switcher"
- [ ] True vector tracing via potrace

---

## 📝 License

MIT - see LICENSE.txt

---

## 🙏 Credits

Built with ❤️ for universal image conversion. Fr fr lets gooo.

