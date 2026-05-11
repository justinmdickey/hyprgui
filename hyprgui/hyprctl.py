"""Read/write Hyprland settings via hyprctl subprocess calls.

Read path (``getoption``) is identical in both legacy hyprlang and the new Lua
config (Hyprland 0.55+). Write path differs: legacy mode uses ``hyprctl keyword``,
Lua mode uses ``hyprctl eval 'hl.config({...})'`` because the Lua parser rejects
``keyword``. :func:`apply_setting` picks the right path based on
:func:`~hyprgui.config_mode.detect_mode`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from hyprgui import lua_format
from hyprgui.config_mode import ConfigMode, detect_mode
from hyprgui.settings_registry import SettingDef, SettingType


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=5)


def reload_config() -> bool:
    """Tell Hyprland to reload its config via `hyprctl reload`."""
    try:
        result = _run(["hyprctl", "reload"])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def getoption(key: str) -> dict | None:
    """Return parsed JSON from `hyprctl -j getoption <key>`, or None on failure."""
    try:
        result = _run(["hyprctl", "-j", "getoption", key])
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def set_keyword(key: str, value: str) -> bool:
    """Apply a setting via legacy ``hyprctl keyword`` (hyprlang mode only).

    Under the Lua parser this fails with "keyword can't work with non-legacy
    parsers. Use eval." — callers should prefer :func:`apply_setting`.
    """
    try:
        result = _run(["hyprctl", "keyword", key, value])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def eval_lua(lua: str) -> bool:
    """Run a Lua snippet via ``hyprctl eval`` (Lua mode write path)."""
    try:
        result = _run(["hyprctl", "eval", lua])
        return result.returncode == 0 and "ok" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def apply_setting(sdef: SettingDef, value: object) -> bool:
    """Push a single setting to Hyprland for instant preview, mode-aware.

    Hyprlang mode → ``hyprctl keyword``. Lua mode → ``hyprctl eval
    'hl.config({...})'`` with a one-key nested table. ``hl.config`` merges,
    so this leaves all other settings alone (verified on 0.55.0).
    """
    if detect_mode() is ConfigMode.LUA:
        return eval_lua(lua_format.eval_snippet_for(sdef, value))
    return set_keyword(sdef.key, format_value(sdef, value))


def parse_option_value(sdef: SettingDef, data: dict | None) -> object:
    """Extract the typed value from a hyprctl getoption JSON response."""
    if data is None:
        return sdef.default

    try:
        if sdef.setting_type == SettingType.BOOL:
            # hyprctl returns {"int": 0/1} for bools
            return bool(data.get("int", int(sdef.default)))

        if sdef.setting_type == SettingType.INT:
            return int(data.get("int", sdef.default))

        if sdef.setting_type == SettingType.FLOAT:
            return float(data.get("float", sdef.default))

        if sdef.setting_type == SettingType.COLOR:
            # Two response shapes:
            #  * plain color keys (decoration.shadow.color, misc.background_color, ...)
            #    -> {"int": <decimal AARRGGBB>}  (same as pre-0.55)
            #  * gradient keys (general.col.*, group.groupbar.col.*, ...) under the
            #    Lua parser -> {"gradient": "AARRGGBB [AARRGGBB...] [Ndeg]"} (new in 0.55)
            grad = data.get("gradient")
            if isinstance(grad, str) and grad.strip():
                # Take the first colour stop; ignore further stops + angle for now.
                # (hyprgui's UI only exposes single-colour borders.)
                first = grad.strip().split()[0]
                # 8-hex-digit AARRGGBB → our internal RRGGBBAA
                if re.fullmatch(r"[0-9a-fA-F]{8}", first):
                    aa, rr, gg, bb = first[0:2], first[2:4], first[4:6], first[6:8]
                    return f"{rr}{gg}{bb}{aa}".lower()
            raw = data.get("int")
            if raw is not None:
                # The int is AARRGGBB as a 32-bit value
                val = int(raw) & 0xFFFFFFFF
                aa = (val >> 24) & 0xFF
                rr = (val >> 16) & 0xFF
                gg = (val >> 8) & 0xFF
                bb = val & 0xFF
                return f"{rr:02x}{gg:02x}{bb:02x}{aa:02x}"
            return sdef.default

        if sdef.setting_type == SettingType.STRING:
            return str(data.get("str", sdef.default))

        if sdef.setting_type == SettingType.ENUM:
            raw = str(data.get("str", sdef.default)).strip()
            if sdef.enum_values:
                # Map raw hyprctl value back to display label
                # Try int field first (for numeric enums like follow_mouse)
                int_raw = data.get("int")
                if int_raw is not None:
                    int_str = str(int(int_raw))
                    if int_str in sdef.enum_values:
                        idx = sdef.enum_values.index(int_str)
                        return sdef.enum_options[idx]
                if raw in sdef.enum_values:
                    idx = sdef.enum_values.index(raw)
                    return sdef.enum_options[idx]
                return sdef.default
            return raw

    except (ValueError, TypeError, KeyError):
        pass

    return sdef.default


def format_value(sdef: SettingDef, value: object) -> str:
    """Format a Python value into the string hyprctl / config expects."""
    if sdef.setting_type == SettingType.BOOL:
        return "true" if value else "false"

    if sdef.setting_type == SettingType.INT:
        return str(int(value))

    if sdef.setting_type == SettingType.FLOAT:
        return f"{float(value):.6f}".rstrip("0").rstrip(".")

    if sdef.setting_type == SettingType.COLOR:
        # value is RRGGBBAA hex string, hyprctl wants "rgba(RRGGBBAA)"
        return f"rgba({value})"

    if sdef.setting_type == SettingType.ENUM and sdef.enum_values:
        # Map display label back to hyprctl value
        label = str(value)
        if label in sdef.enum_options:
            idx = sdef.enum_options.index(label)
            return sdef.enum_values[idx]

    # STRING, ENUM (without enum_values)
    return str(value)


# -- Cursor theme helpers ---------------------------------------------------

_CURSOR_DIRS = [
    Path.home() / ".local" / "share" / "icons",
    Path.home() / ".icons",
    Path("/usr/share/icons"),
]


def find_cursor_themes() -> list[str]:
    """Scan standard icon directories for installed cursor themes."""
    themes: set[str] = set()
    for base in _CURSOR_DIRS:
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if not child.is_dir():
                continue
            # Hyprcursor themes have manifest.hl or manifest.toml
            # XCursor themes have a cursors/ subdirectory
            if ((child / "cursors").is_dir()
                    or (child / "manifest.hl").exists()
                    or (child / "manifest.toml").exists()):
                themes.add(child.name)
    return sorted(themes)


def get_current_cursor() -> tuple[str, int]:
    """Return (theme_name, size) from environment variables."""
    theme = os.environ.get("HYPRCURSOR_THEME")
    if not theme:
        theme = os.environ.get("XCURSOR_THEME", "")
    size_str = os.environ.get("HYPRCURSOR_SIZE")
    if not size_str:
        size_str = os.environ.get("XCURSOR_SIZE", "24")
    try:
        size = int(size_str)
    except ValueError:
        size = 24
    return theme, size


def set_cursor(theme: str, size: int) -> bool:
    """Apply cursor theme and size via ``hyprctl setcursor``."""
    try:
        result = _run(["hyprctl", "setcursor", theme, str(size)])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
