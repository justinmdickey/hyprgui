"""Detect whether Hyprland is using the new Lua config or the legacy hyprlang config.

Hyprland 0.55 introduced ``~/.config/hypr/hyprland.lua``. When that file exists,
Hyprland runs in "Lua mode" (and ignores ``hyprland.conf``); otherwise it falls
back to the legacy hyprlang parser. hyprgui mirrors that choice for everything it
writes and for how it pushes live changes (``hyprctl eval`` vs ``hyprctl keyword``).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

HYPR_DIR = Path.home() / ".config" / "hypr"
HYPRLAND_LUA = HYPR_DIR / "hyprland.lua"
HYPRLAND_CONF = HYPR_DIR / "hyprland.conf"

# Managed-file names per mode.
HYPRGUI_LUA = HYPR_DIR / "hyprgui.lua"
HYPRGUI_CONF = HYPR_DIR / "hyprgui.conf"


class ConfigMode(Enum):
    LUA = "lua"
    HYPRLANG = "hyprlang"


def detect_mode() -> ConfigMode:
    """Return :data:`ConfigMode.LUA` if ``hyprland.lua`` exists, else ``HYPRLANG``."""
    return ConfigMode.LUA if HYPRLAND_LUA.exists() else ConfigMode.HYPRLANG


def both_configs_present() -> bool:
    """True if both ``hyprland.lua`` and ``hyprland.conf`` exist.

    In this case Hyprland uses the Lua one and silently ignores the legacy file;
    the UI should warn so the user isn't confused about why ``.conf`` edits do nothing.
    """
    return HYPRLAND_LUA.exists() and HYPRLAND_CONF.exists()


def managed_file(mode: ConfigMode | None = None) -> Path:
    """Path to the config file hyprgui owns and rewrites, for the given mode."""
    if mode is None:
        mode = detect_mode()
    return HYPRGUI_LUA if mode is ConfigMode.LUA else HYPRGUI_CONF
