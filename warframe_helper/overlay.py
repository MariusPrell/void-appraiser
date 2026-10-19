"""Overlay über dem Spiel: Preise unter den Belohnungskarten und Infos zum Relikt.

Die Overlay-Fenster sind durchsichtig und lassen Klicks durch.
- Windows/X11: Qt platziert die Fenster selbst, rahmenlos und immer im Vordergrund.
- Hyprland: Platzierung per hyprctl. Im Leerlauf liegt das Overlay auf einem
  versteckten Spezial-Arbeitsbereich, damit das Spiel kein Fenster über sich hat
  (sonst kein Direct Scanout). Verstecken und wieder Zeigen geht nicht, weil das
  unter Wayland ein neues Fenster erzeugt, das den Fokus klaut. Das Verschieben
  passiert "silent", damit der Fokus beim Spiel bleibt.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

from . import capture, hypr

# Bereiche relativ zur 16:9-Fläche des Spiels (x0, y0, x1, y1)
REWARDS_AREA = (0.08, 0.525, 0.92, 0.59)  # unter den Spielernamen der Karten (bis zu 2 Zeilen)
RELIC_AREA = (0.30, 0.625, 0.70, 0.70)  # unter dem Ausrüsten-Dialog

BG = QColor(12, 18, 28, 225)
BEST_BG = QColor(45, 106, 79, 240)
TEXT = QColor(235, 235, 235)
ACCENT = QColor(232, 197, 71)


@dataclass(frozen=True)
class Item:
    x: float  # Mitte relativ zur Fensterbreite (0 bis 1)
    lines: tuple[str, ...]
    best: bool = False


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
        self.full_width = False  # ein breites Feld statt einzelner Kästen

    def set_items(self, items: list[Item], full_width: bool = False) -> None:
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
            p.fillPath(path, BEST_BG if item.best else BG)
            line_h = (h - 2 * pad * 0.5) / len(item.lines)
            for i, (f, text) in enumerate(zip(fonts, item.lines)):
                p.setFont(f)
                p.setPen(ACCENT if i == 0 and not item.best else TEXT)
                line_rect = QRectF(rect.left(), pad * 0.5 + i * line_h, rect.width(), line_h)
                p.drawText(line_rect, Qt.AlignCenter, text)
        p.end()


def _game_area(monitor_name: str) -> tuple[capture.Rect, str | None]:
    """16:9-Fläche des Spiels in Bildschirmkoordinaten und der Monitorname (Hyprland)."""
    from .recognize import ui_area

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
    ax, ay, aw, ah = ui_area(rect.w, rect.h)
    if sys.platform == "win32":
        # Win32 liefert physische Pixel, Qt arbeitet mit logischen
        ratio = QApplication.primaryScreen().devicePixelRatio()
        return capture.Rect(int((rect.x + ax) / ratio), int((rect.y + ay) / ratio), int(aw / ratio), int(ah / ratio)), None
    return capture.Rect(rect.x + ax, rect.y + ay, aw, ah), monitor


class OverlayManager:
    def __init__(self, monitor_name: str = ""):
        self.monitor_name = monitor_name
        self.enabled = True
        self.use_hypr = isinstance(capture.backend(), capture.HyprlandBackend)
        # PID im Titel, damit sich zwei laufende Instanzen nicht in die Quere kommen
        pid = os.getpid()
        self.rewards = OverlayPanel(f"Warframe Helper Overlay Belohnungen {pid}")
        self.relic = OverlayPanel(f"Warframe Helper Overlay Relikt {pid}")
        self._addresses: dict[OverlayPanel, str] = {}
        self._relic_timer = QTimer()
        self._relic_timer.setSingleShot(True)
        self._relic_timer.timeout.connect(lambda: self._hide(self.relic))
        self._reward_timer = QTimer()
        self._reward_timer.setSingleShot(True)
        self._reward_timer.timeout.connect(lambda: self._hide(self.rewards))
        if self.use_hypr:
            self._previous_focus = hypr.active_window()
            for panel in (self.rewards, self.relic):
                panel.resize(10, 10)
                panel.show()
            self._setup_tries = 0
            QTimer.singleShot(50, self._hypr_setup)

    # --- Hyprland: Fenster einmalig einrichten ----------------------------

    def _hypr_setup(self) -> None:
        for panel in (self.rewards, self.relic):
            if panel not in self._addresses:
                address = hypr.find_window(panel.windowTitle())
                if address:
                    self._addresses[panel] = address
                    hypr.setup_overlay(address)
                    self._park(panel)
        self._setup_tries += 1
        if len(self._addresses) < 2 and self._setup_tries < 40:
            QTimer.singleShot(50, self._hypr_setup)
            return
        # Den Fokus zurückgeben, den das neue Fenster beim Öffnen bekommen hat
        if self._previous_focus:
            hypr.focus(self._previous_focus)

    def _park(self, panel: OverlayPanel) -> None:
        address = self._addresses.get(panel)
        if address:
            hypr.park(address)

    # --- Anzeigen und Verstecken ------------------------------------------

    def _show(self, panel: OverlayPanel, area: tuple[float, float, float, float]) -> None:
        game, monitor = _game_area(self.monitor_name)
        x0, y0, x1, y1 = area
        x = game.x + int(x0 * game.w)
        y = game.y + int(y0 * game.h)
        w = int((x1 - x0) * game.w)
        h = int((y1 - y0) * game.h)
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
        # Sicherheitsnetz, falls das Ende des Bildschirms verpasst wird
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

    def hide_all(self) -> None:
        self._relic_timer.stop()
        self.hide_rewards()
        self._hide(self.relic)

    def close(self) -> None:
        self.rewards.close()
        self.relic.close()
