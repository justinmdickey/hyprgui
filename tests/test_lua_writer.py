"""End-to-end-ish tests for lua_writer: round-trip through state sidecar +
generated hyprgui.lua, and Lua-syntax validation of the output.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui import config_mode, lua_writer  # noqa: E402
from hyprgui.settings_registry import SETTINGS  # noqa: E402


def _redirect_hypr_dir(tmp_path: Path) -> None:
    """Point the module's path constants at a temp dir for isolation."""
    lua_writer.HYPR_DIR = tmp_path
    lua_writer.HYPRGUI_LUA = tmp_path / "hyprgui.lua"
    lua_writer.HYPRLAND_LUA = tmp_path / "hyprland.lua"
    lua_writer.STATE_FILE = tmp_path / ".hyprgui-state.json"
    config_mode.HYPR_DIR = tmp_path
    config_mode.HYPRGUI_LUA = tmp_path / "hyprgui.lua"
    config_mode.HYPRLAND_LUA = tmp_path / "hyprland.lua"


def _validate_lua(path: Path) -> tuple[bool, str]:
    luac = shutil.which("luac") or shutil.which("luac5.5") or shutil.which("luac5.4")
    lua_bin = shutil.which("lua") or shutil.which("luajit")
    if luac:
        r = subprocess.run([luac, "-p", str(path)], capture_output=True, text=True)
    elif lua_bin:
        # Stub `hl`/`os` so loadfile doesn't barf on undefined globals.
        r = subprocess.run(
            [lua_bin, "-e", f'local f,e=loadfile("{path}"); if not f then io.stderr:write(e); os.exit(1) end'],
            capture_output=True, text=True,
        )
    else:
        return True, "skipped (no lua)"
    return r.returncode == 0, r.stderr


def test_write_creates_file_and_state(tmp_path):
    _redirect_hypr_dir(tmp_path)
    values = {s.key: s.default for s in SETTINGS if s.default is not None}
    managed = set(values.keys())
    lua_writer.write_hyprgui_lua(values, managed_keys=managed, cursor_theme="Bibata", cursor_size=24,
                                 monitors={"DP-1": "DP-1,2560x1440@144,0x0,1"})

    out = (tmp_path / "hyprgui.lua").read_text()
    assert "hl.config({" in out
    assert "decoration = {" in out
    assert "rounding = 0," in out  # default
    assert 'hl.env("HYPRCURSOR_THEME", "Bibata")' in out
    assert 'hl.monitor({ output = "DP-1"' in out
    assert 'mode = "2560x1440@144"' in out

    ok, err = _validate_lua(tmp_path / "hyprgui.lua")
    assert ok, f"generated Lua failed to parse: {err}\n---\n{out}"

    state = lua_writer.load_state()
    assert "decoration:rounding" in state["managed_keys"]
    assert state["cursor_theme"] == "Bibata"
    assert state["cursor_size"] == 24
    assert state["monitors"] == {"DP-1": "DP-1,2560x1440@144,0x0,1"}


def test_state_roundtrip_via_upsert_monitors(tmp_path):
    _redirect_hypr_dir(tmp_path)
    # initial write with a couple of settings + one monitor
    lua_writer.write_hyprgui_lua(
        {"decoration:rounding": 12, "general:gaps_in": 8},
        managed_keys={"decoration:rounding", "general:gaps_in"},
        monitors={"DP-1": "DP-1,1920x1080,0x0,1"},
    )
    # add another monitor; managed settings + their values must survive
    lua_writer.upsert_managed_monitors({"HDMI-A-1": "HDMI-A-1,1280x720,1920x0,1"})

    state = lua_writer.load_state()
    assert set(state["managed_keys"]) == {"decoration:rounding", "general:gaps_in"}
    assert state["values"] == {"decoration:rounding": 12, "general:gaps_in": 8}
    assert set(state["monitors"]) == {"DP-1", "HDMI-A-1"}

    out = (tmp_path / "hyprgui.lua").read_text()
    assert "rounding = 12," in out
    assert "gaps_in = 8," in out
    assert "DP-1" in out and "HDMI-A-1" in out


def test_link_helpers(tmp_path):
    _redirect_hypr_dir(tmp_path)
    (tmp_path / "hyprland.lua").write_text('-- user config\nhl.config({ general = { gaps_in = 5 } })\n')
    assert not lua_writer.is_linked()
    lua_writer.append_link_line()
    assert lua_writer.is_linked()
    assert lua_writer.hyprgui_lua_exists()
    text = (tmp_path / "hyprland.lua").read_text()
    assert "dofile" in text and "hyprgui.lua" in text
    # appending again would duplicate the line — caller's job to check is_linked() first.


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
