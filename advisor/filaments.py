"""Filament brand, type, and diameter choices taken from the installed OrcaSlicer profiles."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from advisor.profiles import app_profiles_dir, config_dir

# Profile files store color as an occasional hex value, not a color name.
FILAMENT_COLORS = [
    "Black",
    "White",
    "Gray",
    "Natural",
    "Red",
    "Blue",
    "Green",
    "Yellow",
    "Orange",
    "Purple",
    "Pink",
    "Brown",
    "Clear",
    "Silver",
    "Gold",
]

_OPTIONS: dict | None = None


def _text(value) -> str:
    if isinstance(value, list) and value:
        return str(value[0]).strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _profile_roots() -> list[Path]:
    roots = [config_dir() / "system"]
    bundled = app_profiles_dir()
    if bundled is not None:
        roots.append(bundled)
    user = config_dir() / "user" / "default" / "filament"
    if user.is_dir():
        roots.append(user)
    return roots


def _iter_filament_files():
    seen: set[str] = set()
    for root in _profile_roots():
        if not root.exists():
            continue
        paths = root.glob("*.json") if root.name == "filament" else root.glob("**/filament/*.json")
        for path in paths:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            yield path


def filament_options() -> dict:
    global _OPTIONS
    if _OPTIONS is None:
        _OPTIONS = _build_options()
    return _OPTIONS


def _build_options() -> dict:
    folder_vendors: dict[Path, Counter] = defaultdict(Counter)
    records = []
    for path in _iter_filament_files():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        vendor = _text(data.get("filament_vendor"))
        material = _text(data.get("filament_type"))
        diameter = _text(data.get("filament_diameter"))
        if vendor:
            folder_vendors[path.parent][vendor] += 1
        records.append((path.parent, vendor, material, diameter))

    types_by_brand: dict[str, set[str]] = defaultdict(set)
    diameters = {"1.75", "2.85"}
    for folder, vendor, material, diameter in records:
        if diameter in ("1.75", "2.85"):
            diameters.add(diameter)
        if not material:
            continue
        brand = vendor or (folder_vendors[folder].most_common(1)[0][0] if folder_vendors[folder] else "")
        if brand:
            types_by_brand[brand].add(material)

    brands = sorted(types_by_brand, key=str.casefold)
    return {
        "brands": brands,
        "types_by_brand": {brand: sorted(types_by_brand[brand], key=str.casefold) for brand in brands},
        "diameters": sorted(diameters, key=float),
        "colors": FILAMENT_COLORS,
    }
