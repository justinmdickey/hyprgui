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

    # ENUM options (display labels shown in dropdown)
    enum_options: tuple[str, ...] = ()
    # ENUM values (actual hyprctl values; maps 1:1 with enum_options)
    enum_values: tuple[str, ...] = ()

    # Default fallback when hyprctl read fails
    default: object = None


# -- Page metadata ----------------------------------------------------------

PAGE_TITLES: dict[str, str] = {
    "decoration": "Decoration",
    "gaps_borders": "Gaps & Borders",
    "animations": "Animations",
    "input": "Input",
    "layouts": "Layouts",
    "misc": "Miscellaneous",
}

PAGE_ICONS: dict[str, str] = {
    "decoration": "preferences-desktop-theme-symbolic",
    "gaps_borders": "view-grid-symbolic",
    "animations": "media-playback-start-symbolic",
    "input": "input-keyboard-symbolic",
    "layouts": "view-dual-symbolic",
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
    SettingDef(
        key="decoration:blur:ignore_opacity",
        label="Ignore Opacity",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Blur",
        default=False,
    ),
    SettingDef(
        key="decoration:blur:xray",
        label="Xray",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Blur",
        default=False,
    ),
    SettingDef(
        key="decoration:blur:new_optimizations",
        label="New Optimizations",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Blur",
        default=True,
    ),
    SettingDef(
        key="decoration:blur:popups",
        label="Blur Popups",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Blur",
        default=False,
    ),
    SettingDef(
        key="decoration:blur:vibrancy",
        label="Vibrancy",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Blur",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.1696,
    ),
    SettingDef(
        key="decoration:blur:vibrancy_darkness",
        label="Vibrancy Darkness",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Blur",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.0,
    ),
    SettingDef(
        key="decoration:blur:contrast",
        label="Contrast",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Blur",
        min_val=0.0,
        max_val=2.0,
        step=0.05,
        default=0.8916,
    ),
    SettingDef(
        key="decoration:blur:brightness",
        label="Brightness",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Blur",
        min_val=0.0,
        max_val=2.0,
        step=0.05,
        default=0.8172,
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
        key="decoration:shadow:render_power",
        label="Render Power",
        setting_type=SettingType.INT,
        page="decoration",
        group="Shadow",
        min_val=1,
        max_val=4,
        step=1,
        default=3,
    ),
    SettingDef(
        key="decoration:shadow:color",
        label="Shadow Color",
        setting_type=SettingType.COLOR,
        page="decoration",
        group="Shadow",
        default="1a1a1aee",
    ),
    SettingDef(
        key="decoration:shadow:color_inactive",
        label="Inactive Shadow Color",
        setting_type=SettingType.COLOR,
        page="decoration",
        group="Shadow",
        default="60000000",
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
        key="decoration:rounding_power",
        label="Rounding Power",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=5.0,
        step=0.1,
        default=2.0,
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
        key="decoration:dim_inactive",
        label="Dim Inactive Windows",
        setting_type=SettingType.BOOL,
        page="decoration",
        group="Appearance",
        default=False,
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
    SettingDef(
        key="decoration:dim_around",
        label="Dim Around",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.4,
    ),
    SettingDef(
        key="decoration:dim_special",
        label="Dim Special Workspace",
        setting_type=SettingType.FLOAT,
        page="decoration",
        group="Appearance",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.2,
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
    SettingDef(
        key="general:resize_on_border",
        label="Resize on Border",
        setting_type=SettingType.BOOL,
        page="gaps_borders",
        group="Borders",
        default=False,
    ),
    SettingDef(
        key="general:hover_icon_on_border",
        label="Show Resize Icon",
        setting_type=SettingType.BOOL,
        page="gaps_borders",
        group="Borders",
        default=True,
    ),
    SettingDef(
        key="general:extend_border_grab_area",
        label="Border Grab Area",
        setting_type=SettingType.INT,
        page="gaps_borders",
        group="Borders",
        min_val=0,
        max_val=50,
        step=1,
        default=15,
    ),

    # ── Gaps & Borders: General ───────────────────────────────────────
    SettingDef(
        key="general:allow_tearing",
        label="Allow Tearing",
        setting_type=SettingType.BOOL,
        page="gaps_borders",
        group="General",
        default=False,
    ),

    # ── Gaps & Borders: Snapping ──────────────────────────────────────
    SettingDef(
        key="general:snap:enabled",
        label="Enable Window Snapping",
        setting_type=SettingType.BOOL,
        page="gaps_borders",
        group="Snapping",
        default=False,
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

    # ── Input: Keyboard ───────────────────────────────────────────────
    SettingDef(
        key="input:kb_layout",
        label="Keyboard Layout",
        setting_type=SettingType.STRING,
        page="input",
        group="Keyboard",
        default="us",
    ),

    # ── Input: Mouse ──────────────────────────────────────────────────
    SettingDef(
        key="input:follow_mouse",
        label="Follow Mouse Focus",
        setting_type=SettingType.ENUM,
        page="input",
        group="Mouse",
        enum_options=("Disabled", "Always", "Loose", "Strict"),
        enum_values=("0", "1", "2", "3"),
        default="Always",
    ),
    SettingDef(
        key="input:sensitivity",
        label="Mouse Sensitivity",
        setting_type=SettingType.FLOAT,
        page="input",
        group="Mouse",
        min_val=-1.0,
        max_val=1.0,
        step=0.05,
        default=0.0,
    ),
    SettingDef(
        key="input:accel_profile",
        label="Acceleration Profile",
        setting_type=SettingType.ENUM,
        page="input",
        group="Mouse",
        enum_options=("Default", "adaptive", "flat"),
        enum_values=("", "adaptive", "flat"),
        default="Default",
    ),

    # ── Input: Touchpad ───────────────────────────────────────────────
    SettingDef(
        key="input:touchpad:natural_scroll",
        label="Natural Scroll",
        setting_type=SettingType.BOOL,
        page="input",
        group="Touchpad",
        default=False,
    ),
    SettingDef(
        key="input:touchpad:disable_while_typing",
        label="Disable While Typing",
        setting_type=SettingType.BOOL,
        page="input",
        group="Touchpad",
        default=True,
    ),
    SettingDef(
        key="input:touchpad:tap-to-click",
        label="Tap to Click",
        setting_type=SettingType.BOOL,
        page="input",
        group="Touchpad",
        default=True,
    ),
    SettingDef(
        key="input:touchpad:clickfinger_behavior",
        label="Clickfinger Behavior",
        setting_type=SettingType.BOOL,
        page="input",
        group="Touchpad",
        default=False,
    ),
    SettingDef(
        key="input:touchpad:scroll_factor",
        label="Scroll Factor",
        setting_type=SettingType.FLOAT,
        page="input",
        group="Touchpad",
        min_val=0.1,
        max_val=3.0,
        step=0.1,
        default=1.0,
    ),

    # ── Layouts: Layout ──────────────────────────────────────────────
    SettingDef(
        key="general:layout",
        label="Layout",
        setting_type=SettingType.ENUM,
        page="layouts",
        group="Layout",
        enum_options=("dwindle", "master", "monocle", "scrolling"),
        default="dwindle",
    ),

    # ── Layouts: Dwindle ──────────────────────────────────────────────
    SettingDef(
        key="dwindle:pseudotile",
        label="Pseudotile",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Dwindle",
        default=False,
    ),
    SettingDef(
        key="dwindle:force_split",
        label="Force Split Direction",
        setting_type=SettingType.ENUM,
        page="layouts",
        group="Dwindle",
        enum_options=("Follows mouse", "Always left", "Always right"),
        enum_values=("0", "1", "2"),
        default="Follows mouse",
    ),
    SettingDef(
        key="dwindle:preserve_split",
        label="Preserve Split",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Dwindle",
        default=False,
    ),
    SettingDef(
        key="dwindle:smart_split",
        label="Smart Split",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Dwindle",
        default=False,
    ),
    SettingDef(
        key="dwindle:smart_resizing",
        label="Smart Resizing",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Dwindle",
        default=True,
    ),
    SettingDef(
        key="dwindle:default_split_ratio",
        label="Default Split Ratio",
        setting_type=SettingType.FLOAT,
        page="layouts",
        group="Dwindle",
        min_val=0.1,
        max_val=1.9,
        step=0.05,
        default=1.0,
    ),

    # ── Layouts: Master ───────────────────────────────────────────────
    SettingDef(
        key="master:orientation",
        label="Orientation",
        setting_type=SettingType.ENUM,
        page="layouts",
        group="Master",
        enum_options=("left", "right", "top", "bottom", "center"),
        default="left",
    ),
    SettingDef(
        key="master:mfact",
        label="Master Factor",
        setting_type=SettingType.FLOAT,
        page="layouts",
        group="Master",
        min_val=0.0,
        max_val=1.0,
        step=0.05,
        default=0.55,
    ),
    SettingDef(
        key="master:new_on_top",
        label="New Windows on Top",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Master",
        default=False,
    ),
    SettingDef(
        key="master:smart_resizing",
        label="Smart Resizing",
        setting_type=SettingType.BOOL,
        page="layouts",
        group="Master",
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

    # ── Miscellaneous: Performance ────────────────────────────────────
    SettingDef(
        key="misc:vfr",
        label="Variable Frame Rate",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Performance",
        default=True,
    ),

    # ── Miscellaneous: Power ──────────────────────────────────────────
    SettingDef(
        key="misc:mouse_move_enables_dpms",
        label="Mouse Wakes Screen",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Power",
        default=False,
    ),
    SettingDef(
        key="misc:key_press_enables_dpms",
        label="Key Press Wakes Screen",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Power",
        default=False,
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
        key="misc:disable_splash_rendering",
        label="Disable Splash",
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
    SettingDef(
        key="misc:allow_session_lock_restore",
        label="Allow Session Lock Restore",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Miscellaneous",
        default=False,
    ),

    # ── Miscellaneous: XWayland ───────────────────────────────────────
    SettingDef(
        key="xwayland:force_zero_scaling",
        label="Force Zero Scaling",
        setting_type=SettingType.BOOL,
        page="misc",
        group="XWayland",
        default=False,
    ),

    # ── Miscellaneous: Binds ──────────────────────────────────────────
    SettingDef(
        key="binds:movefocus_cycles_fullscreen",
        label="Move Focus Cycles Fullscreen",
        setting_type=SettingType.BOOL,
        page="misc",
        group="Binds",
        default=True,
    ),
]
