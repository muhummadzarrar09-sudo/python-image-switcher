"""No AI mockup is a golden image; compare only explicitly approved OS captures."""
import json

import numpy as np
import pytest
from PIL import Image

from scripts.compare_ui_capture import compare


def _write(folder, pixels, dpi=96):
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"platform": "Windows-11", "requested_window": {"width": 16, "height": 12},
            "dpi_for_window": dpi, "states": {"populated-editor": {}}}
    (folder / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    Image.fromarray(pixels).save(folder / "populated-editor.png")


def test_approved_chrome_roi_masks_variable_text_and_reports_real_change(tmp_path):
    baseline, actual, output = (tmp_path / name for name in ("baseline", "actual", "diff"))
    pixels = np.zeros((12, 16, 3), dtype=np.uint8)
    _write(baseline, pixels)
    changed = pixels.copy()
    changed[0:4, 0:4] = 255  # named variable region, intentionally ignored
    _write(actual, changed)
    manifest = {"approved": True, "scope": "chrome-only", "approved_by": "human reviewer",
                "approved_at": "2026-10-13", "reference_id": "test-reference",
                "regions": {"populated-editor": [{"name": "header without variable label",
                                                   "rect": [0, 0, 16, 4], "exclude": [[0, 0, 4, 4]],
                                                   "channel_delta": 3, "max_changed_fraction": 0}]}}
    manifest_file = baseline / "review-manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    report = compare(manifest_file, actual, output)
    assert report["passed"] and report["regions"][0]["compared_pixels"] == 48
    assert (output / "comparison.json").is_file()
    with Image.open(output / "populated-editor-diff-mask.png") as mask:
        assert not np.asarray(mask).any()  # diff artifact contains no original photo pixels
    changed[1, 6] = [100, 0, 0]
    _write(actual, changed)
    report = compare(manifest_file, actual, output)
    assert not report["passed"]
    assert report["regions"][0]["changed_fraction"] == pytest.approx(1/48, abs=1e-6)
    with Image.open(output / "populated-editor-diff-mask.png") as mask:
        assert mask.getpixel((6, 1)) == (255, 55, 55)
        assert mask.getpixel((0, 0)) == (0, 0, 0)


def test_rejects_unapproved_reference_or_mismatched_dpi(tmp_path):
    baseline, actual, output = (tmp_path / name for name in ("baseline", "actual", "diff"))
    pixels = np.zeros((12, 16, 3), dtype=np.uint8)
    _write(baseline, pixels)
    _write(actual, pixels)
    manifest = {"approved": False, "scope": "chrome-only", "approved_by": "x",
                "approved_at": "2026-10-13", "reference_id": "ref",
                "regions": {"populated-editor": [{"name": "header", "rect": [0, 0, 16, 4],
                                                   "channel_delta": 0, "max_changed_fraction": 0}]}}
    path = baseline / "review-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="human-reviewed"):
        compare(path, actual, output)
    manifest["approved"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    _write(actual, pixels, dpi=144)
    with pytest.raises(ValueError, match="DPI differ"):
        compare(path, actual, output)
    _write(actual, pixels)
    manifest["regions"]["populated-editor"][0]["rect"] = [0, 0, 17, 4]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        compare(path, actual, output)
