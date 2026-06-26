"""Helpers for normalizing GOG metadata shapes."""

from __future__ import annotations

from typing import Any

_PLATFORM_ORDER = ("windows", "mac", "linux")
_PLATFORM_ALIASES = {
    "windows": "windows",
    "win": "windows",
    "mac": "mac",
    "osx": "mac",
    "macos": "mac",
    "linux": "linux",
}


def normalize_platforms(values: Any) -> list[str]:
    """Normalize platform names while preserving a stable display order."""
    if isinstance(values, dict):
        names = [key for key, enabled in values.items() if enabled]
    elif isinstance(values, list | tuple | set):
        names = list(values)
    else:
        names = []

    normalized = {
        platform
        for value in names
        if (platform := _PLATFORM_ALIASES.get(str(value).strip().lower()))
    }
    return [platform for platform in _PLATFORM_ORDER if platform in normalized]


def extract_download_platforms(product_or_cache: dict[str, Any]) -> list[str]:
    """Return platforms implied by product download metadata."""
    product = product_or_cache.get("data", product_or_cache)
    if not isinstance(product, dict):
        return []

    platform_values: list[str] = []
    downloads = product.get("downloads", {})
    if isinstance(downloads, dict):
        for entries in downloads.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                os_value = entry.get("os")
                if os_value:
                    platform_values.append(str(os_value))

    compatibility = product.get("content_system_compatibility")
    if isinstance(compatibility, dict):
        platform_values.extend(
            str(platform) for platform, supported in compatibility.items() if supported
        )

    return normalize_platforms(platform_values)
