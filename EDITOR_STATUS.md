# Still-photo editor: implementation status (preview, not a finished release)

Launch the existing app (`python src/app.py`), then choose **Still Photo Editor**. This is a separate, in-progress workflow; the existing converter's quality slider and acceptance gate do not govern the editor.

## Working in the source tree

- Import numbered stills including Nikon NEF/JPG and PNG/JPG screenshots; rejects animation/multipage media rather than silently taking one frame. 16-bit PNG/TIFF, CMYK and HEIC/AVIF are currently **blocked** until precision and color-management paths are validated. Not every NEF camera/compression has been tested.
- Preserve the numbered batch when selecting one photo; batch sliders update unprotected photos, while the first individual slider/crop/rotation/mask edit locks that photo's current batch values. Locked photos are visibly listed and **are still exported**. Unlocking is explicit.
- Exposure, brightness, contrast, highlights, shadows, saturation, warmth, tint, sharpness and vignette; crop, 90-degree rotation, horizontal flip. Manual background mask painting/erasing, blur, removal, color and supplied-image replacement for 8-bit source images. **There is no automatic subject detection yet.** Manual brush is provisional, not pixel-accurate refinement.
- `.isbatch` JSON session, and per-photo `.isphoto` ZIP project holding the untouched source, edit recipe, optional supplied background and rendered PNG/TIFF master. SHA-256 checks detect corruption, **not creator identity**. Opening a project verifies assets and requires selecting a durable directory for the extracted original/master; save the session separately if desired.
- Export lossless PNG for 8-bit decoded stills, and 16-bit RGB TIFF for processed NEF. Files are numbered; existing exports are refused rather than overwritten. Source files are never rewritten. ICC profile is carried for Pillow sources when available; NEF TIFF is tagged with sRGB after rawpy's sRGB demosaic. Preview is downsampled but export uses full decoded resolution.

## Important limitations before any full release

- Converting a JPG's *decoded* pixels to PNG is lossless from that point forward; it cannot recover details discarded by the input JPG. Demosaicing a NEF creates a new render, not a byte-identical RAW equivalent. Untouched source bytes remain in `.isphoto`.
- NEF background masks/replacements are blocked instead of silently demoting a 16-bit render to 8 bits. Large images over the 100-million-pixel safety ceiling are blocked; memory and performance still need larger-camera testing. Color controls operate on encoded RGB channel values, not in a fully managed linear-light workflow. No local retouch/automatic subject segmentation yet.
- Rights strings are *declared fields in `.isphoto` only*: standard PNG/TIFF exports do not yet carry comprehensive IPTC/XMP copyright, attribution or C2PA. No embedded robust watermark, independently trusted signer, revocation flow, remote recovery, or credential interoperability matrix is implemented. A screenshot can lack original image provenance and can never restore lost information. Do not use the preview to claim ownership verification.
- `.isphoto` is a container, not a new standard image codec. Other apps need the companion PNG/TIFF. Archive checksums do not sign the wrapper, and a signature on an inner image would not automatically sign the wrapper.
- No clean Windows 11 VM installation/UI validation or signed production installer has been performed. `installer.iss` and the GitHub Actions job generate **unsigned development previews only** (CI uses a Windows runner, not a clean Windows 11 PC); their existence is not a release gate pass. Do not distribute them as a finished editor.

## Try and test

```bash
python -m pip install -r requirements.txt pytest
python -m pytest -q tests/test_photo_project.py tests/test_editor_render.py
python src/app.py --editor-self-test  # headless round-trip for packaged executables
python src/app.py                     # opens the desktop app, requires a GUI
```

Build a *development preview* on Windows with `python -m pip install -r requirements-editor.txt` and `python build_editor.py --console`, run `dist\ImageSwitcherEditor\ImageSwitcherEditor.exe --editor-self-test`, then compile `installer.iss` with Inno Setup 6. For the existing converter executable, use the separate legacy `build_exe.py`. The preview installer still requires manual installation, editing/export, uninstall and clean Windows 11 verification, including Nikon camera fixtures and credential tests, before a real release.
