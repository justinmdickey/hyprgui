"""Hyprgui — GTK4 settings app for Hyprland."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from hyprgui.config_manager import append_source_line, is_source_line_present


class HyprguiApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.github.hyprgui")

    def do_activate(self):
        from hyprgui.window import HyprguiWindow

        win = HyprguiWindow(app=self)
        win.present()

        # First-run: offer to add source line
        if not is_source_line_present():
            self._show_first_run_dialog(win)

    def _show_first_run_dialog(self, parent: Gtk.Window) -> None:
        dialog = Adw.AlertDialog(
            heading="First-Time Setup",
            body=(
                "Hyprgui needs to add a source line to your hyprland.conf "
                "so saved settings persist across restarts.\n\n"
                "This will append:\n"
                "  source = ~/.config/hypr/hyprgui.conf\n\n"
                "You can remove it at any time."
            ),
        )
        dialog.add_response("cancel", "Not Now")
        dialog.add_response("add", "Add Source Line")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")

        dialog.connect("response", self._on_first_run_response, parent)
        dialog.present(parent)

    def _on_first_run_response(self, _dialog, response: str, parent) -> None:
        if response == "add":
            try:
                append_source_line()
                from hyprgui.hyprctl import reload_config
                reload_config()
                toast = Adw.Toast(title="Source line added to hyprland.conf")
                parent.add_toast(toast)
            except OSError as e:
                err = Adw.AlertDialog(
                    heading="Error",
                    body=f"Could not modify hyprland.conf:\n{e}",
                )
                err.add_response("ok", "OK")
                err.present(parent)


def main():
    app = HyprguiApp()
    app.run(sys.argv)
