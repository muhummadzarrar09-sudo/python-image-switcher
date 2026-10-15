"""Entry point for the standalone still-photo editor preview executable."""
from __future__ import annotations

import sys
from pathlib import Path

# PyInstaller and a direct `python src/editor_app.py` invocation both work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    if "--editor-self-test" in sys.argv:
        from src.app import editor_self_test
        editor_self_test()
        return
    if "--gpu-report" in sys.argv:
        index = sys.argv.index("--gpu-report")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--gpu-report requires a JSON output path")
        from src.editor.diagnostics import installed_gpu_report
        installed_gpu_report(sys.argv[index + 1])
        return
    import customtkinter as ctk
    from src.editor.window import EditorWindow
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.withdraw()
    window = EditorWindow(root)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
