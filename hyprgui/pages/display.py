"""Display settings page — per-monitor resolution, scale, transform, VRR."""

from __future__ import annotations

import json
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from hyprgui.persistence import upsert_monitors as upsert_managed_monitors  # noqa: E402
from hyprgui.pages.base import BasePage  # noqa: E402
from hyprgui.widgets.monitor_layout import MonitorLayoutWidget  # noqa: E402

TRANSFORM_LABELS = [
    "Normal",
    "90\u00b0",
    "180\u00b0",
    "270\u00b0",
    "Flipped",
    "Flipped 90\u00b0",
    "Flipped 180\u00b0",
    "Flipped 270\u00b0",
]


def _get_monitors() -> list[dict]:
    """Return parsed JSON from ``hyprctl monitors -j``, or [] on failure."""
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _apply_monitor(name: str, width: int, height: int, refresh: float,
                   x: int, y: int, scale: float) -> bool:
    """Apply resolution, position, and scale via ``hyprctl keyword monitor``."""
    spec = f"{name},{width}x{height}@{refresh:.2f},{x}x{y},{scale}"
    try:
        result = subprocess.run(
            ["hyprctl", "keyword", "monitor", spec],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _build_monitor_spec(name: str, width: int, height: int, refresh: float,
                        x: int, y: int, scale: float, transform: int = 0) -> str:
    """Build a Hyprland-config-format monitor spec string (without the leading 'monitor =')."""
    spec = f"{name},{width}x{height}@{refresh:.2f},{x}x{y},{scale}"
    if transform:
        spec += f",transform,{transform}"
    return spec


def _apply_transform(name: str, transform: int) -> bool:
    """Apply a transform value via ``hyprctl keyword monitor``."""
    spec = f"{name},transform,{transform}"
    try:
        result = subprocess.run(
            ["hyprctl", "keyword", "monitor", spec],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _apply_vrr(name: str, enabled: bool) -> bool:
    """Toggle VRR (adaptive sync) for a monitor."""
    val = "1" if enabled else "0"
    try:
        result = subprocess.run(
            ["hyprctl", "keyword", "misc:vrr", val],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _parse_mode(mode_str: str) -> tuple[int, int, float] | None:
    """Parse ``'1920x1080@60.00Hz'`` into ``(1920, 1080, 60.0)``."""
    try:
        res_part, hz_part = mode_str.split("@")
        w, h = res_part.split("x")
        refresh = float(hz_part.rstrip("Hz"))
        return int(w), int(h), refresh
    except (ValueError, AttributeError):
        return None


class DisplayPage(BasePage):
    """Per-monitor display settings (resolution, scale, transform, VRR)."""

    page_key = "display"
    page_title = "Display"
    page_icon = "video-display-symbolic"

    def __init__(self) -> None:
        self._page: Adw.PreferencesPage | None = None
        # Per-monitor widget references, keyed by monitor name.
        self._widgets: dict[str, dict] = {}
        # Track groups we've added so we can remove them
        self._groups: list[Adw.PreferencesGroup] = []
        # Suppress handler signals during programmatic updates.
        self._updating = False
        # Visual layout widget + pending position changes
        self._layout_widget: MonitorLayoutWidget | None = None
        self._layout_apply_btn: Gtk.Button | None = None
        self._layout_reset_btn: Gtk.Button | None = None
        self._pending_positions: dict[str, tuple[int, int]] = {}

    # ------------------------------------------------------------------
    # BasePage interface
    # ------------------------------------------------------------------

    def build(self) -> Adw.PreferencesPage:
        self._page = Adw.PreferencesPage.new()
        self._page.set_title(self.page_title)
        self._page.set_icon_name(self.page_icon)
        self._populate()
        return self._page

    def activate(self) -> None:
        self._populate()

    def deactivate(self) -> None:
        pass

    def get_search_terms(self) -> list[str]:
        return ["display", "monitor", "resolution", "scale", "transform",
                "vrr", "adaptive sync", "refresh"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        """Rebuild all preference groups from live monitor data."""
        if self._page is None:
            return

        # Remove existing groups
        for grp in self._groups:
            self._page.remove(grp)
        self._groups.clear()
        self._widgets.clear()

        monitors = _get_monitors()
        if not monitors:
            group = Adw.PreferencesGroup.new()
            group.set_title("No monitors detected")
            group.set_description(
                "Could not query Hyprland. Is hyprctl available?"
            )
            self._page.add(group)
            self._groups.append(group)
            return

        self._add_layout_group(monitors)
        for mon in monitors:
            self._add_monitor_group(mon)

    def _add_layout_group(self, monitors: list[dict]) -> None:
        """Add the visual drag-and-drop layout group at the top."""
        group = Adw.PreferencesGroup.new()
        group.set_title("Layout")
        group.set_description(
            "Drag monitors to arrange them. Edges snap to neighbors — "
            "hold Shift while dragging to disable snapping."
        )

        layout = MonitorLayoutWidget(on_changed=self._on_layout_changed)
        layout.set_monitors(monitors)
        layout.add_css_class("card")
        self._layout_widget = layout

        apply_btn = Gtk.Button(label="Apply Layout")
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_sensitive(False)
        apply_btn.connect("clicked", self._on_apply_layout)
        self._layout_apply_btn = apply_btn

        reset_btn = Gtk.Button(label="Revert")
        reset_btn.set_sensitive(False)
        reset_btn.connect("clicked", self._on_revert_layout)
        self._layout_reset_btn = reset_btn

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)
        btn_box.append(reset_btn)
        btn_box.append(apply_btn)

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.append(layout)
        container.append(btn_box)
        group.add(container)

        self._page.add(group)
        self._groups.append(group)
        self._pending_positions = {}

    def _on_layout_changed(self, positions: dict[str, tuple[int, int]]) -> None:
        """Called when the user drops a monitor at a new spot."""
        self._pending_positions = positions
        if self._layout_apply_btn is not None:
            self._layout_apply_btn.set_sensitive(True)
        if self._layout_reset_btn is not None:
            self._layout_reset_btn.set_sensitive(True)

    def _on_apply_layout(self, _btn: Gtk.Button) -> None:
        """Apply positions live AND persist them to hyprgui.conf."""
        if not self._pending_positions:
            return
        updates: dict[str, str] = {}
        for mon in _get_monitors():
            name = mon.get("name", "")
            if name not in self._pending_positions:
                continue
            new_x, new_y = self._pending_positions[name]
            if (new_x, new_y) == (mon.get("x", 0), mon.get("y", 0)):
                continue
            w = mon.get("width", 0)
            h = mon.get("height", 0)
            hz = mon.get("refreshRate", 0.0)
            scale = mon.get("scale", 1.0)
            transform = mon.get("transform", 0)
            _apply_monitor(name, w, h, hz, new_x, new_y, scale)
            updates[name] = _build_monitor_spec(name, w, h, hz, new_x, new_y, scale, transform)
        if updates:
            upsert_managed_monitors(updates)
        # Refresh the whole page so positions and the layout view reflect reality
        self._populate()

    def _on_revert_layout(self, _btn: Gtk.Button) -> None:
        """Discard pending drag changes and reload from hyprctl."""
        self._populate()

    def _add_monitor_group(self, mon: dict) -> None:
        """Create an Adw.PreferencesGroup for a single monitor."""
        name: str = mon.get("name", "unknown")
        description: str = mon.get("description", "")
        cur_width: int = mon.get("width", 0)
        cur_height: int = mon.get("height", 0)
        cur_refresh: float = mon.get("refreshRate", 0.0)
        cur_scale: float = mon.get("scale", 1.0)
        cur_transform: int = mon.get("transform", 0)
        pos_x: int = mon.get("x", 0)
        pos_y: int = mon.get("y", 0)
        available_modes: list[str] = mon.get("availableModes", [])
        vrr_mode: int = mon.get("vrr", 0)

        group = Adw.PreferencesGroup.new()
        title = name
        if description:
            # Take just the first meaningful part of the description.
            short_desc = description.split(" (")[0] if " (" in description else description
            title = f"{name} \u2014 {short_desc}"
        group.set_title(title)

        widgets: dict = {}

        # -- Resolution ComboRow ------------------------------------------
        mode_strings: list[str] = []
        active_idx = 0
        for mode_raw in available_modes:
            parsed = _parse_mode(mode_raw)
            if parsed is None:
                continue
            w, h, hz = parsed
            label = f"{w}x{h}@{hz:.2f}Hz"
            mode_strings.append(label)
            if w == cur_width and h == cur_height and abs(hz - cur_refresh) < 0.5:
                active_idx = len(mode_strings) - 1

        string_list = Gtk.StringList.new(mode_strings)
        res_row = Adw.ComboRow.new()
        res_row.set_title("Resolution")
        res_row.set_model(string_list)
        if mode_strings:
            res_row.set_selected(active_idx)
        res_row.connect("notify::selected", self._on_resolution_changed, name)
        group.add(res_row)
        widgets["resolution"] = res_row
        widgets["modes"] = mode_strings

        # -- Scale SpinRow ------------------------------------------------
        scale_adj = Gtk.Adjustment.new(cur_scale, 0.5, 3.0, 0.25, 0.5, 0)
        scale_row = Adw.SpinRow.new(scale_adj, 0.25, 2)
        scale_row.set_title("Scale")
        scale_row.connect("notify::value", self._on_scale_changed, name)
        group.add(scale_row)
        widgets["scale"] = scale_row

        # -- Transform ComboRow -------------------------------------------
        transform_list = Gtk.StringList.new(TRANSFORM_LABELS)
        transform_row = Adw.ComboRow.new()
        transform_row.set_title("Transform")
        transform_row.set_model(transform_list)
        transform_row.set_selected(cur_transform if 0 <= cur_transform <= 7 else 0)
        transform_row.connect("notify::selected", self._on_transform_changed, name)
        group.add(transform_row)
        widgets["transform"] = transform_row

        # -- VRR SwitchRow ------------------------------------------------
        vrr_row = Adw.SwitchRow.new()
        vrr_row.set_title("VRR (Adaptive Sync)")
        vrr_row.set_active(vrr_mode != 0)
        vrr_row.connect("notify::active", self._on_vrr_changed, name)
        group.add(vrr_row)
        widgets["vrr"] = vrr_row

        # -- Position ActionRow (read-only) --------------------------------
        pos_row = Adw.ActionRow.new()
        pos_row.set_title("Position")
        pos_row.set_subtitle(f"{pos_x}, {pos_y}")
        pos_row.set_activatable(False)
        group.add(pos_row)
        widgets["position"] = pos_row

        self._widgets[name] = widgets
        self._page.add(group)
        self._groups.append(group)

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _current_monitor_params(self, name: str) -> dict | None:
        """Re-query a single monitor's live state."""
        for mon in _get_monitors():
            if mon.get("name") == name:
                return mon
        return None

    def _persist_monitor(self, name: str, *, width: int, height: int,
                         refresh: float, x: int, y: int, scale: float,
                         transform: int) -> None:
        """Write the current spec for ``name`` to hyprgui.conf."""
        spec = _build_monitor_spec(name, width, height, refresh, x, y, scale, transform)
        upsert_managed_monitors({name: spec})

    def _on_resolution_changed(self, row: Adw.ComboRow, _pspec, name: str) -> None:
        if self._updating:
            return
        idx = row.get_selected()
        modes = self._widgets.get(name, {}).get("modes", [])
        if idx >= len(modes):
            return
        parsed = _parse_mode(modes[idx])
        if parsed is None:
            return
        w, h, hz = parsed

        mon = self._current_monitor_params(name)
        if mon is None:
            return
        scale = self._widgets[name]["scale"].get_value()
        _apply_monitor(name, w, h, hz, mon.get("x", 0), mon.get("y", 0), scale)
        self._persist_monitor(
            name, width=w, height=h, refresh=hz,
            x=mon.get("x", 0), y=mon.get("y", 0),
            scale=scale, transform=mon.get("transform", 0),
        )

    def _on_scale_changed(self, row: Adw.SpinRow, _pspec, name: str) -> None:
        if self._updating:
            return
        scale = row.get_value()
        mon = self._current_monitor_params(name)
        if mon is None:
            return
        _apply_monitor(
            name,
            mon.get("width", 0),
            mon.get("height", 0),
            mon.get("refreshRate", 0.0),
            mon.get("x", 0),
            mon.get("y", 0),
            scale,
        )
        self._persist_monitor(
            name, width=mon.get("width", 0), height=mon.get("height", 0),
            refresh=mon.get("refreshRate", 0.0),
            x=mon.get("x", 0), y=mon.get("y", 0),
            scale=scale, transform=mon.get("transform", 0),
        )

    def _on_transform_changed(self, row: Adw.ComboRow, _pspec, name: str) -> None:
        if self._updating:
            return
        transform = row.get_selected()
        _apply_transform(name, transform)
        mon = self._current_monitor_params(name)
        if mon is None:
            return
        self._persist_monitor(
            name, width=mon.get("width", 0), height=mon.get("height", 0),
            refresh=mon.get("refreshRate", 0.0),
            x=mon.get("x", 0), y=mon.get("y", 0),
            scale=mon.get("scale", 1.0), transform=transform,
        )

    def _on_vrr_changed(self, row: Adw.SwitchRow, _pspec, name: str) -> None:
        if self._updating:
            return
        _apply_vrr(name, row.get_active())
