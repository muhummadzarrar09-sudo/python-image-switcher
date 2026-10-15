"""
Entry point for Image Switcher App
"""
import sys
import os
# Ensure src is in path when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def editor_self_test():
    """Headless executable smoke test for the Windows packaging job."""
    import tempfile
    from pathlib import Path
    import numpy as np
    from PIL import Image
    from src.editor.batch import BatchSession
    from src.editor.project import read_project
    from src.editor.render import render
    from src.editor.workflow import export_batch, import_project
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources = [root / "camera.jpg", root / "screenshot.png", root / "product.jpg"]
        for index, source in enumerate(sources):
            Image.new("RGB", (32, 24), (80 + index * 20, 120, 140)).save(source)
        batch = BatchSession()
        for source in sources:
            batch.add_photo(str(source))
        batch.edit_photo(2, "contrast", .2)  # manual exception stays in batch
        batch.set_batch("exposure", .5)
        assert batch.excluded_numbers == [2]
        assert batch.effective_settings(2)["exposure"] == 0
        batch.save(str(root / "batch.isbatch"))
        batch = BatchSession.load(str(root / "batch.isbatch"))
        exports = export_batch(batch, str(root / "exports"))
        assert [number for number, _, _ in exports] == [1, 2, 3]
        for number, master, project in exports:
            photo = batch.get(number)
            assert read_project(project).manifest["protected"] == (number == 2)
            with Image.open(master) as actual:
                expected, _, _ = render(photo, batch)
                assert np.array_equal(np.asarray(expected), np.asarray(actual))
        imported = import_project(BatchSession(), exports[1][2], str(root / "reopened"))
        assert imported.number == 2 and imported.protected
        assert Path(imported.source).read_bytes() == sources[1].read_bytes()
    print("Editor headless package smoke test (numbered protected full batch): PASS")


def main():
    if "--editor-self-test" in sys.argv:
        editor_self_test()
        return
    from src.ui.main_window import ImageSwitcherApp
    app = ImageSwitcherApp()
    # Handle file drop via command line arg
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path):
            app.after(500, lambda: app.load_file(path))
    app.mainloop()

if __name__ == "__main__":
    main()
