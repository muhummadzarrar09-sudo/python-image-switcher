from PIL import Image

from scripts.inspect_still import inspect


def test_inspect_still_reports_no_full_path_or_exif(tmp_path):
    source = tmp_path / "CSC0108.JPG"
    Image.new("RGB", (10, 8), "red").save(source)
    info = inspect(source)
    assert info == {"filename": "CSC0108.JPG", "format": "JPEG",
                    "frames": 1, "animated_flag": False, "size": [10, 8]}
    assert str(tmp_path) not in str(info)
