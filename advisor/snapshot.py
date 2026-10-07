"""Assemble the active profile into groups and a JSON review request."""

from __future__ import annotations

import json
from pathlib import Path

from advisor.catalog import CATALOG, catalog_index
from advisor.profiles import (
    HIDDEN_KEYS,
    bed_label,
    bed_size,
    display_value,
    get_setup,
    list_setups,
    resolve_preset,
)

SKIP_SUFFIXES = ("_gcode",)


def _parent_values(kind: str, inherits: str) -> dict:
    if not inherits:
        return {}
    try:
        return resolve_preset(kind, inherits).values
    except FileNotFoundError:
        return {}


def _lookup(key: str, preferred: str, resolved: dict) -> tuple[str | None, object]:
    order = [preferred] if preferred else []
    order += [kind for kind in ("filament", "process", "machine") if kind not in order]
    for kind in order:
        values = resolved[kind].values
        if key in values:
            return kind, values[key]
    return None, None


def _is_hidden(key: str) -> bool:
    if key in HIDDEN_KEYS:
        return True
    return any(key.endswith(suffix) for suffix in SKIP_SUFFIXES)


def build_snapshot(
    setup_index: int | None = None,
    notes: str = "",
    filament_info: dict | None = None,
    model: dict | None = None,
) -> dict:
    setup = get_setup(setup_index)
    resolved = {
        "machine": resolve_preset("machine", setup["machine"]),
        "process": resolve_preset("process", setup["process"]),
        "filament": resolve_preset("filament", setup["filament"]),
    }
    parents = {
        kind: _parent_values(preset.kind, preset.inherits)
        for kind, preset in resolved.items()
    }
    indexed = catalog_index()
    groups: dict[str, list[dict]] = {}
    used_keys: set[str] = set()
    for group, preferred, key, label in CATALOG:
        kind, value = _lookup(key, preferred, resolved)
        if kind is None:
            continue
        used_keys.add(key)
        parent = parents[kind].get(key)
        overridden = (
            resolved[kind].user_leaf
            and key in resolved[kind].leaf_keys
            and display_value(parent) != display_value(value)
        )
        entry = {
            "key": key,
            "label": label,
            "kind": kind,
            "value": display_value(value),
            "raw": value,
            "overridden": overridden,
            "parent": display_value(parent) if overridden else "",
        }
        groups.setdefault(group, []).append(entry)

    overrides = []
    for kind, preset in resolved.items():
        for key in sorted(preset.leaf_keys):
            if not preset.user_leaf or _is_hidden(key) or key in used_keys or key == "filament_notes":
                continue
            value = preset.values.get(key)
            parent = parents[kind].get(key)
            if display_value(parent) == display_value(value):
                continue
            label = indexed.get(key, {}).get("label") or key.replace("_", " ")
            overrides.append(
                {
                    "key": key,
                    "label": label,
                    "kind": kind,
                    "value": display_value(value),
                    "raw": value,
                    "overridden": True,
                    "parent": display_value(parent),
                }
            )

    plate_name, plate_key = bed_label(setup["bed_type"])
    active_temp = ""
    if plate_key:
        _kind, temp = _lookup(plate_key, "filament", resolved)
        if temp is not None:
            active_temp = display_value(temp)
    nozzle = display_value(resolved["machine"].values.get("nozzle_diameter"))
    notes_text = (resolved["filament"].values.get("filament_notes") or "")
    if isinstance(notes_text, list):
        notes_text = "\n".join(str(item) for item in notes_text)
    notes_text = str(notes_text).strip()
    if len(notes_text) > 1500:
        notes_text = notes_text[:1500] + "…"

    group_list = []
    for name, entries in groups.items():
        group_list.append({"name": name, "settings": [{k: v for k, v in item.items() if k != "raw"} for item in entries]})

    filament = _filament_info(setup, resolved, filament_info or {})
    prompt = _prompt(
        setup=setup,
        resolved=resolved,
        groups=groups,
        overrides=overrides,
        plate_name=plate_name,
        plate_key=plate_key,
        active_temp=active_temp,
        nozzle=nozzle,
        filament_notes=notes_text,
        notes=notes,
        filament=filament,
        model=model,
    )
    return {
        "setups": list_setups(),
        "setup": setup,
        "plate": {"id": setup["bed_type"], "name": plate_name, "temp_key": plate_key, "temp": active_temp},
        "nozzle": nozzle,
        "bed": bed_size(resolved["machine"].values),
        "presets": {
            kind: {"name": preset.name, "inherits": preset.inherits, "path": str(preset.path)}
            for kind, preset in resolved.items()
        },
        "groups": group_list,
        "overrides": [{k: v for k, v in item.items() if k != "raw"} for item in overrides],
        "filament_notes": notes_text,
        "filament": filament,
        "model": model,
        "prompt": prompt,
    }


