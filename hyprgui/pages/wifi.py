"""Wi-Fi settings page using NetworkManager D-Bus API."""

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

NM_BUS = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
NM_IFACE = "org.freedesktop.NetworkManager"
NM_DEVICE_IFACE = "org.freedesktop.NetworkManager.Device"
NM_WIRELESS_IFACE = "org.freedesktop.NetworkManager.Device.Wireless"
NM_AP_IFACE = "org.freedesktop.NetworkManager.AccessPoint"
NM_CONN_ACTIVE_IFACE = "org.freedesktop.NetworkManager.Connection.Active"
NM_SETTINGS_IFACE = "org.freedesktop.NetworkManager.Settings"
NM_SETTINGS_CONN_IFACE = "org.freedesktop.NetworkManager.Settings.Connection"
NM_SETTINGS_PATH = "/org/freedesktop/NetworkManager/Settings"
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"

# NM device types
NM_DEVICE_TYPE_WIFI = 2

# NM security flags — non-zero means some security is present
NM_AP_SEC_NONE = 0x0

# NM active connection states
NM_ACTIVE_STATE_ACTIVATED = 2


def _signal_icon(strength: int) -> str:
    """Return the appropriate signal strength icon name."""
    if strength >= 80:
        return "network-wireless-signal-excellent-symbolic"
    if strength >= 55:
        return "network-wireless-signal-good-symbolic"
    if strength >= 30:
        return "network-wireless-signal-ok-symbolic"
    return "network-wireless-signal-weak-symbolic"


def _ssid_from_bytes(ssid_bytes) -> str:
    """Decode SSID byte array to string."""
    if ssid_bytes is None:
        return ""
    if isinstance(ssid_bytes, bytes):
        return ssid_bytes.decode("utf-8", errors="replace")
    # GLib may give us a list of ints
    return bytes(ssid_bytes).decode("utf-8", errors="replace")


def _ap_is_secured(ap_proxy: Gio.DBusProxy) -> bool:
    """Check if an access point requires authentication."""
    wpa = get_property(ap_proxy, "WpaFlags") or 0
    rsn = get_property(ap_proxy, "RsnFlags") or 0
    return (wpa != NM_AP_SEC_NONE) or (rsn != NM_AP_SEC_NONE)


