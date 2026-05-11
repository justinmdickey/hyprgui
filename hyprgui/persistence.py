"""Mode-aware persistence façade — picks Lua or hyprlang backend transparently.

Callers (window.py, main.py, pages/display.py) use this module instead of
``config_manager`` or ``lua_writer`` directly. The right backend is chosen by
:func:`hyprgui.config_mode.detect_mode` at each call. This keeps the legacy
hyprlang path 100% intact and adds the new Lua path behind a single switch.
"""

from __future__ import annotations

from hyprgui import config_manager, lua_writer
from hyprgui.config_mode import ConfigMode, detect_mode
from hyprgui.settings_registry import SETTINGS, SettingType


def is_linked() -> bool:
    """True if the user's main config already pulls in our managed file."""
    if detect_mode() is ConfigMode.LUA:
        return lua_writer.is_linked()
    return config_manager.is_source_line_present()


def link() -> None:
    """Append the link line to the user's main config + create the managed stub."""
    if detect_mode() is ConfigMode.LUA:
        lua_writer.append_link_line()
    else:
        config_manager.append_source_line()


def reset_managed_file() -> None:
    if detect_mode() is ConfigMode.LUA:
        lua_writer.reset_hyprgui_lua()
    else:
        config_manager.reset_hyprgui_conf()


def managed_keys() -> set[str]:
    """The set of SettingDef keys currently persisted in the managed file."""
    if detect_mode() is ConfigMode.LUA:
        state = lua_writer.load_state()
        return set(state.get("managed_keys") or [])
    return config_manager.parse_hyprgui_conf()


def write(
    values: dict[str, object],
    *,
    managed: set[str] | None = None,
    cursor_theme: str = "",
    cursor_size: int = 0,
    monitors: dict[str, str] | None = None,
) -> None:
    if detect_mode() is ConfigMode.LUA:
        lua_writer.write_hyprgui_lua(
            values, managed_keys=managed, cursor_theme=cursor_theme,
            cursor_size=cursor_size, monitors=monitors,
        )
    else:
        config_manager.write_hyprgui_conf(
            values, managed_keys=managed, cursor_theme=cursor_theme,
            cursor_size=cursor_size, monitors=monitors,
        )


def upsert_monitors(updates: dict[str, str]) -> None:
    if detect_mode() is ConfigMode.LUA:
        lua_writer.upsert_managed_monitors(updates)
    else:
        config_manager.upsert_managed_monitors(updates)


def managed_monitors() -> dict[str, str]:
    if detect_mode() is ConfigMode.LUA:
        state = lua_writer.load_state()
        return dict(state.get("monitors") or {})
    return config_manager.parse_managed_monitors()


# --- mode-specific UI hints -----------------------------------------------

def link_prompt_text() -> tuple[str, str]:
    """Return ``(title, body)`` strings for the first-run linking dialog."""
    if detect_mode() is ConfigMode.LUA:
        return (
            "Link Hyprgui into your Lua config?",
            "Hyprgui will append a `dofile(...)` line to ~/.config/hypr/hyprland.lua "
            "so its managed settings are applied when Hyprland reloads. You can "
            "remove that line at any time.",
        )
    return (
        "Link Hyprgui into your Hyprland config?",
        "Hyprgui will append a `source = ...` line to ~/.config/hypr/hyprland.conf "
        "so its managed settings are applied when Hyprland reloads. You can "
        "remove that line at any time.",
    )


__all__ = [
    "SETTINGS", "SettingType",  # re-export for convenience
    "is_linked", "link", "reset_managed_file", "managed_keys", "write",
    "upsert_monitors", "managed_monitors", "link_prompt_text",
]
