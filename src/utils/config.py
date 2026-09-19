"""
Config - Local & Offline Settings Persistence
Saves to %APPDATA%/ImageSwitcher/config.json on Windows or ~/.config/ImageSwitcher on Linux/Mac
100% local, no cloud, no tracking - suiiiii
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

def get_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "ImageSwitcher"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "ImageSwitcher"

def get_config_file() -> Path:
    return get_config_dir() / "config.json"

DEFAULT_CONFIG = {
    "version": "1.1.0",
    "theme": "dark",
    "last_target_format": "webp",
    "last_quality": 90,
    "last_bg_color": "white",
    "last_output_dir": "",
    "last_input_dir": "",
    "batch": {
        "target": "webp",
        "quality": 90,
        "recursive": True,
        "keep_structure": True,
        "overwrite": False,
    },
    "recent_files": [],  # list of paths, max 10
    "recent_folders": [],  # for batch
    "window": {
        "width": 1400,
        "height": 900,
        "maximized": False,
    },
    "ui": {
        "show_toasts": True,
        "comparison_slider": False,
        "auto_check_updates": True,
        "confirm_on_close": False,
    },
    "presets": {
        "favorites": [],  # list of preset ids
        "last_category": "all",
    },
    "first_run": True,
}

def load_config() -> Dict[str, Any]:
    cfg_file = get_config_file()
    if not cfg_file.exists():
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(cfg_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Merge with defaults for missing keys
        merged = DEFAULT_CONFIG.copy()
        # Deep merge for nested dicts
        for k, v in data.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged
    except Exception as e:
        print(f"Config load failed: {e}, using defaults")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]):
    try:
        cfg_dir = get_config_dir()
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = get_config_file()
        # Don't save first_run as True after first save
        if config.get("first_run"):
            config["first_run"] = False
        with open(cfg_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Config save failed: {e}")

def add_recent_file(config: Dict[str, Any], path: str, max_items: int = 10):
    recent = config.get("recent_files", [])
    # Remove if exists
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    # Trim
    recent = recent[:max_items]
    # Only keep existing files (optional, but keep even if deleted for history)
    config["recent_files"] = recent
    save_config(config)

def add_recent_folder(config: Dict[str, Any], path: str, max_items: int = 10):
    recent = config.get("recent_folders", [])
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:max_items]
    config["recent_folders"] = recent
    save_config(config)

def get_recent_files() -> List[str]:
    cfg = load_config()
    return cfg.get("recent_files", [])

def update_setting(key: str, value: Any):
    cfg = load_config()
    # Support dot notation: "batch.quality"
    if "." in key:
        parts = key.split(".")
        d = cfg
        for p in parts[:-1]:
            if p not in d:
                d[p] = {}
            d = d[p]
        d[parts[-1]] = value
    else:
        cfg[key] = value
    save_config(cfg)
    return cfg
