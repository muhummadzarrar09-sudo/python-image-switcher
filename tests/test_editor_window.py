"""Windows GUI smoke test: real adjustment controls and deferred export dialog."""
import sys
import time
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Tk desktop smoke test runs on Windows CI")


def test_named_adjustment_sliders_and_export_dialog_do_not_write_early(tmp_path, tk_root):
    from PIL import Image

    from src.editor.batch import EDIT_FIELDS
    from src.editor.window import EditorWindow, ExportOptions

    source = tmp_path / "product.png"
    Image.new("RGB", (30, 24), (100, 120, 140)).save(source)
    root = tk_root
    editor = None
    dialog = None
    try:
        editor = EditorWindow(root)
        root.update()
        # Concept-derived layout: one working action row, then three adjacent
        # surfaces, not a second toolbar consuming canvas height.
        assert editor.header.winfo_height() <= 55
        assert not editor._header_wrapped
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


def test_primary_and_narrow_header_actions_stay_on_screen(tk_root):
    import customtkinter as ctk
    from src.editor.window import EditorWindow

    editor = EditorWindow(tk_root)
    try:
        for size in ("1456x766", "1000x700", "960x640"):
            editor.geometry(size)
            tk_root.update()
            left = editor.header.winfo_rootx()
            right = left + editor.header.winfo_width()
            actions = [child for group in (editor._header_left, editor._header_right)
                       for child in group.winfo_children()
                       if isinstance(child, (ctk.CTkButton, ctk.CTkSegmentedButton))]
            assert len(actions) >= 8
            for action in actions:
                assert action.winfo_width() >= 30, (size, action.cget("text") if isinstance(action, ctk.CTkButton) else "scope")
                assert left - 2 <= action.winfo_rootx()
                assert action.winfo_rootx() + action.winfo_width() <= right + 2, size
            assert editor.sidebar.winfo_rootx() + editor.sidebar.winfo_width() <= editor.workspace.winfo_rootx() + 2
            assert editor.workspace.winfo_rootx() + editor.workspace.winfo_width() <= editor.panel.winfo_rootx() + 2
            assert editor.canvas.winfo_width() >= 200
    finally:
        editor.destroy()


def test_simulated_150_percent_narrow_client_keeps_controls_inside(tk_root):
    """Supplement (not replace) actual DPI captures with a scaled Tk smoke test."""
    import customtkinter as ctk
    from src.editor.window import EditorWindow

    editor = None
    try:
        ctk.set_widget_scaling(1.5)
        ctk.set_window_scaling(1.5)
        editor = EditorWindow(tk_root)
        scale = editor._get_window_scaling()
        editor.geometry(f"{round(1000 / scale)}x{round(700 / scale)}")
        tk_root.update()
        assert abs(editor.winfo_width() - 1000) <= 3, editor.winfo_width()
        assert abs(editor.winfo_height() - 700) <= 3, editor.winfo_height()
        client_right = editor.winfo_rootx() + editor.winfo_width()
        header = editor.header
        assert editor._header_wrapped, (
            header.winfo_width(), editor._header_left.winfo_reqwidth(),
            editor._header_right.winfo_reqwidth(), editor._brand_visible,
            editor._header_left.winfo_width(), editor._header_right.winfo_width())
        assert header.winfo_rootx() + header.winfo_width() <= client_right + 3
        for group in (editor._header_left, editor._header_right):
            for action in group.winfo_children():
                if isinstance(action, (ctk.CTkButton, ctk.CTkSegmentedButton)):
                    assert action.winfo_width() >= 30
                    assert action.winfo_rootx() + action.winfo_width() <= client_right + 3, (
                        action.cget("text") if isinstance(action, ctk.CTkButton) else "scope",
                        action.winfo_rootx(), action.winfo_width(), client_right)
        assert editor.panel.winfo_rootx() + editor.panel.winfo_width() <= client_right + 3, (
            editor.sidebar.winfo_width(), editor.workspace.winfo_width(),
            editor.panel.winfo_rootx(), editor.panel.winfo_width(), client_right)
        assert editor.canvas.winfo_width() >= 180
        assert editor._compact_footer
        assert editor.panel_view.winfo_manager() == "pack"
    finally:
        if editor and editor.winfo_exists():
            editor.destroy()
        ctk.set_window_scaling(1)
        ctk.set_widget_scaling(1)