class WifiPage(BasePage):
    """Wi-Fi settings page backed by NetworkManager D-Bus."""

    page_key = "wifi"
    page_title = "Wi-Fi"
    page_icon = "network-wireless-symbolic"

    def __init__(self) -> None:
        self._nm_proxy: Gio.DBusProxy | None = None
        self._wireless_proxy: Gio.DBusProxy | None = None
        self._wireless_device_path: str | None = None
        self._signal_ids: list[int] = []
        self._connection: Gio.DBusConnection | None = None
        self._scan_timeout_id: int = 0
        self._page: Adw.PreferencesPage | None = None
        self._toggle_row: Adw.SwitchRow | None = None
        self._ap_group: Adw.PreferencesGroup | None = None
        self._saved_group: Adw.PreferencesGroup | None = None
        self._status_group: Adw.PreferencesGroup | None = None
        self._active_ap_path: str | None = None
        self._disposed = False
        # Track rows for cleanup
        self._ap_rows: list[Gtk.Widget] = []
        self._saved_rows: list[Gtk.Widget] = []

    # ------------------------------------------------------------------
    # BasePage interface
    # ------------------------------------------------------------------

    def build(self) -> Adw.PreferencesPage:
        self._page = Adw.PreferencesPage(
            title="Wi-Fi",
            icon_name="network-wireless-symbolic",
        )

        # Try to connect to NetworkManager
        self._nm_proxy = get_proxy(NM_BUS, NM_PATH, NM_IFACE)

        if self._nm_proxy is None:
            self._build_status_page("NetworkManager is not available.")
            return self._page

        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error:
            self._build_status_page("Cannot connect to system D-Bus.")
            return self._page

        # Find first wireless device
        self._wireless_device_path = self._find_wireless_device()
        if self._wireless_device_path is None:
            self._build_status_page("No Wi-Fi adapter found.")
            return self._page

        self._wireless_proxy = get_proxy(
            NM_BUS, self._wireless_device_path, NM_WIRELESS_IFACE
        )
        if self._wireless_proxy is None:
            self._build_status_page("Cannot access Wi-Fi device.")
            return self._page

        # -- Wi-Fi toggle group --
        toggle_group = Adw.PreferencesGroup()
        self._toggle_row = Adw.SwitchRow(title="Wi-Fi")
        wifi_enabled = self._get_wireless_enabled()
        self._toggle_row.set_active(wifi_enabled)
        self._toggle_row.connect("notify::active", self._on_wifi_toggled)
        toggle_group.add(self._toggle_row)
        self._page.add(toggle_group)

        # -- Available Networks group --
        self._ap_group = Adw.PreferencesGroup(title="Available Networks")
        self._page.add(self._ap_group)

        # -- Saved Networks group --
        self._saved_group = Adw.PreferencesGroup(title="Saved Networks")
        self._page.add(self._saved_group)

        # Initial population
        self._refresh_access_points()
        self._refresh_saved_connections()

        return self._page

    def activate(self) -> None:
        if self._wireless_proxy is None or self._connection is None:
            return

        # Request a scan
        self._request_scan()

        # Subscribe to AccessPointAdded / AccessPointRemoved
        sid = subscribe_signal(
            self._connection,
            NM_BUS,
            self._wireless_device_path,
            NM_WIRELESS_IFACE,
            "AccessPointAdded",
            self._on_ap_changed,
        )
        self._signal_ids.append(sid)

        sid = subscribe_signal(
            self._connection,
            NM_BUS,
            self._wireless_device_path,
            NM_WIRELESS_IFACE,
            "AccessPointRemoved",
            self._on_ap_changed,
        )
        self._signal_ids.append(sid)

        # Subscribe to NM PropertiesChanged (for WirelessEnabled)
        sid = subscribe_signal(
            self._connection,
            NM_BUS,
            NM_PATH,
            DBUS_PROPS_IFACE,
            "PropertiesChanged",
            self._on_nm_props_changed,
        )
        self._signal_ids.append(sid)

        # Periodic re-scan every 15 seconds
        self._scan_timeout_id = GLib.timeout_add_seconds(15, self._periodic_scan)

    def deactivate(self) -> None:
        if self._scan_timeout_id:
            GLib.source_remove(self._scan_timeout_id)
            self._scan_timeout_id = 0

    def dispose(self) -> None:
        self._disposed = True
        self.deactivate()
        if self._connection is not None:
            for sid in self._signal_ids:
                self._connection.signal_unsubscribe(sid)
        self._signal_ids.clear()
        self._nm_proxy = None
        self._wireless_proxy = None
        self._connection = None

    def get_search_terms(self) -> list[str]:
        return ["wi-fi", "wifi", "wireless", "network", "internet"]

    # ------------------------------------------------------------------
    # Internal: D-Bus helpers
    # ------------------------------------------------------------------

    def _find_wireless_device(self) -> str | None:
        """Find the object path of the first Wi-Fi device."""
        result = call_method(
            self._nm_proxy, "GetDevices", None
        )
        if result is None:
            return None
        device_paths = result.unpack()[0]
        for path in device_paths:
            dev_proxy = get_proxy(NM_BUS, path, NM_DEVICE_IFACE)
            if dev_proxy is None:
                continue
            dev_type = get_property(dev_proxy, "DeviceType")
            if dev_type == NM_DEVICE_TYPE_WIFI:
                return path
        return None

    def _get_wireless_enabled(self) -> bool:
        """Read the WirelessEnabled property from NetworkManager."""
        if self._nm_proxy is None:
            return False
        val = get_property(self._nm_proxy, "WirelessEnabled")
        return bool(val) if val is not None else False

    def _get_active_ap_path(self) -> str | None:
        """Get the object path of the currently active access point."""
        if self._wireless_proxy is None:
            return None
        path = get_property(self._wireless_proxy, "ActiveAccessPoint")
        if path and path != "/":
            return path
        return None

    def _get_access_points(self) -> list[dict]:
        """Fetch and return info dicts for all visible access points."""
        if self._wireless_proxy is None:
            return []
        result = call_method(self._wireless_proxy, "GetAccessPoints", None)
        if result is None:
            return []
        ap_paths = result.unpack()[0]
        self._active_ap_path = self._get_active_ap_path()

        seen_ssids: set[str] = set()
        aps: list[dict] = []
        for path in ap_paths:
            ap_proxy = get_proxy(NM_BUS, path, NM_AP_IFACE)
            if ap_proxy is None:
                continue
            ssid_bytes = get_property(ap_proxy, "Ssid")
            ssid = _ssid_from_bytes(ssid_bytes)
            if not ssid or ssid in seen_ssids:
                continue
            seen_ssids.add(ssid)
            strength = get_property(ap_proxy, "Strength") or 0
            secured = _ap_is_secured(ap_proxy)
            is_active = (path == self._active_ap_path)
            aps.append({
                "ssid": ssid,
                "strength": strength,
                "secured": secured,
                "active": is_active,
                "path": path,
            })
        # Sort: active first, then by signal strength descending
        aps.sort(key=lambda a: (-a["active"], -a["strength"]))
        return aps

    def _get_saved_connections(self) -> list[dict]:
        """Return saved Wi-Fi connections from NM Settings."""
        settings_proxy = get_proxy(NM_BUS, NM_SETTINGS_PATH, NM_SETTINGS_IFACE)
        if settings_proxy is None:
            return []
        result = call_method(settings_proxy, "ListConnections", None)
        if result is None:
            return []
        conn_paths = result.unpack()[0]
        saved: list[dict] = []
        for path in conn_paths:
            conn_proxy = get_proxy(NM_BUS, path, NM_SETTINGS_CONN_IFACE)
            if conn_proxy is None:
                continue
            settings_result = call_method(conn_proxy, "GetSettings", None)
            if settings_result is None:
                continue
            settings = settings_result.unpack()[0]
            conn_section = settings.get("connection", {})
            conn_type = conn_section.get("type", "")
            if conn_type != "802-11-wireless":
                continue
            conn_id = conn_section.get("id", "Unknown")
            saved.append({"id": conn_id, "path": path})
        saved.sort(key=lambda c: c["id"].lower())
        return saved

    def _request_scan(self) -> None:
        """Ask the wireless device to scan for networks."""
        if self._wireless_proxy is None:
            return
        options = GLib.Variant("(a{sv})", ({},))
        call_method_async(self._wireless_proxy, "RequestScan", options)

    # ------------------------------------------------------------------
    # Internal: UI builders
    # ------------------------------------------------------------------

    def _build_status_page(self, message: str) -> None:
        """Add a single status-message group to the page."""
        self._status_group = Adw.PreferencesGroup()
        row = Adw.ActionRow(title=message)
        row.set_sensitive(False)
        self._status_group.add(row)
        self._page.add(self._status_group)

    def _clear_group(self, group: Adw.PreferencesGroup, rows: list[Gtk.Widget]) -> None:
        """Remove all rows from a preferences group."""
        for row in rows:
            group.remove(row)
        rows.clear()

    def _refresh_access_points(self) -> None:
        """Rebuild the Available Networks group."""
        if self._ap_group is None:
            return
        self._clear_group(self._ap_group, self._ap_rows)

        if not self._get_wireless_enabled():
            row = Adw.ActionRow(title="Wi-Fi is disabled")
            row.set_sensitive(False)
            self._ap_group.add(row)
            self._ap_rows.append(row)
            return

        aps = self._get_access_points()
        if not aps:
            row = Adw.ActionRow(title="No networks found")
            row.set_sensitive(False)
            self._ap_group.add(row)
            self._ap_rows.append(row)
            return

        for ap_info in aps:
            row = self._make_ap_row(ap_info)
            self._ap_group.add(row)
            self._ap_rows.append(row)

    def _refresh_saved_connections(self) -> None:
        """Rebuild the Saved Networks group."""
        if self._saved_group is None:
            return
        self._clear_group(self._saved_group, self._saved_rows)

        saved = self._get_saved_connections()
        if not saved:
            row = Adw.ActionRow(title="No saved networks")
            row.set_sensitive(False)
            self._saved_group.add(row)
            self._saved_rows.append(row)
            return

        for conn in saved:
            row = Adw.ActionRow(title=conn["id"])
            row.set_activatable(True)

            delete_btn = Gtk.Button(
                icon_name="user-trash-symbolic",
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
                tooltip_text="Forget network",
            )
            delete_btn.connect(
                "clicked", self._on_delete_saved, conn["path"], conn["id"]
            )
            row.add_suffix(delete_btn)
            self._saved_group.add(row)
            self._saved_rows.append(row)

    def _make_ap_row(self, ap_info: dict) -> Adw.ActionRow:
        """Create an ActionRow for a scanned access point."""
        row = Adw.ActionRow(title=ap_info["ssid"])
        row.set_activatable(True)

        if ap_info["active"]:
            row.set_subtitle("Connected")

        # Signal strength icon
        signal_icon = Gtk.Image(
            icon_name=_signal_icon(ap_info["strength"]),
            valign=Gtk.Align.CENTER,
        )
        row.add_suffix(signal_icon)

        # Lock icon for secured networks
        if ap_info["secured"]:
            lock_icon = Gtk.Image(
                icon_name="system-lock-screen-symbolic",
                valign=Gtk.Align.CENTER,
            )
            row.add_suffix(lock_icon)

        # Navigation arrow
        arrow = Gtk.Image(
            icon_name="go-next-symbolic",
            valign=Gtk.Align.CENTER,
        )
        row.add_suffix(arrow)

        row.connect(
            "activated",
            self._on_ap_row_activated,
            ap_info,
        )
        return row

    # ------------------------------------------------------------------
    # Signal / event handlers
    # ------------------------------------------------------------------

    def _on_wifi_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        """Toggle Wi-Fi enabled via NM D-Bus property."""
        if self._nm_proxy is None:
            return
        enabled = row.get_active()
        variant = GLib.Variant("(ssv)", (NM_IFACE, "WirelessEnabled", GLib.Variant("b", enabled)))
        props_proxy = get_proxy(NM_BUS, NM_PATH, DBUS_PROPS_IFACE)
        if props_proxy is not None:
            call_method_async(props_proxy, "Set", variant, callback=self._on_toggle_done)

    def _on_toggle_done(self, _result) -> None:
        if self._disposed:
            return
        # Delay refresh to let NM process the state change
        GLib.timeout_add(500, self._deferred_refresh)

    def _deferred_refresh(self) -> bool:
        if not self._disposed:
            self._refresh_access_points()
        return GLib.SOURCE_REMOVE

    def _on_ap_changed(self, _conn, _sender, _path, _iface, _signal, _params) -> None:
        """Called when an AP is added or removed."""
        if self._disposed:
            return
        # Schedule refresh on main thread
        GLib.idle_add(self._refresh_access_points)

    def _on_nm_props_changed(self, _conn, _sender, _path, _iface, _signal, params) -> None:
        """Handle PropertiesChanged on NM — update Wi-Fi toggle."""
        if self._disposed or self._toggle_row is None:
            return
        try:
            args = params.unpack()
            iface_name = args[0]
            changed = args[1]
        except (ValueError, IndexError):
            return
        if iface_name != NM_IFACE:
            return
        if "WirelessEnabled" in changed:

            def _update():
                if self._disposed or self._toggle_row is None:
                    return False
                enabled = bool(changed["WirelessEnabled"])
                # Block handler to avoid feedback loop
                self._toggle_row.handler_block_by_func(self._on_wifi_toggled)
                self._toggle_row.set_active(enabled)
                self._toggle_row.handler_unblock_by_func(self._on_wifi_toggled)
                self._refresh_access_points()
                return False

            GLib.idle_add(_update)

    def _periodic_scan(self) -> bool:
        """Periodic scan callback for GLib.timeout_add_seconds."""
        if self._disposed:
            return GLib.SOURCE_REMOVE
        self._request_scan()
        # Refresh after giving the scan a moment
        GLib.timeout_add(2000, self._deferred_refresh)
        return GLib.SOURCE_CONTINUE

    def _on_ap_row_activated(self, _row: Adw.ActionRow, ap_info: dict) -> None:
        """Handle click on an access point row."""
        if ap_info["active"]:
            # Already connected — do nothing
            return
        if ap_info["secured"]:
            self._show_password_dialog(ap_info)
        else:
            self._connect_to_open_network(ap_info)

    def _connect_to_open_network(self, ap_info: dict) -> None:
        """Activate an open (unsecured) network."""
        if self._nm_proxy is None or self._wireless_device_path is None:
            return
        # connection settings = {} means NM auto-creates
        args = GLib.Variant(
            "(a{sa{sv}}oo)",
            ({}, self._wireless_device_path, ap_info["path"]),
        )
        call_method_async(
            self._nm_proxy,
            "AddAndActivateConnection",
            args,
            callback=lambda _res: GLib.idle_add(self._refresh_access_points),
        )

    def _connect_with_password(self, ap_info: dict, password: str) -> None:
        """Activate a secured network with the given password."""
        if self._nm_proxy is None or self._wireless_device_path is None:
            return

        ap_proxy = get_proxy(NM_BUS, ap_info["path"], NM_AP_IFACE)
        if ap_proxy is None:
            return

        ssid_bytes = get_property(ap_proxy, "Ssid")
        if ssid_bytes is None:
            return

        # Build connection settings dict
        ssid_variant = GLib.Variant("ay", bytes(ssid_bytes))
        conn_settings: dict = {
            "connection": {
                "type": GLib.Variant("s", "802-11-wireless"),
                "id": GLib.Variant("s", ap_info["ssid"]),
            },
            "802-11-wireless": {
                "ssid": ssid_variant,
                "mode": GLib.Variant("s", "infrastructure"),
            },
            "802-11-wireless-security": {
                "key-mgmt": GLib.Variant("s", "wpa-psk"),
                "psk": GLib.Variant("s", password),
            },
        }

        # Wrap inner dicts as a{sv}
        settings_variant_dict: dict = {}
        for section, props in conn_settings.items():
            settings_variant_dict[section] = props

        args = GLib.Variant(
            "(a{sa{sv}}oo)",
            (settings_variant_dict, self._wireless_device_path, ap_info["path"]),
        )
        call_method_async(
            self._nm_proxy,
            "AddAndActivateConnection",
            args,
            callback=lambda _res: GLib.idle_add(self._post_connect_refresh),
        )

    def _post_connect_refresh(self) -> bool:
        if not self._disposed:
            self._refresh_access_points()
            self._refresh_saved_connections()
        return GLib.SOURCE_REMOVE

    def _show_password_dialog(self, ap_info: dict) -> None:
        """Show an Adw.AlertDialog prompting for the Wi-Fi password."""
        dialog = Adw.AlertDialog(
            heading=f"Connect to {ap_info['ssid']}",
            body="Enter the password for this network.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("connect", "Connect")
        dialog.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("connect")
        dialog.set_close_response("cancel")

        # Password entry row inside a preferences group for proper styling
        group = Adw.PreferencesGroup()
        password_row = Adw.PasswordEntryRow(title="Password")
        group.add(password_row)
        dialog.set_extra_child(group)

        def on_response(_dialog, response):
            if response == "connect":
                password = password_row.get_text()
                if password:
                    self._connect_with_password(ap_info, password)

        dialog.connect("response", on_response)

        # Find the toplevel window for presenting the dialog
        if self._page is not None:
            root = self._page.get_root()
            if root is not None:
                dialog.present(root)
            else:
                dialog.present(None)

    def _on_delete_saved(self, _button: Gtk.Button, conn_path: str, conn_id: str) -> None:
        """Confirm and delete a saved connection."""
        if self._page is None:
            return

        dialog = Adw.AlertDialog(
            heading=f"Forget \u201c{conn_id}\u201d?",
            body="This network will be removed from saved connections.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("forget", "Forget")
        dialog.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response == "forget":
                conn_proxy = get_proxy(NM_BUS, conn_path, NM_SETTINGS_CONN_IFACE)
                if conn_proxy is not None:
                    call_method_async(
                        conn_proxy,
                        "Delete",
                        None,
                        callback=lambda _res: GLib.idle_add(self._refresh_saved_connections),
                    )

        dialog.connect("response", on_response)
        root = self._page.get_root()
        dialog.present(root if root is not None else None)
