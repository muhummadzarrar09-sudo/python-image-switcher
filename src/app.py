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
    from PIL import Image
    from src.editor.batch import BatchSession
    from src.editor.workflow import export_batch, import_project
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "sample.png"
        Image.new("RGB", (32, 24), (80, 120, 140)).save(source)
        batch = BatchSession()
        batch.add_photo(str(source))
        batch.set_batch("exposure", 0.5)
        batch.save(str(Path(directory) / "batch.isbatch"))
        batch = BatchSession.load(str(Path(directory) / "batch.isbatch"))
        exports = export_batch(batch, str(Path(directory) / "exports"))
        imported = import_project(BatchSession(), exports[0][2], str(Path(directory) / "reopened"))
        assert Path(imported.source).read_bytes() == source.read_bytes()
        with Image.open(exports[0][1]) as image:
            image.verify()
    print("Editor headless package smoke test: PASS")


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
