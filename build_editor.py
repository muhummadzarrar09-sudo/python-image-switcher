"""Build a standalone Windows still-photo editor PREVIEW (not a release)."""
import argparse
import importlib.util
from pathlib import Path
import PyInstaller.__main__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--console", action="store_true", help="Keep a console for CI diagnostics")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    options = [
        str(root / "src" / "editor_app.py"),
        "--name=ImageSwitcherEditor", "--onedir", "--noconfirm", "--clean",
        f"--distpath={root / 'dist'}", f"--workpath={root / 'build'}",
        f"--specpath={root}", "--collect-all=customtkinter",
        "--collect-all=rawpy", "--collect-all=tifffile",
        "--hidden-import=PIL.PngImagePlugin", "--hidden-import=PIL.TiffImagePlugin",
        "--hidden-import=PIL.JpegImagePlugin", "--hidden-import=PIL.WebPImagePlugin",
        "--hidden-import=src.editor.window",
    ]
    # Optional wheel is installed best-effort by the Windows updater. Bundle
    # its Python/OpenCL loader only when present; the GPU driver/ICD remains a
    # device capability, never a prerequisite for launching on a CPU-only PC.
    if importlib.util.find_spec("pyopencl") is not None:
        options.append("--collect-all=pyopencl")
    if (root / "assets" / "icon.ico").is_file():
        options.append(f"--icon={root / 'assets' / 'icon.ico'}")
    options.append("--console" if args.console else "--windowed")
    PyInstaller.__main__.run(options)


if __name__ == "__main__":
    main()
