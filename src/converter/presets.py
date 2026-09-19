"""
Resize Presets - Instagram, Web, Print, Social - RHHHAAAAA Edition
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List

@dataclass
class ResizePreset:
    id: str
    name: str
    width: int
    height: int
    description: str
    category: str  # social, web, print, discord, etc
    keep_aspect: bool = False
    quality: int = 90
    format: Optional[str] = None  # preferred format

PRESETS = [
    # Instagram
    ResizePreset("insta_square", "Instagram Square", 1080, 1080, "Instagram feed square 1:1", "instagram", False, 90, "jpg"),
    ResizePreset("insta_portrait", "Instagram Portrait", 1080, 1350, "Instagram portrait 4:5", "instagram", False, 90, "jpg"),
    ResizePreset("insta_story", "Instagram Story", 1080, 1920, "Story/Reel 9:16", "instagram", False, 85, "jpg"),
    ResizePreset("insta_landscape", "Instagram Landscape", 1080, 566, "Landscape 1.91:1", "instagram", False, 90, "jpg"),

    # Social
    ResizePreset("yt_thumb", "YouTube Thumbnail", 1280, 720, "YouTube thumbnail 16:9", "social", False, 90, "jpg"),
    ResizePreset("yt_banner", "YouTube Banner", 2560, 1440, "Channel banner", "social", False, 90, "jpg"),
    ResizePreset("twitter_post", "Twitter Post", 1600, 900, "Twitter/X post 16:9", "social", False, 90, "jpg"),
    ResizePreset("twitter_header", "Twitter Header", 1500, 500, "Twitter header", "social", False, 90, "jpg"),
    ResizePreset("fb_cover", "Facebook Cover", 1640, 924, "Facebook cover", "social", False, 90, "jpg"),
    ResizePreset("linkedin_post", "LinkedIn Post", 1200, 627, "LinkedIn post", "social", False, 90, "jpg"),

    # Discord / Gaming
    ResizePreset("discord_emoji", "Discord Emoji", 128, 128, "Discord emoji 128x128", "discord", False, 100, "png"),
    ResizePreset("discord_sticker", "Discord Sticker", 320, 320, "Discord sticker 320x320", "discord", False, 100, "png"),
    ResizePreset("discord_icon", "Discord Server Icon", 512, 512, "Server icon 512x512", "discord", False, 95, "png"),
    ResizePreset("discord_banner", "Discord Banner", 960, 540, "Server banner 16:9", "discord", False, 90, "jpg"),

    # Web
    ResizePreset("web_thumb", "Web Thumbnail", 400, 300, "Small thumbnail 4:3", "web", True, 80, "webp"),
    ResizePreset("web_medium", "Web Medium", 800, 600, "Medium web 4:3", "web", True, 85, "webp"),
    ResizePreset("web_large", "Web Large", 1920, 1080, "Full HD 16:9", "web", True, 90, "webp"),
    ResizePreset("web_hero", "Web Hero", 1920, 1080, "Hero banner 16:9 high quality", "web", True, 90, "webp"),
    ResizePreset("web_icon", "Web Icon", 512, 512, "PWA icon 512x512", "web", False, 100, "png"),
    ResizePreset("favicon", "Favicon", 32, 32, "Favicon 32x32", "web", False, 100, "ico"),

    # Print
    ResizePreset("print_a4_300", "Print A4 300DPI", 2480, 3508, "A4 at 300 DPI", "print", False, 100, "png"),
    ResizePreset("print_4x6_300", "Print 4x6 300DPI", 1200, 1800, "4x6 photo 300 DPI", "print", False, 100, "jpg"),
    ResizePreset("print_hd", "Print HD", 3000, 2000, "High quality print 3:2", "print", True, 100, "png"),

    # AI / Special
    ResizePreset("ai_upscale_2x", "AI Upscale 2x", 0, 0, "Upscale 2x via AI (width/height auto)", "ai", False, 95, None),
    ResizePreset("ai_upscale_4x", "AI Upscale 4x", 0, 0, "Upscale 4x via AI (width/height auto)", "ai", False, 95, None),
]

# Lookup
ID_TO_PRESET = {p.id: p for p in PRESETS}

def get_preset_by_id(pid: str) -> Optional[ResizePreset]:
    return ID_TO_PRESET.get(pid)

def get_presets_by_category(cat: str) -> List[ResizePreset]:
    return [p for p in PRESETS if p.category == cat]

def all_presets() -> List[ResizePreset]:
    return PRESETS

def categories() -> List[str]:
    return sorted(set(p.category for p in PRESETS))

# For UI dropdown
def preset_choices():
    """Return list of (display_name, id) for UI"""
    return [(f"{p.name} - {p.width}x{p.height} ({p.category})", p.id) for p in PRESETS]
