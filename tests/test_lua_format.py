"""Unit tests for hyprgui.lua_format (pure, offline).

Run: python -m pytest tests/test_lua_format.py -v   (or: python tests/test_lua_format.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui import lua_format as lf  # noqa: E402
from hyprgui.settings_registry import SettingDef, SettingType  # noqa: E402


def _sdef(key, st, **kw):
    return SettingDef(key=key, label="x", setting_type=st, page="p", group="g", **kw)


def test_lua_path_for():
    assert lf.lua_path_for(_sdef("decoration:rounding", SettingType.INT)) == "decoration.rounding"
    assert lf.lua_path_for(_sdef("decoration:shadow:range", SettingType.INT)) == "decoration.shadow.range"
    assert lf.lua_path_for(_sdef("input:touchpad:tap-to-click", SettingType.BOOL)) == "input.touchpad.tap_to_click"
    assert lf.lua_path_for(_sdef("general:col.active_border", SettingType.COLOR)) == "general.col.active_border"


def test_lua_string_escaping():
    assert lf.lua_string("hi") == '"hi"'
    assert lf.lua_string('a"b') == '"a\\"b"'
    assert lf.lua_string("a\\b") == '"a\\\\b"'


def test_lua_value_bool_int_float():
    assert lf.lua_value(_sdef("decoration:blur:enabled", SettingType.BOOL), True) == "true"
    assert lf.lua_value(_sdef("decoration:blur:enabled", SettingType.BOOL), False) == "false"
    assert lf.lua_value(_sdef("general:gaps_in", SettingType.INT), 6) == "6"
    assert lf.lua_value(_sdef("master:mfact", SettingType.FLOAT), 0.55) == "0.55"
    assert lf.lua_value(_sdef("decoration:active_opacity", SettingType.FLOAT), 1.0) == "1"


def test_lua_value_color_plain_vs_gradient():
    # shadow color -> plain rgba string
    s = _sdef("decoration:shadow:color", SettingType.COLOR)
    assert lf.lua_value(s, "1a1a1aee") == '"rgba(1a1a1aee)"'
    # border color -> gradient table
    g = _sdef("general:col.active_border", SettingType.COLOR)
    assert lf.lua_value(g, "33ccffee") == '{ colors = { "rgba(33ccffee)" } }'


def test_lua_value_enum_numeric_vs_string():
    follow = _sdef("input:follow_mouse", SettingType.ENUM,
                   enum_options=("Disabled", "Always", "Loose", "Strict"),
                   enum_values=("0", "1", "2", "3"))
    assert lf.lua_value(follow, "Loose") == "2"  # numeric enum -> bare number
    layout = _sdef("general:layout", SettingType.ENUM,
                   enum_options=("dwindle", "master", "monocle", "scrolling"))
    assert lf.lua_value(layout, "master") == '"master"'  # string enum -> quoted


def test_lua_value_string():
    assert lf.lua_value(_sdef("input:kb_layout", SettingType.STRING), "us") == '"us"'


def test_nest_paths():
    nested = lf.nest_paths({
        "decoration.rounding": "8",
        "decoration.shadow.range": "12",
        "decoration.shadow.enabled": "true",
        "general.gaps_in": "6",
    })
    assert nested == {
        "decoration": {"rounding": "8", "shadow": {"range": "12", "enabled": "true"}},
        "general": {"gaps_in": "6"},
    }


def test_build_hl_config_call_roundtrip_shape():
    call = lf.build_hl_config_call({
        "decoration.rounding": "8",
        "decoration.shadow.range": "12",
        "general.col.active_border": '{ colors = { "rgba(33ccffee)" } }',
    })
    assert call.startswith("hl.config({")
    assert call.rstrip().endswith("})")
    assert "rounding = 8," in call
    assert "shadow = {" in call
    assert "range = 12," in call
    assert '["col.active_border"] = { colors' not in call  # col.active_border is a real nested key? no:
    # general.col.active_border -> general -> col -> active_border ; "col" and "active_border" are valid idents
    assert "col = {" in call
    assert "active_border = { colors = {" in call


def test_build_empty():
    assert lf.build_hl_config_call({}) == "hl.config({})"


def test_eval_snippet_single_key_single_line():
    s = _sdef("decoration:shadow:range", SettingType.INT)
    snip = lf.eval_snippet_for(s, 12)
    assert snip == "hl.config({ decoration = { shadow = { range = 12 } } })"
    assert "\n" not in snip
    # gradient
    g = _sdef("general:col.active_border", SettingType.COLOR)
    snip2 = lf.eval_snippet_for(g, "33ccffee")
    assert snip2 == 'hl.config({ general = { col = { active_border = { colors = { "rgba(33ccffee)" } } } } })'


def test_bracket_key_only_when_needed():
    # a key with a dot would need brackets; normal idents don't
    nested = {"misc": {"col.splash": '"rgba(ffffffff)"'}}
    out = lf.render_table(nested)
    assert '["col.splash"]' in out
    assert "misc = {" in out


def test_generated_config_is_valid_lua():
    """The full hyprgui.lua we'd emit must at least parse under `lua`/`luac`.

    Builds a call from every current registry setting at its default and checks
    `luac -p` (syntax-only). Skips if no Lua interpreter is installed.
    """
    import shutil
    import subprocess
    import tempfile

    from hyprgui.settings_registry import SETTINGS

    luac = shutil.which("luac") or shutil.which("luac5.5") or shutil.which("luac5.4")
    lua_bin = shutil.which("lua") or shutil.which("luajit")
    if not luac and not lua_bin:
        print("SKIP test_generated_config_is_valid_lua: no lua/luac found")
        return

    literals = {}
    for s in SETTINGS:
        if s.default is None:
            continue
        literals[lf.lua_path_for(s)] = lf.lua_value(s, s.default)
    src = "-- generated by hyprgui (test)\nhl = hl or setmetatable({}, {__index=function() return function() end end})\n" \
          + lf.build_hl_config_call(literals) + "\n"

    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        if luac:
            cmd = [luac, "-p", path]
        else:
            # `lua` can't syntax-only-check, but `loadfile` works as a parse check.
            assert lua_bin is not None
            cmd = [lua_bin, "-e", f'local f,e=loadfile("{path}"); if not f then io.stderr:write(e); os.exit(1) end']
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, f"generated Lua failed to parse:\n{r.stderr}\n---\n{src}"
    finally:
        Path(path).unlink(missing_ok=True)


# --- run all when executed directly ---------------------------------------

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
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
