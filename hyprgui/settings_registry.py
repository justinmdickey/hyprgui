"""Declarative settings registry — the extensibility core.

To add a new setting, append one SettingDef to the SETTINGS list.
The UI, live preview, and config persistence are all derived automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class SettingType(Enum):
    BOOL = auto()
    INT = auto()
    FLOAT = auto()
    COLOR = auto()
    STRING = auto()
    ENUM = auto()


@dataclass(frozen=True)
class SettingDef:
    key: str  # hyprctl option key, e.g. "decoration:blur:enabled"
    label: str  # human-readable label
    setting_type: SettingType
    page: str  # page name (matches PAGE_TITLES key)
    group: str  # group title within the page

    # Numeric bounds (INT / FLOAT)
    min_val: float = 0
    max_val: float = 100
    step: float = 1

    # ENUM options
    enum_options: tuple[str, ...] = ()

    # Default fallback when hyprctl read fails
    default: object = None


# -- Page metadata ----------------------------------------------------------

PAGE_TITLES: dict[str, str] = {
    "decoration": "Decoration",
    "gaps_borders": "Gaps & Borders",
    "animations": "Animations",
    "misc": "Miscellaneous",
}

PAGE_ICONS: dict[str, str] = {
    "decoration": "preferences-desktop-theme-symbolic",
    "gaps_borders": "view-grid-symbolic",
    "animations": "media-playback-start-symbolic",
    "misc": "preferences-other-symbolic",
}

# -- Settings definitions ---------------------------------------------------

SETTINGS: list[SettingDef] = [
    # ── Decoration: Blur ──────────────────────────────────────────────
    SettingDef(
        key="decoration:blur:enabled",
        label="Enable Blur",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Blur",
        default=True,
    ),
    SettingDef(
        key="decoration:blur:size",
        label="Blur Size",
        setting_type=SettingType.INT,
        page="decoration",
        group="Blur",
        min_val=1,
        max_val=20,
        step=1,
        default=8,
    ),
    SettingDef(
        key="decoration:blur:passes",
        label="Blur Passes",
        setting_type=SettingType.INT,
        page="decoration",
        group="Blur",
        min_val=1,
        max_val=10,
        step=1,
        default=1,
    ),

    # ── Decoration: Shadow ────────────────────────────────────────────
    SettingDef(
        key="decoration:shadow:enabled",
        label="Enable Shadow",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Shadow",
        default=True,
    ),
    SettingDef(
        key="decoration:shadow:range",
        label="Shadow Range",
        setting_type=SettingType.INT,
        page="decoration",
        group="Shadow",
        min_val=0,
        max_val=100,
        step=1,
        default=4,
    ),
    SettingDef(
        key="decoration:shadow:color",
        label="Shadow Color",
        setting_type=SettingType.COLOR,
        page="decoration",
        group="Shadow",
        default="1a1a1aee",
    ),

    # ── Decoration: Appearance ────────────────────────────────────────
    SettingDef(
        key="decoration:rounding",
        label="Corner Rounding",
        setting_type=SettingType.INT,
        page="decoration",
        group="Appearance",
        min_val=0,
        max_val=30,
        step=1,
        default=0,
    ),
    SettingDef(
        key="decoration:active_opacity",
        label="Active Opacity",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=1.0,
    ),
    SettingDef(
        key="decoration:inactive_opacity",
        label="Inactive Opacity",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=1.0,
    ),
    SettingDef(
        key="decoration:dim_strength",
        label="Dim Strength",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.5,
    ),

    # ── Gaps & Borders: Gaps ──────────────────────────────────────────
    SettingDef(
        key="general:gaps_in",
        label="Inner Gaps",
        setting_type=SettingType.INT,
        page="gaps_borders",
        group="Gaps",
        min_val=0,
        max_val=50,
        step=1,
        default=5,
    ),
    SettingDef(
        key="general:gaps_out",
        label="Outer Gaps",
        setting_type=SettingType.INT,
        page="gaps_borders",
        group="Gaps",
        min_val=0,
        max_val=60,
        step=1,
        default=20,
    ),

    # ── Gaps & Borders: Borders ───────────────────────────────────────
    SettingDef(
        key="general:border_size",
        label="Border Size",
        setting_type=SettingType.INT,
        page="gaps_borders",
        group="Borders",
        min_val=0,
        max_val=10,
        step=1,
        default=1,
    ),
    SettingDef(
        key="general:col.active_border",
        label="Active Border Color",
        setting_type=SettingType.COLOR,
        page="gaps_borders",
        group="Borders",
        default="33ccffee",
    ),
    SettingDef(
        key="general:col.inactive_border",
        label="Inactive Border Color",
        setting_type=SettingType.COLOR,
        page="gaps_borders",
        group="Borders",
        default="595959aa",
    ),

    # ── Gaps & Borders: Layout ────────────────────────────────────────
    SettingDef(
        key="general:layout",
        label="Layout",
        setting_type=SettingType.ENUM,
        page="gaps_borders",
        group="Layout",
        enum_options=("dwindle", "master"),
        default="dwindle",
    ),

    # ── Animations ────────────────────────────────────────────────────
    SettingDef(
        key="animations:enabled",
        label="Enable Animations",
        setting_type=SettingType.BOOL,
        page="animations",
        group="Animations",
        default=True,
    ),

    # ── Miscellaneous: Cursor ─────────────────────────────────────────
    SettingDef(
        key="cursor:zoom_factor",
        label="Cursor Zoom Factor",
        setting_type=SettingType.FLOAT,
        page="misc",
        group="Cursor",
        min_val=1.0,
        max_val=10.0,
        step=0.25,
        default=1.0,
    ),
    SettingDef(
        key="cursor:enable_hyprcursor",
        label="Enable Hyprcursor",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Cursor",
        default=True,
    ),

    # ── Miscellaneous: Misc ───────────────────────────────────────────
    SettingDef(
        key="misc:font_family",
        label="Font Family",
        setting_type=SettingType.STRING,
        page="misc",
        group="Miscellaneous",
        default="Sans",
    ),
    SettingDef(
        key="misc:disable_hyprland_logo",
        label="Disable Hyprland Logo",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Miscellaneous",
        default=False,
    ),
    SettingDef(
        key="misc:focus_on_activate",
        label="Focus on Activate",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Miscellaneous",
        default=True,
    ),
]
