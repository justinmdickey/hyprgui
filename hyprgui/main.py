"""Hyprgui — GTK4 settings app for Hyprland."""

from __future__ import annotations

import shutil
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from hyprgui.config_manager import append_source_line, is_source_line_present


class HyprguiApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.github.hyprgui")

        action = Gio.SimpleAction(name="about")
        action.connect("activate", self._show_about)
        self.add_action(action)

    def do_activate(self):
        from hyprgui.window import HyprguiWindow

        self._has_hyprctl = bool(shutil.which("hyprctl"))

        win = HyprguiWindow(app=self)
        win.present()

        if not self._has_hyprctl:
            toast = Adw.Toast(title="hyprctl not found — Hyprland settings unavailable")
            toast.set_timeout(5)
            win.add_toast(toast)
            return

        # First-run: offer to add source line
        if not is_source_line_present():
            self._show_first_run_dialog(win)

    def _show_missing_hyprctl_dialog(self) -> None:
        dialog = Adw.AlertDialog(
            heading="Hyprland Not Found",
            body=(
                "Could not find hyprctl. Hyprland may not be installed "
                "or not running.\n\n"
                "Hyprgui requires Hyprland to function."
            ),
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")

        # Need a temporary window to present the dialog
        win = Adw.ApplicationWindow(application=self)
        win.set_default_size(0, 0)
        win.present()
        dialog.connect("response", lambda *_: self.quit())
        dialog.present(win)

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

    def _show_about(self, _action, _param) -> None:
        about = Adw.AboutDialog(
            application_name="Hyprgui",
            application_icon="preferences-system-symbolic",
            version="0.1.0",
            developer_name="hyprgui contributors",
            developers=["hyprgui contributors"],
        )
        win = self.get_active_window()
        if win:
            about.present(win)


def main():
    app = HyprguiApp()
    app.run(sys.argv)
