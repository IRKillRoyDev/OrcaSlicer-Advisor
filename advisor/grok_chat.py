"""Send a prompt through the Safari window that is already open.

Remote-control sessions were opening extra Safaris and then talking to an old
empty one. This talks only to the front window of the Safari you are using.
The password is typed on grok.com. This app does not store it.
"""

from __future__ import annotations

import json
import subprocess
import time
import traceback
from datetime import datetime
from pathlib import Path

GROK_URL = "https://grok.com/"
LOG_PATH = Path(__file__).resolve().parents[1] / "work" / "grok.log"
JS_PATH = LOG_PATH.parent / "grok-step.js"


def _log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def send_to_grok(prompt: str, stl_path: Path | None = None) -> str:
    if not prompt.strip():
        raise ValueError("The prompt is empty.")
    _log(f"send start chars={len(prompt)} stl={stl_path.name if stl_path else None}")
    try:
        home = _advisor_tab()
        if home is None:
            raise RuntimeError(
                "Safari is open, but the advisor page was not one of its tabs. "
                "Switch to the OrcaSlicer Advisor window and press Send to Grok again."
            )
        _log(f"using front window {home[0]} tab {home[1]} {home[2]}")
        work_index = _open_tab(home[0])
        _log(f"opened tab {work_index}")
        _wait_for_load(home[0], work_index)
        _dismiss_cookies(home[0], work_index)
        signed_in = _becomes_signed_in(home[0], work_index, 12)
        _log(f"signed_in={signed_in}")
        if not signed_in:
            _show_tab(home[0], work_index)
            _wait_until_signed_in(home[0], work_index)
        else:
            _show_tab(home[0], home[1])
        if stl_path is not None:
            _log(f"stl is named in the prompt; Safari cannot attach the file from here: {stl_path.name}")
        _fill_prompt(home[0], work_index, prompt)
        _click_submit(home[0], work_index)
        _show_tab(home[0], home[1])
        reply = _wait_for_reply(home[0], work_index, prompt)
        _log(f"reply chars={len(reply)}")
        _close_tab(home[0], work_index)
        return reply
    except Exception:
        _log(traceback.format_exc().rstrip())
        raise


def _osascript(source: str) -> str:
    result = subprocess.run(["osascript", "-e", source], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Safari did not answer."
        _log(f"osascript {message}")
        if "Allow JavaScript from Apple Events" in message:
            raise RuntimeError(
                "Safari blocked the script. Open Develop → Developer Settings and turn on "
                "“Allow JavaScript from Apple Events.” This uses the Safari already open. "
                "It does not start another one."
            )
        raise RuntimeError(message)
    return result.stdout.strip()


def _advisor_tab() -> tuple[int, int, str] | None:
    raw = _osascript(
        """
tell application "Safari"
  if (count of windows) is 0 then
    activate
    delay 0.5
  end if
  if (count of windows) is 0 then return "windows=0"
  set found to ""
  repeat with w in windows
    set ti to 0
    repeat with t in tabs of w
      set ti to ti + 1
      set u to ""
      try
        set u to URL of t
      end try
      if u contains "127.0.0.1:8777" then
        set found to (id of w as text) & "|" & (ti as text) & "|" & u
        exit repeat
      end if
    end repeat
    if found is not "" then exit repeat
  end repeat
  if found is "" then return "windows=" & (count of windows) & " advisor=missing"
  return found
end tell
"""
    )
    _log(f"advisor tab lookup {raw!r}")
    parts = raw.split("|")
    if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1]), parts[2]


def _open_tab(window_id: int) -> int:
    raw = _osascript(
        f"""
tell application "Safari"
  set w to window id {window_id}
  make new tab at end of tabs of w with properties {{URL:"{GROK_URL}"}}
  return count of tabs of w
end tell
"""
    )
    if not raw.isdigit():
        raise RuntimeError(f"Safari did not open a Grok tab. {raw}")
    return int(raw)


def _show_tab(window_id: int, tab_index: int) -> None:
    _osascript(
        f"""
tell application "Safari"
  set current tab of window id {window_id} to tab {tab_index} of window id {window_id}
end tell
"""
    )


def _close_tab(window_id: int, tab_index: int) -> None:
    _osascript(
        f"""
tell application "Safari"
  try
    close tab {tab_index} of window id {window_id}
  end try
end tell
"""
    )


def _js(window_id: int, tab_index: int, source: str) -> str:
    JS_PATH.write_text(source, encoding="utf-8")
    return _osascript(
        f"""
tell application "Safari"
  set js to read POSIX file "{JS_PATH}" as «class utf8»
  return do JavaScript js in tab {tab_index} of window id {window_id}
end tell
"""
    )


def _wait_for_load(window_id: int, tab_index: int) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        state = _js(window_id, tab_index, "document.readyState || ''")
        _log(f"ready {state}")
        if state in {"interactive", "complete"}:
            return
        time.sleep(0.4)


