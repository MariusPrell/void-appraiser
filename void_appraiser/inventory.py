"""Tab "Inventory": scanned prime parts with platinum, ducats and ducats per platinum.

Idea: Baro Ki'Teer is paid in ducats. Parts with many ducats but little
platinum value are best given to Baro; parts with a high platinum value are
better sold to other players.
"""

from __future__ import annotations

import json
import time
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .data import Price
from .i18n import num, tr
from .paths import cache_dir
from .recognize import GridItem

# From this many ducats per platinum, Baro is worth it (rule of thumb, column turns green)
GOOD_RATIO = 10.0
COLUMNS = ("Part", "Count", "Platinum", "Ducats", "Ducats per platinum", "Platinum total", "Ducats total")
COUNT_COL = 1


class _Num(QTableWidgetItem):
    """Cell that sorts by its number."""

    def __init__(self, text: str, key: float | None):
        super().__init__(text)
        self.key = key if key is not None else -1.0
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.key < other.key if isinstance(other, _Num) else super().__lt__(other)


class InventoryStore:
    """Scanned parts, stored in cache/inventory.json."""

    def __init__(self):
        self.path = cache_dir() / "inventory.json"
        try:
            self.items: dict[str, dict] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = {}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, scanned: list[GridItem], crafted: dict[str, str | None]) -> int:
        """Take over scanned parts. On a repeated scan (e.g. after scrolling) the new
        count wins. Returns the number of new parts."""
        new = 0
        now = time.time()
        for item in scanned:
            if item.name not in self.items:
                new += 1
            self.items[item.name] = {"count": item.count, "blueprint": crafted.get(item.name), "seen": now}
        self.save()
        return new

    def add_received(self, received: list[GridItem], crafted: dict[str, str | None]) -> None:
        """Parts received in a mission: add to the count (a later inventory scan
        sets the exact count again)."""
        now = time.time()
        for item in received:
            entry = self.items.setdefault(item.name, {"count": 0, "blueprint": crafted.get(item.name)})
            entry["count"] = int(entry.get("count", 0)) + item.count
            entry["seen"] = now
        self.save()

    def set_count(self, name: str, count: int) -> None:
        if name in self.items:
            if count <= 0:
                del self.items[name]
            else:
                self.items[name]["count"] = count
            self.save()

    def clear(self) -> None:
        self.items = {}
        self.save()


class InventoryTab(QWidget):
    def __init__(self, hotkey_label: Callable[[], str], request_prices: Callable[[list[str]], None]):
        super().__init__()
        self.store = InventoryStore()
        self.hotkey_label = hotkey_label
        self.request_prices = request_prices
        self.prices: dict[str, Price | None] = {}
        self.ducats: Callable[[str], int | None] = lambda name: None
        self._filling = False
        self._user_sorted = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)
        self.info = QLabel()
        self.info.setObjectName("hint")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLUMNS])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        theme.style_table(self.table)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._count_edited)
        header.sectionClicked.connect(lambda _: setattr(self, "_user_sorted", True))
        layout.addWidget(self.table, 1)

        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        load = QPushButton(tr("Load prices"))
        load.setObjectName("primary")
        load.clicked.connect(lambda: self.request_prices(list(self.store.items)))
        clear = QPushButton(tr("Clear list"))
        clear.clicked.connect(self._clear)
        buttons.addWidget(load)
        buttons.addStretch(1)
        buttons.addWidget(clear)
        layout.addLayout(buttons)

        self.refresh()

    # --- Data ---------------------------------------------------------------

    def add_scan(self, items: list[GridItem], crafted: dict[str, str | None]) -> int:
        new = self.store.add(items, crafted)
        # Built parts have no price (not tradeable)
        self.request_prices([i.name for i in items if not crafted.get(i.name)])
        self.refresh()
        return new

    def add_received(self, items: list[GridItem], crafted: dict[str, str | None]) -> None:
        self.store.add_received(items, crafted)
        self.request_prices([i.name for i in items if not crafted.get(i.name)])
        self.refresh()

    def _clear(self) -> None:
        answer = QMessageBox.question(self, tr("Clear list"), tr("Remove all scanned parts from the list?"))
        if answer == QMessageBox.Yes:
            self.store.clear()
            self.refresh()

    def _count_edited(self, cell: QTableWidgetItem) -> None:
        if self._filling or cell.column() != COUNT_COL:
            return
        name = self.table.item(cell.row(), 0).data(Qt.UserRole)
        try:
            count = int(cell.text())
        except ValueError:
            self.refresh()
            return
        self.store.set_count(name, count)
        self.refresh()

    # --- Display ------------------------------------------------------------

    def refresh(self) -> None:
        self._filling = True
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_order = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        rows = sorted(self.store.items.items())
        self.table.setRowCount(len(rows))
        total_plat = total_ducats = 0.0
        for row, (name, entry) in enumerate(rows):
            count = int(entry.get("count", 1))
            blueprint = entry.get("blueprint")
            price = None if blueprint else self.prices.get(name)
            plat = price.value if price else None
            ducats = None if blueprint else self.ducats(name)
            ratio = ducats / plat if ducats and plat else None

            label = QTableWidgetItem(name + (tr("  (built, not tradeable)") if blueprint else ""))
            label.setData(Qt.UserRole, name)
            label.setFlags(label.flags() & ~Qt.ItemIsEditable)
            count_cell = _Num(str(count), count)
            count_cell.setToolTip(tr("Double-click to change, 0 removes the part"))
            cells = [
                label,
                count_cell,
                _Num(num(plat), plat),
                _Num(num(ducats), ducats),
                _Num(num(ratio, 1), ratio),
                _Num(num(plat * count if plat else None), plat * count if plat else None),
                _Num(num(ducats * count if ducats else None), ducats * count if ducats else None),
            ]
            for col, cell in enumerate(cells):
                if col != COUNT_COL:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, cell)
            if ratio is not None and ratio >= GOOD_RATIO:
                cells[4].setBackground(QBrush(QColor(theme.GREEN)))
                cells[4].setForeground(QBrush(QColor("white")))
            total_plat += (plat or 0) * count
            total_ducats += (ducats or 0) * count
        self.table.setSortingEnabled(True)
        if self._user_sorted:
            self.table.sortItems(sort_col, sort_order)
        else:
            self.table.sortItems(4, Qt.DescendingOrder)  # default: best ducat candidates first
        self._filling = False

        pieces = sum(int(e.get("count", 1)) for e in self.store.items.values())
        self.info.setText(
            tr(
                "In the game, open <b>Inventory → Prime Parts</b>: the visible parts are read "
                "automatically (or with <b>{key}</b>). Scroll to add more. Parts you receive in "
                "missions are added from the end-of-mission screen. Double-click a count to correct it.",
                key=self.hotkey_label(),
            )
        )
        self.summary.setText(
            tr(
                "{parts} different parts, {pieces} pieces · value: <b>{plat} platinum</b> "
                "or <b>{ducats} ducats</b><br>"
                "<b>Ducats per platinum</b>: how many ducats you get for 1 platinum of market value. "
                "From about {ratio} (green), Baro Ki'Teer is worth it; below that, rather sell to players.",
                parts=len(rows),
                pieces=pieces,
                plat=num(total_plat),
                ducats=num(total_ducats),
                ratio=f"{GOOD_RATIO:.0f}",
            )
        )
