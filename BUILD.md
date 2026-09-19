# Build Guide - EXE + Setup Installer V2 RHHHAAAAA

## Prerequisites (Windows Recommended)

- Python 3.9+ (3.11 recommended, 3.14 works but bleeding edge)
- Git
- Windows 10/11 for EXE build

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

Full:
```bash
pip install pillow-heif pillow-avif-plugin PyMuPDF cairosvg customtkinter
```

## Step 2: Run App V2

```bash
python src/app.py
# V2 has 3 tabs: Single, Batch 🔥, Tools
# Tools tab has pinger + context menu info + landing page
```

Test pinger:
```bash
python tools/pinger.py
python tools/pinger.py --watch --interval 60
powershell -File tools/pinger.ps1 -Watch
```

## Step 3: Build EXE

### OneFile
```bash
python build_exe.py --onefile
```
Output: `dist/ImageSwitcher.exe` (~80-120 MB)

### OneDir
```bash
python build_exe.py --onedir
```

Manual:
```bash
pyinstaller --onefile --windowed --name=ImageSwitcher --icon=assets/icon.ico --add-data="assets;assets" --collect-all=customtkinter --collect-all=cairosvg --hidden-import=PIL --hidden-import=cairosvg --hidden-import=pillow_heif --hidden-import=fitz src/app.py
```

Troubleshooting:
- **cairo not found**: Normal on Windows without GTK, SVG raster will fail but app works for raster. Install GTK runtime if needed.
- **PyMuPDF not found**: Renamed to pymupdf, but bundled anyway.

## Step 4: Install / Distribute V2

### Option A (recommended): PowerShell installer V2 - `install.ps1`

Full native installer, no extra tools, PowerShell 5.1 built-in.

**NEW V2: Context Menu + File Associations**

```powershell
# Basic - auto-detects dist\ImageSwitcher.exe
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1

# V2 FULL POWER - RHHHAAAAA mode
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -ContextMenu -FileAssociations -Force

# All users + context menu (UAC)
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -ContextMenu -FileAssociations -MachineScope

# From GitHub release
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Release -Sha256 <hash> -ContextMenu
```

**What it does V2:**
- Per-user `%LOCALAPPDATA%\Programs\Image Switcher` (no admin) or Program Files with `-MachineScope` + auto UAC relaunch
- SHA-256 verification
- Upgrade with timestamped backup, closes running app
- Desktop + Start Menu shortcuts
- Uninstall entry in Settings > Apps
- Generates `Uninstall-ImageSwitcher.ps1/.bat`
- **File associations** for 13 exts (`-FileAssociations`)
- **NEW: Context menu** (`-ContextMenu`):
  - `SystemFileAssociations\image\shell\ImageSwitcher` → Right-click image → Convert with Image Switcher
  - Per-extension handlers for each of 13 formats
  - `Directory\shell\ImageSwitcherBatch` → Right-click folder → Convert images in folder
  - `Directory\Background\shell\ImageSwitcherBatch` → Right-click inside folder
- Launches app when done

**Switches V2:**

| Switch | Effect |
|---|---|
| `-ReleaseUrl <url>` | Download specific EXE |
| `-Release` | Latest release ImageSwitcher.exe |
| `-Sha256 <hash>` | Verify checksum |
| `-InstallDir <path>` | Custom location |
| `-MachineScope` | All-users Program Files |
| `-FileAssociations` | Register PNG/JPG/WEBP/... |
| `-ContextMenu` | **NEW** Explorer context menu image + folder |
| `-NoDesktopIcon` / `-NoStartMenu` | Skip shortcuts |
| `-NoLaunch` | Don't start app |
| `-NoBackup` | No backup on upgrade |
| `-Force` / `-Quiet` | No prompts |
| `-Version <ver>` | Override version |

### Option B: Classic GUI Setup.exe via Inno Setup

1. Install Inno Setup 6: https://jrsoftware.org/download.php/is.exe
2. `iscc installer.iss`
3. Output: `dist/ImageSwitcher-Setup-1.1.0.exe`

## Step 5: Distribute V2

You now have:
- `dist/ImageSwitcher.exe` - portable
- `install.ps1` - V2 with context menu support
- `dist/ImageSwitcher-Setup-1.1.0.exe` - classic GUI (optional)
- `website/index.html` - landing page (deploy to GitHub Pages)
- `tools/pinger.py` + `tools/pinger.ps1` - update checker

For GitHub Releases: upload `ImageSwitcher.exe` + SHA-256 + `install.ps1` as assets.

Users install with:
```powershell
.\install.ps1 -Release -Sha256 <hash> -ContextMenu -FileAssociations
```

## Step 6: Landing Page

```bash
# Just open in browser, Tailwind CDN, no build
start website/index.html
# Or serve
python -m http.server 8000 --directory website
```

Deploy to GitHub Pages: push `website/` content to `gh-pages` branch or set Pages source to `/website` folder.

## Step 7: Pinger Usage

```bash
# Check once
python tools/pinger.py
# Watch mode with toast
python tools/pinger.py --watch --interval 60
# JSON output for CI
python tools/pinger.py --json
# PowerShell with toast
powershell -File tools/pinger.ps1 -Watch -Interval 60
```

In-app: Header shows live banner, Tools tab has buttons.

## Testing V2

1. EXE runs on clean Windows VM
2. Single tab: PNG → JPG, SVG → PNG, PNG → SVG
3. Batch tab: Select folder with 10 images, target WEBP, convert all
4. Context menu: Right-click image → Convert with Image Switcher (after install -ContextMenu)
5. Pinger: `python tools/pinger.py` shows remote main SHA
6. Searchable dropdown: type "trans" shows PNG, WEBP, SVG
7. Viewer: old vs new with checkerboard
8. Landing page: open `website/index.html`

## Final Checklist V2

- [ ] App runs via `python src/app.py` - 3 tabs visible
- [ ] Single conversion works
- [ ] Batch mode scans folder and converts
- [ ] Pinger shows main status
- [ ] Context menu installs and uninstalls
- [ ] EXE builds and runs on clean Windows
- [ ] install.ps1 V2 with -ContextMenu works
- [ ] New 3D icon shows in EXE and shortcuts
- [ ] Landing page opens and looks neon
- [ ] Mockup present in mockups/

You are done V2 RHHHAAAAA!
