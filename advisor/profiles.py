"""Read OrcaSlicer presets and resolve inheritance."""

from __future__ import annotations

import json
import platform
from pathlib import Path

META_KEYS = {
    "type",
    "setting_id",
    "name",
    "from",
    "instantiation",
    "inherits",
    "version",
    "renamed_from",
    "description",
    "force_validation",
}

HIDDEN_KEYS = META_KEYS | {
    "compatible_printers",
    "compatible_printers_condition",
    "compatible_prints",
    "compatible_prints_condition",
    "print_extruder_id",
    "print_extruder_variant",
    "filament_extruder_variant",
    "printer_extruder_id",
    "printer_extruder_variant",
    "different_settings_to_system",
    "filament_settings_id",
    "print_settings_id",
    "printer_settings_id",
    "filament_id",
    "default_filament_profile",
    "default_print_profile",
    "inherits_group",
}

# OrcaSlicer BedType enum. The number stored in OrcaSlicer.conf is this value.
BED_TYPES = {
    "0": ("Default", None),
    "1": ("Cool Plate", "cool_plate_temp"),
    "2": ("Engineering Plate", "eng_plate_temp"),
    "3": ("Smooth PEI Plate", "hot_plate_temp"),
    "4": ("Textured PEI Plate", "textured_plate_temp"),
    "5": ("SuperTack Plate", "supertack_plate_temp"),
}


def config_dir() -> Path:
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library/Application Support/OrcaSlicer"
    if system == "Windows":
        return Path.home() / "AppData/Roaming/OrcaSlicer"
    return home / ".config/OrcaSlicer"


def app_profiles_dir() -> Path | None:
    mac = Path("/Applications/OrcaSlicer.app/Contents/Resources/profiles")
    if mac.is_dir():
        return mac
    return None


def orca_binary() -> Path | None:
    mac = Path("/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer")
    if mac.is_file():
        return mac
    return None


def preset_roots() -> list[Path]:
    roots: list[Path] = []
    cfg = config_dir()
    user = cfg / "user" / "default"
    if user.is_dir():
        roots.append(user)
    system = cfg / "system"
    if system.is_dir():
        roots.append(system)
    app = app_profiles_dir()
    if app is not None:
        roots.append(app)
    return roots


def read_base_id(info_path: Path) -> str:
    if not info_path.is_file():
        return ""
    for line in info_path.read_text().splitlines():
        if line.startswith("base_id"):
            return line.split("=", 1)[1].strip()
    return ""


def preset_version(kind: str, parent_name: str) -> str:
    """OrcaSlicer skips a user preset whose JSON has no semver version."""
    try:
        preset = load_json(find_preset(kind, parent_name))
    except FileNotFoundError:
        preset = {}
    version = preset.get("version")
    if isinstance(version, str) and version.count(".") >= 2:
        return version
    folder = config_dir() / "user" / "default" / kind
    if folder.is_dir():
        for preset_path in sorted(folder.glob("*.json")):
            try:
                preset = load_json(preset_path)
            except (OSError, ValueError):
                continue
            version = preset.get("version")
            if isinstance(version, str) and version.count(".") >= 2 and preset.get("inherits") == parent_name:
                return version
            if preset.get("name") == parent_name and isinstance(version, str) and version.count(".") >= 2:
                return version
    return "2.3.2.73"


def base_id_for_parent(kind: str, parent_name: str) -> str:
    """OrcaSlicer ignores a user preset whose .info file has an empty base_id."""
    folder = config_dir() / "user" / "default" / kind
    inherited = read_base_id(folder / f"{parent_name}.info")
    if inherited:
        return inherited
    if folder.is_dir():
        for info_path in sorted(folder.glob("*.info")):
            preset_path = info_path.with_suffix(".json")
            if not preset_path.is_file():
                continue
            try:
                preset = load_json(preset_path)
            except (OSError, ValueError):
                continue
            if preset.get("inherits") != parent_name:
                continue
            found = read_base_id(info_path)
            if found:
                return found
    try:
        preset = load_json(find_preset(kind, parent_name))
    except FileNotFoundError:
        return ""
    setting_id = preset.get("setting_id") or ""
    if isinstance(setting_id, list):
        setting_id = setting_id[0] if setting_id else ""
    return str(setting_id)


def load_json(path: Path) -> dict:
    with path.open() as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def find_preset(kind: str, name: str) -> Path:
    filename = f"{name}.json"
    for root in preset_roots():
        direct = root / kind / filename
        if direct.is_file():
            return direct
        matches = sorted(root.glob(f"*/{kind}/{filename}"))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No {kind} preset named {name!r}")


def inheritance_chain(kind: str, name: str) -> list[tuple[Path, dict]]:
    seen: set[str] = set()
    chain: list[tuple[Path, dict]] = []
    current = name
    while current and current not in seen:
        seen.add(current)
        path = find_preset(kind, current)
        data = load_json(path)
        chain.append((path, data))
        parent = data.get("inherits") or ""
        current = parent.strip() if isinstance(parent, str) else ""
    chain.reverse()
    return chain


class Resolved:
    def __init__(self, kind: str, name: str, inherits: str, path: Path, values: dict, leaf_keys: set[str], user_leaf: bool):
        self.kind = kind
        self.name = name
        self.inherits = inherits
        self.path = path
        self.values = values
        self.leaf_keys = leaf_keys
        self.user_leaf = user_leaf


