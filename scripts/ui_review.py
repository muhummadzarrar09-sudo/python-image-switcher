"""Audit actual Windows editor captures without treating an AI fixture as approval.

This checks reproducibility and measurable panel geometry. It deliberately does
NOT compare pixels to the AI concept or call any capture an approved baseline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from PIL import Image

STATES = ("empty-editor", "populated-editor", "missing-source", "protected-batch", "crop-tools",
          "background-tools", "background-before", "background-rejected",
          "background-ready", "export-overlay")

# These are actual foreground/surface pairs from the current implementation,
# not targets copied from an AI illustration. Large text >= 3:1 is not used to
# waive the ordinary 4.5:1 threshold for these small UI captions.
TEXT_PAIRS = {
    "footer hint": ("#858e9b", "#1b1e23"),
    "footer status": ("#aab0b9", "#1b1e23"),
    "adjustment heading": ("#c9ced7", "#21252b"),
    "photo caption": ("#abb3bd", "#282c32"),
    "protected caption": ("#8dc0ff", "#23446b"),
    "mask warning": ("#d2b889", "#25282d"),
    "export hint": ("#939ca8", "#25282d"),
    "export error": ("#ffc188", "#25282d"),
}


def relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def within(inner: dict, outer: dict, tolerance: int = 3) -> bool:
    return (inner["width"] > 0 and inner["height"] > 0
            and outer["x"] - tolerance <= inner["x"]
            and outer["y"] - tolerance <= inner["y"]
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + tolerance
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + tolerance)


def audit_capture(directory: Path) -> dict:
    meta = json.loads((directory / "capture.json").read_text(encoding="utf-8"))
    checks: list[dict] = []

    def check(name: str, condition: bool) -> None:
        checks.append({"check": name, "passed": bool(condition)})

    check("No capture script error", not meta.get("error"))
    check("All expected states captured", set(STATES) <= set(meta["states"]))
    measures: dict = {}
    for name in STATES:
        state = meta["states"].get(name)
        if state is None:
            continue
        file = directory / f"{name}.png"
        if not file.is_file():
            check(f"{name} screenshot exists", False)
            continue
        with Image.open(file) as screenshot:
            pixels = screenshot.size
            screenshot.verify()
        client = state["editor_client"]
        check(f"{name} screenshot matches measured client", list(pixels) == state["image_pixels"]
              and all(abs(a - b) <= 3 for a, b in zip(pixels, (client["width"], client["height"]))))
        for section in ("header", "sidebar", "workspace", "panel"):
            check(f"{name} {section} inside client", within(state[section], client))
        check(f"{name} canvas inside workspace", within(state["canvas"], state["workspace"]))
        sidebar, workspace, panel = (state[key] for key in ("sidebar", "workspace", "panel"))
        check(f"{name} three-panel order", sidebar["x"] < workspace["x"] < panel["x"]
              and sidebar["x"] + sidebar["width"] <= workspace["x"] + 3
              and workspace["x"] + workspace["width"] <= panel["x"] + 3)
        popup = state.get("popup")
        if popup:
            popup_file = directory / f"{name}-popup.png"
            if popup_file.is_file():
                with Image.open(popup_file) as screenshot:
                    popup_pixels = screenshot.size
                    screenshot.verify()
                check(f"{name} popup screenshot matches bounds", list(popup_pixels) ==
                      [popup["width"], popup["height"]])
            else:
                check(f"{name} popup screenshot exists", False)
        measures[name] = {"client_pixels": list(pixels),
                          "rail_width": sidebar["width"], "workspace_width": workspace["width"],
                          "adjustments_width": panel["width"],
                          "header_height": state["header"]["height"],
                          "canvas_inset_left": state["canvas"]["x"] - workspace["x"],
                          "popup_pixels": ([popup["width"], popup["height"]] if popup else None)}
    states = meta["states"]
    check("Empty state has no selected photo", states.get("empty-editor", {}).get("selected_number") is None)
    check("Fixture has stable selected #0001", states.get("populated-editor", {}).get("selected_number") == 1)
    check("Missing source is a separate numbered correctable state",
          states.get("missing-source", {}).get("selected_number") == 3
          and states.get("missing-source", {}).get("source_missing") is True)
    check("Protected photo stays numbered", 1 in states.get("protected-batch", {}).get("protected_numbers", []))
    check("Before disarms manual mask", "Select After" in states.get("background-before", {}).get("mask_status", ""))
    check("Undersized image rejected without effect", "upscaled" in meta.get("background_rejection", "")
          and states.get("background-rejected", {}).get("background_mode") == "none")
    check("After with effect arms manual mask", states.get("background-ready", {}).get("background_mode") == "color"
          and "Mask ready" in states.get("background-ready", {}).get("mask_status", ""))
    check("Export stays in separate popup", bool(states.get("export-overlay", {}).get("popup")))
    contrast = {name: round(contrast_ratio(*pair), 2) for name, pair in TEXT_PAIRS.items()}
    for name, ratio in contrast.items():
        check(f"{name} small-text contrast >= 4.5:1", ratio >= 4.5)
    return {"passed": all(item["passed"] for item in checks),
            "fixture_only": meta.get("fixture_only"),
            "approved_reference": False,
            "note": "Geometry/fixture smoke checks only. User-approved reference and real Windows 11 DPI review still required.",
            "capture_dpi_for_window": meta.get("dpi_for_window"),
            "requested_window": meta.get("requested_window"),
            "measured": measures, "contrast_of_current_tokens": contrast, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Folder containing capture.json and state PNGs")
    args = parser.parse_args()
    report = audit_capture(args.directory)
    (args.directory / "review.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failed = [item["check"] for item in report["checks"] if not item["passed"]]
    print(f"{len(report['checks']) - len(failed)}/{len(report['checks'])} capture/contrast checks passed; "
          f"approved reference: no")
    if failed:
        parser.exit(1, "Failed: " + "; ".join(failed) + "\n")


if __name__ == "__main__":
    main()
