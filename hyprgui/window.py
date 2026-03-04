"""Dynamic preferences window — generates UI from the settings registry."""

from __future__ import annotations

from collections import OrderedDict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from hyprgui import hyprctl
from hyprgui.settings_registry import (
    PAGE_ICONS,
    PAGE_TITLES,
    SETTINGS,
    SettingDef,
    SettingType,
)
from hyprgui.widgets.color_row import create_color_row, rgba_to_hex


class HyprguiWindow(Adw.PreferencesWindow):
    """Main preferences window — built dynamically from SETTINGS registry."""

    def __init__(self, app: Adw.Application, **kwargs):
        super().__init__(application=app, title="Hyprgui", **kwargs)
        self.set_default_size(680, 780)
        self.set_search_enabled(False)

        # Current UI values: key -> python value
        self._values: dict[str, object] = {}
        # Widget references for potential future use
        self._widgets: dict[str, Gtk.Widget] = {}
        self._dirty = False

        self._build_ui()
        self._load_current_values()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        """Build pages, groups, and rows from the settings registry."""
        # Collect settings by page, then group (preserving insertion order)
        pages: dict[str, OrderedDict[str, list[SettingDef]]] = OrderedDict()
        for sdef in SETTINGS:
            page_groups = pages.setdefault(sdef.page, OrderedDict())
            page_groups.setdefault(sdef.group, []).append(sdef)

        for page_key, groups in pages.items():
            page = Adw.PreferencesPage(
                title=PAGE_TITLES.get(page_key, page_key),
                icon_name=PAGE_ICONS.get(page_key, "preferences-system-symbolic"),
            )

            for group_title, sdefs in groups.items():
                group = Adw.PreferencesGroup(title=group_title)
                for sdef in sdefs:
                    row = self._create_row(sdef)
                    if row is not None:
                        group.add(row)
                page.add(group)

            self.add(page)

        # Save button in the header bar
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)

        header = self.get_content().get_first_child()
        if hasattr(self, "add_action"):
            pass
        # Add save button to the header via toolbar
        self._add_save_button(save_btn)

    def _add_save_button(self, button: Gtk.Button) -> None:
        """Add a save button to the window's header bar."""
        # AdwPreferencesWindow has a built-in header; we use a custom approach
        # by adding a toolbar-style button into the window's title bar
        bar = Adw.HeaderBar()
        bar.set_show_title(False)
        bar.pack_end(button)

        # Insert at top of the window content
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(bar)

        # We need to reparent the content. Adw.PreferencesWindow doesn't
        # expose a clean way to add header bar buttons, so we use the
        # set_content approach via the built-in toolbar.
        # Actually, AdwPreferencesWindow already has a header bar.
        # Let's just use a floating action approach with a toast overlay.
        # Simpler: use the window's built-in header bar end widget.

        # AdwPreferencesWindow doesn't expose its header bar directly,
        # but we can walk the widget tree to find it.
        self._save_button = button
        self._inject_header_button(button)

    def _inject_header_button(self, button: Gtk.Button) -> None:
        """Walk widget tree to find the header bar and inject our button."""
        def _find_header(widget):
            if isinstance(widget, Adw.HeaderBar):
                return widget
            child = widget.get_first_child() if hasattr(widget, "get_first_child") else None
            while child:
                result = _find_header(child)
                if result:
                    return result
                child = child.get_next_sibling()
            return None

        # Defer to after the window is mapped
        def _on_map(_widget):
            hb = _find_header(self)
            if hb:
                hb.pack_end(button)
            self.disconnect(handler_id)

        handler_id = self.connect("map", _on_map)

    # -- Row factory --------------------------------------------------------

    def _create_row(self, sdef: SettingDef) -> Gtk.Widget | None:
        """Create the appropriate widget row for a SettingDef."""
        if sdef.setting_type == SettingType.BOOL:
            return self._make_switch_row(sdef)
        if sdef.setting_type == SettingType.INT:
            return self._make_spin_row(sdef, digits=0)
        if sdef.setting_type == SettingType.FLOAT:
            return self._make_spin_row(sdef, digits=2)
        if sdef.setting_type == SettingType.COLOR:
            return self._make_color_row(sdef)
        if sdef.setting_type == SettingType.STRING:
            return self._make_entry_row(sdef)
        if sdef.setting_type == SettingType.ENUM:
            return self._make_combo_row(sdef)
        return None

    def _make_switch_row(self, sdef: SettingDef) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=sdef.label)
        self._values[sdef.key] = sdef.default
        self._widgets[sdef.key] = row

        def _on_notify(row, _pspec):
            val = row.get_active()
            self._values[sdef.key] = val
            self._apply_live(sdef, val)

        row.connect("notify::active", _on_notify)
        return row

    def _make_spin_row(self, sdef: SettingDef, digits: int) -> Adw.SpinRow:
        adj = Gtk.Adjustment(
            value=float(sdef.default or 0),
            lower=sdef.min_val,
            upper=sdef.max_val,
            step_increment=sdef.step,
            page_increment=sdef.step * 10,
        )
        row = Adw.SpinRow(title=sdef.label, adjustment=adj, digits=digits)
        self._values[sdef.key] = sdef.default
        self._widgets[sdef.key] = row

        def _on_notify(row, _pspec):
            val = row.get_value()
            if digits == 0:
                val = int(val)
            self._values[sdef.key] = val
            self._apply_live(sdef, val)

        row.connect("notify::value", _on_notify)
        return row

    def _make_color_row(self, sdef: SettingDef) -> Adw.ActionRow:
        initial = str(sdef.default or "ffffffff")

        def _on_change(hex_str: str):
            self._values[sdef.key] = hex_str
            self._apply_live(sdef, hex_str)

        row, button = create_color_row(sdef.label, initial, _on_change)
        self._values[sdef.key] = initial
        self._widgets[sdef.key] = button
        return row

    def _make_entry_row(self, sdef: SettingDef) -> Adw.EntryRow:
        row = Adw.EntryRow(title=sdef.label)
        row.set_text(str(sdef.default or ""))
        self._values[sdef.key] = sdef.default
        self._widgets[sdef.key] = row

        def _on_changed(row):
            val = row.get_text()
            self._values[sdef.key] = val
            self._apply_live(sdef, val)

        row.connect("changed", _on_changed)
        return row

    def _make_combo_row(self, sdef: SettingDef) -> Adw.ComboRow:
        row = Adw.ComboRow(title=sdef.label)
        model = Gtk.StringList()
        for opt in sdef.enum_options:
            model.append(opt)
        row.set_model(model)
        self._values[sdef.key] = sdef.default
        self._widgets[sdef.key] = row

        def _on_notify(row, _pspec):
            idx = row.get_selected()
            if 0 <= idx < len(sdef.enum_options):
                val = sdef.enum_options[idx]
                self._values[sdef.key] = val
                self._apply_live(sdef, val)

        row.connect("notify::selected", _on_notify)
        return row

    # -- Load current values from Hyprland ----------------------------------

    def _load_current_values(self) -> None:
        """Read current values from hyprctl and update widgets."""
        for sdef in SETTINGS:
            data = hyprctl.getoption(sdef.key)
            value = hyprctl.parse_option_value(sdef, data)
            self._values[sdef.key] = value
            self._set_widget_value(sdef, value)

    def _set_widget_value(self, sdef: SettingDef, value: object) -> None:
        """Set a widget's displayed value without triggering change callbacks."""
        widget = self._widgets.get(sdef.key)
        if widget is None:
            return

        if sdef.setting_type == SettingType.BOOL:
            widget.set_active(bool(value))

        elif sdef.setting_type in (SettingType.INT, SettingType.FLOAT):
            widget.set_value(float(value))

        elif sdef.setting_type == SettingType.COLOR:
            from hyprgui.widgets.color_row import hex_to_rgba
            widget.set_rgba(hex_to_rgba(str(value)))

        elif sdef.setting_type == SettingType.STRING:
            widget.set_text(str(value))

        elif sdef.setting_type == SettingType.ENUM:
            try:
                idx = sdef.enum_options.index(str(value))
                widget.set_selected(idx)
            except ValueError:
                pass

    # -- Live preview -------------------------------------------------------

    def _apply_live(self, sdef: SettingDef, value: object) -> None:
        """Send the value to Hyprland immediately for live preview."""
        self._dirty = True
        formatted = hyprctl.format_value(sdef, value)
        hyprctl.set_keyword(sdef.key, formatted)

    # -- Save ---------------------------------------------------------------

    def _on_save_clicked(self, _button: Gtk.Button) -> None:
        from hyprgui.config_manager import write_hyprgui_conf
        write_hyprgui_conf(self._values)
        self._dirty = False
        toast = Adw.Toast(title="Settings saved to hyprgui.conf")
        self.add_toast(toast)
