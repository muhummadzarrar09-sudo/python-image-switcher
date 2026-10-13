# Windows editor geometry / token audit (MUH-44 and MUH-53)

**Status: provisional implementation measurements, NOT an approved visual specification.** The selected export concept informs the entire editor, but no approved Windows 11 reference package (MUH-45) exists yet. Do not derive authoritative pixel tolerances or claim pixel accuracy from AI art. The first comparison contract is at an *actual* 1456 × 766 client size, with a 1000 × 700 narrow smoke test. At 125% and 150% Windows display scaling, repeat both captures on a real desktop; changing the window size alone does **not** simulate changing display scaling.

| Component | Current source request / color | Measurement evidence | Approved target |
| --- | --- | --- | --- |
| Window | `1456x766`, minimum `1000x700` CTk logical units | `capture.json` requested size, editor client physical bounds, `review.json` measured client | **Pending MUH-45** |
| Header | 48 logical units, `#1c1e22`; brand blue `#19539a`, actions `#30343a`, Export `#2468b9` | `review.json` header height and three-panel edges | **Pending** |
| Photo rail | width 164 logical units, `#1f2227`; selected tile `#23446b` | `review.json` rail width; protected caption contrast 5.27:1 at current tokens | **Pending** |
| Workspace/matte | `#17191d`; canvas inset from frame (source `padx=10`, top `pady=10`); image fit is centered, not 100%-pixel zoom | canvas coordinates and screenshot; `mask_point()` tests inset exclusion | **Pending** |
| Footer | `#1b1e23`, height request 50; hint `#858e9b` | footer hint contrast 5.05:1 at current tokens | **Pending** |
| Adjustment rail | width request 295, `#21252b`, scrollable; named working sliders | measured actual panel width; heading contrast 9.74:1 | **Pending** |
| Tool popups | crop 375×305, background 410×435; graphite `#25282d` | popup PNG and measured dimensions | **Pending** |
| Export overlay | 530×575, `#25282d`, centered over measured editor; dim `#000000` at alpha .42 | separate popup PNG and geometry; Escape/Cancel GUI tests | **Pending** |

All colors and sizes above are **current code values**, not measurements of the user's monitor or sign-off targets. `scripts/ui_review.py` computes actual measured rectangles and WCAG contrast for specified small-text foreground/background pairs, fails on missing screenshots, off-client panels, wrong selected/protected states or background rejection, and writes `review.json` with `approved_reference: false`. It does not grade the look of text, focus indication, keyboard traversal, font rasterization or closeness to the AI concept. CI collects 1456×766 and 1000×700 Windows-runner fixture captures as reviewable, **unapproved** artifacts.

## Responsive behavior and manual matrix

The editor uses weighted center grid (`sidebar` fixed request, `workspace` expands, `panel` fixed request) and a scrollable adjustment column. The 1000×700 minimum is enforced by Tk; this is not proof every 150%-scale physical display fits. If usable display area is below the scaled minimum, the current app **does not claim adaptive toolbar reflow**; report the clipped state and adjust layout before approving that size. Test the same selected photo and modal at (1) primary 1456×766 100%, (2) narrow 1000×700 100%, (3) 125%, (4) 150%, and (5) largest usable viewport, recording *actual* DPI, OS text scaling, display resolution and window bounds. Any physical clipping, hidden button, absent focus ring, unreadable text or popup outside the visible monitor is a failure, not a tolerance adjustment.

For primary major edges, ±2–4 **physical** pixels is only a **proposed** starting tolerance. Approve named ROIs/masks and final tolerances against real Windows 11 captures, not against the generated sample camera or the illustrated concept. Windows ClearType/font antialiasing is reviewed separately; do not treat a literal full-frame pixel mismatch as a UI failure when it is limited to rasterization. Real user photos and screenshot filenames can be private; keep them in ignored `ui-captures/` and share only reviewed artifacts. MUH-44 and MUH-53 remain open until the human-approved reference and multi-DPI checks exist.
