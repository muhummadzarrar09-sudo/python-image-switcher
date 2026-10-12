"""Windows-only integration: progress stays visible while camera JPGs import."""
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Tk GUI tested on Windows CI")


def test_bulk_jpg_and_mpo_import_keeps_all_stills_and_reports_progress(tmp_path, monkeypatch, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    paths = []
    for i in range(12):
        path = tmp_path / f"CSC{i:04d}.JPG"
        Image.new("RGB", (36, 28), (100 + i, 80, 50)).save(path)
        paths.append(str(path))
    multi = tmp_path / "CSC9999.JPG"
    Image.new("RGB", (36, 28), "red").save(
        multi, format="MPO", save_all=True,
        append_images=[Image.new("RGB", (36, 28), "blue")])
    paths.append(str(multi))
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not a still photo")
    paths.append(str(broken))
    notices = []
    monkeypatch.setattr("src.editor.window.messagebox.showwarning", lambda *args, **kwargs: notices.append(args))
    root = tk_root
    editor = EditorWindow(root)
    try:
        root.update()
        editor.start_import(paths)
        root.update()
        assert editor.importing and editor.import_dialog.winfo_exists()
        deadline = time.monotonic() + 15
        while editor.importing and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert not editor.importing, "background import did not finish"
        assert [p.number for p in editor.batch.photos] == list(range(1, 15))
        assert [p.frame_index for p in editor.batch.photos[-2:]] == [0, 1]
        assert editor.current == 14
        assert len(notices) == 1 and "broken.jpg" in str(notices[0])
        assert "13/14 file(s)" not in editor.status.cget("text")  # processed all, including failure
        assert "14/14 file(s)" in editor.status.cget("text")
        assert not editor.import_dialog
    finally:
        editor.destroy()


def test_import_progress_can_stop_between_files(tmp_path, monkeypatch, tk_root):
    from PIL import Image
    from src.editor.window import EditorWindow

    source = tmp_path / "product.jpg"
    Image.new("RGB", (32, 24), "green").save(source)
    import threading
    release = threading.Event()
    started = threading.Event()

    def wait_for_validation(path):
        started.set()
        release.wait(timeout=5)
        return range(1)

    monkeypatch.setattr("src.editor.window.still_photo_frames", wait_for_validation)
    root = tk_root
    editor = EditorWindow(root)
    try:
        root.update()
        editor.start_import([str(source)] * 8)
        assert started.wait(timeout=3)
        root.update()
        editor.import_dialog.request_cancel()
        release.set()
        deadline = time.monotonic() + 6
        while editor.importing and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert not editor.importing
        assert editor.batch.photos == []
        assert "Stopped" in editor.status.cget("text")
    finally:
        release.set()
        editor.destroy()