def _filament_info(setup: dict, resolved: dict, entered: dict) -> dict:
    values = resolved["filament"].values
    preset_brand = display_value(values.get("filament_vendor"))
    preset_type = display_value(values.get("filament_type"))
    preset_diameter = display_value(values.get("filament_diameter"))
    return {
        "preset": setup["filament"],
        "brand": str(entered.get("brand") or "").strip() or preset_brand,
        "type": str(entered.get("type") or "").strip() or preset_type,
        "color": str(entered.get("color") or "").strip(),
        "diameter_mm": str(entered.get("diameter_mm") or "").strip() or preset_diameter,
    }


def _setting_entry(item: dict) -> dict:
    entry = {"value": item["value"], "preset": item["kind"]}
    if item.get("overridden") and item.get("parent"):
        entry["parent"] = item["parent"]
    return entry


def _prompt(
    setup: dict,
    resolved: dict,
    groups: dict,
    overrides: list[dict],
    plate_name: str,
    plate_key: str | None,
    active_temp: str,
    nozzle: str,
    filament_notes: str,
    notes: str,
    filament: dict,
    model: dict | None,
) -> str:
    settings: dict[str, dict] = {}
    for group, entries in groups.items():
        settings[group] = {item["key"]: _setting_entry(item) for item in entries}
    if overrides:
        settings["Other overrides"] = {item["key"]: _setting_entry(item) for item in overrides}

    part: dict = {"notes": notes.strip()}
    rules = [
        "The example in response.changes is not a recommendation. Replace it with real changes, or use an empty list.",
        "Use exact keys from settings. Do not invent keys.",
        'Keep OrcaSlicer value format. Percents include the % sign. Toggles are "0" or "1".',
        "An empty changes list is fine. Prefer it when the current value already agrees with the notes.",
        "parent is the inherited value when this preset overrides it.",
        "Change a setting only when two checks agree. If either check fails, leave it out.",
        "Check 1, this JSON only: the current value conflicts with filament_notes, part.size_mm, or another value in settings. Do not repeat a temperature, flow, pressure advance, or retraction that filament_notes already states.",
        "Check 2, one primary source: the new value matches the filament notes in this JSON, the line width and layer height keys in settings, or the volumetric limit. Volumetric flow is line width × layer height × speed and must stay within filament_max_volumetric_speed. Use those keys. Do not guess a line width.",
        "In reason, name both checks in one sentence. Do not cite a source you did not use.",
    ]
    if model:
        size = model.get("size_mm") or [None, None, None]
        filename = str(model.get("filename") or "")
        part["name"] = Path(filename).stem
        part["stl_filename"] = filename
        part["size_mm"] = {"x": size[0], "y": size[1], "z": size[2]}
        rules.append(
            "No mesh is attached. part.size_mm is only the bounding box from the STL filename. Do not claim walls, overhangs, or holes were measured.",
        )

    task = "Review these OrcaSlicer settings for this part. Reply with JSON only, no markdown."
    document = {
        "task": task,
        "response": {
            "summary": "short assessment of this profile for this part and material",
            "changes": [
                {
                    "key": "sparse_infill_density",
                    "value": "40%",
                    "reason": "Check 1: notes or part size conflict with the current value. Check 2: name the settings keys or filament note used.",
                }
            ],
        },
        "rules": rules,
        "printer": {
            "machine_preset": setup["machine"],
            "process_preset": setup["process"],
            "filament_preset": setup["filament"],
            "nozzle_mm": nozzle,
            "bed_mm": bed_size(resolved["machine"].values),
            "plate": plate_name,
            "bed_type": setup["bed_type"],
            "active_bed_temperature_key": plate_key,
            "active_bed_temperature": active_temp or None,
            "filament_notes": filament_notes or None,
        },
        "filament": filament,
        "part": part,
        "settings": settings,
    }
    return json.dumps(document, indent=2) + "\n"
