"""Tab "Drop-Suche": wo gibt es einen Gegenstand (offizielle DE-Drop-Tabellen)."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .drops import DropTable

COLUMNS = ("Gegenstand", "Fundort", "Seltenheit", "Chance")


class _Bridge(QObject):
    loaded = Signal(object)
    failed = Signal(str)


class _Chance(QTableWidgetItem):
    def __init__(self, value: float | None):
        text = "–" if value is None else f"{value:.2f} %".replace(".", ",")
        super().__init__(text)
        self.key = -1.0 if value is None else value
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.key < other.key if isinstance(other, _Chance) else super().__lt__(other)


class DropSearchTab(QWidget):
    def __init__(self, open_relic: Callable[[str, str, str], None]):
        super().__init__()
        self.open_relic = open_relic
        self.table_data: DropTable | None = None
        self.bridge = _Bridge()
        self.bridge.loaded.connect(self._on_loaded)
        self.bridge.failed.connect(self._on_failed)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Suche, z. B. Gauss Neuroptics oder Axi A1 Relic")
        self.query.setClearButtonEnabled(True)
        row.addWidget(self.query, 1)
        self.refined = QCheckBox("Veredelte Relikte zeigen")
        self.places = QCheckBox("Im Fundort suchen")
        self.places.setToolTip("Zeigt, was es an einem Ort gibt, z. B. „Apollodorus“ oder „Axi A1 Relic“")
        row.addWidget(self.refined)
        row.addWidget(self.places)
        layout.addLayout(row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSortIndicator(3, Qt.DescendingOrder)  # höchste Chance zuerst
        self.table.cellDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        self.status = QLabel("Lade Drop-Tabellen …")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Suchen beim Tippen, mit kurzer Pause, damit nicht jeder Buchstabe sucht
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._search)
        self.query.textChanged.connect(lambda _: self._debounce.start())
        self.query.returnPressed.connect(self._search)
        self.refined.toggled.connect(self._search)
        self.places.toggled.connect(self._search)

        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        try:
            self.bridge.loaded.emit(DropTable.load())
        except Exception as exc:  # Netz weg und kein Cache
            self.bridge.failed.emit(str(exc))

    def _on_loaded(self, table: DropTable) -> None:
        self.table_data = table
        self.status.setText(
            f"{len(table.drops):,} Einträge aus den offiziellen Drop-Tabellen von Digital Extremes "
            "(aufbereitet von drops.warframestat.us, täglich aktualisiert). "
            "Doppelklick auf ein Relikt zeigt dessen Inhalt und Wert.".replace(",", ".")
        )
        self._search()

    def _on_failed(self, message: str) -> None:
        self.status.setText(f"Drop-Tabellen konnten nicht geladen werden: {message}")

    def _search(self) -> None:
        if self.table_data is None:
            return
        hits, total = self.table_data.search(
            self.query.text(), hide_refined=not self.refined.isChecked(), in_places=self.places.isChecked()
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(hits))
        for row, drop in enumerate(hits):
            place = QTableWidgetItem(drop.place)
            if drop.relic:
                place.setToolTip("Doppelklick: Relikt im Tab „Relikte“ öffnen")
            item = QTableWidgetItem(drop.item)
            for col, cell in enumerate((item, place, QTableWidgetItem(drop.rarity), _Chance(drop.chance))):
                self.table.setItem(row, col, cell)
        self.table.setSortingEnabled(True)
        if self.query.text().strip():
            more = f" (die ersten {len(hits)} angezeigt)" if total > len(hits) else ""
            self.status.setText(f"{total} Treffer{more}. Doppelklick auf ein Relikt zeigt dessen Inhalt und Wert.")

    def _double_clicked(self, row: int, column: int) -> None:
        # Relikt als Fundort oder als Gegenstand (z. B. "Axi A1 Relic" als Belohnung)
        from .drops import Drop

        for col in (1, 0):
            text = self.table.item(row, col).text()
            relic = Drop("", text, "", None).relic
            if relic:
                self.open_relic(*relic)
                return
