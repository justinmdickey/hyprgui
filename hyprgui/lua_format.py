"""Render hyprgui setting values as Lua literals for the new Hyprland config.

Used by:
- ``hyprctl.py`` to build ``hyprctl eval 'hl.config({...})'`` for live preview
  under a Lua config (since ``hyprctl keyword`` is rejected by the Lua parser).
- ``lua_writer.py`` to generate ``~/.config/hypr/hyprgui.lua``.

Everything here is pure and offline-testable. See ``tests/test_lua_format.py``.
"""

from __future__ import annotations

from hyprgui.settings_registry import SettingDef, SettingType

# Registry keys whose Lua path isn't just ``key.replace(":", ".").replace("-", "_")``.
# (Currently empty — ``misc:vfr`` should be fixed to ``debug:vfr`` in the registry,
# and ``dwindle:pseudotile`` removed; both tracked in docs/lua-migration-plan.md.)
_LUA_PATH_OVERRIDES: dict[str, str] = {}

# A color setting is a *gradient* (accepts ``{colors=..., angle=...}``) iff its
# parent table is ``col`` — in the Lua schema those are the border-colour keys
# (``general.col.active_border``, ``group.groupbar.col.active``, ...). Plain-colour
# keys (shadow/glow ``color``, ``misc.background_color``, ...) take a ``"rgba(...)"``
# string. The whole hl.config gradient form also accepts a bare string, so emitting
# a string for a gradient key would work too — but the table form is the documented one.
def _is_gradient(lua_path: str) -> bool:
    parts = lua_path.split(".")
    return len(parts) >= 2 and parts[-2] == "col"


def lua_path_for(sdef: SettingDef) -> str:
    """Return the dotted Lua config path for a registry setting.

    e.g. ``decoration:shadow:range`` -> ``decoration.shadow.range``,
    ``input:touchpad:tap-to-click`` -> ``input.touchpad.tap_to_click``.
    """
    if sdef.key in _LUA_PATH_OVERRIDES:
        return _LUA_PATH_OVERRIDES[sdef.key]
    return sdef.key.replace(":", ".").replace("-", "_")


# --- Lua literal rendering -------------------------------------------------

def lua_string(s: str) -> str:
    """Quote a Python string as a Lua string literal (double-quoted)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_number(value: float, *, is_float: bool) -> str:
    if is_float:
        # trim trailing zeros: 0.5500 -> 0.55, 1.0 -> 1
        return f"{float(value):.6f}".rstrip("0").rstrip(".")
    return str(int(value))


def lua_color(rrggbbaa: str) -> str:
    """A plain color value: ``"rgba(RRGGBBAA)"``.

    hyprgui stores colors internally as 8-hex-digit ``RRGGBBAA`` strings.
    """
    return lua_string(f"rgba({rrggbbaa})")


def lua_gradient(rrggbbaa: str) -> str:
    """A gradient value with a single colour stop: ``{ colors = {"rgba(...)"} }``.

    hyprgui's UI currently only exposes single-colour borders, so we emit a
    one-element ``colors`` table and no ``angle`` (Hyprland defaults it).
    """
    return f"{{ colors = {{ {lua_color(rrggbbaa)} }} }}"


def lua_value(sdef: SettingDef, value: object) -> str:
    """Render ``value`` (a hyprgui-internal value) as a Lua literal for its setting."""
    st = sdef.setting_type
    if st == SettingType.BOOL:
        return "true" if value else "false"
    if st == SettingType.INT:
        return lua_number(value, is_float=False)  # type: ignore[arg-type]
    if st == SettingType.FLOAT:
        return lua_number(value, is_float=True)  # type: ignore[arg-type]
    if st == SettingType.COLOR:
        rrggbbaa = str(value)
        return lua_gradient(rrggbbaa) if _is_gradient(lua_path_for(sdef)) else lua_color(rrggbbaa)
    if st == SettingType.ENUM:
        # Map the display label back to the underlying hyprctl/Lua value.
        label = str(value)
        if sdef.enum_values and label in sdef.enum_options:
            raw = sdef.enum_values[sdef.enum_options.index(label)]
        elif sdef.enum_options and label in sdef.enum_options:
            raw = label  # enum without explicit values: label *is* the value
        else:
            raw = label
        # Numeric enums (e.g. follow_mouse "0".."3") -> bare number; string enums -> quoted.
        if raw.lstrip("-").isdigit():
            return raw
        return lua_string(raw)
    # STRING
    return lua_string(str(value))


# --- assembling nested tables ---------------------------------------------

def nest_paths(items: dict[str, str]) -> dict:
    """Turn ``{"decoration.shadow.range": "12", "decoration.rounding": "8"}`` into
    a nested dict ``{"decoration": {"shadow": {"range": "12"}, "rounding": "8"}}``.

    Leaf values are already-rendered Lua literal *strings*.
    """
    root: dict = {}
    for dotted, literal in items.items():
        parts = dotted.split(".")
        node = root
        for seg in parts[:-1]:
            node = node.setdefault(seg, {})
            if not isinstance(node, dict):  # collision — shouldn't happen with valid keys
                raise ValueError(f"path collision at {seg!r} for {dotted!r}")
        node[parts[-1]] = literal
    return root


def _needs_bracket_key(key: str) -> bool:
    # Lua identifier rule: [A-Za-z_][A-Za-z0-9_]*
    if not key or (not key[0].isalpha() and key[0] != "_"):
        return True
    return not all(c.isalnum() or c == "_" for c in key)


def render_table(node: dict, indent: int = 0) -> str:
    """Render a nested dict (leaves = Lua literal strings) as a pretty Lua table body.

    Returns the text *between* the outer braces, e.g.::

        decoration = {
          rounding = 8,
          shadow = {
            range = 12,
          },
        },
    """
    pad = "  " * (indent + 1)
    lines: list[str] = []
    for key in node:  # preserve insertion order
        val = node[key]
        k = f"[{lua_string(key)}]" if _needs_bracket_key(key) else key
        if isinstance(val, dict):
            inner = render_table(val, indent + 1)
            lines.append(f"{pad}{k} = {{\n{inner}{pad}}},")
        else:
            lines.append(f"{pad}{k} = {val},")
    return "\n".join(lines) + ("\n" if lines else "")


def build_hl_config_call(value_literals: dict[str, str]) -> str:
    """Build a complete ``hl.config({ ... })`` call from ``{lua_path: lua_literal}``.

    Used both for the persisted ``hyprgui.lua`` and (single-key) for ``hyprctl eval``.
    """
    nested = nest_paths(value_literals)
    body = render_table(nested, indent=0)
    if not body.strip():
        return "hl.config({})"
    return f"hl.config({{\n{body}}})"


def eval_snippet_for(sdef: SettingDef, value: object) -> str:
    """One-key ``hl.config`` call suitable for ``hyprctl eval '<this>'`` (single line)."""
    nested = nest_paths({lua_path_for(sdef): lua_value(sdef, value)})

    def _flat(node: dict) -> str:
        parts = []
        for k in node:
            v = node[k]
            kk = f"[{lua_string(k)}]" if _needs_bracket_key(k) else k
            parts.append(f"{kk} = {{ {_flat(v)} }}" if isinstance(v, dict) else f"{kk} = {v}")
        return ", ".join(parts)

    return f"hl.config({{ {_flat(nested)} }})"
