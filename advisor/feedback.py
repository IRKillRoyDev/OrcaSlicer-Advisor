"""Parse a review response and diff it against the resolved presets."""

from __future__ import annotations

import json

from advisor.catalog import catalog_index
from advisor.profiles import display_value, get_setup, resolve_preset
from advisor.snapshot import _lookup


def parse_feedback(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found. Paste the JSON Grok returned.")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("The response must be a JSON object.")
    changes = data.get("changes") or []
    if not isinstance(changes, list):
        raise ValueError('"changes" must be a list.')
    cleaned = []
    for item in changes:
        if not isinstance(item, dict) or "key" not in item:
            continue
        cleaned.append(
            {
                "key": str(item["key"]).strip(),
                "value": item.get("value"),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return {"summary": str(data.get("summary") or "").strip(), "changes": cleaned}


def _normalize(current, proposed) -> tuple[object, str]:
    """Return the value to store and a warning, if the format was adjusted."""
    warning = ""
    if isinstance(proposed, bool):
        text = "1" if proposed else "0"
    elif isinstance(proposed, list):
        text = proposed
    elif isinstance(proposed, (int, float)) and not isinstance(proposed, bool):
        text = str(proposed)
        if isinstance(text, str) and text.endswith(".0"):
            text = text[:-2]
    else:
        text = str(proposed).strip()
    current_text = display_value(current)
    if isinstance(text, str) and current_text.endswith("%") and _is_number(text) and not text.endswith("%"):
        text = f"{text}%"
        warning = "Added the % sign so it matches the current setting."
    return text, warning


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _coerce(current, proposed):
    if isinstance(current, list):
        if isinstance(proposed, list):
            return [str(item) for item in proposed]
        return [str(proposed)]
    if isinstance(proposed, list):
        if len(proposed) == 1:
            return str(proposed[0])
        return json.dumps(proposed)
    return str(proposed)


def review_changes(setup_index: int, feedback_text: str) -> dict:
    parsed = parse_feedback(feedback_text)
    setup = get_setup(setup_index)
    resolved = {
        "machine": resolve_preset("machine", setup["machine"]),
        "process": resolve_preset("process", setup["process"]),
        "filament": resolve_preset("filament", setup["filament"]),
    }
    indexed = catalog_index()
    diffs = []
    unknown = []
    for change in parsed["changes"]:
        key = change["key"]
        preferred = indexed.get(key, {}).get("kind")
        kind, current = _lookup(key, preferred, resolved)
        if kind is None:
            unknown.append(key)
            continue
        proposed, warning = _normalize(current, change["value"])
        stored = _coerce(current, proposed)
        before = display_value(current)
        after = display_value(stored)
        diffs.append(
            {
                "key": key,
                "label": indexed.get(key, {}).get("label") or key.replace("_", " "),
                "kind": kind,
                "before": before,
                "after": after,
                "reason": change["reason"],
                "changed": before != after,
                "warning": warning,
                "stored": stored,
            }
        )
    return {
        "summary": parsed["summary"],
        "diffs": diffs,
        "unknown": unknown,
        "change_count": sum(1 for item in diffs if item["changed"]),
    }
