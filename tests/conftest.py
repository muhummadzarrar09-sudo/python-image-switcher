"""One Windows Tk interpreter per test session.

Recreating the withdrawn CTk root between GUI tests can leave Tcl's library
lookup commands invalid on some Windows runners. Editors are isolated
CTkToplevel instances and are destroyed after each test.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture(scope="session")
def tk_root():
    if sys.platform != "win32":
        pytest.skip("Windows GUI fixture")
    import customtkinter as ctk
    root = ctk.CTk()
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()
