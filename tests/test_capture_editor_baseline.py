"""Validate baseline CLI helpers without requiring a GUI on Linux."""
import argparse
import json

import pytest
from PIL import Image

from scripts.capture_editor_baseline import window_size, dpi_for_window, monitor_work_area
from scripts.ui_review import STATES, audit_capture, contrast_ratio, within, main as review_main


@pytest.mark.parametrize("text,expected", [("1456x766", (1456, 766)),
                                          ("1000X700", (1000, 700)),
                                          ("960x640", (960, 640)),
                                          ("1800x1000", (1800, 1000))])
def test_window_size(text, expected):
    assert window_size(text) == expected


@pytest.mark.parametrize("text", ["100x700", "959x799", "960x639", "not-a-size",
                                       "1456", "1456x766x100", "0x0"])
def test_window_size_rejects_invalid_sizes(text):
    with pytest.raises(argparse.ArgumentTypeError):
        window_size(text)


def test_no_dpi_probe_outside_windows():
    import sys
    if sys.platform != "win32":
        assert dpi_for_window(None) is None
        assert monitor_work_area(None) is None


def test_contrast_ratio_uses_linear_srgb_and_geometry_rejects_overflow():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21)
    assert contrast_ratio("#777777", "#ffffff") < 4.5
    outer = {"x": 10, "y": 20, "width": 100, "height": 80}
    assert within({"x": 12, "y": 21, "width": 90, "height": 79}, outer)
    assert not within({"x": 90, "y": 30, "width": 40, "height": 30}, outer)


def test_capture_audit_reports_actual_bounds_and_never_approves_fixture(tmp_path, monkeypatch, capsys):
    client = {"x": 10, "y": 20, "width": 1000, "height": 700}
    header = {"x": 10, "y": 20, "width": 1000, "height": 48}
    rail = {"x": 10, "y": 68, "width": 164, "height": 652}
    workspace = {"x": 174, "y": 68, "width": 530, "height": 652}
    panel = {"x": 704, "y": 68, "width": 306, "height": 652}
    canvas = {"x": 184, "y": 78, "width": 510, "height": 592}
    states = {}
    for name in STATES:
        state = {"editor_client": client, "image_pixels": [1000, 700],
                 "header": header, "sidebar": rail, "workspace": workspace,
                 "panel": panel, "canvas": canvas,
                 "selected_number": None if name == "empty-editor" else 3 if name == "missing-source" else 1,
                 "source_missing": name == "missing-source",
                 "protected_numbers": [1] if name != "empty-editor" else []}
        if name.startswith("background"):
            state["background_mode"] = "color" if name == "background-ready" else "none"
            state["mask_status"] = ("Mask ready" if name == "background-ready"
                                    else "Select After" if name == "background-before" else "Choose background")
        if name.endswith("tools") or name.startswith("background") or name == "export-overlay":
            state["popup"] = {"x": 200, "y": 100, "width": 200, "height": 150}
            Image.new("RGB", (200, 150)).save(tmp_path / f"{name}-popup.png")
        states[name] = state
        Image.new("RGB", (1000, 700)).save(tmp_path / f"{name}.png")
    meta = {"states": states, "fixture_only": True, "background_rejection": "Would be upscaled",
            "requested_window": {"width": 1000, "height": 700}, "dpi_for_window": 96,
            "monitor_work_area": {"x": 0, "y": 0, "width": 1200, "height": 900}}
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    report = audit_capture(tmp_path)
    assert report["passed"] and not report["approved_reference"] and report["fixture_only"]
    assert report["screen_fit_verified"]
    assert not report["header_actions_verified"]  # legacy captures lack button bounds
    assert report["measured"]["populated-editor"]["workspace_width"] == 530
    states["populated-editor"]["header_actions"] = [
        {"x": 20 + i * 80, "y": 25, "width": 55, "height": 30} for i in range(8)]
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    assert audit_capture(tmp_path)["passed"]
    states["populated-editor"]["header_actions"][7]["x"] = 1010
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    clipped = audit_capture(tmp_path)
    assert not clipped["passed"]
    assert "populated-editor header actions are visible" in [
        x["check"] for x in clipped["checks"] if not x["passed"]]
    del states["populated-editor"]["header_actions"]
    meta["requested_window"]["width"] = 1500  # DPI minsize must not silently change the requested test
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    report = audit_capture(tmp_path)
    assert not report["passed"]
    assert "Requested physical client size is actually honored" in [
        x["check"] for x in report["checks"] if not x["passed"]]
    meta["requested_window"]["width"] = 1000
    meta["monitor_work_area"]["height"] = 600
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    report = audit_capture(tmp_path)
    assert not report["passed"]
    assert "Editor remains inside monitor working area" in [
        x["check"] for x in report["checks"] if not x["passed"]]
    meta["monitor_work_area"]["height"] = 900
    meta["monitor_probe_attempted"] = True
    original_area = meta.pop("monitor_work_area")
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    assert "Monitor working area probe succeeded" in [
        x["check"] for x in audit_capture(tmp_path)["checks"] if not x["passed"]]
    meta["monitor_work_area"] = original_area
    states["populated-editor"]["panel"] = {"x": 950, "y": 68, "width": 306, "height": 652}
    (tmp_path / "capture.json").write_text(json.dumps(meta), encoding="utf-8")
    report = audit_capture(tmp_path)
    assert not report["passed"]
    assert "populated-editor panel inside client" in [x["check"] for x in report["checks"] if not x["passed"]]
    monkeypatch.setattr("sys.argv", ["ui_review.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        review_main()
    assert exc.value.code == 1
    assert "Empty-state physical bounds: client=" in capsys.readouterr().err
