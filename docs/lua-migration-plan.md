# Hyprland Lua config support — plan

Status: **in progress** on branch `feature/lua-config-support`.

## Background

Hyprland 0.55 (May 2026) replaces the hyprlang config (`hyprland.conf`) with a Lua
config (`hyprland.lua`). hyprlang is deprecated and will be removed in roughly two
more releases. Hyprgui must work in both modes during the transition, then default
to Lua.

### Confirmed facts (0.55, verified on Justin's machine)

| Thing | Behavior under a Lua config |
|---|---|
| `hyprctl -j getoption decoration:rounding` | ✅ works, same JSON shape — `{"option": ..., "int": 18, "set": true}` |
| `hyprctl keyword decoration:rounding 10` | ❌ `"keyword can't work with non-legacy parsers. Use eval."` |
| `hyprctl dispatch <legacy syntax>` | ❌ rejected — needs `hyprctl dispatch 'hl.dsp.*()'` |
| `hyprctl reload` | ✅ still the manual-reload command |
| `hl.config({...})` called multiple times | ✅ **merges** — confirmed by Justin's split config (hyprland.lua + decoration.lua + colors.lua all stack) |
| `~/.config/hypr/hyprland.lua` exists | Hyprland uses Lua mode; ignores `hyprland.conf` for that session |
| no `hyprland.lua` | falls back to `hyprland.conf` (legacy) |

### Authoritative schema source

`/usr/share/hypr/stubs/hl.meta.lua` (ships with Hyprland) — the LSP type stub. It
contains:
- `HL.ConfigKey` alias: every valid config key in dotted form (`decoration.shadow.range`, `general.col.active_border`, …) — 341 keys.
- `HL.ConfigValueTypes`: the type of each key (`integer|boolean`, `number|boolean`, `string`, `HL.Gradient`, `HL.Vec2Like`, `HL.CssGap`).
- `HL.API` / `HL.MonitorSpec` / `HL.DspNamespace` etc.

The `meta/` dir in the Hyprland repo has a bindings generator; the stub is generated
from the same metadata, so it's the source of truth.

### Registry → Lua key audit (65/67 map cleanly)

`section:key` → `section.key`, `section:sub:key` → `section.sub.key`, `-` → `_`.
Two exceptions:

