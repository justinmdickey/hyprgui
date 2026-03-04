"""Dynamic settings window — generates UI from the settings registry."""

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


class HyprguiWindow(Adw.ApplicationWindow):
    """Main settings window with sidebar navigation."""

    def __init__(self, app: Adw.Application, **kwargs):
        super().__init__(application=app, title="Hyprgui", **kwargs)
        self.set_default_size(900, 700)

        # Current UI values: key -> python value
        self._values: dict[str, object] = {}
        # Widget references for potential future use
        self._widgets: dict[str, Gtk.Widget] = {}
        self._dirty = False

        self._build_ui()
        self._load_current_values()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        """Build sidebar + content layout from the settings registry."""
        # Collect settings by page, then group (preserving insertion order)
        pages: dict[str, OrderedDict[str, list[SettingDef]]] = OrderedDict()
        for sdef in SETTINGS:
            page_groups = pages.setdefault(sdef.page, OrderedDict())
            page_groups.setdefault(sdef.group, []).append(sdef)

        # -- Content area: stack of PreferencesPages -----------------------
        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

        for page_key, groups in pages.items():
            pref_page = Adw.PreferencesPage()
            for group_title, sdefs in groups.items():
                group = Adw.PreferencesGroup(title=group_title)
                for sdef in sdefs:
                    row = self._create_row(sdef)
                    if row is not None:
                        group.add(row)
                pref_page.add(group)
            self._stack.add_named(pref_page, page_key)

        # Content header bar with save button
        self._content_title = Adw.WindowTitle(title=PAGE_TITLES.get(
            next(iter(pages)), ""))

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)

        content_header = Adw.HeaderBar(title_widget=self._content_title)
        content_header.pack_end(save_btn)

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(content_header)
        content_toolbar.set_content(self._stack)

        content_page = Adw.NavigationPage(
            child=content_toolbar,
            title=PAGE_TITLES.get(next(iter(pages)), ""),
        )

        # -- Sidebar -------------------------------------------------------
        sidebar_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        sidebar_listbox.add_css_class("navigation-sidebar")

        first_row = None
        for page_key in pages:
            row = Gtk.ListBoxRow()
            row.page_key = page_key
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.append(Gtk.Image(icon_name=PAGE_ICONS.get(
                page_key, "preferences-system-symbolic")))
            box.append(Gtk.Label(
                label=PAGE_TITLES.get(page_key, page_key),
                xalign=0, hexpand=True,
            ))
            row.set_child(box)
            sidebar_listbox.append(row)
            if first_row is None:
                first_row = row

        sidebar_listbox.connect("row-selected", self._on_sidebar_row_selected)

        sidebar_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vexpand=True,
        )
        sidebar_scroll.set_child(sidebar_listbox)

        sidebar_header = Adw.HeaderBar(
            title_widget=Adw.WindowTitle(title="Hyprgui"),
        )

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_toolbar.add_top_bar(sidebar_header)
        sidebar_toolbar.set_content(sidebar_scroll)

        sidebar_page = Adw.NavigationPage(
            child=sidebar_toolbar, title="Hyprgui",
        )

        # -- Split view ----------------------------------------------------
        self._split_view = Adw.NavigationSplitView(
            min_sidebar_width=220,
            max_sidebar_width=260,
            sidebar=sidebar_page,
            content=content_page,
        )

        # -- Toast overlay wrapping everything -----------------------------
        self._toast_overlay = Adw.ToastOverlay(child=self._split_view)
        self.set_content(self._toast_overlay)

        # Select first sidebar row
        if first_row is not None:
            sidebar_listbox.select_row(first_row)

    def _on_sidebar_row_selected(self, listbox, row):
        if row is None:
            return
        self._stack.set_visible_child_name(row.page_key)
        self._content_title.set_title(PAGE_TITLES.get(row.page_key, row.page_key))
        self._split_view.set_show_content(True)

    def add_toast(self, toast):
        """Forward toast calls to the internal overlay."""
        self._toast_overlay.add_toast(toast)

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
