"""Dynamic settings window — generates UI from the settings registry."""

from __future__ import annotations

from collections import OrderedDict

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from hyprgui import hyprctl
from hyprgui.settings_registry import (
    PAGE_ICONS,
    PAGE_TITLES,
    SETTINGS,
    SettingDef,
    SettingType,
)
from hyprgui.widgets.color_row import create_color_row, rgba_to_hex


# System pages — imported lazily to avoid hard failures when D-Bus
# services are absent.  Each entry: (module_path, class_name).
_SYSTEM_PAGE_SPECS: list[tuple[str, str]] = [
    ("hyprgui.pages.wifi", "WifiPage"),
    ("hyprgui.pages.bluetooth", "BluetoothPage"),
    ("hyprgui.pages.sound", "SoundPage"),
    ("hyprgui.pages.display", "DisplayPage"),
]


class HyprguiWindow(Adw.ApplicationWindow):
    """Main settings window with sidebar navigation."""

    def __init__(self, app: Adw.Application, **kwargs):
        super().__init__(application=app, title="Hyprgui", **kwargs)
        self.set_default_size(900, 700)

        import shutil
        self._has_hyprctl = bool(shutil.which("hyprctl"))

        # Current UI values: key -> python value
        self._values: dict[str, object] = {}
        # Widget references for potential future use
        self._widgets: dict[str, Gtk.Widget] = {}
        self._dirty = False
        self._loading = False

        # Per-row search: (sdef, row_widget, original_parent_group)
        self._row_info: list[tuple[SettingDef, Gtk.Widget, Adw.PreferencesGroup]] = []
        # Temporary groups created on the search page
        self._search_groups: list[Adw.PreferencesGroup] = []
        # Which page was selected before entering search
        self._active_page_key: str = ""
        self._in_search: bool = False

        # BasePage instances keyed by page_key
        self._system_pages: dict[str, object] = {}
        # Currently active BasePage (for deactivate on switch)
        self._active_system_page = None

        self._build_ui()
        if self._has_hyprctl:
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

        # -- Sidebar -------------------------------------------------------
        sidebar_listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        sidebar_listbox.add_css_class("navigation-sidebar")
        self._sidebar_listbox = sidebar_listbox

        self._sidebar_rows: list[Gtk.ListBoxRow] = []
        self._page_labels: dict[str, list[str]] = {}

        # --- System pages (Wi-Fi, Bluetooth, Sound, Display) ---
        self._load_system_pages()

        for page_key, page_inst in self._system_pages.items():
            pref_page = page_inst.build()
            self._stack.add_named(pref_page, page_key)
            self._page_labels[page_key] = page_inst.get_search_terms()

            row = self._make_sidebar_row(
                page_key, page_inst.page_title, page_inst.page_icon)
            sidebar_listbox.append(row)
            self._sidebar_rows.append(row)

        # Separator between system and Hyprland pages
        if self._system_pages and pages:
            sep = Gtk.ListBoxRow(selectable=False, activatable=False)
            sep.set_child(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
            sep.set_sensitive(False)
            sidebar_listbox.append(sep)

        # --- Hyprland registry pages ---
        first_page_key = None
        for page_key, groups in pages.items():
            pref_page = Adw.PreferencesPage()
            for group_title, sdefs in groups.items():
                group = Adw.PreferencesGroup(title=group_title)
                for sdef in sdefs:
                    row = self._create_row(sdef)
                    if row is not None:
                        group.add(row)
                        self._row_info.append((sdef, row, group))
                pref_page.add(group)
            self._stack.add_named(pref_page, page_key)

            labels = []
            for sdefs in groups.values():
                labels.extend(s.label.lower() for s in sdefs)
            self._page_labels[page_key] = labels

            row = self._make_sidebar_row(
                page_key,
                PAGE_TITLES.get(page_key, page_key),
                PAGE_ICONS.get(page_key, "preferences-system-symbolic"),
            )
            sidebar_listbox.append(row)
            self._sidebar_rows.append(row)
            if first_page_key is None:
                first_page_key = page_key

        # Hidden search results page
        self._search_page = Adw.PreferencesPage()
        self._stack.add_named(self._search_page, "_search")

        # Pick initial page: first system page if any, else first registry page
        if self._system_pages:
            initial_key = next(iter(self._system_pages))
        else:
            initial_key = first_page_key or ""

        # Content header bar with save button
        self._content_title = Adw.WindowTitle(
            title=self._resolve_page_title(initial_key))

        self._save_btn = Gtk.Button(label="Save")
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.connect("clicked", self._on_save_clicked)

        reset_btn = Gtk.Button(icon_name="edit-clear-all-symbolic",
                               tooltip_text="Reset all settings")
        reset_btn.add_css_class("flat")
        reset_btn.connect("clicked", self._on_reset_clicked)

        content_header = Adw.HeaderBar(title_widget=self._content_title)
        content_header.pack_end(self._save_btn)
        content_header.pack_start(reset_btn)

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(content_header)
        content_toolbar.set_content(self._stack)

        content_page = Adw.NavigationPage(
            child=content_toolbar,
            title=self._resolve_page_title(initial_key),
        )

        sidebar_listbox.connect("row-selected", self._on_sidebar_row_selected)

        sidebar_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vexpand=True,
        )
        sidebar_scroll.set_child(sidebar_listbox)

        # Search bar
        self._search_entry = Gtk.SearchEntry(placeholder_text="Search settings…")
        self._search_entry.connect("search-changed", self._on_search_changed)

        self._search_bar = Gtk.SearchBar(child=self._search_entry)
        self._search_bar.connect_entry(self._search_entry)

        sidebar_header = Adw.HeaderBar(
            title_widget=Adw.WindowTitle(title="Hyprgui"),
        )

        self._search_btn = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self._search_btn.add_css_class("flat")
        self._search_btn.bind_property(
            "active", self._search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        sidebar_header.pack_start(self._search_btn)

        menu_model = Gio.Menu()
        menu_model.append("About", "app.about")
        menu_btn = Gtk.MenuButton(
            icon_name="open-menu-symbolic",
            menu_model=menu_model,
        )
        menu_btn.add_css_class("flat")
        sidebar_header.pack_end(menu_btn)

        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.append(self._search_bar)
        sidebar_box.append(sidebar_scroll)

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_toolbar.add_top_bar(sidebar_header)
        sidebar_toolbar.set_content(sidebar_box)

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

        # Keyboard shortcuts
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.MANAGED)
        ctrl.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>s"),
            action=Gtk.CallbackAction.new(lambda *_: self._on_save_clicked(None)),
        ))
        ctrl.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("<Control>k"),
            action=Gtk.CallbackAction.new(
                lambda *_: self._search_btn.set_active(
                    not self._search_btn.get_active())),
        ))
        ctrl.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string("Escape"),
            action=Gtk.CallbackAction.new(self._on_escape),
        ))
        self.add_controller(ctrl)

        # Warn on close with unsaved changes
        self.connect("close-request", self._on_close_request)

        # Select first sidebar row
        first_row = self._sidebar_rows[0] if self._sidebar_rows else None
        if first_row is not None:
            sidebar_listbox.select_row(first_row)

    def _load_system_pages(self) -> None:
        """Import and instantiate system BasePage subclasses."""
        import importlib
        for module_path, class_name in _SYSTEM_PAGE_SPECS:
            try:
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                inst = cls()
                self._system_pages[inst.page_key] = inst
            except Exception:
                # Page unavailable (missing D-Bus service, etc.) — skip silently
                pass

    def _make_sidebar_row(
        self, page_key: str, title: str, icon_name: str,
    ) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.page_key = page_key
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.append(Gtk.Image(icon_name=icon_name))
        box.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        row.set_child(box)
        return row

    def _resolve_page_title(self, page_key: str) -> str:
        if page_key in self._system_pages:
            return self._system_pages[page_key].page_title
        return PAGE_TITLES.get(page_key, page_key)

    def _on_sidebar_row_selected(self, listbox, row):
        if row is None or not hasattr(row, "page_key"):
            return

        # Deactivate previous system page
        if self._active_system_page is not None:
            self._active_system_page.deactivate()
            self._active_system_page = None

        self._active_page_key = row.page_key
        if self._in_search:
            self._search_entry.set_text("")
        self._stack.set_visible_child_name(row.page_key)
        self._content_title.set_title(self._resolve_page_title(row.page_key))
        self._split_view.set_show_content(True)

        # Activate new system page
        if row.page_key in self._system_pages:
            self._active_system_page = self._system_pages[row.page_key]
            self._active_system_page.activate()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip().lower()
        if not query:
            self._end_search()
            return
        self._begin_search(query)

    def _begin_search(self, query: str) -> None:
        # End previous search first (move rows back)
        if self._in_search:
            self._restore_rows()

        self._in_search = True

        # Clear old search groups from search page
        for grp in self._search_groups:
            self._search_page.remove(grp)
        self._search_groups.clear()

        # Build search results: group matching rows by "Page › Group"
        grouped: OrderedDict[str, list[tuple[SettingDef, Gtk.Widget, Adw.PreferencesGroup]]] = OrderedDict()
        for sdef, row, orig_group in self._row_info:
            if query in sdef.label.lower() or query in sdef.key.lower():
                page_title = PAGE_TITLES.get(sdef.page, sdef.page)
                section = f"{page_title} › {sdef.group}"
                grouped.setdefault(section, []).append((sdef, row, orig_group))

        # Reparent matching rows into search page groups
        for section_title, items in grouped.items():
            search_group = Adw.PreferencesGroup(title=section_title)
            for sdef, row, orig_group in items:
                orig_group.remove(row)
                search_group.add(row)
            self._search_page.add(search_group)
            self._search_groups.append(search_group)

        self._stack.set_visible_child_name("_search")
        self._content_title.set_title("Search Results")

        # Filter sidebar rows too
        for srow in self._sidebar_rows:
            page_key = srow.page_key
            title = self._resolve_page_title(page_key).lower()
            labels = self._page_labels.get(page_key, [])
            srow.set_visible(query in title or any(query in l for l in labels))

    def _end_search(self) -> None:
        if not self._in_search:
            # Just restore sidebar visibility
            for srow in self._sidebar_rows:
                srow.set_visible(True)
            return

        self._restore_rows()
        self._in_search = False

        # Clear search groups
        for grp in self._search_groups:
            self._search_page.remove(grp)
        self._search_groups.clear()

        # Restore sidebar visibility
        for srow in self._sidebar_rows:
            srow.set_visible(True)

        # Switch back to previously selected page
        if self._active_page_key:
            self._stack.set_visible_child_name(self._active_page_key)
            self._content_title.set_title(
                self._resolve_page_title(self._active_page_key))

    def _restore_rows(self) -> None:
        """Move all reparented rows back to their original groups."""
        for sdef, row, orig_group in self._row_info:
            parent = row.get_parent()
            if parent is not None and parent is not orig_group:
                parent.remove(row)
                orig_group.add(row)

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
                label = sdef.enum_options[idx]
                self._values[sdef.key] = label
                self._apply_live(sdef, label)

        row.connect("notify::selected", _on_notify)
        return row

    # -- Load current values from Hyprland ----------------------------------

    def _load_current_values(self) -> None:
        """Read current values from hyprctl and update widgets."""
        self._loading = True
        for sdef in SETTINGS:
            data = hyprctl.getoption(sdef.key)
            value = hyprctl.parse_option_value(sdef, data)
            self._values[sdef.key] = value
            self._set_widget_value(sdef, value)
        self._loading = False

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

    # -- Keyboard shortcuts -------------------------------------------------

    def _on_escape(self, *_args) -> bool:
        """Close search bar on Escape if open."""
        if self._search_btn.get_active():
            self._search_btn.set_active(False)
            self._search_entry.set_text("")
        return True

    def _update_dirty_indicator(self) -> None:
        """Update save button to reflect dirty state."""
        if self._dirty:
            self._save_btn.set_label("Save \u2022")
        else:
            self._save_btn.set_label("Save")

    def _on_close_request(self, _window) -> bool:
        """Warn before closing with unsaved changes."""
        # Dispose system pages
        for page_inst in self._system_pages.values():
            page_inst.dispose()

        if not self._dirty:
            return False
        dialog = Adw.AlertDialog(
            heading="Unsaved Changes",
            body="You have unsaved changes that will be lost.",
        )
        dialog.add_response("discard", "Discard")
        dialog.add_response("save", "Save & Close")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("discard")
        dialog.connect("response", self._on_close_dialog_response)
        dialog.present(self)
        return True

    def _on_close_dialog_response(self, _dialog, response: str) -> None:
        if response == "save":
            self._on_save_clicked(None)
        self.destroy()

    # -- Live preview -------------------------------------------------------

    def _apply_live(self, sdef: SettingDef, value: object) -> None:
        """Send the value to Hyprland immediately for live preview."""
        if self._loading:
            return
        self._dirty = True
        self._update_dirty_indicator()
        formatted = hyprctl.format_value(sdef, value)
        hyprctl.set_keyword(sdef.key, formatted)

    # -- Save ---------------------------------------------------------------

    def _on_save_clicked(self, _button: Gtk.Button) -> None:
        from hyprgui.config_manager import write_hyprgui_conf
        write_hyprgui_conf(self._values)
        self._dirty = False
        self._update_dirty_indicator()
        toast = Adw.Toast(title="Settings saved to hyprgui.conf")
        self.add_toast(toast)

    def _on_reset_clicked(self, _button: Gtk.Button) -> None:
        dialog = Adw.AlertDialog(
            heading="Reset All Settings?",
            body="This will clear hyprgui.conf and reload Hyprland so your own config takes effect.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_reset_response)
        dialog.present(self)

    def _on_reset_response(self, dialog, response: str) -> None:
        if response != "reset":
            return
        from hyprgui.config_manager import reset_hyprgui_conf
        reset_hyprgui_conf()
        hyprctl.reload_config()
        self._dirty = False
        self._update_dirty_indicator()
        GLib.timeout_add(300, self._load_after_reset)

    def _load_after_reset(self) -> bool:
        self._load_current_values()
        toast = Adw.Toast(title="Settings reset — using your own config")
        self.add_toast(toast)
        return GLib.SOURCE_REMOVE