def resolve_preset(kind: str, name: str) -> Resolved:
    chain = inheritance_chain(kind, name)
    if not chain:
        raise FileNotFoundError(f"No {kind} preset named {name!r}")
    merged: dict = {}
    for _path, data in chain:
        for key, value in data.items():
            if key in META_KEYS:
                continue
            merged[key] = value
    leaf_path, leaf = chain[-1]
    leaf_keys = {key for key in leaf if key not in META_KEYS}
    return Resolved(
        kind=kind,
        name=str(leaf.get("name") or name),
        inherits=str(leaf.get("inherits") or ""),
        path=leaf_path,
        values=merged,
        leaf_keys=leaf_keys,
        user_leaf=str(leaf.get("from") or "").lower() == "user",
    )


def load_conf() -> dict:
    path = config_dir() / "OrcaSlicer.conf"
    if not path.is_file():
        raise FileNotFoundError(f"OrcaSlicer config not found at {path}")
    return load_json(path)


def list_setups() -> list[dict]:
    conf = load_conf()
    active_machine = str((conf.get("presets") or {}).get("machine") or "")
    slots = conf.get("orca_presets") or []
    setups = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        machine = str(slot.get("machine") or "")
        if not machine and not slot.get("process"):
            continue
        setups.append(
            {
                "index": index,
                "machine": machine,
                "process": str(slot.get("process") or ""),
                "filament": str(slot.get("filament") or ""),
                "bed_type": str(slot.get("curr_bed_type") or ""),
                "active": False,
            }
        )
    chosen = None
    for item in reversed(setups):
        if item["machine"] == active_machine and active_machine:
            chosen = item["index"]
            break
    if chosen is None and setups:
        chosen = setups[-1]["index"]
    for item in setups:
        item["active"] = item["index"] == chosen
    return setups


def get_setup(index: int | None = None) -> dict:
    setups = list_setups()
    if not setups:
        raise RuntimeError("OrcaSlicer.conf has no printer setups")
    if index is None:
        for item in setups:
            if item["active"]:
                return item
        return setups[-1]
    for item in setups:
        if item["index"] == index:
            return item
    raise KeyError(f"No printer setup at index {index}")


def display_value(value) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return display_value(value[0])
        return ", ".join(display_value(item) for item in value)
    if value is None:
        return ""
    text = str(value).strip()
    if "\n" in text:
        text = text.splitlines()[0].rstrip() + " …"
    if len(text) > 180:
        text = text[:177] + "…"
    return text


def bed_label(bed_type: str) -> tuple[str, str | None]:
    return BED_TYPES.get(str(bed_type), (f"Bed type {bed_type}", None))


USER_PRESET_KINDS = ("process", "filament")
USER_PRESET_LABELS = {"process": "Process", "filament": "Filament"}


def _user_preset_folder(kind: str) -> Path:
    if kind not in USER_PRESET_KINDS:
        raise ValueError("Unknown preset type")
    return config_dir() / "user" / "default" / kind


def _preset_file_name(name: str) -> str:
    if not name or name != Path(name).name or name in {".", ".."}:
        raise ValueError("Invalid preset name")
    return name


def list_user_presets() -> list[dict]:
    presets = []
    for kind in USER_PRESET_KINDS:
        folder = _user_preset_folder(kind)
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            try:
                data = load_json(path)
            except (OSError, ValueError):
                continue
            if str(data.get("from") or "user").lower() != "user":
                continue
            name = str(data.get("name") or path.stem)
            if name != path.stem:
                name = path.stem
            presets.append(
                {
                    "kind": kind,
                    "label": USER_PRESET_LABELS[kind],
                    "name": name,
                    "inherits": str(data.get("inherits") or ""),
                }
            )
    return presets


def delete_user_preset(kind: str, name: str) -> dict:
    if kind == "machine":
        raise ValueError("Printer profiles are not deleted from here.")
    folder = _user_preset_folder(kind)
    filename = _preset_file_name(name)
    path = (folder / f"{filename}.json").resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise FileNotFoundError(f"No user preset named {name}")
    data = load_json(path)
    if str(data.get("from") or "user").lower() != "user":
        raise ValueError("That file is not a user preset")
    dependents = [
        item["name"]
        for item in list_user_presets()
        if item["kind"] == kind and item["inherits"] == name and item["name"] != name
    ]
    if dependents:
        quoted = ", ".join(f"“{item}”" for item in dependents)
        raise ValueError(f"Delete {quoted} first. It is based on this preset.")
    path.unlink()
    path.with_suffix(".info").unlink(missing_ok=True)
    return {"kind": kind, "name": name}


def bed_size(machine_values: dict) -> str:
    height = display_value(machine_values.get("printable_height")) or "?"
    area = machine_values.get("printable_area") or []
    xs: list[float] = []
    ys: list[float] = []
    if isinstance(area, list):
        for point in area:
            if isinstance(point, str) and "x" in point.lower():
                left, right = point.lower().split("x", 1)
                try:
                    xs.append(float(left))
                    ys.append(float(right))
                except ValueError:
                    continue
    if xs and ys:
        width = max(xs) - min(xs)
        depth = max(ys) - min(ys)
        return f"{width:.0f} × {depth:.0f} × {height} mm"
    return f"height {height} mm"
