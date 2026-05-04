"""Visual drag-and-drop monitor layout widget."""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Gtk  # noqa: E402


SNAP_THRESHOLD_PX = 8  # widget-pixel distance within which edges snap
PADDING = 20  # px around the layout in widget space
MIN_HEIGHT = 260


@dataclass
class _Monitor:
    name: str
    description: str
    width: int  # logical px — what hyprctl reports (already post-scale)
    height: int
    x: int
    y: int
    transform: int = 0

    @property
    def display_width(self) -> int:
        """Width as it appears on screen (swap for 90/270° transforms)."""
        return self.height if self.transform in (1, 3, 5, 7) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.transform in (1, 3, 5, 7) else self.height


class MonitorLayoutWidget(Gtk.DrawingArea):
    """Drawing area that lets the user drag monitors into a layout.

    Coordinates are kept in Hyprland's "logical layout" space (the same
    integers ``hyprctl monitors`` reports for ``x``/``y``/``width``/``height``).
    The widget scales that space to fit its allocation.

    Callers wire up ``on_changed(name -> (x, y))`` to receive the new
    positions whenever the user finishes a drag.
    """

    def __init__(self, on_changed=None):
        super().__init__()
        self.set_hexpand(True)
        self.set_content_height(MIN_HEIGHT)
        self.set_draw_func(self._on_draw)

        self._monitors: list[_Monitor] = []
        self._on_changed = on_changed

        # Drag state
        self._drag_idx: int | None = None
        self._drag_start_xy: tuple[int, int] = (0, 0)  # monitor-space original pos

        # Cached layout scale.  Recomputed on draw when no drag is active;
        # frozen during a drag so the cursor stays anchored to the same point
        # on the rectangle.
        self._scale: float = 1.0
        self._origin_x: float = 0.0
        self._origin_y: float = 0.0

        # Gesture
        drag = Gtk.GestureDrag.new()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_monitors(self, monitors: list[dict]) -> None:
        """Load monitors from ``hyprctl monitors -j`` output."""
        self._monitors = [
            _Monitor(
                name=m.get("name", "?"),
                description=m.get("description", ""),
                width=int(m.get("width", 0)),
                height=int(m.get("height", 0)),
                x=int(m.get("x", 0)),
                y=int(m.get("y", 0)),
                transform=int(m.get("transform", 0)),
            )
            for m in monitors
        ]
        self.queue_draw()

    def get_positions(self) -> dict[str, tuple[int, int]]:
        """Return current positions keyed by monitor name."""
        return {m.name: (m.x, m.y) for m in self._monitors}

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _compute_scale(self, width: float, height: float) -> None:
        """Compute the scale factor that fits all monitors into the widget."""
        if not self._monitors:
            self._scale = 1.0
            self._origin_x = 0.0
            self._origin_y = 0.0
            return

        min_x = min(m.x for m in self._monitors)
        min_y = min(m.y for m in self._monitors)
        max_x = max(m.x + m.display_width for m in self._monitors)
        max_y = max(m.y + m.display_height for m in self._monitors)

        layout_w = max(1, max_x - min_x)
        layout_h = max(1, max_y - min_y)

        avail_w = max(1.0, width - 2 * PADDING)
        avail_h = max(1.0, height - 2 * PADDING)

        scale = min(avail_w / layout_w, avail_h / layout_h)
        self._scale = scale

        # Center the layout
        used_w = layout_w * scale
        used_h = layout_h * scale
        self._origin_x = (width - used_w) / 2 - min_x * scale
        self._origin_y = (height - used_h) / 2 - min_y * scale

    def _to_widget(self, mx: float, my: float) -> tuple[float, float]:
        return self._origin_x + mx * self._scale, self._origin_y + my * self._scale

    def _to_monitor(self, wx: float, wy: float) -> tuple[float, float]:
        if self._scale == 0:
            return 0.0, 0.0
        return (wx - self._origin_x) / self._scale, (wy - self._origin_y) / self._scale

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_draw(self, area, cr, width, height):
        # While dragging, keep the previously computed scale/origin so the
        # cursor stays anchored to the same point on the dragged rectangle.
        if self._drag_idx is None:
            self._compute_scale(width, height)

        # Background
        style = self.get_style_context()
        bg = style.lookup_color("view_bg_color")
        if bg[0]:
            c = bg[1]
            cr.set_source_rgb(c.red, c.green, c.blue)
        else:
            cr.set_source_rgb(0.13, 0.13, 0.13)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if not self._monitors:
            cr.set_source_rgb(0.6, 0.6, 0.6)
            cr.select_font_face("Sans")
            cr.set_font_size(14)
            text = "No monitors detected"
            ext = cr.text_extents(text)
            cr.move_to((width - ext.width) / 2, height / 2)
            cr.show_text(text)
            return

        # Accent color for active monitor
        accent = style.lookup_color("accent_bg_color")
        if accent[0]:
            ar, ag, ab = accent[1].red, accent[1].green, accent[1].blue
        else:
            ar, ag, ab = 0.21, 0.52, 0.89

        for i, m in enumerate(self._monitors):
            x, y = self._to_widget(m.x, m.y)
            w = m.display_width * self._scale
            h = m.display_height * self._scale
            is_dragging = self._drag_idx == i

            # Fill
            if is_dragging:
                cr.set_source_rgba(ar, ag, ab, 0.55)
            else:
                cr.set_source_rgba(ar, ag, ab, 0.30)
            cr.rectangle(x, y, w, h)
            cr.fill()

            # Border
            cr.set_source_rgba(ar, ag, ab, 1.0)
            cr.set_line_width(2.0)
            cr.rectangle(x, y, w, h)
            cr.stroke()

            # Label: "DP-1\n1920x1080"
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.select_font_face("Sans")
            cr.set_font_size(13)
            name_ext = cr.text_extents(m.name)
            cr.move_to(x + (w - name_ext.width) / 2, y + h / 2 - 2)
            cr.show_text(m.name)

            cr.set_font_size(10)
            res = f"{m.width}×{m.height}"
            res_ext = cr.text_extents(res)
            cr.move_to(x + (w - res_ext.width) / 2, y + h / 2 + 14)
            cr.show_text(res)

            # Position badge in the top-left
            cr.set_font_size(9)
            pos = f"({m.x}, {m.y})"
            cr.move_to(x + 4, y + 11)
            cr.show_text(pos)

    # ------------------------------------------------------------------
    # Drag handling
    # ------------------------------------------------------------------

    def _hit_test(self, wx: float, wy: float) -> int | None:
        """Return monitor index under widget-space point, top-most first."""
        for i in range(len(self._monitors) - 1, -1, -1):
            m = self._monitors[i]
            mx, my = self._to_widget(m.x, m.y)
            mw = m.display_width * self._scale
            mh = m.display_height * self._scale
            if mx <= wx <= mx + mw and my <= wy <= my + mh:
                return i
        return None

    def _on_drag_begin(self, gesture, start_x, start_y):
        idx = self._hit_test(start_x, start_y)
        if idx is None:
            self._drag_idx = None
            return
        # Move dragged monitor to top of draw order, then drag THAT index
        m = self._monitors.pop(idx)
        self._monitors.append(m)
        self._drag_idx = len(self._monitors) - 1
        # Remember the monitor's original position; drag offsets are deltas
        # from this anchor, so the cursor stays glued to the same spot on the
        # rectangle even if the widget redraws at a different scale.
        self._drag_start_xy = (m.x, m.y)
        self.set_cursor(Gdk.Cursor.new_from_name("grabbing"))
        self.queue_draw()

    def _on_drag_update(self, gesture, offset_x, offset_y):
        if self._drag_idx is None or self._scale <= 0:
            return
        # Convert the gesture's widget-pixel offset into monitor-space delta
        # using the FROZEN scale (untouched while dragging).
        dx = offset_x / self._scale
        dy = offset_y / self._scale
        start_x, start_y = self._drag_start_xy
        new_mx = int(round(start_x + dx))
        new_my = int(round(start_y + dy))

        # Hold Shift to disable snapping for fine positioning.
        snap = not self._shift_held(gesture)
        m = self._monitors[self._drag_idx]
        if snap:
            m.x, m.y = self._snap(self._drag_idx, new_mx, new_my)
        else:
            m.x, m.y = new_mx, new_my
        self.queue_draw()

    @staticmethod
    def _shift_held(gesture) -> bool:
        event = gesture.get_current_event()
        if event is None:
            return False
        return bool(event.get_modifier_state() & Gdk.ModifierType.SHIFT_MASK)

    def _on_drag_end(self, gesture, offset_x, offset_y):
        if self._drag_idx is None:
            return
        m = self._monitors[self._drag_idx]
        moved = (m.x, m.y) != self._drag_start_xy
        self._drag_idx = None
        self.set_cursor(None)
        # Refit the view now that the layout bounds may have changed
        self.queue_draw()
        if moved and self._on_changed is not None:
            self._on_changed(self.get_positions())

    # ------------------------------------------------------------------
    # Snapping: align edges with neighbors when within threshold
    # ------------------------------------------------------------------

    def _snap(self, idx: int, x: int, y: int) -> tuple[int, int]:
        m = self._monitors[idx]
        mw, mh = m.display_width, m.display_height
        # Snap within ~8 widget pixels — converted to monitor units via the
        # current (frozen-during-drag) scale so the dead zone stays visually
        # constant regardless of how zoomed-out the layout is.
        threshold = max(1, int(SNAP_THRESHOLD_PX / max(self._scale, 0.0001)))

        best_dx = threshold + 1
        best_dy = threshold + 1
        snap_x = x
        snap_y = y

        for j, other in enumerate(self._monitors):
            if j == idx:
                continue
            ow, oh = other.display_width, other.display_height
            x_candidates = [
                other.x,              # left edges align
                other.x + ow,         # our left == their right
                other.x + ow - mw,    # right edges align
                other.x - mw,         # our right == their left
            ]
            for cx in x_candidates:
                d = abs(x - cx)
                if d < best_dx:
                    best_dx = d
                    snap_x = cx

            y_candidates = [
                other.y,
                other.y + oh,
                other.y + oh - mh,
                other.y - mh,
            ]
            for cy in y_candidates:
                d = abs(y - cy)
                if d < best_dy:
                    best_dy = d
                    snap_y = cy

        return snap_x, snap_y
