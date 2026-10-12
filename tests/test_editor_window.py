"""Windows GUI smoke test: real adjustment controls and deferred export dialog."""
import sys

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
        assert set(editor.sliders) == set(EDIT_FIELDS)
        assert "sharpness" in editor.sliders and "sharpening" not in editor.sliders
        assert set(editor.value_labels) == set(EDIT_FIELDS)
        assert not hasattr(editor, "field")  # no single category/dropdown selector
        assert not hasattr(editor, "creator")  # rights appear only inside export
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        assert photo.id in editor._thumbnail_cache
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
