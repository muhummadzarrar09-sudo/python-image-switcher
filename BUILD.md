# Still-photo editor alpha 0.2.0-alpha.1

This is an **unsigned, incomplete alpha**, not a production release. See [EDITOR_STATUS.md](EDITOR_STATUS.md) for supported features and blocked fidelity/ownership workflows. The editor installer packages the standalone editor, not the older converter.

## Update and install in an existing Windows 11 checkout

Open PowerShell in the checkout directory after switching to the alpha branch:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\update-alpha.ps1
```

The script locates Python 3.11 or uses Windows Package Manager (`winget`) to install it for the current user; creates/updates the ignored `.venv`, installs `requirements-editor.txt` and pytest; runs tests and a headless project round-trip; builds a windowed executable and tests it; installs Inno Setup 6 if needed via `winget`; compiles the unsigned alpha setup; then starts the setup interactively. It stops on failures and does **not** silently rewrite photos, delete an existing environment, or switch your Git branch. It needs network access for missing tools/dependencies, and a Windows 11 desktop for the interactive setup/UI. If a newly installed tool is not discoverable immediately, reopen PowerShell and rerun it.

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
.\dist\ImageSwitcher-Setup-0.2.0-alpha.1.exe
```

The installer can be unsigned and show an unknown-publisher warning; proceed only if you trust this checkout. The Windows workflow builds the installer, silently installs it on its disposable runner, smoke-tests the installed executable and uninstalls it. That is **not** proof of GUI functionality, camera compatibility, or clean Windows 11 installation. The app cannot be remotely installed on your personal PC from this sandbox.

## Legacy converter (separate)

`python src/app.py` runs the original converter and can open the editor. `python build_exe.py --onedir` packages the older converter only. `installer.iss` packages `dist\ImageSwitcherEditor`, produced by `build_editor.py`.