def _dismiss_cookies(window_id: int, tab_index: int) -> None:
    clicked = _js(
        window_id,
        tab_index,
        """
        var labels = ["Reject All", "Accept All Cookies"];
        var buttons = document.querySelectorAll("button");
        for (var i = 0; i < buttons.length; i++) {
          var text = (buttons[i].innerText || "").replace(/^\\s+|\\s+$/g, "");
          if (labels.indexOf(text) >= 0) { buttons[i].click(); text; }
        }
        "";
        """,
    )
    if clicked:
        _log(f"cookies {clicked}")


def _login_state(window_id: int, tab_index: int) -> str:
    raw = _js(
        window_id,
        tab_index,
        """
        var signedOut = false;
        var hasBox = false;
        var nodes = document.querySelectorAll("a, button, textarea, div");
        for (var i = 0; i < nodes.length; i++) {
          var el = nodes[i];
          var text = (el.innerText || "").replace(/^\\s+|\\s+$/g, "");
          if (text === "Sign in" && el.getClientRects().length > 0) signedOut = true;
          var label = el.getAttribute ? (el.getAttribute("aria-label") || "") : "";
          if (label.indexOf("Ask Grok") === 0 || el.tagName === "TEXTAREA") hasBox = true;
        }
        JSON.stringify({signedOut: signedOut, hasBox: hasBox});
        """,
    )
    _log(f"login raw {raw[:300]}")
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "loading"
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return "loading"
    if not isinstance(data, dict):
        return "loading"
    if data.get("signedOut"):
        return "out"
    if data.get("hasBox"):
        return "in"
    return "loading"


def _becomes_signed_in(window_id: int, tab_index: int, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = _login_state(window_id, tab_index)
        if state == "in":
            return True
        if state == "out":
            return False
        time.sleep(0.4)
    return _login_state(window_id, tab_index) == "in"


def _wait_until_signed_in(window_id: int, tab_index: int) -> None:
    deadline = time.time() + 180
    while time.time() < deadline:
        if _login_state(window_id, tab_index) == "in":
            return
        time.sleep(1)
    raise TimeoutError("Sign in to Grok in the Safari window, then press Send to Grok again.")


def _fill_prompt(window_id: int, tab_index: int, prompt: str) -> None:
    result = _js(
        window_id,
        tab_index,
        "var text = "
        + json.dumps(prompt)
        + """;
        var el = null;
        var nodes = document.querySelectorAll("textarea, div");
        for (var i = 0; i < nodes.length; i++) {
          var label = nodes[i].getAttribute ? (nodes[i].getAttribute("aria-label") || "") : "";
          if (label.indexOf("Ask Grok") === 0 || nodes[i].tagName === "TEXTAREA") { el = nodes[i]; break; }
        }
        if (!el) "missing";
        else {
          el.focus();
          if (el.isContentEditable) el.textContent = text;
          else el.value = text;
          el.dispatchEvent(new InputEvent("input", {bubbles: true, data: text}));
          "ok";
        }
        """,
    )
    if result.strip() != "ok":
        raise RuntimeError("Could not find the Grok message box in Safari.")


def _click_submit(window_id: int, tab_index: int) -> None:
    result = _js(
        window_id,
        tab_index,
        """
        var button = null;
        var buttons = document.querySelectorAll("button");
        for (var i = 0; i < buttons.length; i++) {
          var label = buttons[i].getAttribute("aria-label") || "";
          if (label === "Submit" || buttons[i].type === "submit") { button = buttons[i]; break; }
        }
        if (!button) "missing";
        else { button.click(); "ok"; }
        """,
    )
    if result.strip() != "ok":
        raise RuntimeError("Could not find Grok’s send button in Safari.")


def _wait_for_reply(window_id: int, tab_index: int, prompt: str) -> str:
    deadline = time.time() + 180
    last = ""
    stable = 0
    while time.time() < deadline:
        text = _js(
            window_id,
            tab_index,
            """
            var main = document.querySelector("main");
            main ? main.innerText : (document.body ? document.body.innerText : "");
            """,
        )
        reply = _reply_after_prompt(text, prompt)
        if reply and reply == last:
            stable += 1
            if stable >= 3:
                return reply
        else:
            stable = 0
            last = reply
        time.sleep(0.8)
    if last:
        return last
    raise TimeoutError("Grok did not answer in time. Try Send to Grok again.")


_PLACEHOLDER_SUMMARY = "short assessment of this profile for this part and material"


def _reply_after_prompt(page_text: str, prompt: str) -> str:
    """Return Grok's settings JSON, not the request that is still on the page."""
    del prompt
    chosen = ""
    for raw in _json_objects(page_text):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "task" in data:
            continue
        summary = data.get("summary")
        changes = data.get("changes")
        if not isinstance(summary, str) or not isinstance(changes, list):
            continue
        if summary.strip() == _PLACEHOLDER_SUMMARY:
            continue
        chosen = raw.strip()
    return chosen


def _json_objects(text: str) -> list[str]:
    objects: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        start = index
        depth = 0
        in_string = False
        escape = False
        closed = False
        for cursor in range(index, len(text)):
            char = text[cursor]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    objects.append(text[start : cursor + 1])
                    index = cursor + 1
                    closed = True
                    break
        if not closed:
            break
    return objects
