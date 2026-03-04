"""Sound settings page using wpctl/pactl subprocess calls."""

from __future__ import annotations

import re
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from hyprgui.pages.base import BasePage


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def _run(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    """Run a command and return the CompletedProcess, or None on failure."""
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _check_tool(name: str) -> bool:
    """Return True if *name* is available on PATH."""
    result = _run(["which", name])
    return result is not None and result.returncode == 0


# ---------------------------------------------------------------------------
# wpctl / pactl wrappers
# ---------------------------------------------------------------------------

def _wpctl_get_volume(target: str) -> tuple[float, bool] | None:
    """Parse ``wpctl get-volume <target>``.

    Returns (volume_fraction, is_muted) or None on error.
    Example output: ``Volume: 0.50`` or ``Volume: 0.50 [MUTED]``
    """
    result = _run(["wpctl", "get-volume", target])
    if result is None or result.returncode != 0:
        return None
    m = re.search(r"Volume:\s+([\d.]+)", result.stdout)
    if not m:
        return None
    vol = float(m.group(1))
    muted = "[MUTED]" in result.stdout
    return vol, muted


def _wpctl_set_volume(target: str, fraction: float) -> bool:
    result = _run(["wpctl", "set-volume", target, f"{fraction:.2f}"])
    return result is not None and result.returncode == 0


def _wpctl_set_mute(target: str, state: bool) -> bool:
    """Set mute on/off (True = muted)."""
    val = "1" if state else "0"
    result = _run(["wpctl", "set-mute", target, val])
    return result is not None and result.returncode == 0


def _wpctl_set_default(device_id: str) -> bool:
    result = _run(["wpctl", "set-default", device_id])
    return result is not None and result.returncode == 0


def _pactl_list_devices(kind: str) -> list[tuple[str, str]]:
    """List sinks or sources via ``pactl list {kind} short``.

    Returns list of (id, name) tuples.
    """
    result = _run(["pactl", "list", kind, "short"])
    if result is None or result.returncode != 0:
        return []
    devices: list[tuple[str, str]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            devices.append((parts[0], parts[1]))
    return devices


def _pactl_get_default(kind: str) -> str | None:
    """Get default sink/source name via ``pactl get-default-{kind}``."""
    cmd = f"get-default-{kind}"
    result = _run(["pactl", cmd])
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# SoundPage
# ---------------------------------------------------------------------------

class SoundPage(BasePage):
    page_key = "sound"
    page_title = "Sound"
    page_icon = "audio-volume-high-symbolic"

    def __init__(self) -> None:
        self._page: Adw.PreferencesPage | None = None

        # Widgets — output
        self._out_vol_scale: Gtk.Scale | None = None
        self._out_vol_label: Gtk.Label | None = None
        self._out_mute_row: Adw.SwitchRow | None = None
        self._out_device_row: Adw.ComboRow | None = None
        self._out_devices: list[tuple[str, str]] = []  # (id, name)

        # Widgets — input
        self._in_vol_scale: Gtk.Scale | None = None
        self._in_vol_label: Gtk.Label | None = None
        self._in_mute_row: Adw.SwitchRow | None = None
        self._in_device_row: Adw.ComboRow | None = None
        self._in_devices: list[tuple[str, str]] = []

        # Debounce timer IDs
        self._out_vol_timer: int = 0
        self._in_vol_timer: int = 0

        # Guard against recursive signal handling
        self._updating = False

    # ------------------------------------------------------------------
    # BasePage interface
    # ------------------------------------------------------------------

    def build(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(
            title=self.page_title,
            icon_name=self.page_icon,
        )
        self._page = page

        # Check tool availability
        has_wpctl = _check_tool("wpctl")
        has_pactl = _check_tool("pactl")

        if not has_wpctl or not has_pactl:
            missing = []
            if not has_wpctl:
                missing.append("wpctl (WirePlumber)")
            if not has_pactl:
                missing.append("pactl (PulseAudio/PipeWire)")
            group = Adw.PreferencesGroup(
                title="Sound Unavailable",
                description=f"Missing required tools: {', '.join(missing)}.\n"
                "Install WirePlumber and PipeWire/PulseAudio utilities.",
            )
            page.add(group)
            return page

        # --- Output group ---
        out_group = Adw.PreferencesGroup(title="Output")

        # Volume row
        out_vol_row = Adw.ActionRow(title="Volume")
        self._out_vol_label = Gtk.Label(label="0 %", width_chars=5, xalign=1)
        self._out_vol_scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            draw_value=False,
            adjustment=Gtk.Adjustment(
                value=0, lower=0, upper=150, step_increment=1, page_increment=5
            ),
        )
        self._out_vol_scale.set_size_request(200, -1)
        self._out_vol_scale.connect("value-changed", self._on_out_vol_changed)

        vol_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        vol_box.append(self._out_vol_scale)
        vol_box.append(self._out_vol_label)
        out_vol_row.add_suffix(vol_box)
        out_group.add(out_vol_row)

        # Mute row
        self._out_mute_row = Adw.SwitchRow(title="Mute")
        self._out_mute_row.connect("notify::active", self._on_out_mute_toggled)
        out_group.add(self._out_mute_row)

        # Device selector
        self._out_device_row = Adw.ComboRow(title="Output Device")
        self._out_device_row.set_model(Gtk.StringList.new([]))
        self._out_device_row.connect("notify::selected", self._on_out_device_changed)
        out_group.add(self._out_device_row)

        page.add(out_group)

        # --- Input group ---
        in_group = Adw.PreferencesGroup(title="Input")

        in_vol_row = Adw.ActionRow(title="Volume")
        self._in_vol_label = Gtk.Label(label="0 %", width_chars=5, xalign=1)
        self._in_vol_scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            draw_value=False,
            adjustment=Gtk.Adjustment(
                value=0, lower=0, upper=150, step_increment=1, page_increment=5
            ),
        )
        self._in_vol_scale.set_size_request(200, -1)
        self._in_vol_scale.connect("value-changed", self._on_in_vol_changed)

        in_vol_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            valign=Gtk.Align.CENTER,
        )
        in_vol_box.append(self._in_vol_scale)
        in_vol_box.append(self._in_vol_label)
        in_vol_row.add_suffix(in_vol_box)
        in_group.add(in_vol_row)

        self._in_mute_row = Adw.SwitchRow(title="Mute")
        self._in_mute_row.connect("notify::active", self._on_in_mute_toggled)
        in_group.add(self._in_mute_row)

        self._in_device_row = Adw.ComboRow(title="Input Device")
        self._in_device_row.set_model(Gtk.StringList.new([]))
        self._in_device_row.connect("notify::selected", self._on_in_device_changed)
        in_group.add(self._in_device_row)

        page.add(in_group)

        return page

    def activate(self) -> None:
        """Refresh current volumes and device lists."""
        self._refresh_all()

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        # Cancel any pending timers
        if self._out_vol_timer:
            GLib.source_remove(self._out_vol_timer)
            self._out_vol_timer = 0
        if self._in_vol_timer:
            GLib.source_remove(self._in_vol_timer)
            self._in_vol_timer = 0

    def get_search_terms(self) -> list[str]:
        return ["sound", "audio", "volume", "speaker", "microphone", "output", "input"]

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        self._updating = True
        try:
            self._refresh_output()
            self._refresh_input()
        finally:
            self._updating = False

    def _refresh_output(self) -> None:
        # Volume & mute
        info = _wpctl_get_volume("@DEFAULT_AUDIO_SINK@")
        if info is not None:
            vol, muted = info
            pct = round(vol * 100)
            if self._out_vol_scale is not None:
                self._out_vol_scale.set_value(pct)
            if self._out_vol_label is not None:
                self._out_vol_label.set_label(f"{pct} %")
            if self._out_mute_row is not None:
                self._out_mute_row.set_active(muted)

        # Device list
        self._out_devices = _pactl_list_devices("sinks")
        default_name = _pactl_get_default("sink")
        if self._out_device_row is not None:
            names = [d[1] for d in self._out_devices]
            self._out_device_row.set_model(Gtk.StringList.new(names))
            # Select the default
            selected_idx = 0
            if default_name:
                for i, (_, name) in enumerate(self._out_devices):
                    if name == default_name:
                        selected_idx = i
                        break
            self._out_device_row.set_selected(selected_idx)

    def _refresh_input(self) -> None:
        info = _wpctl_get_volume("@DEFAULT_AUDIO_SOURCE@")
        if info is not None:
            vol, muted = info
            pct = round(vol * 100)
            if self._in_vol_scale is not None:
                self._in_vol_scale.set_value(pct)
            if self._in_vol_label is not None:
                self._in_vol_label.set_label(f"{pct} %")
            if self._in_mute_row is not None:
                self._in_mute_row.set_active(muted)

        self._in_devices = _pactl_list_devices("sources")
        default_name = _pactl_get_default("source")
        if self._in_device_row is not None:
            names = [d[1] for d in self._in_devices]
            self._in_device_row.set_model(Gtk.StringList.new(names))
            selected_idx = 0
            if default_name:
                for i, (_, name) in enumerate(self._in_devices):
                    if name == default_name:
                        selected_idx = i
                        break
            self._in_device_row.set_selected(selected_idx)

    # ------------------------------------------------------------------
    # Signal handlers — output
    # ------------------------------------------------------------------

    def _on_out_vol_changed(self, scale: Gtk.Scale) -> None:
        pct = round(scale.get_value())
        if self._out_vol_label is not None:
            self._out_vol_label.set_label(f"{pct} %")
        if self._updating:
            return
        # Debounce: apply after 50 ms of inactivity
        if self._out_vol_timer:
            GLib.source_remove(self._out_vol_timer)
        self._out_vol_timer = GLib.timeout_add(
            50, self._apply_out_volume, pct
        )

    def _apply_out_volume(self, pct: int) -> bool:
        self._out_vol_timer = 0
        _wpctl_set_volume("@DEFAULT_AUDIO_SINK@", pct / 100.0)
        return GLib.SOURCE_REMOVE

    def _on_out_mute_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        if self._updating:
            return
        _wpctl_set_mute("@DEFAULT_AUDIO_SINK@", row.get_active())

    def _on_out_device_changed(self, row: Adw.ComboRow, _pspec) -> None:
        if self._updating:
            return
        idx = row.get_selected()
        if idx < len(self._out_devices):
            device_id = self._out_devices[idx][0]
            _wpctl_set_default(device_id)

    # ------------------------------------------------------------------
    # Signal handlers — input
    # ------------------------------------------------------------------

    def _on_in_vol_changed(self, scale: Gtk.Scale) -> None:
        pct = round(scale.get_value())
        if self._in_vol_label is not None:
            self._in_vol_label.set_label(f"{pct} %")
        if self._updating:
            return
        if self._in_vol_timer:
            GLib.source_remove(self._in_vol_timer)
        self._in_vol_timer = GLib.timeout_add(
            50, self._apply_in_volume, pct
        )

    def _apply_in_volume(self, pct: int) -> bool:
        self._in_vol_timer = 0
        _wpctl_set_volume("@DEFAULT_AUDIO_SOURCE@", pct / 100.0)
        return GLib.SOURCE_REMOVE

    def _on_in_mute_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        if self._updating:
            return
        _wpctl_set_mute("@DEFAULT_AUDIO_SOURCE@", row.get_active())

    def _on_in_device_changed(self, row: Adw.ComboRow, _pspec) -> None:
        if self._updating:
            return
        idx = row.get_selected()
        if idx < len(self._in_devices):
            device_id = self._in_devices[idx][0]
            _wpctl_set_default(device_id)
