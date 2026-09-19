"""
Acceptance Gate - Validates every source -> target conversion pair
Returns status, warnings, and required handling
"""
from dataclasses import dataclass
from typing import List, Optional
from .formats import ImageFormat, get_format_by_id

@dataclass
class GateResult:
    allowed: bool
    status: str  # green, yellow, red
    reason: str
    warnings: List[str]
    needs_background: bool  # alpha -> no alpha
    needs_plugin: Optional[str]
    loss_description: str

def validate_conversion(source: ImageFormat, target: ImageFormat, source_has_alpha: bool = False, source_is_animated: bool = False) -> GateResult:
    if source is None or target is None:
        return GateResult(False, "red", "Invalid format", ["Source or target is None"], False, None, "Invalid")
    warnings = []
    needs_bg = False
    needs_plugin = None
    loss = ""
    allowed = True
    status = "green"
    reason = "Fully compatible"

    # Check plugins
    if target.requires_plugin:
        # We don't block, but warn
        needs_plugin = target.requires_plugin
        warnings.append(f"Target needs plugin: {target.requires_plugin}")
    
    if source.requires_plugin:
        warnings.append(f"Source needs plugin: {source.requires_plugin}")

    # Vector -> Raster
    if source.is_vector and not target.is_vector:
        reason = f"Vector {source.id.upper()} will be rasterized to {target.id.upper()}"
        status = "green"
        if source.id in ("svg", "svgz"):
            # cairosvg needed
            needs_plugin = "cairosvg"
        if target.supports_alpha is False and source.supports_alpha:
            needs_bg = True
            warnings.append(f"{target.id.upper()} doesn't support transparency - will composite on background")
            status = "yellow"
            loss = "Transparency will be flattened"
        return GateResult(allowed, status, reason, warnings, needs_bg, needs_plugin, loss)

    # Raster -> Vector
    if not source.is_vector and target.is_vector:
        reason = f"Raster will be embedded in {target.id.upper()} vector (100% fidelity, not traced)"
        status = "yellow"
        loss = "Image will be wrapped in vector, not true vectorization (use Trace mode for edges)"
        if target.id == "svg":
            warnings.append("SVG will contain base64 embedded raster - scales but not infinite")
        elif target.id in ("pdf", "eps", "ps"):
            warnings.append(f"{target.id.upper()} will contain raster image on a page")
        return GateResult(allowed, status, reason, warnings, False, needs_plugin, loss)

    # Vector -> Vector
    if source.is_vector and target.is_vector:
        if source.id == target.id:
            return GateResult(True, "green", "Same format - copy", [], False, None, "")
        # SVG -> PDF etc is possible via raster intermediate or direct
        reason = f"Vector {source.id.upper()} -> {target.id.upper()} conversion"
        status = "yellow"
        warnings.append("Vector to vector may rasterize intermediate")
        loss = "May lose editability, becomes flattened"
        return GateResult(True, status, reason, warnings, False, needs_plugin, loss)

    # Raster -> Raster (core logic)
    # Alpha check
    if source_has_alpha or source.supports_alpha:
        if not target.supports_alpha:
            needs_bg = True
            warnings.append(f"{target.id.upper()} does not support alpha - needs background color")
            status = "yellow"
            loss = "Transparency loss - alpha will be composited"

    # Animation check
    if source_is_animated or source.supports_animation:
        if not target.supports_animation:
            warnings.append(f"{target.id.upper()} doesn't support animation - only first frame saved")
            if status == "green":
                status = "yellow"
            loss += " Animation lost" if loss else "Animation will be lost (first frame only)"

    # Lossy check
    if not source.is_lossless and target.is_lossless:
        # lossy -> lossless is ok, no extra loss but file bigger
        pass
    if source.is_lossless and not target.is_lossless and not target.is_vector:
        warnings.append(f"{target.id.upper()} is lossy - quality loss possible")
        if status == "green":
            status = "yellow"
        loss += " Lossy compression" if loss else "Lossy compression applied"

    # Write capability
    if not target.can_write:
        allowed = False
        status = "red"
        reason = f"{target.id.upper()} is read-only, cannot write"
        return GateResult(allowed, status, reason, warnings, needs_bg, needs_plugin, loss)

    # Read capability
    if not source.can_read:
        allowed = False
        status = "red"
        reason = f"{source.id.upper()} is write-only, cannot read"
        return GateResult(allowed, status, reason, warnings, needs_bg, needs_plugin, loss)

    # Special cases
    if target.id == "gif" and source.id != "gif":
        warnings.append("GIF limited to 256 colors - color quantization will occur")
        status = "yellow"
        loss += " 256 color limit" if loss else "Color reduced to 256"

    if target.id in ("jpg","jpeg") and source.id in ("png","webp"):
        # already handled alpha
        pass

    if not warnings:
        reason = f"{source.id.upper()} -> {target.id.upper()} fully compatible"
    else:
        reason = f"{source.id.upper()} -> {target.id.upper()} compatible with notes"

    return GateResult(allowed, status, reason, warnings, needs_bg, needs_plugin, loss.strip())

def get_compatible_targets(source: ImageFormat):
    """Return all targets sorted by compatibility"""
    results = []
    for target in __import__('src.converter.formats', fromlist=['FORMATS']).FORMATS if False else []:
        pass
    # Avoid circular import - import locally
    from .formats import FORMATS
    for tgt in FORMATS:
        res = validate_conversion(source, tgt)
        results.append((tgt, res))
    # Sort: green first, then yellow, then red
    order = {"green": 0, "yellow": 1, "red": 2}
    results.sort(key=lambda x: (order[x[1].status], x[0].name))
    return results

def get_all_valid_targets(source: ImageFormat):
    from .formats import FORMATS
    valid = []
    for tgt in FORMATS:
        res = validate_conversion(source, tgt)
        if res.allowed:
            valid.append((tgt, res))
    return valid
