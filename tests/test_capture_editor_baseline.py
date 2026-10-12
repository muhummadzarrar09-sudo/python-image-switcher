"""Validate baseline CLI helpers without requiring a GUI on Linux."""
import argparse

import pytest

from scripts.capture_editor_baseline import window_size, dpi_for_window


@pytest.mark.parametrize("text,expected", [("1456x766", (1456, 766)),
                                          ("1000X700", (1000, 700)),
                                          ("1800x1000", (1800, 1000))])
def test_window_size(text, expected):
    assert window_size(text) == expected


@pytest.mark.parametrize("text", ["100x700", "999x799", "1456x699", "not-a-size",
                                       "1456", "1456x766x100", "0x0"])
def test_window_size_rejects_invalid_sizes(text):
    with pytest.raises(argparse.ArgumentTypeError):
        window_size(text)


def test_no_dpi_probe_outside_windows():
    import sys
    if sys.platform != "win32":
        assert dpi_for_window(None) is None
