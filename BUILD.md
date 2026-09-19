# Build Guide - EXE + Setup Installer

## Prerequisites (Windows Recommended)

- Python 3.9+ (3.11 recommended)
- Git
- Windows 10/11 for EXE build (Linux/Mac can build but installer is Windows)

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

For full format support:
```bash
pip install pillow-heif pillow-avif-plugin PyMuPDF cairosvg customtkinter
```

## Step 2: Run App (Dev)

```bash
python src/app.py
# or
python main.py
```

## Step 3: Build EXE with PyInstaller

### Option A: OneFile (single EXE, easy to share)
```bash
python build_exe.py --onefile
```
Output: `dist/ImageSwitcher.exe` (~80-120 MB, includes all deps)

### Option B: OneDir (folder, fast startup)
```bash
python build_exe.py --onedir
```
Output: `dist/ImageSwitcher/ImageSwitcher.exe` + dependencies folder

### Manual PyInstaller (if script fails)

```bash
pyinstaller --onefile --windowed --name=ImageSwitcher --icon=assets/icon.ico --add-data="assets;assets" --collect-all=customtkinter --collect-all=cairosvg --hidden-import=PIL --hidden-import=cairosvg --hidden-import=pillow_heif --hidden-import=fitz src/app.py
```

### Troubleshooting Build

- **Missing tkinter**: On Linux, `sudo apt install python3-tk`
- **Missing cairo**: On Windows, cairosvg bundles needed DLLs via PyInstaller. If fails, install GTK runtime: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
- **libpython not found (Linux)**: `sudo apt install libpython3.11`
- **Large EXE**: Normal, includes Pillow, CustomTkinter, Cairo, etc. Use UPX to compress: download UPX and add `--upx-dir=/path/to/upx`

## Step 4: Build Setup Installer (Windows Setup.exe)

This creates a professional installer like any real Windows app.

1. Install **Inno Setup 6**: https://jrsoftware.org/download.php/is.exe
2. (Optional) Install Inno Setup VSCode extension
3. Compile:

**Via GUI:**
- Open `installer.iss` in Inno Setup Compiler
- Click Build → Compile
- Output: `dist/ImageSwitcher-Setup-1.0.0.exe`

**Via Command Line (if iscc in PATH):**
```bash
iscc installer.iss
```

**What the installer does:**
- Shows welcome, license (LICENSE.txt)
- Asks install dir (default Program Files)
- Copies EXE or folder
- Creates Start Menu shortcut
- Optional Desktop icon
- Creates uninstaller in Control Panel
- Optional: associate image formats

### Customizing installer.iss

Edit these lines in `installer.iss`:
```
#define MyAppVersion "1.0.0"  ; change version
#define MyAppPublisher "Your Name"
OutputBaseFilename=ImageSwitcher-Setup-{#MyAppVersion}
```

Add more file associations in [Tasks] and [Registry] sections if needed.

## Step 5: Distribute

You now have:
- `dist/ImageSwitcher.exe` - portable, no install needed, just run
- `dist/ImageSwitcher-Setup-1.0.0.exe` - full installer, professional

Share either. Setup is recommended for end users.

## Linux / Mac Build

Same PyInstaller command works, produces:
- Linux: `dist/ImageSwitcher` (binary)
- Mac: `dist/ImageSwitcher.app` (use --windowed --onedir for .app bundle)

For Mac DMG installer:
```bash
# Install create-dmg
brew install create-dmg
create-dmg --volname "Image Switcher" --window-pos 200 120 --window-size 600 400 --icon-size 100 --app-drop-link 425 120 dist/ImageSwitcher.dmg dist/ImageSwitcher.app
```

## CI/CD (GitHub Actions)

Example workflow to auto-build EXE on push:

```yaml
name: Build EXE
on: [push]
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: {python-version: '3.11'}
      - run: pip install -r requirements.txt pyinstaller
      - run: python build_exe.py --onefile
      - uses: actions/upload-artifact@v3
        with: {name: exe, path: dist/}
```

## Testing the EXE

1. Run `dist/ImageSwitcher.exe` on a clean Windows VM (no Python installed) to ensure it works standalone
2. Test conversions:
   - PNG → JPG (alpha handling)
   - SVG → PNG (rasterization)
   - PNG → SVG (embedding)
   - WEBP → AVIF (modern)
3. Check viewer shows old vs new
4. Test searchable dropdown: type "trans" should show PNG, WEBP, SVG, etc.

## Size Optimization (Optional)

- Use `--exclude-module` for unused formats if you want smaller EXE (but we want ALL formats)
- Use UPX compression
- Use `pip install pyinstaller[encryption]` for bytecode encryption

## Final Checklist Before Release

- [ ] App runs via `python src/app.py`
- [ ] `python src/cli.py list` shows 38+ formats
- [ ] `python src/cli.py gate png jpeg` shows yellow with warnings
- [ ] EXE builds and runs on clean Windows
- [ ] Setup installer builds and installs/uninstalls correctly
- [ ] Icons show correctly
- [ ] Viewer shows old and new images
- [ ] Search inside dropdown works

You are done! You have a COMPLETE app, not just a script.
