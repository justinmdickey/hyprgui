"""Tests for the Display page's mode-aware monitor write helpers.

The Display page used to call ``hyprctl keyword monitor ...`` directly, which
the Lua parser rejects ("keyword can't work with non-legacy parsers"). The
fix routes through ``hl.monitor({...})`` via ``hyprctl eval`` in Lua mode.

These tests stub out ``hyprctl.eval_lua`` and ``_keyword_monitor`` to capture
exactly what each apply path would send, without needing a running Hyprland.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _patch(tmp_path):
    """Reset module-level state and patch out the write/eval calls."""
    from hyprgui import config_mode
    from hyprgui.pages import display

    # Force Lua mode regardless of host config.
    config_mode.HYPRLAND_LUA = tmp_path / "hyprland.lua"
    (tmp_path / "hyprland.lua").write_text("-- test")

    captured: dict[str, list] = {"eval": [], "keyword": []}
    display.eval_lua = lambda s: (captured["eval"].append(s), True)[1]
    display._keyword_monitor = lambda s: (captured["keyword"].append(s), True)[1]
    return display, captured


def test_apply_monitor_lua_mode_uses_hl_monitor(tmp_path):
    display, captured = _patch(tmp_path)
    display._apply_monitor("DP-1", 2560, 1440, 144.0, 100, 200, 1.0)
    assert captured["keyword"] == []
    assert len(captured["eval"]) == 1
    snippet = captured["eval"][0]
    assert snippet.startswith("hl.monitor({")
    assert 'output = "DP-1"' in snippet
    assert 'mode = "2560x1440@144.00"' in snippet
    assert 'position = "100x200"' in snippet
    assert 'scale = "1.0"' in snippet


def test_apply_transform_lua_mode(tmp_path):
    display, captured = _patch(tmp_path)
    display._apply_transform("DP-1", 1)
    assert captured["keyword"] == []
    assert captured["eval"] == ['hl.monitor({ output = "DP-1", transform = 1 })']


def test_apply_vrr_lua_mode(tmp_path):
    display, captured = _patch(tmp_path)
    display._apply_vrr("DP-1", True)
    display._apply_vrr("DP-1", False)
    assert captured["keyword"] == []
    assert captured["eval"] == [
        'hl.monitor({ output = "DP-1", vrr = 1 })',
        'hl.monitor({ output = "DP-1", vrr = 0 })',
    ]


def test_apply_monitor_legacy_mode(tmp_path):
    # Remove the Lua marker -> legacy mode.
    from hyprgui import config_mode
    from hyprgui.pages import display
    config_mode.HYPRLAND_LUA = tmp_path / "definitely-not-here.lua"
    captured: dict[str, list] = {"eval": [], "keyword": []}
    display.eval_lua = lambda s: (captured["eval"].append(s), True)[1]
    display._keyword_monitor = lambda s: (captured["keyword"].append(s), True)[1]

    display._apply_monitor("DP-1", 2560, 1440, 144.0, 0, 0, 1.0)
    display._apply_transform("DP-1", 2)
    display._apply_vrr("DP-1", True)

    assert captured["eval"] == []
    assert captured["keyword"] == [
        "DP-1,2560x1440@144.00,0x0,1.0",
        "DP-1,transform,2",
        "DP-1,vrr,1",
    ]


def test_build_monitor_spec_roundtrips_through_lua_writer(tmp_path):
    """The spec written by Display -> upsert_managed_monitors must parse back
    into the equivalent hl.monitor call when lua_writer emits hyprgui.lua."""
    from hyprgui import lua_writer
    from hyprgui.pages.display import _build_monitor_spec

    spec_plain = _build_monitor_spec("DP-1", 2560, 1440, 144.0, 0, 0, 1.0)
    assert spec_plain == "DP-1,2560x1440@144.00,0x0,1.0"
    assert lua_writer._monitor_call("DP-1", spec_plain) == \
        'hl.monitor({ output = "DP-1", mode = "2560x1440@144.00", position = "0x0", scale = "1.0" })'

    spec_xform = _build_monitor_spec("DP-1", 2560, 1440, 144.0, 0, 0, 1.0, transform=1)
    assert spec_xform.endswith(",transform,1")
    assert "transform = 1" in lua_writer._monitor_call("DP-1", spec_xform)


def _run_all() -> int:
    import tempfile
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
