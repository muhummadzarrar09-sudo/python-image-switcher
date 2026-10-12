"""Create/update an isolated alpha environment and run editor verification.

Use Python 3.11. On Windows, use the PowerShell wrapper at repo root to also
bootstrap Python/Inno Setup and optionally build/install the desktop app.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> None:
    print("+", *args, flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", default=".venv", help="Environment directory inside this checkout")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11):
        parser.error("The alpha is tested with Python 3.11; run this script using Python 3.11")
    path = (ROOT / args.venv).resolve()
    if path == ROOT or ROOT not in path.parents:
        parser.error("The environment path must be a subdirectory of this checkout")
    python = path / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        if path.exists():
            parser.error(f"{path} exists but is not a Python venv; refusing to replace it")
        print(f"Creating isolated environment: {path}", flush=True)
        venv.EnvBuilder(with_pip=True).create(path)
    # Never repurpose an existing venv built against another Python version.
    run(str(python), "-c", "import sys; assert sys.version_info[:2] == (3, 11), 'The existing venv must use Python 3.11'")
    run(str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-editor.txt"), "pytest")
    run(str(python), "-m", "pytest", "-q", "tests/test_photo_project.py", "tests/test_editor_render.py")
    run(str(python), "src/editor_app.py", "--editor-self-test")
    print(f"Alpha dependencies installed and verified in {path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Update stopped: command exited with status {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode or 1)
