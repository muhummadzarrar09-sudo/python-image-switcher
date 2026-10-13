# Windows 11 UI parity — reference and capture contract (MUH-45)

**Status: awaiting real Windows captures and human approval.** The AI export concept is the selected visual direction for the entire editor **and** Export overlay, not an implementation screenshot or a specification of working controls. The previously shared alpha.3 screenshot shows an *empty* editor; the concept shows a populated editor. Do not count an empty-vs-populated difference as a visual regression.

## Proposed primary viewport

At the native 1568 × 885 PNG size of `editor-export-concept.png`, the illustrated app's client region is **approximately** x=54..1510, y=29..795, or **1456 × 766 physical pixels**. Its rail is roughly 164 px, center image workspace 978 px, and adjustment panel 312 px wide; the export popup is approximately 464 × 550 px. These are **manual approximations from AI art, not approved measurements**. OS titlebar, taskbar and sample camera are outside the comparison contract. At 125%/150% Windows scaling, logical dimensions may differ while physical pixels are measured separately.

First measure a real 1456 × 766 client area at 100% Windows scaling. If the user's actual display cannot fit it, record that and choose the closest attainable reference with the user before tuning layout. Use the `capture.json` coordinates and actual PNG sizes, not a guessed display resolution. Also exercise 125%, 150%, and narrow/wide window sizes without clipping. Compare major panel/dialog edges after a human-reviewed baseline (provisional tolerance ±2–4 **physical** pixels at the primary size); review font rasterization and antialiasing visually rather than requiring literal per-pixel equality with the AI image.

## Capture on the user's Windows 11 machine

Close the installed editor so the screenshots come from one build. From this branch's checkout after running `update-alpha.ps1 -DependenciesOnly`, run the default **AI-generated, non-branded test fixture** without providing your own photo:

```powershell
.\.venv\Scripts\python.exe scripts\capture_editor_baseline.py --window 1456x766
```

The fixture (`tests/fixtures/ui-camera.jpg`, 1536 × 1024, ~156 KB) was made for visual *development/testing*, not for product advertising or an approved real-photo baseline. It lets us develop without your private images; `capture.json` marks these screenshots `fixture_only: true`. If/when a real photo becomes available, optionally pass `--photo "C:\path\to\a\real\photo.jpg"` (repeat for another still; preferably JPG and Nikon NEF, increasing `--wait-ms 1800` for a slow NEF). With one photo the script loads it **twice as separate numbered entries**, then hand-edits #0001 to exercise the protected state. It does not modify or export the original. Keep sensitive source photos private. It writes ignored files under `ui-captures/windows-11/`: `empty-editor.png`, `populated-editor.png`, `protected-batch.png`, `crop-tools.png`, `background-tools.png`, `background-before.png`, `background-rejected.png`, `background-ready.png`, `export-overlay.png`, popup crops, and `capture.json` with OS/DPI/Tk scaling, window and component bounds, mask guidance/rejection, and source **filenames only**. The rejected replacement is generated in the ignored capture directory and deleted immediately; it is never applied to the photo. Examine the captures before sharing: visible filenames or a photo may reveal personal information. Do not commit captures or NEF fixtures; share an approved/sanitized reference package through a private channel.

Record Windows **display scaling**, text size, resolution, theme and whether the app was maximized, and identify an approved photo fixture. Save a second set using the export popup *after* a batch is populated. The baseline script captures actual Tk windows; the illustrated camera or mockup text is never injected into the app.

## Required comparison states and truthful controls

| State | Compare / verify |
| --- | --- |
| Empty | Deliberate add-photo prompt; app geometry and controls, no concept photo. |
| Populated | Real photo with numbered rail, canvas framing, selected state and direct adjustments. |
| Protected | Visible #0001 protection; batch edits do not replace its manual edit, but it stays in export. |
| Tools | Crop/rotation and background/manual mask interactions remain usable. |
| Export | Only appears after Export; dimming, focus, geometry, scope, untouched original and `.isphoto` wording, Cancel without writing. |

Only implement existing editing fields, including **Sharpness**. Do not add concept-only Whites/Blacks/Clarity/Denoise, pixel-exact RAW zoom, automatic selection, silent output collision skipping or signed ownership credentials. Ask for human screenshot sign-off before marking MUH-45 done or claiming pixel accuracy.
