"""Base class for system settings pages."""

from __future__ import annotations

from abc import ABC, abstractmethod

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw


class BasePage(ABC):
    """Abstract base for dynamic system settings pages.

    Unlike registry-driven Hyprland pages, these pages manage their own
    UI, data fetching (typically via D-Bus), and lifecycle.
    """

    page_key: str       # unique identifier, e.g. "wifi"
    page_title: str     # display name, e.g. "Wi-Fi"
    page_icon: str      # symbolic icon name

    @abstractmethod
    def build(self) -> Adw.PreferencesPage:
        """Create and return the page widget. Called once at startup."""

    def activate(self) -> None:
        """Called when the page becomes visible. Start scanning, etc."""

    def deactivate(self) -> None:
        """Called when leaving the page. Pause scanning, etc."""

    def dispose(self) -> None:
        """Called on window destroy. Clean up D-Bus subscriptions."""

    def get_search_terms(self) -> list[str]:
        """Return lowercase search terms for sidebar filtering."""
        return [self.page_title.lower()]
