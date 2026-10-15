"""Screen placement math uses physical coordinates, not CTk logical units."""
import sys

from src.editor.window_geometry import popup_position, monitor_work_area


def test_150_percent_popup_is_clamped_to_work_area():
    client = {"x": 8, "y": 39, "width": 1000, "height": 700}
    area = {"x": 0, "y": 0, "width": 1920, "height": 1008}
    x, y = popup_position(client, (795, 862), area)
    assert x >= 8 and x + 795 <= 1920 - 8
    assert y >= 35 and y + 862 <= 1008 - 8
    for size in ((562, 458), (615, 652)):
        x, y = popup_position(client, size, area)
        assert x >= 8 and x + size[0] <= 1912
        assert y >= 35 and y + size[1] <= 1000


def test_unfittable_popup_not_declared_fitting():
    client = {"x": 8, "y": 39, "width": 960, "height": 640}
    x, y = popup_position(client, (795, 862),
                          {"x": 0, "y": 0, "width": 1024, "height": 720})
    assert y == 35 and y + 862 > 720  # strict capture review will reject it
    if sys.platform != "win32":
        assert monitor_work_area(None) is None
