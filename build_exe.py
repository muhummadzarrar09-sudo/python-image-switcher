"""
Build EXE for Python Image Switcher
Creates a complete standalone executable using PyInstaller

Usage:
  python build_exe.py --onefile   # single EXE (slower start, easy distribute)
  python build_exe.py --onedir    # folder with exe (fast start, recommended dev)
  python build_exe.py --onedir --windowed   # no console

Outputs to dist/
"""
import argparse
import os
import sys
import shutil
import PyInstaller.__main__

APP_NAME = "ImageSwitcher"
ENTRY = "src/app.py"
ICON_PATH = "assets/icon.ico"  # will create if missing

def ensure_icon():
    os.makedirs("assets", exist_ok=True)
    if not os.path.exists(ICON_PATH):
        # Create a simple icon from PNG using Pillow
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (256,256), (30,30,30,255))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([20,20,236,236], radius=30, fill=(74,222,128,255))
            draw.text((70,90), "IMG", fill=(0,0,0,255), font=None)  # simple
            # Save as ico
            img.save(ICON_PATH, sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
            print(f"Created placeholder icon at {ICON_PATH}")
        except Exception as e:
            print(f"Could not create icon: {e}")
            return None
    return ICON_PATH if os.path.exists(ICON_PATH) else None

def build(onefile=True, windowed=True, clean=True):
    icon = ensure_icon()

    args = [
        ENTRY,
        f"--name={APP_NAME}",
        "--noconfirm",
        f"--distpath={os.path.join(os.getcwd(),'dist')}",
        f"--workpath={os.path.join(os.getcwd(),'build')}",
        f"--specpath={os.getcwd()}",
        # Hidden imports
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=customtkinter",
        "--hidden-import=cairosvg",
        "--hidden-import=pillow_heif",
        "--hidden-import=fitz",
        "--hidden-import=PyMuPDF",
        "--collect-all=customtkinter",
        "--collect-all=cairosvg",
        # Add data
        f"--add-data=assets{os.pathsep}assets" if os.path.exists("assets") else "",
        # Optimize
        "--log-level=WARN",
    ]
    # Remove empty
    args = [a for a in args if a]

    if onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    if windowed:
        args.append("--windowed")
    else:
        args.append("--console")

    if icon:
        args.append(f"--icon={icon}")

    if clean:
        args.append("--clean")

    print("Building with args:", args)
    PyInstaller.__main__.run(args)

    # Post-build info
    dist = os.path.join(os.getcwd(), "dist")
    print(f"\n✅ Build finished. Check {dist}")
    if onefile:
        exe = os.path.join(dist, f"{APP_NAME}.exe" if sys.platform=="win32" else APP_NAME)
        if os.path.exists(exe):
            size_mb = os.path.getsize(exe)/1024/1024
            print(f"EXE: {exe} ({size_mb:.1f} MB)")
    else:
        folder = os.path.join(dist, APP_NAME)
        print(f"Folder build: {folder}")

    print("\nNext steps for SETUP installer:")
    print("1. Install Inno Setup (https://jrsoftware.org/isinfo.php)")
    print("2. Open installer.iss and compile to create Setup.exe")
    print("Or run: iscc installer.iss (if Inno Setup in PATH)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="Build single file exe")
    parser.add_argument("--onedir", action="store_true", help="Build folder")
    parser.add_argument("--console", action="store_true", help="Show console window")
    args = parser.parse_args()

    onefile = True
    if args.onedir:
        onefile = False
    if args.onefile:
        onefile = True

    windowed = not args.console

    build(onefile=onefile, windowed=windowed)
