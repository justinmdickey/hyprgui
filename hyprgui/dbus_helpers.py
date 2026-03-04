"""Shared D-Bus utilities for system settings pages."""

from __future__ import annotations

from gi.repository import Gio, GLib


def get_proxy(
    bus_name: str,
    object_path: str,
    interface_name: str,
    bus_type: Gio.BusType = Gio.BusType.SYSTEM,
) -> Gio.DBusProxy | None:
    """Create a synchronous D-Bus proxy, returning None on failure."""
    try:
        return Gio.DBusProxy.new_for_bus_sync(
            bus_type,
            Gio.DBusProxyFlags.NONE,
            None,
            bus_name,
            object_path,
            interface_name,
            None,
        )
    except GLib.Error:
        return None


def get_proxy_async(
    bus_name: str,
    object_path: str,
    interface_name: str,
    callback,
    bus_type: Gio.BusType = Gio.BusType.SYSTEM,
) -> None:
    """Create an async D-Bus proxy, calling callback(proxy_or_None)."""
    def _on_ready(_source, result):
        try:
            proxy = Gio.DBusProxy.new_for_bus_finish(result)
            callback(proxy)
        except GLib.Error:
            callback(None)

    Gio.DBusProxy.new_for_bus(
        bus_type,
        Gio.DBusProxyFlags.NONE,
        None,
        bus_name,
        object_path,
        interface_name,
        None,
        _on_ready,
    )


def get_property(proxy: Gio.DBusProxy, prop_name: str):
    """Get a cached property value from a proxy, unpacking the variant."""
    variant = proxy.get_cached_property(prop_name)
    if variant is None:
        return None
    return variant.unpack()


def call_method(
    proxy: Gio.DBusProxy,
    method: str,
    args: GLib.Variant | None = None,
    timeout: int = -1,
) -> GLib.Variant | None:
    """Call a D-Bus method synchronously, returning result or None on error."""
    try:
        return proxy.call_sync(method, args, Gio.DBusCallFlags.NONE, timeout, None)
    except GLib.Error:
        return None


def call_method_async(
    proxy: Gio.DBusProxy,
    method: str,
    args: GLib.Variant | None = None,
    callback=None,
    timeout: int = -1,
) -> None:
    """Call a D-Bus method asynchronously."""
    def _on_ready(_proxy, result):
        try:
            res = proxy.call_finish(result)
        except GLib.Error:
            res = None
        if callback:
            callback(res)

    proxy.call(method, args, Gio.DBusCallFlags.NONE, timeout, None, _on_ready)


def subscribe_signal(
    connection: Gio.DBusConnection,
    bus_name: str,
    object_path: str | None,
    interface_name: str,
    signal_name: str | None,
    callback,
) -> int:
    """Subscribe to a D-Bus signal, returning the subscription ID."""
    return connection.signal_subscribe(
        bus_name,
        interface_name,
        signal_name,
        object_path,
        None,
        Gio.DBusSignalFlags.NONE,
        callback,
    )
