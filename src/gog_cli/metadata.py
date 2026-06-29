"""Helpers for normalizing GOG metadata shapes."""

from __future__ import annotations

from datetime import UTC, datetime
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


def normalize_genres(*values: Any) -> list[str]:
    """Normalize genre/category/tag-like metadata into display values."""
    genres: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _flatten_metadata_values(value):
            normalized = " ".join(str(item).strip().split())
            if not normalized:
                continue
            if normalized.isdigit():
                continue
            key = normalized.casefold()
            if key not in seen:
                genres.append(normalized)
                seen.add(key)
    return genres


def normalize_release_date(value: Any) -> str:
    """Normalize GOG release date shapes to YYYY-MM-DD where possible."""
    if isinstance(value, dict):
        value = value.get("date")
    if not isinstance(value, str) or not value.strip():
        return ""

    raw = value.strip()
    candidates = [
        raw,
        raw.replace("Z", "+00:00"),
        raw.replace(" ", "T"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC)
        return parsed.date().isoformat()

    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    if len(raw) >= 4 and raw[:4].isdigit():
        return raw[:4]
    return raw


def release_year(value: Any) -> int | None:
    """Return the year from a normalized or raw GOG release date."""
    release_date = normalize_release_date(value)
    if len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return None


def extract_size_summary(product_or_cache: dict[str, Any]) -> dict[str, Any]:
    """Return installer sizes by platform and total extras size from download metadata."""
    product = product_or_cache.get("data", product_or_cache)
    if not isinstance(product, dict):
        return {}
    downloads = product.get("downloads")
    if not isinstance(downloads, dict):
        return {}

    installer_sizes: dict[str, int] = {}
    for entry in downloads.get("installers", []):
        if not isinstance(entry, dict):
            continue
        platform = _PLATFORM_ALIASES.get(str(entry.get("os", "")).strip().lower())
        if not platform:
            continue
        for file_entry in entry.get("files") or []:
            if not isinstance(file_entry, dict):
                continue
            raw = (
                file_entry["size"] if file_entry.get("size") is not None
                else entry.get("total_size")
            )
            size = _parse_int(raw)
            if size:
                installer_sizes[platform] = installer_sizes.get(platform, 0) + size

    extras_total = 0
    for entry in downloads.get("bonus_content", []):
        if not isinstance(entry, dict):
            continue
        for file_entry in entry.get("files") or []:
            if not isinstance(file_entry, dict):
                continue
            raw = (
                file_entry["size"] if file_entry.get("size") is not None
                else entry.get("total_size")
            )
            size = _parse_int(raw)
            if size:
                extras_total += size

    return {
        "installer_sizes": installer_sizes if installer_sizes else None,
        "extras_size": extras_total if extras_total else None,
    }


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_download_summary(product_or_cache: dict[str, Any]) -> dict[str, Any]:
    """Return list-facing metadata implied by product download metadata."""
    product = product_or_cache.get("data", product_or_cache)
    if not isinstance(product, dict):
        return {}

    summary: dict[str, Any] = {
        "platforms": extract_download_platforms(product_or_cache),
        "is_installable": (
            bool(product["is_installable"]) if "is_installable" in product else None
        ),
        "download_type": str(product.get("game_type") or ""),
    }
    release_date = normalize_release_date(product.get("release_date"))
    year = release_year(release_date)
    if release_date and year is not None and year >= 1995:
        summary["release_date"] = release_date
        summary["release_year"] = year
    return summary


def _flatten_metadata_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.split(",") if part.strip()]
    if isinstance(value, dict):
        for key in ("name", "title", "label"):
            if value.get(key):
                return [value[key]]
        return []
    if isinstance(value, list | tuple | set):
        items: list[Any] = []
        for item in value:
            items.extend(_flatten_metadata_values(item))
        return items
    return [value]
