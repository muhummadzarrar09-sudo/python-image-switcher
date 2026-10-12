"""The installed-app diagnostic is photo-free and CPU-only PCs stay usable."""
from __future__ import annotations

import json

from src.editor.diagnostics import installed_gpu_report


def test_generated_report_in_cpu_fallback_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_SWITCHER_GPU", "off")
    path = tmp_path / "report.json"
    report = installed_gpu_report(str(path))
    assert json.loads(path.read_text()) == report
    assert report["gpu_status"] == "CPU (GPU off)"
    assert report["gpu_used_for_generated_preview"] is False
    assert report["gpu_used_for_generated_export"] is False
    assert report["export_max_channel_difference"] == 0
    assert report["exported_png_max_channel_difference"] == 0
    assert report["max_channel_difference"] == 0
    assert report["differing_channel_count"] == 0
    assert report["total_channels"] == 512 * 256 * 3
    assert report["cpu_pixel_sha256"] == report["preview_pixel_sha256"]
    assert "generated" in report["note"].lower()
