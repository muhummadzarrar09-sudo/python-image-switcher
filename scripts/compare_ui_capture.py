"""Compare explicitly approved Windows UI *regions* and write reviewable diff masks.

There is no approved baseline bundled with the project. A human-provided
manifest is required; this script cannot certify approval or a legal identity.
Do not use the AI export illustration or a private photo as a pixel baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _rectangle(value: list[int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    if (not isinstance(value, list) or len(value) != 4
            or any(type(item) is not int for item in value)):
        raise ValueError("ROI/exclusion must be [x, y, width, height] integers")
    x, y, width, height = value
    if min(x, y) < 0 or width <= 0 or height <= 0 or x + width > size[0] or y + height > size[1]:
        raise ValueError("ROI/exclusion lies outside the screenshot")
    return x, y, width, height


def _load_capture(directory: Path) -> dict:
    meta = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    if "Windows" not in meta.get("platform", ""):
        raise ValueError("Both baselines and captures must originate on a Windows desktop")
    return meta


def compare(manifest_path: Path, actual_dir: Path, output_dir: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # A marker can be self-declared; it is a workflow guard, not authentication.
    if (manifest.get("approved") is not True or manifest.get("scope") != "chrome-only"
            or not all(isinstance(manifest.get(k), str) and manifest[k].strip()
                       for k in ("approved_by", "approved_at", "reference_id"))
            or not isinstance(manifest.get("regions"), dict) or not manifest["regions"]):
        raise ValueError("Requires a human-reviewed chrome-only manifest with explicit approval metadata and ROIs")
    baseline_dir = manifest_path.parent
    baseline_meta, actual_meta = _load_capture(baseline_dir), _load_capture(actual_dir)
    if baseline_meta.get("requested_window") != actual_meta.get("requested_window"):
        raise ValueError("Reference and actual client viewport requests differ")
    if baseline_meta.get("dpi_for_window") != actual_meta.get("dpi_for_window"):
        raise ValueError("Reference and actual measured DPI differ; compare matching display settings")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for state, regions in manifest["regions"].items():
        if not isinstance(regions, list) or not regions:
            raise ValueError(f"{state} needs at least one explicitly approved region")
        if state not in baseline_meta.get("states", {}) or state not in actual_meta.get("states", {}):
            raise ValueError(f"Missing captured state: {state}")
        baseline_file, actual_file = baseline_dir / f"{state}.png", actual_dir / f"{state}.png"
        with Image.open(baseline_file) as image:
            before = np.asarray(image.convert("RGB"))
        with Image.open(actual_file) as image:
            after = np.asarray(image.convert("RGB"))
        if before.shape != after.shape:
            raise ValueError(f"{state} screenshot dimensions differ")
        height, width, _ = before.shape
        diff = np.max(np.abs(before.astype(np.int16) - after.astype(np.int16)), axis=2)
        display = np.zeros((height, width, 3), dtype=np.uint8)
        for region in regions:
            name = region["name"]
            x, y, w, h = _rectangle(region["rect"], (width, height))
            tolerance = region["channel_delta"]
            allowed = region["max_changed_fraction"]
            if (type(tolerance) is not int or not 0 <= tolerance <= 255
                    or isinstance(allowed, bool) or not isinstance(allowed, (int, float))
                    or not 0 <= allowed <= 1):
                raise ValueError(f"{state}/{name} needs channel_delta 0..255 and max_changed_fraction 0..1")
            included = np.zeros((height, width), dtype=bool)
            included[y:y+h, x:x+w] = True
            for excluded in region.get("exclude", []):
                ex, ey, ew, eh = _rectangle(excluded, (width, height))
                included[ey:ey+eh, ex:ex+ew] = False
            examined = int(np.count_nonzero(included))
            if not examined:
                raise ValueError(f"{state}/{name} excludes every pixel")
            changed = included & (diff > tolerance)
            fraction = int(np.count_nonzero(changed)) / examined
            display[changed] = (255, 55, 55)  # mask only; never include private source pixels
            rows.append({"state": state, "region": name, "compared_pixels": examined,
                         "changed_fraction": round(fraction, 6), "max_changed_fraction": allowed,
                         "channel_delta": tolerance, "passed": fraction <= allowed,
                         "baseline_sha256": hashlib.sha256(baseline_file.read_bytes()).hexdigest()})
        Image.fromarray(display).save(output_dir / f"{state}-diff-mask.png")
    report = {"passed": all(row["passed"] for row in rows), "reference_id": manifest["reference_id"],
              "scope": "approved chrome-only ROIs; image/photo content is not compared",
              "notice": "A manifest approval marker is not a verified signature or user sign-off by itself.",
              "regions": rows}
    (output_dir / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="User-approved manifest located beside reference capture.json")
    parser.add_argument("--actual", type=Path, required=True, help="New capture directory with matching viewport/DPI")
    parser.add_argument("--output", type=Path, required=True, help="Ignored directory for comparison.json and red-only diff masks")
    args = parser.parse_args()
    report = compare(args.manifest, args.actual, args.output)
    print(f"{sum(row['passed'] for row in report['regions'])}/{len(report['regions'])} approved chrome ROIs within tolerances")
    if not report["passed"]:
        parser.exit(1, "Visual changes exceed approved ROI tolerances; review comparison.json and red masks.\n")


if __name__ == "__main__":
    main()
