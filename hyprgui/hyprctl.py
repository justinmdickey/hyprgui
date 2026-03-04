"""Read/write Hyprland settings via hyprctl subprocess calls."""

from __future__ import annotations

import json
import subprocess

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
    """Apply a setting immediately via `hyprctl keyword <key> <value>`."""
    try:
        result = _run(["hyprctl", "keyword", key, value])
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


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
            # hyprctl returns color as a decimal int in "int" field
            # Convert to RRGGBBAA hex string
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
            return str(data.get("str", sdef.default))

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

    # STRING, ENUM
    return str(value)
