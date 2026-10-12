# Still-photo editor alpha 0.2.0-alpha.2

This is an **unsigned, incomplete alpha**, not a production release. See [EDITOR_STATUS.md](EDITOR_STATUS.md) for supported features and blocked fidelity/ownership workflows. The editor installer packages the standalone editor, not the older converter.

## Update and install in an existing Windows 11 checkout

Open PowerShell in the checkout directory after switching to the alpha branch:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1
```

The script finds/installs Python 3.11 when missing, creates/updates the ignored `.venv`, verifies dependencies and tests, builds the windowed executable, locates/installs Inno Setup 6 and compiles the unsigned alpha setup. **If the editor is already installed, close it first:** the script detects the existing executable, performs a quiet **in-place update** using the stable Inno AppId and previous installation path, then smoke-tests the updated executable. It does not create a second app or remove your photos, exports or sessions. Only a first-time setup launches the interactive wizard. The updater stops on failures and never switches your Git branch. Missing dependencies/tools require network access; the alpha is unsigned.

To install dependencies and run tests **without building or installing** the desktop app:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1 -DependenciesOnly
```

If `winget` is unavailable, install Python 3.11 and Inno Setup 6 using their official installers first. On Linux/macOS, `python3.11 scripts/update_alpha.py` sets up and tests Python dependencies but cannot build/install the Windows app. You can also download the unsigned setup from the successful Windows alpha workflow artifact rather than build locally.

### Manual Windows steps (if you do not use the updater)

```powershell
py -3.11 scripts/update_alpha.py
.\.venv\Scripts\python.exe build_editor.py
.\dist\ImageSwitcherEditor\ImageSwitcherEditor.exe --editor-self-test
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer.iss
.\dist\ImageSwitcher-Setup-0.2.0-alpha.2.exe
```

The setup is unsigned and can show an unknown-publisher warning; proceed only if you trust this checkout. The Windows workflow builds the setup, installs it on its disposable runner, runs the updater against that existing install, smoke-tests the updated executable and uninstalls it. That is **not** proof of GUI functionality, camera compatibility, or clean Windows 11 installation. The app cannot be remotely installed on your personal PC from this sandbox.

## Legacy converter (separate)

`python src/app.py` runs the original converter and can open the editor. `python build_exe.py --onedir` packages the older converter only. `installer.iss` packages `dist\ImageSwitcherEditor`, produced by `build_editor.py`.