- `dwindle:pseudotile` — **not a config key** in the Lua schema (never really was;
  it's a window prop / dispatcher). Pre-existing registry bug. Drop or replace it.
- `misc:vfr` — moved to `debug.vfr`. Change the registry key to `debug:vfr`
  regardless of Lua. (Justin's own config already uses `debug = { vfr = true }`.)

Also: `input:touchpad:tap-to-click` (hyphen) → Lua key `input.touchpad.tap_to_click`
(underscore). The hyphen form may still work as a hyprctl alias; the Lua table key
must be `tap_to_click`.

## Design

### Mode detection — `hyprgui/config_mode.py` (new)

```python
def detect_mode() -> Literal["lua", "hyprlang"]:
    return "lua" if (HYPR_DIR / "hyprland.lua").exists() else "hyprlang"
```

Single branch point. Could also gate on `hyprctl version >= 0.55` to decide whether
Lua is even available, but presence of `hyprland.lua` is the practical signal.

### Runtime layer — `hyprgui/hyprctl.py`

- `getoption(key)` / `parse_option_value(...)` — **unchanged**. Works in both modes.
  Key syntax stays `section:key` / `section:sub:key` (colon form, as today).
- New `apply_setting(sdef, value)` replaces direct `set_keyword` calls:
  - hyprlang mode → `hyprctl keyword <key> <value>` (today's behavior).
  - lua mode → `hyprctl eval '<lua>'` where `<lua>` is
    `hl.config({ <nested table for this one key> })`. Needs the registry→Lua-path map.
    Example: `decoration:shadow:range` → `hl.config({ decoration = { shadow = { range = 12 } } })`.
- `reload_config()`, `set_cursor()` (`hyprctl setcursor`) — **unchanged** (cursor is
  not a parser thing; verify on 0.55 anyway).
- Display page monitor logic — audit for any `keyword`/`dispatch` use; route through
  `apply_setting` / a lua-aware monitor setter (`hyprctl eval 'hl.monitor({...})'`).

### Lua value formatting — `hyprgui/lua_format.py` (new), driven by stub types

| Stub type | hyprgui SettingType | Lua literal |
|---|---|---|
| `boolean` | BOOL | `true` / `false` |
| `integer\|boolean` | INT | `12` |
| `number\|boolean` | FLOAT | `0.55` (trim trailing zeros) |
| `string` | STRING / ENUM(no values) | `"value"` (escape quotes/backslashes) |
| `string` (ENUM with values) | ENUM | the mapped value as a `"string"` |
| `HL.Gradient` (= `string\|{colors,angle?}`) | COLOR (border/groupbar `col.*`) | solid: `"rgba(RRGGBBAA)"`; gradient: `{ colors = {"rgba(...)"}, angle = N }` |
| `string` (shadow/glow `color`) | COLOR | `"rgba(RRGGBBAA)"` (these are plain colors, not gradients) |
| `HL.Vec2Like` | (n/a in registry yet) | `"0 4"` string form |
| `HL.CssGap` | (n/a yet) | integer |

Note `decoration.shadow.color` etc. are plain `string` colors, NOT gradients —
`rgba(...)` string works for all colors. Only `*.col.*` keys are gradients.

### Persistence layer

- hyprlang mode → existing `config_manager.py` writing `hyprgui.conf` — **untouched**.
- lua mode → new `hyprgui/lua_writer.py` writing `~/.config/hypr/hyprgui.lua`:
  - One `hl.config({ ...nested tables built from managed SettingDefs... })`.
  - `hl.monitor({...})` calls for Display-page monitors.
  - `hl.env("HYPRCURSOR_THEME", ...)` / `hl.env("XCURSOR_THEME", ...)` for cursor.
  - Atomic tmp+rename, like today.
- **State sidecar (recommended): `~/.config/hypr/.hyprgui-state.json`** — the source
  of truth for "which keys hyprgui manages + their values". Generate the `.lua` (or
  `.conf`) from it on every save. Avoids parsing Lua to recover state on next launch.
  Adopt for hyprlang mode too eventually for consistency; not required for v1.
- First-run / linking dialog:
  - lua mode → offer to append `dofile(os.getenv("HOME") .. "/.config/hypr/hyprgui.lua")`
    to the end of `hyprland.lua`, and create a stub `hyprgui.lua` with `hl.config({})`.
    (`dofile` with an absolute path is more robust than `require` — `require` needs the
    hypr dir on `package.path`, which it normally is, but `dofile` always works.)
  - hyprlang mode → existing `source = ...` behavior.
  - both files exist → prefer `.lua` (matches what Hyprland loads when started with
    Lua), surface a warning that the legacy config is being ignored.
- `is_source_line_present` / `append_source_line` / `create_empty_conf` /
  `reset_hyprgui_conf` all gain a mode branch (or dispatch to lua_writer equivalents).

### Settings registry changes

- Add a `lua_path` field to `SettingDef`? **No** — derive it (`key.replace(':','.').replace('-','_')`)
  with a small override dict for exceptions. Keeps `SETTINGS` clean.
- Fix `misc:vfr` → `debug:vfr`.
- Remove or replace `dwindle:pseudotile` (it isn't a config option in either parser
  cleanly; check what `getoption dwindle:pseudotile` returns today).
- Optionally: a build-time test that asserts every registry key resolves to a
  `HL.ConfigKey` in the stub (skipped if stub absent). See `tests/test_lua_keys.py`.

## Open questions — RESOLVED (2026-05-11, Hyprland 0.55.0)

All settled by `tests/verify_lua_runtime.sh` run on the XPS. Pasted output in commit
log; summary here:

1. **Merge vs replace** — `hl.config` **MERGES**. Setting `decoration.rounding=7` left
   `decoration.blur.size=6` untouched. ⇒ push single-key updates via `eval` for live
   preview; no need to send the whole config.
2. **`hl.dispatch` wrapper** — NOT needed for `hl.config` calls via `eval`. Bare
   `hyprctl eval 'hl.config({...})'` works (`ok`).
3. **Nested vs bracket-dotted table form** — both accepted by `hl.config`. We use
   nested (matches the example file).
4. **`getoption` IPC key spelling** — always `section:sub:key` (colon all the way).
   `decoration:shadow_range` returns "no such option". So registry keys stay as-is
   for the read path.
5. **Gradient (`*.col.*`) round-trip** — **breaking change**: `getoption` now returns
   `{"option": ..., "gradient": "AARRGGBB Ndeg", "set": true}` for gradient keys,
   NOT the old `{"int": <decimal>}`. ``hyprctl.parse_option_value`` for COLOR must
   handle a `gradient` field (parse the first colour stop's `AARRGGBB`, convert to
   our internal `RRGGBBAA`). Plain-colour keys (shadow.color etc.) need re-verifying
   but likely still come back as `int`.
6. **`setcursor` under Lua** — unverified live; deferred. Will smoke-test by running
   the app.
7. **`dofile`+`reload` re-apply** — unverified; the next phase (linking) will smoke
   it. `reload` re-runs the whole `hyprland.lua` from scratch, so it must.

(Items 6/7 unchecked because they require touching the user's running session.)

### One newly-discovered subtlety: gradient read format

```
$ hyprctl -j getoption general:col.active_border
{"option": "general:col.active_border", "gradient": "ee33ccff 45deg", "set": true}
```

Format is `"<AARRGGBB1> [<AARRGGBB2>...] [Ndeg]"` — space-separated colour stops
followed by an optional angle. hyprgui currently exposes single-colour borders
only, so we parse the first stop, swap AARRGGBB → RRGGBBAA. Keep the angle/extra
stops for future multi-stop UI; round-trip them via the state sidecar.

## Work breakdown / sequencing

1. **[done]** Branch, gather stub + example, audit registry keys, write this plan.
2. `tests/verify_lua_runtime.sh` — the live checklist above (run by Justin on XPS).
3. `tests/test_lua_keys.py` — offline: assert every registry key maps to a stub
   `HL.ConfigKey`; assert SettingType is compatible with the stub's value type.
4. `config_mode.py` — `detect_mode()`.
5. `lua_format.py` — value → Lua literal, type-aware (uses stub types).
6. `lua_writer.py` — `write_hyprgui_lua(...)` + state sidecar read/write.
7. `hyprctl.py` — `apply_setting()` abstraction (keyword | eval); update callers in
   `window.py`.
8. First-run dialog branch in `main.py` + linking helpers in (renamed?) config layer.
9. Registry fixes (`misc:vfr` → `debug:vfr`, drop `dwindle:pseudotile`).
10. Display page audit for keyword/dispatch usage.
11. Docs: update `CLAUDE.md` (Config Strategy, Data Flow, file names), `README`.
12. Manual end-to-end test in both modes on the XPS.

## Risk notes

- Lowest risk: reads (`getoption`) confirmed stable — keep as-is.
- Medium: the `apply_setting` abstraction + mode branching — mechanical.
- The `eval` merge-vs-replace question (item 1) is the one thing that could force a
  redesign of live preview (e.g. send the full managed config on every change, or
  accept that live preview needs a `reload`). Justin's split config makes "merge"
  very likely.
- Keep the hyprlang path 100% intact; only *add* the Lua path behind `detect_mode()`.
