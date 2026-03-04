"""AdwActionRow + GtkColorDialogButton helper for color settings."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk


def hex_to_rgba(hex_str: str) -> Gdk.RGBA:
    """Convert RRGGBBAA hex string to Gdk.RGBA."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        hex_str += "ff"
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    a = int(hex_str[6:8], 16) / 255.0
    rgba = Gdk.RGBA()
    rgba.red = r
    rgba.green = g
    rgba.blue = b
    rgba.alpha = a
    return rgba


def rgba_to_hex(rgba: Gdk.RGBA) -> str:
    """Convert Gdk.RGBA to RRGGBBAA hex string."""
    r = max(0, min(255, int(rgba.red * 255)))
    g = max(0, min(255, int(rgba.green * 255)))
    b = max(0, min(255, int(rgba.blue * 255)))
    a = max(0, min(255, int(rgba.alpha * 255)))
    return f"{r:02x}{g:02x}{b:02x}{a:02x}"


def create_color_row(label: str, initial_hex: str, on_change) -> tuple[Adw.ActionRow, Gtk.ColorDialogButton]:
    """Create an AdwActionRow with a ColorDialogButton suffix.

    Args:
        label: Row label text.
        initial_hex: Initial color as RRGGBBAA hex.
        on_change: Callback(hex_str) called when color changes.

    Returns:
        (row, button) tuple.
    """
    row = Adw.ActionRow(title=label)

    dialog = Gtk.ColorDialog()
    dialog.set_with_alpha(True)

    button = Gtk.ColorDialogButton(dialog=dialog)
    button.set_rgba(hex_to_rgba(initial_hex))
    button.set_valign(Gtk.Align.CENTER)

    def _on_notify_rgba(btn, _pspec):
        on_change(rgba_to_hex(btn.get_rgba()))

    button.connect("notify::rgba", _on_notify_rgba)

    row.add_suffix(button)
    row.set_activatable_widget(button)

    return row, button
