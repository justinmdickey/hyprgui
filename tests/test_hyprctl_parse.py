"""Tests for hyprctl.parse_option_value — especially the new 0.55 gradient response."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui import hyprctl  # noqa: E402
from hyprgui.settings_registry import SettingDef, SettingType  # noqa: E402


def _sdef(key, st, **kw):
    return SettingDef(key=key, label="x", setting_type=st, page="p", group="g", **kw)


def test_parse_gradient_color_new_format():
    s = _sdef("general:col.active_border", SettingType.COLOR, default="33ccffee")
    # what `hyprctl -j getoption general:col.active_border` returns on 0.55+ Lua:
    data = {"option": "general:col.active_border", "gradient": "ee33ccff 45deg", "set": True}
    assert hyprctl.parse_option_value(s, data) == "33ccffee"


def test_parse_gradient_multi_stop_takes_first():
    s = _sdef("general:col.active_border", SettingType.COLOR, default="000000ff")
    data = {"gradient": "ee33ccff ff00ff00 90deg"}
    assert hyprctl.parse_option_value(s, data) == "33ccffee"


def test_parse_plain_color_still_int_field():
    s = _sdef("decoration:shadow:color", SettingType.COLOR, default="1a1a1aee")
    # AARRGGBB = 0xee1a1a1a -> RRGGBBAA = 1a1a1aee
    data = {"option": "decoration:shadow:color", "int": 0xee1a1a1a, "set": True}
    assert hyprctl.parse_option_value(s, data) == "1a1a1aee"


def test_parse_int_bool_float_unchanged():
    # legacy "int": 0/1 form for bools
    assert hyprctl.parse_option_value(
        _sdef("decoration:rounding", SettingType.INT, default=0),
        {"option": "decoration:rounding", "int": 18, "set": True},
    ) == 18
    assert hyprctl.parse_option_value(
        _sdef("decoration:blur:enabled", SettingType.BOOL, default=False),
        {"int": 1},
    ) is True
    assert hyprctl.parse_option_value(
        _sdef("master:mfact", SettingType.FLOAT, default=0.5),
        {"float": 0.55},
    ) == 0.55


def test_parse_bool_new_field_in_0_55():
    """0.55+ returns BOOLs as {"bool": true|false}, not {"int": 0|1}.

    Live-sweep regression: every BOOL was failing because we fell back to
    the SettingDef.default. Now we accept the new field shape.
    """
    s = _sdef("decoration:blur:enabled", SettingType.BOOL, default=True)
    # Hyprland says False; we must return False (not the default True).
    assert hyprctl.parse_option_value(
        s, {"option": "decoration:blur:enabled", "bool": False, "set": True}
    ) is False
    # And the inverse.
    assert hyprctl.parse_option_value(
        _sdef("misc:disable_hyprland_logo", SettingType.BOOL, default=False),
        {"option": "misc:disable_hyprland_logo", "bool": True, "set": True},
    ) is True


def test_parse_int_css_field_for_gaps():
    """0.55+ returns HL.CssGap fields as {"css": "T R B L"}.

    Live-sweep regression: general:gaps_in / gaps_out returned the default
    instead of the actual value. Take the first component (top); the UI
    exposes a single int, not a 4-tuple.
    """
    s = _sdef("general:gaps_in", SettingType.INT, default=5)
    assert hyprctl.parse_option_value(
        s, {"option": "general:gaps_in", "css": "6 6 6 6", "set": True}
    ) == 6
    # Non-symmetric (TRBL) — the first component wins for the single-int UI.
    assert hyprctl.parse_option_value(
        s, {"option": "general:gaps_in", "css": "10 20 30 40", "set": True}
    ) == 10


def _run_all() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
