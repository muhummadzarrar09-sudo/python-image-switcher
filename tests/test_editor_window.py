"""Windows GUI smoke test: real adjustment controls and deferred export dialog."""
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Tk desktop smoke test runs on Windows CI")


def test_named_adjustment_sliders_and_export_dialog_do_not_write_early(tmp_path):
    import customtkinter as ctk
    from PIL import Image

    from src.editor.batch import EDIT_FIELDS
    from src.editor.window import EditorWindow, ExportOptions

    source = tmp_path / "product.png"
    Image.new("RGB", (30, 24), (100, 120, 140)).save(source)
    root = ctk.CTk()
    root.withdraw()
    editor = None
    dialog = None
    try:
        editor = EditorWindow(root)
        root.update()
        # Concept-derived layout: one working action row, then three adjacent
        # surfaces, not a second toolbar consuming canvas height.
        assert editor.header.winfo_height() <= 55
        assert editor.sidebar.winfo_rooty() == editor.workspace.winfo_rooty()
        assert editor.workspace.winfo_rooty() == editor.panel.winfo_rooty()
        assert editor.sidebar.winfo_width() <= 185
        assert editor.panel.winfo_rootx() > editor.canvas.winfo_rootx()
        assert set(editor.sliders) == set(EDIT_FIELDS)
        assert "sharpness" in editor.sliders and "sharpening" not in editor.sliders
        assert set(editor.value_labels) == set(EDIT_FIELDS)
        assert not hasattr(editor, "field")  # no single category/dropdown selector
        assert not hasattr(editor, "creator")  # rights appear only inside export
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        assert photo.id in editor._thumbnail_cache
        tile = editor._tiles[photo.id][0]
        editor.select(photo.number)
        assert editor._tiles[photo.id][0] is tile  # no costly rail rebuild
        editor.view_mode.set("Before")
        editor.show_current()  # real source preview, no non-functional before button
        editor.view_mode.set("After")
        editor.show_current()
        editor.scope.set("Selected")
        editor.sync_sliders()
        editor.change_value("contrast", 0.3)
        assert photo.protected
        assert editor.batch.effective_settings(photo.number)["contrast"] == 0.3
        editor.open_crop_tools()
        assert editor.crop_window and editor.crop_window.winfo_exists()
        editor.close_crop_tools()
        output = tmp_path / "outputs"
        dialog = ExportOptions(editor)
        root.update()
        assert dialog.folder.get() == ""
        assert dialog.selection.get().startswith("Entire numbered batch")
        assert not output.exists()  # opening/canceling Export never emits files
        dialog.close()
        dialog = None
        assert not output.exists()
    finally:
        if dialog and dialog.winfo_exists():
            dialog.close()
        if editor and editor.winfo_exists():
            editor.destroy()
        root.destroy()


def test_latest_preview_wins_after_fast_selection_and_edits(tmp_path):
    import customtkinter as ctk
    from PIL import Image
    from src.editor.window import EditorWindow

    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (800, 600), "red").save(first)
    Image.new("RGB", (800, 600), "blue").save(second)
    root = ctk.CTk()
    root.withdraw()
    editor = EditorWindow(root)
    try:
        root.update()
        a = editor.batch.add_photo(str(first))
        b = editor.batch.add_photo(str(second))
        editor.select(a.number)
        editor.select(b.number)
        editor.scope.set("Selected")
        editor.change_value("contrast", 0.15)
        deadline = time.monotonic() + 5
        while editor._displayed_number != b.number and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert editor._displayed_number == b.number
        assert editor._canvas_bounds[2] > 0
        assert editor.status.cget("text").startswith(f"#{b.number:04d}")
        assert editor._tiles[b.id][0].winfo_exists()
    finally:
        editor.destroy()
        root.destroy()
