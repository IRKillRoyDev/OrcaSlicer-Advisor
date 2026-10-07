"""Write review changes as new user presets, leaving the current ones in place."""

from __future__ import annotations

import json
from pathlib import Path

from advisor.profiles import (
    META_KEYS,
    base_id_for_parent,
    config_dir,
    display_value,
    get_setup,
    inheritance_chain,
    preset_version,
    resolve_preset,
)

USER_KINDS = ("process", "filament", "machine")
ID_FIELD = {
    "process": "print_settings_id",
    "filament": "filament_settings_id",
    "machine": "printer_settings_id",
}


def safe_preset_name(name: str) -> str:
    cleaned = " ".join(name.replace("/", " ").replace("\\", " ").split()).strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Preset name is empty")
    return cleaned


def unique_name(kind: str, base: str) -> str:
    folder = config_dir() / "user" / "default" / kind
    candidate = base
    number = 2
    while (folder / f"{candidate}.json").exists():
        candidate = f"{base} {number}"
        number += 1
    return candidate


def apply_changes(setup_index: int, diffs: list[dict], label: str) -> dict:
    setup = get_setup(setup_index)
    resolved = {
        "machine": resolve_preset("machine", setup["machine"]),
        "process": resolve_preset("process", setup["process"]),
        "filament": resolve_preset("filament", setup["filament"]),
    }
    grouped: dict[str, dict] = {kind: {} for kind in USER_KINDS}
    applied = []
    for item in diffs:
        if not item.get("changed"):
            continue
        kind = item.get("kind")
        key = item.get("key")
        if kind not in grouped or not key:
            continue
        current = resolved[kind].values.get(key)
        stored = item.get("stored")
        if stored is None:
            stored = item.get("after")
        if isinstance(current, list) and not isinstance(stored, list):
            stored = [str(stored)]
        if display_value(current) == display_value(stored):
            continue
        grouped[kind][key] = stored
        applied.append(
            {
                "kind": kind,
                "key": key,
                "before": display_value(current),
                "after": display_value(stored),
            }
        )
    written = []
    for kind, changes in grouped.items():
        if not changes:
            continue
        parent = resolved[kind].name
        inherits, carried = inherit_basis(kind, parent)
        short = safe_preset_name(label)
        if not short:
            raise ValueError("Name the preset after the part.")
        base = safe_preset_name(parent if parent.endswith(f" - {short}") else f"{parent} - {short}")
        name = unique_name(kind, base)
        path = _write_user_preset(kind, name, inherits, resolved[kind].values, changes, carried)
        written.append({"kind": kind, "name": name, "inherits": inherits, "path": str(path), "keys": sorted(changes)})
    if not written:
        raise ValueError("None of the suggested values differ from the current presets.")
    return {
        "written": written,
        "applied": applied,
        "note": "Quit OrcaSlicer completely and reopen it. The new preset is under User presets. The original presets were left unchanged.",
    }


def inherit_basis(kind: str, parent_name: str) -> tuple[str, dict]:
    """OrcaSlicer cannot inherit a user preset while that folder is still loading.

    New presets inherit the system profile and keep the user profile's own values.
    """
    skip = META_KEYS | {
        "filament_settings_id",
        "print_settings_id",
        "printer_settings_id",
        "filament_id",
    }
    system_name = parent_name
    carried: dict = {}
    for path, data in inheritance_chain(kind, parent_name):
        user_file = "/user/default/" in path.as_posix()
        if user_file or str(data.get("from") or "").lower() == "user":
            for key, value in data.items():
                if key not in skip:
                    carried[key] = value
        else:
            system_name = str(data.get("name") or path.stem)
            carried = {}
    return system_name, carried


def _write_user_preset(
    kind: str,
    name: str,
    inherits: str,
    current_values: dict,
    changes: dict,
    carried: dict | None = None,
) -> Path:
    folder = config_dir() / "user" / "default" / kind
    folder.mkdir(parents=True, exist_ok=True)
    body: dict = {
        "name": name,
        "inherits": inherits,
        "from": "User",
        "instantiation": "true",
        "version": preset_version(kind, inherits),
    }
    id_field = ID_FIELD[kind]
    if kind == "filament":
        body[id_field] = [name]
        printers = current_values.get("compatible_printers")
        if printers:
            body["compatible_printers"] = printers
    else:
        body[id_field] = name
    if carried:
        body.update(carried)
    if kind == "filament" and current_values.get("compatible_printers") and "compatible_printers" not in body:
        body["compatible_printers"] = current_values["compatible_printers"]
    body.update(changes)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(body, indent="\t") + "\n")
    info = folder / f"{name}.info"
    base_id = base_id_for_parent(kind, inherits)
    info.write_text(
        "sync_info = create\n"
        "user_id = \n"
        "setting_id = \n"
        f"base_id = {base_id}\n"
        "updated_time = 0\n"
    )
    return path
