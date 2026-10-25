"""Tab "Drop search": where to get an item (official DE drop tables)."""

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

from . import theme
from .drops import Drop, DropTable
from .i18n import num, tr

COLUMNS = ("Item", "Location", "Rarity", "Chance")


class _Bridge(QObject):
    loaded = Signal(object)
    failed = Signal(str)


class _Chance(QTableWidgetItem):
    def __init__(self, value: float | None):
        text = "–" if value is None else f"{num(value, 2)} %"
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
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("Search, e.g. Gauss Neuroptics or Axi A1 Relic"))
        self.query.setClearButtonEnabled(True)
        row.addWidget(self.query, 1)
        self.refined = QCheckBox(tr("Show refined relics"))
        self.places = QCheckBox(tr("Search in locations"))
        self.places.setToolTip(tr("Shows what drops at a location, e.g. “Apollodorus” or “Axi A1 Relic”"))
        row.addWidget(self.refined)
        row.addWidget(self.places)
        layout.addLayout(row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        theme.style_table(self.table)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSortIndicator(3, Qt.DescendingOrder)  # highest chance first
        self.table.cellDoubleClicked.connect(self._double_clicked)
        layout.addWidget(self.table, 1)

        self.status = QLabel(tr("Loading drop tables …"))
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # Search while typing, with a short pause so not every letter triggers a search
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
        except Exception as exc:  # no network and no cache
            self.bridge.failed.emit(str(exc))

    def _on_loaded(self, table: DropTable) -> None:
        self.table_data = table
        self.status.setText(
            tr(
                "{count} entries from the official Digital Extremes drop tables "
                "(prepared by drops.warframestat.us, updated daily). "
                "Double-click a relic to see its contents and value.",
                count=num(len(table.drops)),
            )
        )
        self._search()

    def _on_failed(self, message: str) -> None:
        self.status.setText(tr("Could not load the drop tables: {error}", error=message))

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
                place.setToolTip(tr("Double-click: open the relic in the “Relics” tab"))
            item = QTableWidgetItem(drop.item)
            for col, cell in enumerate((item, place, QTableWidgetItem(drop.rarity), _Chance(drop.chance))):
                self.table.setItem(row, col, cell)
        self.table.setSortingEnabled(True)
        if self.query.text().strip():
            more = tr(" (showing the first {count})", count=len(hits)) if total > len(hits) else ""
            self.status.setText(
                tr("{count} results{more}. Double-click a relic to see its contents and value.", count=total, more=more)
            )

    def _double_clicked(self, row: int, column: int) -> None:
        # Relic as location or as item (e.g. "Axi A1 Relic" as a reward)
        for col in (1, 0):
            text = self.table.item(row, col).text()
            relic = Drop("", text, "", None).relic
            if relic:
                self.open_relic(*relic)
                return
