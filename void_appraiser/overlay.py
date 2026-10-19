"""Overlay on top of the game: prices below the reward cards and relic info.

The overlay windows are transparent and let clicks through.
- Windows/X11: Qt places the windows itself, frameless and always on top.
- Hyprland: placement via hyprctl. While idle the overlay sits on a hidden
  special workspace, so the game has no window on top of it (otherwise no
  direct scanout). Hiding and showing again does not work, because on Wayland
  that creates a new window which steals the focus. Moves happen "silently"
  so the focus stays with the game.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

from . import capture, hypr

# Areas in the same notation as recognize.py: (x0, y0, x1, y1, scale, anchor)
REWARDS_AREA = (0.08, 0.525, 0.92, 0.59, 1.0, "center")  # below the player names of the cards (up to 2 lines)
RELIC_AREA = (0.30, 0.625, 0.70, 0.70, 1.0, "center")  # below the equip dialog
HINT_AREA = (0.33, 0.06, 0.67, 0.105, 1.0, "center")  # top center, between header and account balance

BG = QColor(12, 18, 28, 225)
BEST_BG = QColor(45, 106, 79, 240)
HINT_BG = QColor(170, 30, 30, 235)
TEXT = QColor(235, 235, 235)
ACCENT = QColor(232, 197, 71)


@dataclass(frozen=True)
class Item:
    x: float  # center relative to the window width (0 to 1)
    lines: tuple[str, ...]
    best: bool = False
    bg: QColor | None = None  # custom background color (e.g. red hint)


class OverlayPanel(QWidget):
    def __init__(self, title: str):
        super().__init__(None)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.items: list[Item] = []
        self.full_width = False  # one wide box instead of separate boxes

    def set_items(self, items: list[Item], full_width: bool = False) -> None:
        if items == self.items and full_width == self.full_width:
            return  # nothing changed, do not repaint
        self.items = items
        self.full_width = full_width
        self.update()

    def paintEvent(self, event) -> None:
        if not self.items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        font = QFont()
        font.setPixelSize(max(10, int(h * 0.30)))
        font.setBold(True)
        small = QFont(font)
        small.setPixelSize(max(9, int(h * 0.24)))
        small.setBold(False)
        for item in self.items:
            fonts = [font] + [small] * (len(item.lines) - 1)
            widths = [QFontMetrics(f).horizontalAdvance(t) for f, t in zip(fonts, item.lines)]
            pad = h * 0.18
            if self.full_width:
                box_w = self.width() - 2
            else:
                box_w = min(max(widths) + 2 * pad, self.width() / max(1, len(self.items)) * 0.95)
            cx = item.x * self.width()
            rect = QRectF(cx - box_w / 2, 1, box_w, h - 2)
            rect.moveLeft(max(1, min(rect.left(), self.width() - box_w - 1)))
            path = QPainterPath()
            path.addRoundedRect(rect, h * 0.15, h * 0.15)
            p.fillPath(path, item.bg or (BEST_BG if item.best else BG))
            line_h = (h - 2 * pad * 0.5) / len(item.lines)
            for i, (f, text) in enumerate(zip(fonts, item.lines)):
                p.setFont(f)
                p.setPen(ACCENT if i == 0 and not item.best else TEXT)
                line_rect = QRectF(rect.left(), pad * 0.5 + i * line_h, rect.width(), line_h)
                p.drawText(line_rect, Qt.AlignCenter, text)
        p.end()


def _game_area(monitor_name: str) -> tuple[capture.Rect, str | None]:
    """Area of the game in screen coordinates and the monitor name (Hyprland)."""
    be = capture.backend()
    rect = None
    monitor = None
    if not monitor_name:
        window = be.game_window()
        if window:
            rect = window.rect
    mons = be.monitors()
    for mon in mons:
        if monitor_name and mon.name == monitor_name:
            rect = mon.rect
        if rect and mon.rect.x <= rect.x + rect.w // 2 < mon.rect.x + mon.rect.w and mon.rect.y <= rect.y + rect.h // 2 < mon.rect.y + mon.rect.h:
            monitor = mon.name
    if rect is None:
        screen = QApplication.primaryScreen().geometry()
        rect = capture.Rect(screen.x(), screen.y(), screen.width(), screen.height())
    if sys.platform == "win32":
        # Win32 reports physical pixels, Qt works with logical ones
        ratio = QApplication.primaryScreen().devicePixelRatio()
        return capture.Rect(int(rect.x / ratio), int(rect.y / ratio), int(rect.w / ratio), int(rect.h / ratio)), None
    return rect, monitor


class OverlayManager:
    def __init__(self, monitor_name: str = ""):
        self.monitor_name = monitor_name
        self.enabled = True
        self.use_hypr = isinstance(capture.backend(), capture.HyprlandBackend)
        # PID in the title so two running instances do not get in each other's way
        pid = os.getpid()
        self.rewards = OverlayPanel(f"Void Appraiser Overlay Rewards {pid}")
        self.relic = OverlayPanel(f"Void Appraiser Overlay Relic {pid}")
        self.hint = OverlayPanel(f"Void Appraiser Overlay Hint {pid}")
        self._hint_text = ""
        self._hint_timer = QTimer()
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(self._hint_flash_over)
        self._addresses: dict[OverlayPanel, str] = {}
        self._relic_timer = QTimer()
        self._relic_timer.setSingleShot(True)
        self._relic_timer.timeout.connect(lambda: self._hide(self.relic))
        self._reward_timer = QTimer()
        self._reward_timer.setSingleShot(True)
        self._reward_timer.timeout.connect(lambda: self._hide(self.rewards))
        if self.use_hypr:
            self._previous_focus = hypr.active_window()
            for panel in self._panels():
                panel.resize(10, 10)
                panel.show()
            self._setup_tries = 0
            QTimer.singleShot(50, self._hypr_setup)

    # --- Hyprland: set up the windows once -----------------------------------

    def _hypr_setup(self) -> None:
        for panel in self._panels():
            if panel not in self._addresses:
                address = hypr.find_window(panel.windowTitle())
                if address:
                    self._addresses[panel] = address
                    hypr.setup_overlay(address)
                    self._park(panel)
        self._setup_tries += 1
        if len(self._addresses) < len(self._panels()) and self._setup_tries < 40:
            QTimer.singleShot(50, self._hypr_setup)
            return
        # Give back the focus the new window received when it opened
        if self._previous_focus:
            hypr.focus(self._previous_focus)

    def _park(self, panel: OverlayPanel) -> None:
        address = self._addresses.get(panel)
        if address:
            hypr.park(address)

    # --- Showing and hiding -------------------------------------------------

    def _show(self, panel: OverlayPanel, area: tuple) -> None:
        from .recognize import region_rect

        game, monitor = _game_area(self.monitor_name)
        rx, ry, w, h = region_rect(game.w, game.h, area)
        x, y = game.x + rx, game.y + ry
        if self.use_hypr:
            address = self._addresses.get(panel)
            if address and monitor:
                hypr.place(address, monitor, x, y, w, h)
            panel.resize(w, h)
        else:
            panel.setGeometry(x, y, w, h)
            panel.show()

    def _hide(self, panel: OverlayPanel) -> None:
        panel.set_items([])
        if self.use_hypr:
            self._park(panel)
        else:
            panel.hide()

    def show_rewards(self, items: list[Item]) -> None:
        if not self.enabled or not items:
            return
        self.rewards.set_items(items)
        if not self._reward_timer.isActive():
            self._show(self.rewards, REWARDS_AREA)
        # Safety net in case the end of the screen is missed
        self._reward_timer.start(25_000)

    def hide_rewards(self) -> None:
        self._reward_timer.stop()
        self._hide(self.rewards)

    def show_relic(self, lines: tuple[str, ...], seconds: float = 5.0) -> None:
        if not self.enabled:
            return
        self.relic.set_items([Item(0.5, lines)], full_width=True)
        if not self._relic_timer.isActive():
            self._show(self.relic, RELIC_AREA)
        self._relic_timer.start(int(seconds * 1000))

    def _panels(self) -> tuple[OverlayPanel, ...]:
        return (self.rewards, self.relic, self.hint)

    # --- Red hint at the top (inventory) ------------------------------------

    def show_hint(self, text: str) -> None:
        """Permanent hint until hide_hint() is called."""
        self._hint_text = text
        if not self._hint_timer.isActive():
            self._set_hint(text)

    def flash_hint(self, text: str, seconds: float = 4.0) -> None:
        """Short message, then back to the permanent hint (if still active)."""
        self._set_hint(text, QColor(45, 106, 79, 240))
        self._hint_timer.start(int(seconds * 1000))

    def hide_hint(self) -> None:
        self._hint_text = ""
        if not self._hint_timer.isActive():
            self._hide(self.hint)

    def _hint_flash_over(self) -> None:
        if self._hint_text:
            self._set_hint(self._hint_text)
        else:
            self._hide(self.hint)

    def _set_hint(self, text: str, color: QColor = HINT_BG) -> None:
        if not self.enabled:
            return
        was_visible = bool(self.hint.items)
        self.hint.set_items([Item(0.5, (text,), bg=color)], full_width=True)
        if not was_visible:
            self._show(self.hint, HINT_AREA)

    def hide_all(self) -> None:
        self._relic_timer.stop()
        self.hide_rewards()
        self._hide(self.relic)
        self._hint_timer.stop()
        self._hint_text = ""
        self._hide(self.hint)

    def close(self) -> None:
        self.rewards.close()
        self.relic.close()
        self.hint.close()
