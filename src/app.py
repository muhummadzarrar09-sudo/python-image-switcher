"""
Entry point for Image Switcher App
"""
import sys
import os
# Ensure src is in path when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.main_window import ImageSwitcherApp

def main():
    app = ImageSwitcherApp()
    # Handle file drop via command line arg
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path):
            app.after(500, lambda: app.load_file(path))
    app.mainloop()

if __name__ == "__main__":
    main()
