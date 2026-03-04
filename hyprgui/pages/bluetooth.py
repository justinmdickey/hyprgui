"""Bluetooth settings page using BlueZ D-Bus API."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from hyprgui.dbus_helpers import (
    call_method,
    call_method_async,
    get_property,
    get_proxy,
    subscribe_signal,
)
from hyprgui.pages.base import BasePage

_BLUEZ_BUS = "org.bluez"
_ADAPTER_PATH = "/org/bluez/hci0"
_ADAPTER_IFACE = "org.bluez.Adapter1"
_DEVICE_IFACE = "org.bluez.Device1"
_BATTERY_IFACE = "org.bluez.Battery1"
_OBJMGR_IFACE = "org.freedesktop.DBus.ObjectManager"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"


class BluetoothPage(BasePage):
    """Bluetooth settings: toggle adapter, list paired/available devices."""

    page_key = "bluetooth"
    page_title = "Bluetooth"
    page_icon = "bluetooth-symbolic"

    def __init__(self) -> None:
        self._adapter_proxy: Gio.DBusProxy | None = None
        self._adapter_props: Gio.DBusProxy | None = None
        self._objmgr_proxy: Gio.DBusProxy | None = None
        self._connection: Gio.DBusConnection | None = None
        self._signal_ids: list[int] = []
        self._discovering = False

        # Widgets
        self._page: Adw.PreferencesPage | None = None
        self._power_row: Adw.SwitchRow | None = None
        self._paired_group: Adw.PreferencesGroup | None = None
        self._available_group: Adw.PreferencesGroup | None = None
        self._status_page: Adw.StatusPage | None = None
        self._stack: Gtk.Stack | None = None

        # Track device rows: object_path -> Adw.ActionRow
        self._device_rows: dict[str, Adw.ActionRow] = {}

        # Guard against signal handler firing during toggle set
        self._updating_power = False

    # ------------------------------------------------------------------
    # BasePage interface
    # ------------------------------------------------------------------

    def build(self) -> Adw.PreferencesPage:
        self._page = Adw.PreferencesPage(
            title=self.page_title,
            icon_name=self.page_icon,
        )

        # We use a stack so we can swap between "working" and "unavailable".
        self._stack = Gtk.Stack()

        # --- Main content --------------------------------------------------
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Power toggle group
        power_group = Adw.PreferencesGroup(title="Bluetooth")
        self._power_row = Adw.SwitchRow(title="Bluetooth", subtitle="Enable or disable the adapter")
        self._power_row.connect("notify::active", self._on_power_toggled)
        power_group.add(self._power_row)

        # Wrap in a clamp so it matches libadwaita style
        power_clamp = Adw.Clamp(maximum_size=600, child=power_group)
        main_box.append(power_clamp)

        # Paired devices group
        self._paired_group = Adw.PreferencesGroup(title="Paired Devices")
        paired_clamp = Adw.Clamp(maximum_size=600, child=self._paired_group)
        main_box.append(paired_clamp)

        # Available devices group
        self._available_group = Adw.PreferencesGroup(title="Available Devices")
        available_clamp = Adw.Clamp(maximum_size=600, child=self._available_group)
        main_box.append(available_clamp)

        self._stack.add_named(main_box, "main")

        # --- Error / unavailable status page --------------------------------
        self._status_page = Adw.StatusPage(
            icon_name="bluetooth-disabled-symbolic",
            title="Bluetooth Unavailable",
            description="BlueZ service is not running or no adapter was found.",
        )
        self._stack.add_named(self._status_page, "unavailable")

        # Embed the stack into a dummy preferences group so it lives inside
        # the PreferencesPage scroll view.
        wrapper_group = Adw.PreferencesGroup()
        wrapper_group.add(self._stack)
        self._page.add(wrapper_group)

        # Try initial connection
        self._init_bluez()

        return self._page

    def activate(self) -> None:
        if self._adapter_proxy is None:
            self._init_bluez()
            return
        self._start_discovery()

    def deactivate(self) -> None:
        self._stop_discovery()

    def dispose(self) -> None:
        self._stop_discovery()
        self._unsubscribe_signals()

    def get_search_terms(self) -> list[str]:
        return ["bluetooth", "wireless", "paired", "devices"]

    # ------------------------------------------------------------------
    # BlueZ initialisation
    # ------------------------------------------------------------------

    def _init_bluez(self) -> None:
        """Connect to BlueZ and populate initial state."""
        self._adapter_proxy = get_proxy(_BLUEZ_BUS, _ADAPTER_PATH, _ADAPTER_IFACE)
        if self._adapter_proxy is None:
            self._show_unavailable()
            return

        self._adapter_props = get_proxy(_BLUEZ_BUS, _ADAPTER_PATH, _PROPS_IFACE)
        self._objmgr_proxy = get_proxy(_BLUEZ_BUS, "/", _OBJMGR_IFACE)
        if self._objmgr_proxy is None:
            self._show_unavailable()
            return

        self._connection = self._adapter_proxy.get_connection()

        self._stack.set_visible_child_name("main")

        # Read current power state
        powered = get_property(self._adapter_proxy, "Powered")
        self._updating_power = True
        self._power_row.set_active(bool(powered))
        self._updating_power = False

        # Subscribe to ObjectManager signals for device add/remove
        sig_id = subscribe_signal(
            self._connection,
            _BLUEZ_BUS,
            None,
            _OBJMGR_IFACE,
            "InterfacesAdded",
            self._on_interfaces_added,
        )
        self._signal_ids.append(sig_id)

        sig_id = subscribe_signal(
            self._connection,
            _BLUEZ_BUS,
            None,
            _OBJMGR_IFACE,
            "InterfacesRemoved",
            self._on_interfaces_removed,
        )
        self._signal_ids.append(sig_id)

        # Subscribe to property changes on the adapter (for Powered changes)
        sig_id = subscribe_signal(
            self._connection,
            _BLUEZ_BUS,
            _ADAPTER_PATH,
            _PROPS_IFACE,
            "PropertiesChanged",
            self._on_adapter_props_changed,
        )
        self._signal_ids.append(sig_id)

        # Populate existing devices
        self._refresh_devices()

    def _show_unavailable(self) -> None:
        if self._stack is not None:
            self._stack.set_visible_child_name("unavailable")

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------

    def _refresh_devices(self) -> None:
        """Enumerate BlueZ objects and rebuild device rows."""
        self._clear_device_rows()

        if self._objmgr_proxy is None:
            return

        result = call_method(self._objmgr_proxy, "GetManagedObjects")
        if result is None:
            return

        objects: dict = result.unpack()[0]
        for obj_path, ifaces in objects.items():
            if _DEVICE_IFACE in ifaces:
                props = ifaces[_DEVICE_IFACE]
                battery_props = ifaces.get(_BATTERY_IFACE, {})
                self._add_device_row(obj_path, props, battery_props)

    def _clear_device_rows(self) -> None:
        """Remove all device rows from both groups."""
        for path, row in self._device_rows.items():
            parent = row.get_parent()
            if parent is not None:
                parent.remove(row)
        self._device_rows.clear()

    def _add_device_row(
        self,
        obj_path: str,
        props: dict,
        battery_props: dict | None = None,
    ) -> None:
        """Create and add an Adw.ActionRow for a device."""
        name = props.get("Name") or props.get("Alias") or props.get("Address", "Unknown")
        paired = bool(props.get("Paired", False))
        connected = bool(props.get("Connected", False))
        icon_name = props.get("Icon", "bluetooth-symbolic")
        # BlueZ icon names don't always have -symbolic, ensure we have a fallback
        if icon_name and not icon_name.endswith("-symbolic"):
            icon_name = icon_name + "-symbolic"

        row = Adw.ActionRow(
            title=str(name),
            subtitle="Connected" if connected else ("Paired" if paired else "Disconnected"),
            activatable=True,
        )
        row.add_prefix(Gtk.Image(icon_name=icon_name))

        # Battery percentage suffix
        battery_level = None
        if battery_props:
            battery_level = battery_props.get("Percentage")
        if battery_level is None:
            # Try fetching via a dedicated proxy
            battery_level = self._get_battery_level(obj_path)
        if battery_level is not None:
            battery_label = Gtk.Label(
                label=f"{battery_level}%",
                css_classes=["dim-label"],
                valign=Gtk.Align.CENTER,
            )
            row.add_suffix(battery_label)

        # Navigation arrow
        row.add_suffix(
            Gtk.Image(
                icon_name="go-next-symbolic",
                css_classes=["dim-label"],
                valign=Gtk.Align.CENTER,
            )
        )

        # Click handler — connect/disconnect or pair
        row.connect("activated", self._on_device_activated, obj_path, paired, connected)

        # Subscribe to property changes for this device
        if self._connection is not None:
            sig_id = subscribe_signal(
                self._connection,
                _BLUEZ_BUS,
                obj_path,
                _PROPS_IFACE,
                "PropertiesChanged",
                self._on_device_props_changed,
            )
            self._signal_ids.append(sig_id)

        self._device_rows[obj_path] = row

        if paired:
            self._paired_group.add(row)
        else:
            self._available_group.add(row)

    def _get_battery_level(self, obj_path: str) -> int | None:
        """Attempt to read battery level for a device."""
        proxy = get_proxy(_BLUEZ_BUS, obj_path, _BATTERY_IFACE)
        if proxy is None:
            return None
        level = get_property(proxy, "Percentage")
        return int(level) if level is not None else None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _start_discovery(self) -> None:
        if self._discovering or self._adapter_proxy is None:
            return
        call_method_async(self._adapter_proxy, "StartDiscovery")
        self._discovering = True

    def _stop_discovery(self) -> None:
        if not self._discovering or self._adapter_proxy is None:
            return
        call_method_async(self._adapter_proxy, "StopDiscovery")
        self._discovering = False

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_power_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        if self._updating_power:
            return
        if self._adapter_props is None:
            return
        active = row.get_active()
        call_method_async(
            self._adapter_props,
            "Set",
            GLib.Variant("(ssv)", (_ADAPTER_IFACE, "Powered", GLib.Variant("b", active))),
        )

    def _on_adapter_props_changed(
        self,
        _connection,
        _sender,
        _object_path,
        _interface,
        _signal,
        params,
    ) -> None:
        """React to adapter property changes (e.g. Powered toggled externally)."""
        iface, changed, _invalidated = params.unpack()
        if iface != _ADAPTER_IFACE:
            return
        if "Powered" in changed:
            self._updating_power = True
            self._power_row.set_active(bool(changed["Powered"]))
            self._updating_power = False

    def _on_interfaces_added(
        self,
        _connection,
        _sender,
        _object_path,
        _interface,
        _signal,
        params,
    ) -> None:
        obj_path, ifaces = params.unpack()
        if _DEVICE_IFACE in ifaces:
            props = ifaces[_DEVICE_IFACE]
            battery_props = ifaces.get(_BATTERY_IFACE, {})
            if obj_path not in self._device_rows:
                GLib.idle_add(self._add_device_row, obj_path, props, battery_props)

    def _on_interfaces_removed(
        self,
        _connection,
        _sender,
        _object_path,
        _interface,
        _signal,
        params,
    ) -> None:
        obj_path, ifaces = params.unpack()
        if _DEVICE_IFACE in ifaces:
            GLib.idle_add(self._remove_device_row, obj_path)

    def _on_device_props_changed(
        self,
        _connection,
        _sender,
        object_path,
        _interface,
        _signal,
        params,
    ) -> None:
        """Update a device row when its properties change."""
        iface, changed, _invalidated = params.unpack()
        if iface != _DEVICE_IFACE:
            return
        row = self._device_rows.get(object_path)
        if row is None:
            return

        if "Name" in changed or "Alias" in changed:
            row.set_title(str(changed.get("Name") or changed.get("Alias", "")))

        if "Connected" in changed or "Paired" in changed:
            connected = changed.get("Connected")
            paired = changed.get("Paired")
            # We need to re-check full state; fetch from proxy for accuracy
            GLib.idle_add(self._rebuild_device, object_path)

    def _rebuild_device(self, obj_path: str) -> None:
        """Re-read device properties and rebuild its row."""
        self._remove_device_row(obj_path)

        dev_proxy = get_proxy(_BLUEZ_BUS, obj_path, _DEVICE_IFACE)
        if dev_proxy is None:
            return

        props = {}
        for key in ("Name", "Alias", "Address", "Paired", "Connected", "Icon"):
            val = get_property(dev_proxy, key)
            if val is not None:
                props[key] = val

        battery_level = self._get_battery_level(obj_path)
        battery_props = {"Percentage": battery_level} if battery_level is not None else {}

        self._add_device_row(obj_path, props, battery_props)

    def _remove_device_row(self, obj_path: str) -> None:
        row = self._device_rows.pop(obj_path, None)
        if row is None:
            return
        parent = row.get_parent()
        if parent is not None:
            parent.remove(row)

    # ------------------------------------------------------------------
    # Device actions
    # ------------------------------------------------------------------

    def _on_device_activated(
        self,
        _row: Adw.ActionRow,
        obj_path: str,
        paired: bool,
        connected: bool,
    ) -> None:
        dev_proxy = get_proxy(_BLUEZ_BUS, obj_path, _DEVICE_IFACE)
        if dev_proxy is None:
            return

        if not paired:
            call_method_async(dev_proxy, "Pair", callback=lambda _res: GLib.idle_add(self._rebuild_device, obj_path))
        elif connected:
            call_method_async(dev_proxy, "Disconnect", callback=lambda _res: GLib.idle_add(self._rebuild_device, obj_path))
        else:
            call_method_async(dev_proxy, "Connect", callback=lambda _res: GLib.idle_add(self._rebuild_device, obj_path))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _unsubscribe_signals(self) -> None:
        if self._connection is None:
            return
        for sig_id in self._signal_ids:
            self._connection.signal_unsubscribe(sig_id)
        self._signal_ids.clear()
