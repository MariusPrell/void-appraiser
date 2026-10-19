"""Tab "Overview": Tageszeiten, Void Fissures und Alerts aus dem Worldstate."""

from __future__ import annotations

import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import worldstate
from .worldstate import Worldstate, time_left

REFRESH_MS = 60_000
KIND_COLORS = {"Steel Path": "#d9534f", "Void Storm": "#5b9bd5"}
TIER_COLORS = {"Lith": "#c08a5a", "Meso": "#b0b0b0", "Neo": "#c9b26b", "Axi": "#e8c547", "Requiem": "#b45dd4", "Omnia": "#7fd1c8"}


class _Bridge(QObject):
    loaded = Signal(object)
    failed = Signal(str)


def _table(columns: tuple[str, ...], stretch: int) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    header = table.horizontalHeader()
    for col in range(len(columns)):
        header.setSectionResizeMode(col, QHeaderView.Stretch if col == stretch else QHeaderView.ResizeToContents)
    return table


def _right(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class OverviewTab(QWidget):
    def __init__(self, config: dict, save_config):
        super().__init__()
        self.config = config
        self.save_config = save_config
        self.state: Worldstate | None = None
        self._loading = False
        self._last_reload = 0.0

        self.bridge = _Bridge()
        self.bridge.loaded.connect(self._on_loaded)
        self.bridge.failed.connect(self._on_failed)

        layout = QVBoxLayout(self)
        bold = QFont()
        bold.setBold(True)

        # Tageszeiten als kleine Kacheln
        self.cycle_grid = QGridLayout()
        self.cycle_labels: dict[str, tuple[QLabel, QLabel]] = {}
        for i, (_, place, _) in enumerate(worldstate.CYCLES):
            frame = QFrame()
            frame.setFrameShape(QFrame.StyledPanel)
            box = QVBoxLayout(frame)
            name = QLabel(place)
            state = QLabel("…")
            state.setFont(bold)
            rest = QLabel("")
            for label in (name, state, rest):
                label.setAlignment(Qt.AlignCenter)
                box.addWidget(label)
            self.cycle_labels[place] = (state, rest)
            self.cycle_grid.addWidget(frame, 0, i)
        layout.addLayout(self.cycle_grid)

        # Void Fissures mit Filter
        row = QHBoxLayout()
        title = QLabel("Void Fissures")
        title.setFont(bold)
        row.addWidget(title)
        row.addStretch(1)
        wanted = set(config.get("fissure_filter", ["Normal", "Steel Path", "Void Storm"]))
        self.filters: dict[str, QCheckBox] = {}
        for kind in ("Normal", "Steel Path", "Void Storm"):
            box = QCheckBox(kind)
            box.setChecked(kind in wanted)
            box.toggled.connect(self._filter_changed)
            self.filters[kind] = box
            row.addWidget(box)
        layout.addLayout(row)
        self.fissure_table = _table(("Relikt", "Mission", "Ort", "Gegner", "Art", "Restzeit"), 2)
        layout.addWidget(self.fissure_table, 3)

        alerts_title = QLabel("Alerts")
        alerts_title.setFont(bold)
        layout.addWidget(alerts_title)
        self.alert_table = _table(("Mission", "Ort", "Gegner", "Level", "Belohnung", "Restzeit"), 4)
        layout.addWidget(self.alert_table, 1)

        self.status = QLabel("Lade Daten von api.warframestat.us …")
        layout.addWidget(self.status)

        # Restzeiten jede Sekunde, Daten jede Minute neu
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_times)
        self._tick.start(1000)
        self._refresh = QTimer(self)
        self._refresh.timeout.connect(self.reload)
        self._refresh.start(REFRESH_MS)
        self.reload()

    # --- Laden ------------------------------------------------------------

    def reload(self) -> None:
        # Höchstens alle 20 s, falls die API eine abgelaufene Tageszeit noch nicht erneuert hat
        if self._loading or time.monotonic() - self._last_reload < 20:
            return
        self._loading = True
        self._last_reload = time.monotonic()
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        try:
            self.bridge.loaded.emit(worldstate.fetch())
        except Exception as exc:  # Netz weg, API down: alte Daten bleiben stehen
            self.bridge.failed.emit(str(exc))

    def _on_loaded(self, state: Worldstate) -> None:
        self._loading = False
        self.state = state
        self._fill()
        local = state.fetched.astimezone().strftime("%H:%M:%S")
        self.status.setText(f"Stand: {local} · Quelle: api.warframestat.us (Fan-API) · aktualisiert jede Minute")

    def _on_failed(self, message: str) -> None:
        self._loading = False
        self.status.setText(f"Aktualisieren fehlgeschlagen ({message}), zeige ältere Daten")

    def _filter_changed(self) -> None:
        self.config["fissure_filter"] = [k for k, box in self.filters.items() if box.isChecked()]
        self.save_config(self.config)
        self._fill()

    # --- Anzeige ----------------------------------------------------------

    def _visible_fissures(self):
        if not self.state:
            return []
        now = datetime.now().astimezone()
        return [
            f for f in self.state.fissures if self.filters[f.kind].isChecked() and f.expiry > now
        ]

    def _fill(self) -> None:
        if not self.state:
            return
        for cycle in self.state.cycles:
            labels = self.cycle_labels.get(cycle.place)
            if labels:
                labels[0].setText(cycle.state)

        fissures = self._visible_fissures()
        self.fissure_table.setRowCount(len(fissures))
        for row, f in enumerate(fissures):
            tier = QTableWidgetItem(f.tier)
            tier.setForeground(QBrush(QColor(TIER_COLORS.get(f.tier, "#ffffff"))))
            kind = QTableWidgetItem(f.kind)
            if f.kind in KIND_COLORS:
                kind.setForeground(QBrush(QColor(KIND_COLORS[f.kind])))
            for col, item in enumerate((tier, QTableWidgetItem(f.mission), QTableWidgetItem(f.node), QTableWidgetItem(f.enemy), kind, _right(""))):
                self.fissure_table.setItem(row, col, item)

        alerts = self.state.alerts
        self.alert_table.setRowCount(len(alerts))
        for row, a in enumerate(alerts):
            cells = (QTableWidgetItem(a.mission), QTableWidgetItem(a.node), QTableWidgetItem(a.faction), _right(a.levels), QTableWidgetItem(a.reward), _right(""))
            for col, item in enumerate(cells):
                self.alert_table.setItem(row, col, item)
        self._update_times()

    def _update_times(self) -> None:
        if not self.state:
            return
        now = datetime.now().astimezone()
        for cycle in self.state.cycles:
            labels = self.cycle_labels.get(cycle.place)
            if labels:
                labels[1].setText(f"noch {time_left(cycle.expiry, now)}")
        fissures = self._visible_fissures()
        if len(fissures) != self.fissure_table.rowCount():
            self._fill()  # eine Fissure ist abgelaufen
            return
        for row, f in enumerate(fissures):
            self.fissure_table.item(row, 5).setText(time_left(f.expiry, now))
        for row, a in enumerate(self.state.alerts):
            self.alert_table.item(row, 5).setText(time_left(a.expiry, now))
        # Abgelaufene Tageszeit: gleich neu laden statt eine Minute zu warten
        if any(c.expiry <= now for c in self.state.cycles):
            self.reload()
