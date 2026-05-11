"""Offline checks: every registry SettingDef must map to a valid Hyprland Lua
config key, and its SettingType must be compatible with the key's value type.

Source of truth: /usr/share/hypr/stubs/hl.meta.lua (ships with Hyprland 0.55+).
If the stub isn't installed, these tests skip — they're a CI/dev aid, not a hard
runtime dependency.

Run with: python -m pytest tests/test_lua_keys.py -v
(or just: python tests/test_lua_keys.py)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Make `hyprgui` importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hyprgui.settings_registry import SETTINGS, SettingType  # noqa: E402

STUB_PATH = Path("/usr/share/hypr/stubs/hl.meta.lua")

# Registry-key overrides where simple ':'->'.', '-'->'_' isn't right.
# (Empty for now; `misc:vfr` should become `debug:vfr` in the registry itself,
# and `dwindle:pseudotile` should be removed — both tracked in the plan.)
KEY_OVERRIDES: dict[str, str] = {}

# Registry keys we knowingly haven't fixed yet — xfail, don't hard-fail.
# (Empty: ``misc:vfr`` was renamed to ``debug:vfr`` and ``dwindle:pseudotile`` was
#  removed in commit X. Repopulate here only if a new registry entry needs a
#  temporary waiver while a fix is in flight.)
KNOWN_BAD: set[str] = set()


def _lua_key(registry_key: str) -> str:
    if registry_key in KEY_OVERRIDES:
        return KEY_OVERRIDES[registry_key]
    return registry_key.replace(":", ".").replace("-", "_")


def _load_stub() -> tuple[set[str], dict[str, str]] | None:
    if not STUB_PATH.exists():
        return None
    text = STUB_PATH.read_text()

    # HL.ConfigKey alias block -> set of dotted keys
    m = re.search(r"---@alias HL\.ConfigKey(.*?)---@alias HL\.MonitorSelector", text, re.S)
    keys = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()

    # HL.ConfigValueTypes class -> {dotted key: lua type string}
    types: dict[str, str] = {}
    m2 = re.search(r"---@class HL\.ConfigValueTypes(.*?)local __HL_ConfigValueTypes", text, re.S)
    if m2:
        for line in m2.group(1).splitlines():
            fm = re.match(r"---@field \['([^']+)'\] (.+)$", line.strip())
            if fm:
                types[fm.group(1)] = fm.group(2).strip()
    return keys, types


# --- compatibility: SettingType vs stub lua type --------------------------

def _type_ok(st: SettingType, lt: str) -> bool:
    checks = {
        SettingType.BOOL: ("boolean",),
        SettingType.INT: ("integer", "HL.CssGap"),
        SettingType.FLOAT: ("number", "integer"),  # FLOAT widgets hold ints fine
        SettingType.STRING: ("string",),
        # numeric enums -> integer|boolean keys; string enums -> string keys
        SettingType.ENUM: ("string", "integer"),
        SettingType.COLOR: ("string", "HL.Gradient"),
    }
    return any(token in lt for token in checks.get(st, ()))


def main() -> int:
    loaded = _load_stub()
    if loaded is None:
        print(f"SKIP: {STUB_PATH} not found (Hyprland 0.55+ stubs not installed).")
        return 0
    lua_keys, lua_types = loaded
    print(f"Loaded {len(lua_keys)} config keys, {len(lua_types)} typed keys from stub.")

    bad_key: list[str] = []
    bad_type: list[str] = []
    for s in SETTINGS:
        lk = _lua_key(s.key)
        if lk not in lua_keys:
            (bad_key if s.key not in KNOWN_BAD else []).append(f"{s.key} -> {lk}")
            if s.key in KNOWN_BAD:
                print(f"  xfail (known): {s.key} -> {lk}  (not in stub)")
            continue
        lt = lua_types.get(lk, "")
        if lt and not _type_ok(s.setting_type, lt):
            msg = f"{s.key} ({s.setting_type.name}) vs lua type '{lt}'"
            (bad_type if s.key not in KNOWN_BAD else []).append(msg)

    if bad_key:
        print("\nFAIL — registry keys with no matching Lua config key:")
        for b in bad_key:
            print(f"  {b}")
    if bad_type:
        print("\nFAIL — SettingType incompatible with Lua key type:")
        for b in bad_type:
            print(f"  {b}")

    if bad_key or bad_type:
        return 1
    print(f"\nOK — all {len(SETTINGS)} settings map to valid Lua keys with compatible types"
          f" ({len(KNOWN_BAD)} known-bad keys excluded).")
    return 0


# pytest entry points
def test_registry_keys_map_to_lua_schema():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
