"""Deterministic validation helpers for owner-configured brand asset usage rules.

Palette checks are bounded RGB-distance estimates, not colour-management or
brand-identity certification. Clear-space requirements remain human-reviewed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError

ASSET_KINDS = {"logo", "product_image", "campaign_image", "icon", "other"}
ASSET_USES = {
    "general", "brand_lockup", "campaign", "product_detail", "social_ad",
    "email_banner", "website_hero", "packaging",
}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def extract_palette(data: bytes, limit: int = 8) -> list[dict[str, Any]]:
    """Extract a small weighted palette while ignoring fully transparent pixels."""
    try:
        with Image.open(BytesIO(data)) as original:
            image = original.convert("RGBA")
            image.thumbnail((160, 160))
            pixels = [pixel[:3] for pixel in image.get_flattened_data() if pixel[3] >= 32]
            if not pixels:
                return []
            sample = Image.new("RGB", (len(pixels), 1))
            sample.putdata(pixels)
            quantized = sample.quantize(colors=max(1, min(limit, 12)), method=Image.Quantize.MEDIANCUT)
            palette = quantized.getpalette() or []
            counts = quantized.getcolors(maxcolors=len(pixels) + 1) or []
            total = sum(count for count, _ in counts) or 1
            result = []
            for count, index in sorted(counts, reverse=True)[:limit]:
                offset = index * 3
                if offset + 2 >= len(palette):
                    continue
                red, green, blue = palette[offset:offset + 3]
                result.append({
                    "hex": f"#{red:02X}{green:02X}{blue:02X}",
                    "ratio": round(count / total, 4),
                })
            return result
    except (UnidentifiedImageError, OSError, ValueError):
        return []


def _rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def palette_match_ratio(
    observed: list[dict[str, Any]], allowed: list[str], tolerance: float
) -> float:
    """Return the weighted share of observed palette within RGB tolerance."""
    if not observed or not allowed:
        return 0.0
    allowed_rgb = [_rgb(color) for color in allowed]
    matched = 0.0
    total = 0.0
    for item in observed:
        color = item.get("hex")
        try:
            ratio = max(0.0, float(item.get("ratio", 0)))
            current = _rgb(str(color))
        except (TypeError, ValueError):
            continue
        total += ratio
        distance = min(
            sum((current[channel] - candidate[channel]) ** 2 for channel in range(3)) ** 0.5
            for candidate in allowed_rgb
        )
        if distance <= tolerance:
            matched += ratio
    return matched / total if total else 0.0


def validate_usage_policies(
    value: Any, brand_channels: list[str]
) -> list[dict[str, str]]:
    """Validate the owner-authored usage policy mapping."""
    errors: list[dict[str, str]] = []

    def add(code: str, path: str, message: str) -> None:
        errors.append({"code": code, "path": path, "message": message})

    if value is None:
        return errors
    if not isinstance(value, dict):
        add("ASSET_USAGE_POLICIES_INVALID", "assets.usage_policies", "usage_policies must be an object keyed by asset kind.")
        return errors

    for kind, policy in value.items():
        path = f"assets.usage_policies.{kind}"
        if kind not in ASSET_KINDS:
            add("ASSET_USAGE_KIND_INVALID", path, f"Unsupported asset kind: {kind}.")
            continue
        if not isinstance(policy, dict):
            add("ASSET_USAGE_POLICY_INVALID", path, "Each usage policy must be an object.")
            continue
        channels = policy.get("allowed_channels", [])
        if not isinstance(channels, list) or any(not isinstance(item, str) for item in channels):
            add("ASSET_USAGE_CHANNELS_INVALID", f"{path}.allowed_channels", "allowed_channels must be an array of channel identifiers.")
        elif any(item not in brand_channels for item in channels):
            add("ASSET_USAGE_CHANNEL_UNKNOWN", f"{path}.allowed_channels", "Every allowed channel must exist in brand.channels.")
        uses = policy.get("allowed_uses", [])
        if not isinstance(uses, list) or any(not isinstance(item, str) or item not in ASSET_USES for item in uses):
            add("ASSET_USAGE_USES_INVALID", f"{path}.allowed_uses", f"allowed_uses must contain only: {', '.join(sorted(ASSET_USES))}.")
        for field in ("min_width", "min_height"):
            raw = policy.get(field, 0)
            if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 20000:
                add("ASSET_USAGE_DIMENSION_INVALID", f"{path}.{field}", f"{field} must be an integer between 0 and 20000 pixels.")
        colors = policy.get("palette_hex", [])
        if not isinstance(colors, list) or any(not isinstance(color, str) or not HEX_COLOR.fullmatch(color) for color in colors):
            add("ASSET_USAGE_PALETTE_INVALID", f"{path}.palette_hex", "palette_hex must contain six-digit hexadecimal colours such as #123ABC.")
        tolerance = policy.get("palette_tolerance", 80)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0 <= tolerance <= 441.7:
            add("ASSET_USAGE_PALETTE_TOLERANCE_INVALID", f"{path}.palette_tolerance", "palette_tolerance must be between 0 and 441.7 RGB distance units.")
        match_ratio = policy.get("minimum_palette_match_ratio", 0.7)
        if isinstance(match_ratio, bool) or not isinstance(match_ratio, (int, float)) or not 0 <= match_ratio <= 1:
            add("ASSET_USAGE_PALETTE_RATIO_INVALID", f"{path}.minimum_palette_match_ratio", "minimum_palette_match_ratio must be between 0 and 1.")
        clear_space = policy.get("clear_space_ratio", 0)
        if isinstance(clear_space, bool) or not isinstance(clear_space, (int, float)) or not 0 <= clear_space <= 0.5:
            add("ASSET_USAGE_CLEAR_SPACE_INVALID", f"{path}.clear_space_ratio", "clear_space_ratio must be between 0 and 0.5; non-zero values require human inspection.")
        severity = policy.get("severity", "review_required")
        if severity not in {"blocking", "review_required", "suggestion", "informational"}:
            add("ASSET_USAGE_SEVERITY_INVALID", f"{path}.severity", "severity must be blocking, review_required, suggestion or informational.")
        for field in ("valid_from", "valid_until"):
            raw = policy.get(field)
            if raw not in (None, "") and _parse_time(raw) is None:
                add("ASSET_USAGE_VALIDITY_INVALID", f"{path}.{field}", "Asset policy validity must be timezone-aware ISO-8601.")
        start = _parse_time(policy.get("valid_from"))
        end = _parse_time(policy.get("valid_until"))
        if start and end and end < start:
            add("ASSET_USAGE_VALIDITY_INTERVAL_INVALID", path, "valid_until must be later than or equal to valid_from.")
    return errors


def asset_policy_violations(
    asset: dict[str, Any], policy: dict[str, Any], channel: str,
    intended_use: str, publication_at: datetime,
) -> list[dict[str, str]]:
    """Evaluate only deterministic channel/use/time conditions for an exact asset match."""
    violations: list[dict[str, str]] = []
    allowed_channels = policy.get("allowed_channels") or []
    if allowed_channels and channel not in allowed_channels:
        violations.append({
            "code": "ASSET_CHANNEL_NOT_ALLOWED",
            "message": f"This approved {asset.get('kind', 'brand')} asset is not authorised for the {channel} channel.",
        })
    allowed_uses = policy.get("allowed_uses") or []
    if allowed_uses and intended_use not in allowed_uses:
        violations.append({
            "code": "ASSET_USE_NOT_ALLOWED",
            "message": f"This approved {asset.get('kind', 'brand')} asset is not authorised for the {intended_use} use.",
        })

    moment = publication_at.astimezone(timezone.utc)
    boundaries = (
        (policy.get("valid_from"), policy.get("valid_until"), "ASSET_POLICY_OUTSIDE_VALIDITY"),
        (asset.get("valid_from"), asset.get("valid_until"), "ASSET_OUTSIDE_VALIDITY"),
    )
    for start_raw, end_raw, code in boundaries:
        start, end = _parse_time(start_raw), _parse_time(end_raw)
        if start and moment < start or end and moment > end:
            violations.append({
                "code": code,
                "message": "The asset or its usage policy is not valid at the intended publication time.",
            })
    return violations
