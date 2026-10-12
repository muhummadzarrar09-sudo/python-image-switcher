# Build instructions (development previews only)

## Still-photo editor on Windows

See [EDITOR_STATUS.md](EDITOR_STATUS.md) for implemented features, fidelity restrictions and unimplemented release gates. The standalone editor and the legacy converter have **different entry points**; the current installer script packages only the still-photo editor.

On a Windows x64 machine with Python 3.11, tkinter and Inno Setup 6 installed:

```powershell
python -m pip install -r requirements-editor.txt pytest
python -m pytest -q tests/test_photo_project.py tests/test_editor_render.py
python build_editor.py --console
.\dist\ImageSwitcherEditor\ImageSwitcherEditor.exe --editor-self-test
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer.iss
```

The unsigned preview installer is `dist\ImageSwitcher-Setup-0.2.0-preview.exe`. For a windowed build, run `python build_editor.py` instead of `--console`, then rerun the smoke test and compile Inno Setup. The GitHub Actions workflow builds an **unsigned development preview** on a Windows runner. A successful CI job does not demonstrate that editing works end-to-end on a clean Windows 11 machine.

Before describing it as installable for general use, test on a clean Windows 11 VM (no Python), install/uninstall, open the UI, import real Nikon NEF/JPG and PNG/JPG screenshots, hand-edit numbered locked exceptions, export every photo, reopen projects and compare full-size master pixels and original checksums. Also complete metadata/watermark/C2PA work and independently validate signed supported exports. Those gates have **not** passed yet. We cannot remotely install on a user's device from this repository.

## Existing converter (separate)

`python src/app.py` runs the original converter and includes a button that opens the still-photo editor. `python build_exe.py --onedir` produces the legacy converter executable. It is **not** the input for `installer.iss` and has not been proven to package the editor reliably; it may require Cairo and other dependencies. The desktop editor can instead be launched in source form with `python src/editor_app.py`. Do not present legacy converter docs or binaries as proof of a complete photo-editor installer.
