"""Hyprgui — GTK4 settings app for Hyprland."""

from __future__ import annotations

import shutil
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from hyprgui.persistence import is_linked, link, link_prompt_text


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

        # First-run: offer to link our managed file from the user's main config.
        # Mode-aware: Lua → dofile into hyprland.lua; legacy → source into hyprland.conf.
        if not is_linked():
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
        heading, body = link_prompt_text()
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", "Not Now")
        dialog.add_response("add", "Link")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("add")
        dialog.set_close_response("cancel")

        dialog.connect("response", self._on_first_run_response, parent)
        dialog.present(parent)

    def _on_first_run_response(self, _dialog, response: str, parent) -> None:
        if response == "add":
            try:
                link()
                from hyprgui.hyprctl import reload_config
                reload_config()
                from hyprgui.config_mode import HYPRLAND_CONF, HYPRLAND_LUA, detect_mode, ConfigMode
                target = HYPRLAND_LUA.name if detect_mode() is ConfigMode.LUA else HYPRLAND_CONF.name
                parent.add_toast(Adw.Toast(title=f"Hyprgui linked into {target}"))
            except OSError as e:
                err = Adw.AlertDialog(
                    heading="Error",
                    body=f"Could not modify your Hyprland config:\n{e}",
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
