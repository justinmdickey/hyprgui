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
