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
├── main.py               # Adw.Application, first-run source-line dialog
├── window.py             # AdwPreferencesWindow, dynamic UI from registry
├── settings_registry.py  # Declarative SettingDef list (extensibility core)
├── hyprctl.py            # Read/write via hyprctl subprocess
├── config_manager.py     # Write hyprgui.conf, manage source line
└── widgets/
    └── color_row.py      # AdwActionRow + GtkColorDialogButton helper
```

## Architecture

- **Registry-driven**: all settings defined as `SettingDef` entries in `settings_registry.py`. UI, live preview, and config persistence are all derived from this list.
- **Adding a setting**: append one `SettingDef` to `SETTINGS` — everything else is automatic.
- **Adding a page**: add entry to `PAGE_TITLES`/`PAGE_ICONS` dicts, reference the new page name in settings.

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

1. **Startup**: iterate `SETTINGS`, call `hyprctl -j getoption` for each, populate widgets
2. **Widget change**: `hyprctl keyword <key> <value>` for instant live preview
3. **Save**: serialize all UI values to `~/.config/hypr/hyprgui.conf` in Hyprland section syntax (atomic write via tmp+rename)

## Config Strategy

- App manages `~/.config/hypr/hyprgui.conf` (rewritten from scratch on save)
- Sourced last in `hyprland.conf` so our settings win
- First run: dialog asks to append `source = ~/.config/hypr/hyprgui.conf`, creates empty conf file, then `hyprctl reload`

## Hyprctl Color Format

- `getoption` returns colors as decimal int (AARRGGBB 32-bit) in the `"int"` field
- Config/keyword format: `rgba(RRGGBBAA)`
- Internal representation: `RRGGBBAA` hex string

## Current MVP Settings (22 total)

Decoration (blur, shadow, rounding, opacity, dim), Gaps & Borders (gaps_in/out, border_size, border colors, layout), Animations (enabled toggle), Miscellaneous (cursor zoom/hyprcursor, font_family, disable_logo, focus_on_activate).
