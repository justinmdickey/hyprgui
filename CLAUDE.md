# Hyprgui

GTK4 + libadwaita settings app for Hyprland, written in Python with PyGObject.

## Running

```bash
python -m hyprgui
```

## Project Structure

```
hyprgui/
├── __main__.py           # Entry point for `python -m hyprgui`
├── main.py               # Adw.Application, first-run linking dialog (mode-aware)
├── window.py             # AdwPreferencesWindow, dynamic UI from registry
├── settings_registry.py  # Declarative SettingDef list (extensibility core)
├── hyprctl.py            # Read/write via hyprctl subprocess (mode-aware apply_setting)
├── persistence.py        # Façade: routes to config_manager or lua_writer by mode
├── config_mode.py        # detect_mode() — Lua vs legacy hyprlang
├── config_manager.py     # Legacy hyprlang writer (hyprgui.conf + source line)
├── lua_writer.py         # Lua-mode writer (hyprgui.lua + .hyprgui-state.json sidecar)
├── lua_format.py         # Value → Lua literal, key → dotted-Lua-path
├── dbus_helpers.py       # Shared Gio.DBusProxy utilities
├── pages/
│   ├── base.py           # BasePage ABC (build/activate/deactivate/dispose)
│   ├── wifi.py           # NetworkManager D-Bus
│   ├── bluetooth.py      # BlueZ D-Bus
│   ├── sound.py          # wpctl/pactl subprocess
│   └── display.py        # hyprctl monitors (uses persistence.upsert_monitors)
└── widgets/
    └── color_row.py      # AdwActionRow + GtkColorDialogButton helper
```

Tests live in `tests/` (offline unit tests + a `verify_lua_runtime.sh` checklist
to run against a live Hyprland). Long-form design notes: `docs/lua-migration-plan.md`.

## Architecture

- **Registry-driven**: all settings defined as `SettingDef` entries in `settings_registry.py`. UI, live preview, and config persistence are all derived from this list.
- **Adding a setting**: append one `SettingDef` to `SETTINGS` — everything else is automatic.
- **Adding a page**: add entry to `PAGE_TITLES`/`PAGE_ICONS` dicts, reference the new page name in settings.
- **System pages**: Wi-Fi, Bluetooth, Sound, Display are `BasePage` subclasses in `pages/`, using D-Bus (`dbus_helpers.py`) or subprocess backends. They work independently of Hyprland.

## Widget Mapping

| SettingType | Widget |
|-------------|--------|
| BOOL        | `Adw.SwitchRow` |
| INT         | `Adw.SpinRow` (digits=0) |
| FLOAT       | `Adw.SpinRow` (digits=2) |
| COLOR       | `Adw.ActionRow` + `Gtk.ColorDialogButton` suffix |
| STRING      | `Adw.EntryRow` |
| ENUM        | `Adw.ComboRow` + `Gtk.StringList` |

## Data Flow

1. **Startup**: iterate `SETTINGS`, call `hyprctl -j getoption` for each, populate widgets. `getoption` works identically under hyprlang and Lua (0.55+).
2. **Widget change**: `hyprctl.apply_setting(sdef, value)` for instant live preview. Mode-aware:
   - **hyprlang**: `hyprctl keyword <key> <value>`.
   - **Lua (0.55+)**: `hyprctl eval 'hl.config({...})'` — `keyword` is rejected by the Lua parser. `hl.config` merges, so one-key updates leave everything else alone.
3. **Save**: `persistence.write(...)` routes to the right backend:
   - **hyprlang**: `~/.config/hypr/hyprgui.conf` in Hyprland section syntax.
   - **Lua**: `~/.config/hypr/hyprgui.lua` (one big `hl.config({...})` + `hl.monitor(...)` + `hl.env(...)`), plus `.hyprgui-state.json` sidecar for recovering managed keys without parsing Lua back.
   Atomic write via tmp+rename in both modes.

## Config Strategy (mode-aware)

`config_mode.detect_mode()` returns `LUA` iff `~/.config/hypr/hyprland.lua` exists, else `HYPRLANG`. All persistence/linking decisions branch off this.

- **Lua mode**: app manages `hyprgui.lua`, linked from `hyprland.lua` via `dofile(os.getenv("HOME") .. "/.config/hypr/hyprgui.lua")`. The link is appended on first-run after confirmation.
- **hyprlang mode**: app manages `hyprgui.conf`, sourced from `hyprland.conf` via `source = ~/.config/hypr/hyprgui.conf`. Existing behavior preserved.

After 0.55, hyprlang is deprecated and slated for removal in ~2 more Hyprland releases. The Lua path is the long-term home; the hyprlang path stays until Hyprland drops it.

## Hyprctl Read Format

- Most options: `{"int": ...}` / `{"float": ...}` / `{"str": ...}` / `{"bool": ...}` — unchanged between parsers.
- **Gradient colour keys** (`general.col.*`, `group.groupbar.col.*`, ...) under the Lua parser return `{"gradient": "AARRGGBB [AARRGGBB...] [Ndeg]"}` instead of the old decimal int. `hyprctl.parse_option_value` handles both shapes; internal representation is still `RRGGBBAA` hex.
- Plain colour keys (`decoration.shadow.color`, `misc.background_color`, ...) still return decimal int.

## Current Settings (66 total)

Decoration (24), Gaps & Borders (10), Animations (1), Input (9), Layouts (10), Miscellaneous (12). (`dwindle:pseudotile` was removed — it's a window state, not a config option; `misc:vfr` was renamed to `debug:vfr` to match Hyprland's current schema.)

## System Pages

Wi-Fi (NetworkManager D-Bus), Bluetooth (BlueZ D-Bus), Sound (wpctl/pactl subprocess), Display (hyprctl monitors).
