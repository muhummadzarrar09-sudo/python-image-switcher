"""Private, read-only photo-format probe for diagnosing rejected camera JPGs.

Prints only the basename, decoder format, frame count and size; no EXIF,
image pixels or full path. Keep the original photo private if preferred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def inspect(path: Path) -> dict:
    with Image.open(path) as image:
        return {"filename": path.name, "format": image.format,
                "frames": getattr(image, "n_frames", 1),
                "animated_flag": bool(getattr(image, "is_animated", False)),
                "size": list(image.size)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path, help="One original JPG that showed the import error")
    args = parser.parse_args()
    print(json.dumps(inspect(args.photo), indent=2))


if __name__ == "__main__":
    main()