def test_background_validation_and_stale_mask_click_are_non_destructive(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    source = tmp_path / "subject.jpg"
    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    Image.new("RGB", (40, 30), "blue").save(source)
    Image.new("RGB", (20, 20), "red").save(small)
    Image.new("RGB", (70, 80), "red").save(large)
    editor = EditorWindow(tk_root)
    try:
        tk_root.update()
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        with pytest.raises(ValueError, match="upscaled"):
            editor.set_background("image", source=str(small))
        assert not photo.background and not photo.protected
        editor.batch.set_crop(photo.number, (0, 0, .5, 1))
        editor.batch.set_rotation(photo.number, 90)
        editor.set_background("image", source=str(large))
        assert photo.background["mode"] == "image"
        editor.open_background_tools()
        assert editor.background_window and editor.background_window.winfo_exists()
        editor._canvas_bounds = (10, 10, 40, 30)
        editor._displayed_number = photo.number
        editor._displayed_generation = editor._preview_generation - 1
        editor.paint_mask(SimpleNamespace(x=20, y=20))
        assert not photo.mask_strokes  # preview geometry is stale after the edit
        editor._displayed_generation = editor._preview_generation
        editor.paint_mask(SimpleNamespace(x=20, y=20))
        assert len(photo.mask_strokes) == 1
        nef = tmp_path / "raw.nef"
        nef.write_bytes(b"not a camera file")
        raw_photo = editor.batch.add_photo(str(nef))
        editor.current = raw_photo.number
        with pytest.raises(ValueError, match="16-bit NEF"):
            editor.set_background("color", color="#123456")
        assert not raw_photo.background and not raw_photo.protected
    finally:
        editor.destroy()


def test_manual_mask_requires_live_after_tool_and_can_undo(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    source = tmp_path / "subject.jpg"
    Image.new("RGB", (64, 48), "blue").save(source)
    editor = EditorWindow(tk_root)
    try:
        tk_root.update()
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        # Clearing a blank mask must not unexpectedly exclude a batch photo.
        editor.clear_mask()
        editor.set_background("none")
        assert not photo.protected
        editor.open_background_tools()
        tool = editor.background_window
        click = SimpleNamespace(x=20, y=20)
        editor._canvas_bounds = (10, 10, 40, 30)
        editor._displayed_number = photo.number
        editor._displayed_generation = editor._preview_generation
        editor.paint_mask(click)
        assert not photo.mask_strokes
        assert "Choose a background effect" in tool.mask_status.cget("text")
        editor.set_background("color", color="#123456")
        assert photo.protected
        assert "Waiting" in tool.mask_status.cget("text")
        editor._displayed_generation = editor._preview_generation
        editor._canvas_bounds = (10, 10, 40, 30)
        editor.view_mode.set("Before")
        editor.paint_mask(click)
        assert not photo.mask_strokes
        assert "Select After" in tool.mask_status.cget("text")
        editor.view_mode.set("After")
        editor.busy = True
        editor.paint_mask(click)
        assert not photo.mask_strokes
        assert "Wait" in tool.mask_status.cget("text")
        editor.busy = False
        assert editor._sync_mask_status()
        assert "Mask ready" in tool.mask_status.cget("text")
        editor.on_canvas_resize(SimpleNamespace())
        editor.paint_mask(click)
        assert not photo.mask_strokes  # disarmed immediately, before debounce fires
        assert "Waiting" in tool.mask_status.cget("text")
        editor.show_current()  # cancels the pending resize job
        editor._displayed_generation = editor._preview_generation
        editor._canvas_bounds = (10, 10, 40, 30)
        editor.paint_mask(click)
        assert len(photo.mask_strokes) == 1
        assert "1 stroke" in tool.mask_status.cget("text") or "Waiting" in tool.mask_status.cget("text")
        editor.undo_mask_stroke()
        assert photo.mask_strokes == []
        editor.close_background_tools()
        editor._displayed_generation = editor._preview_generation
        editor._canvas_bounds = (10, 10, 40, 30)
        editor.paint_mask(click)
        assert photo.mask_strokes == [] and not editor.mask_painting
        assert editor.canvas.cget("cursor") == ""
        assert photo.protected  # manual background stays protected and in batch
    finally:
        editor.destroy()


def test_tool_escape_from_focused_children_closes_without_mutating_edits(tmp_path, tk_root):
    """Escape works from native entry/canvas controls, not only the popup frame."""
    from PIL import Image
    import customtkinter as ctk
    from src.editor.window import EditorWindow

    source = tmp_path / "subject.jpg"
    Image.new("RGB", (64, 48), "blue").save(source)
    editor = EditorWindow(tk_root)
    try:
        tk_root.update()
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        editor.open_crop_tools()
        crop = editor.crop_window
        assert crop is not None
        crop.crop.insert(0, "5,5,90,90")  # unsubmitted draft must not apply
        crop_tag = crop._escape_tag
        assert crop.bind_class(crop_tag, "<Escape>")
        assert crop_tag in crop.crop._entry.bindtags()
        crop_buttons = [w for w in crop.winfo_children() if isinstance(w, ctk.CTkButton)]
        assert crop_buttons and crop_tag in crop_buttons[0]._canvas.bindtags()
        # The CI desktop does not guarantee native keyboard focus; verify the
        # focused child's bindtag and invoke its registered handler directly.
        assert crop._close_on_escape(None) == "break"
        assert editor.crop_window is None and photo.crop is None
        assert not editor.bind_class(crop_tag, "<Escape>")  # no leaked global binding

        editor.open_background_tools()
        background = editor.background_window
        assert background is not None
        editor.mask_painting = True
        background.color.delete(0, "end")
        background.color.insert(0, "#ff0000")
        background_tag = background._escape_tag
        assert background_tag != crop_tag
        assert background_tag in background.color._entry.bindtags()
        assert background.bind_class(background_tag, "<Escape>")
        assert background._close_on_escape(None) == "break"
        assert editor.background_window is None and not editor.mask_painting
        assert editor.canvas.cget("cursor") == ""
        assert not photo.background and not photo.protected  # draft was discarded
        assert not editor.bind_class(background_tag, "<Escape>")
    finally:
        editor.destroy()


def test_missing_source_is_correctable_without_losing_number_or_edits(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    source = tmp_path / "camera.jpg"
    Image.new("RGB", (64, 48), "blue").save(source)
    original = source.read_bytes()
    editor = EditorWindow(tk_root)
    try:
        tk_root.update()
        photo = editor.batch.add_photo(str(source))
        editor.select(photo.number)
        editor.scope.set("Selected")
        editor.change_value("contrast", .2)
        source.unlink()  # simulates removable drive moved after import
        editor.show_current()
        deadline = time.monotonic() + 5
        while "Source missing" not in editor.status.cget("text") and time.monotonic() < deadline:
            tk_root.update()
            time.sleep(.02)
        assert editor.status.cget("text").startswith("#0001 · Source missing")
        assert editor._canvas_bounds == (0, 0, 0, 0)
        assert editor.batch.get(1).protected and editor.batch.excluded_numbers == [1]
        source.write_bytes(original)
        editor.select(photo.number)
        deadline = time.monotonic() + 5
        while editor._displayed_generation != editor._preview_generation and time.monotonic() < deadline:
            tk_root.update()
            time.sleep(.02)
        assert editor._displayed_number == photo.number
        assert editor.status.cget("text").startswith("#0001 · Protected")
        assert editor.batch.effective_settings(1)["contrast"] == .2
    finally:
        editor.destroy()


def test_export_escape_closes_without_writing(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow, ExportOptions

    source = tmp_path / "source.png"
    Image.new("RGB", (32, 24), "blue").save(source)
    editor = EditorWindow(tk_root)
    dialog = None
    try:
        tk_root.update()
        editor.select(editor.batch.add_photo(str(source)).number)
        dialog = ExportOptions(editor)
        tk_root.update()
        # A modal must own the Tk grab rather than leaving editing controls
        # clickable behind the dimming overlay. On CI the first grab can be
        # deferred until the native window becomes viewable.
        deadline = time.monotonic() + 3
        while dialog.grab_current() != dialog and time.monotonic() < deadline:
            tk_root.update()
            time.sleep(.02)
        assert dialog.grab_current() == dialog
        dialog.folder.set(str(tmp_path / "output"))
        # CTk entries, radio buttons and canvas-backed buttons all need the
        # modal's unique Escape bindtag; Toplevel binding alone is not inherited.
        import customtkinter as ctk
        tag = dialog._escape_tag
        assert dialog.bind_class(tag, "<Escape>")
        assert tag in dialog.creator._entry.bindtags()
        assert tag in dialog.folder_entry._entry.bindtags()
        radios = [child for child in dialog.winfo_children() if isinstance(child, ctk.CTkRadioButton)]
        assert radios and tag in radios[0]._canvas.bindtags()
        dialog._close_on_escape(None)  # OS physical key remains a manual gate
        assert not dialog.winfo_exists()
        assert not (tmp_path / "output").exists()
        assert editor.batch.rights == {}
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.close()
        editor.destroy()


def test_export_collision_stays_in_popup_and_cancel_keeps_sources(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow, ExportOptions

    source = tmp_path / "camera.jpg"
    Image.new("RGB", (32, 24), "blue").save(source)
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "0001-camera.png"
    existing.write_bytes(b"keep this")
    editor = EditorWindow(tk_root)
    dialog = None
    try:
        tk_root.update()
        editor.select(editor.batch.add_photo(str(source)).number)
        dialog = ExportOptions(editor)
        tk_root.update()
        dialog.folder.set(str(output))
        dialog.creator.insert(0, "Owner")
        dialog.confirm()
        assert dialog.winfo_exists()  # user can correct folder/scope
        assert "already exists" in dialog.preflight_status.cget("text")
        assert dialog.folder.get() == str(output)
        assert dialog.creator.get() == "Owner"
        assert not editor.busy and editor.batch.rights == {}
        assert existing.read_bytes() == b"keep this"
        assert not list(output.glob("*.isphoto"))
        dialog.close()
        assert existing.read_bytes() == b"keep this"
    finally:
        if dialog and dialog.winfo_exists():
            dialog.close()
        editor.destroy()


def test_large_numbered_batch_keeps_rail_widget_count_bounded(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow, RAIL_PAGE_SIZE

    source = tmp_path / "many.jpg"
    Image.new("RGB", (32, 24), "blue").save(source)
    editor = EditorWindow(tk_root)
    try:
        tk_root.update()
        for _ in range(505):
            editor.batch.add_photo(str(source))
        editor.refresh_list()
        assert len(editor.batch.photos) == 505
        assert len(editor._tiles) == RAIL_PAGE_SIZE
        assert editor.page_label.cget("text") == "1 / 11"
        editor.select(505)
        assert editor._rail_page == 10
        assert editor.page_label.cget("text") == "11 / 11"
        assert len(editor._tiles) == 25  # no 505-widget freeze
        assert editor.batch_count.cget("text") == "505"
        last = editor.batch.get(505)
        editor.batch.edit_photo(505, "contrast", .2)
        editor.refresh_list()
        assert last.protected and last.id in editor._tiles
        assert editor._tiles[last.id][2].cget("text").startswith("LOCKED")
        editor.change_rail_page(-1)
        assert len(editor._tiles) == RAIL_PAGE_SIZE
        assert last.id not in editor._tiles  # still in batch, not removed
        assert editor.batch.get(505).protected
    finally:
        editor.destroy()


def test_latest_preview_wins_after_fast_selection_and_edits(tmp_path, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    first = tmp_path / "a.jpg"
    second = tmp_path / "b.jpg"
    Image.new("RGB", (800, 600), "red").save(first)
    Image.new("RGB", (800, 600), "blue").save(second)
    root = tk_root
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
