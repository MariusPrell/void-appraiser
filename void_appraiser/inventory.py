"""Tab "Inventar": eingelesene Prime-Teile mit Platin, Ducats und Ducats pro Platin.

Gedanke: Bei Baro Ki'Teer zahlt man mit Ducats. Teile mit vielen Ducats, aber
wenig Platin-Wert gibt man am besten bei Baro ab; Teile mit hohem Platin-Wert
verkauft man lieber an Spieler.
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

from .data import Price
from .paths import cache_dir
from .recognize import GridItem

# Ab so vielen Ducats pro Platin lohnt sich Baro (Faustregel, Spalte wird grün markiert)
GOOD_RATIO = 10.0
COLUMNS = ("Teil", "Anzahl", "Platin", "Ducats", "Ducats pro Platin", "Platin gesamt", "Ducats gesamt")
COUNT_COL = 1


def _fmt(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "–"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class _Num(QTableWidgetItem):
    """Zelle, die nach Zahlenwert sortiert."""

    def __init__(self, text: str, key: float | None):
        super().__init__(text)
        self.key = key if key is not None else -1.0
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.key < other.key if isinstance(other, _Num) else super().__lt__(other)


class InventoryStore:
    """Eingelesene Teile, gespeichert in cache/inventory.json."""

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
        """Gescannte Teile übernehmen. Bei erneutem Scan (z. B. nach dem Scrollen) gilt die
        neue Anzahl. Gibt die Zahl neuer Teile zurück."""
        new = 0
        now = time.time()
        for item in scanned:
            if item.name not in self.items:
                new += 1
            self.items[item.name] = {"count": item.count, "blueprint": crafted.get(item.name), "seen": now}
        self.save()
        return new

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
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._count_edited)
        header.sectionClicked.connect(lambda _: setattr(self, "_user_sorted", True))
        layout.addWidget(self.table, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        load = QPushButton("Preise laden")
        load.clicked.connect(lambda: self.request_prices(list(self.store.items)))
        clear = QPushButton("Liste leeren")
        clear.clicked.connect(self._clear)
        buttons.addWidget(load)
        buttons.addStretch(1)
        buttons.addWidget(clear)
        layout.addLayout(buttons)

        self.refresh()

    # --- Daten --------------------------------------------------------------

    def add_scan(self, items: list[GridItem], crafted: dict[str, str | None]) -> int:
        new = self.store.add(items, crafted)
        # Preise für gebaute Teile gibt es nicht (nicht handelbar)
        self.request_prices([i.name for i in items if not crafted.get(i.name)])
        self.refresh()
        return new

    def _clear(self) -> None:
        answer = QMessageBox.question(self, "Liste leeren", "Alle eingelesenen Teile aus der Liste entfernen?")
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

    # --- Anzeige ------------------------------------------------------------

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

            label = QTableWidgetItem(name + ("  (gebaut, nicht handelbar)" if blueprint else ""))
            label.setData(Qt.UserRole, name)
            label.setFlags(label.flags() & ~Qt.ItemIsEditable)
            count_cell = _Num(str(count), count)
            count_cell.setToolTip("Doppelklick zum Ändern, 0 entfernt das Teil")
            cells = [
                label,
                count_cell,
                _Num(_fmt(plat), plat),
                _Num(_fmt(ducats), ducats),
                _Num(_fmt(ratio, 1), ratio),
                _Num(_fmt(plat * count if plat else None), plat * count if plat else None),
                _Num(_fmt(ducats * count if ducats else None), ducats * count if ducats else None),
            ]
            for col, cell in enumerate(cells):
                if col != COUNT_COL:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, cell)
            if ratio is not None and ratio >= GOOD_RATIO:
                cells[4].setBackground(QBrush(QColor(45, 106, 79)))
                cells[4].setForeground(QBrush(QColor("white")))
            total_plat += (plat or 0) * count
            total_ducats += (ducats or 0) * count
        self.table.setSortingEnabled(True)
        if self._user_sorted:
            self.table.sortItems(sort_col, sort_order)
        else:
            self.table.sortItems(4, Qt.DescendingOrder)  # Standard: beste Ducats-Kandidaten oben
        self._filling = False

        pieces = sum(int(e.get("count", 1)) for e in self.store.items.values())
        self.info.setText(
            f"Im Spiel <b>Inventar → Prime Parts</b> öffnen und <b>{self.hotkey_label()}</b> drücken. "
            "Dann scrollen und erneut drücken, die Liste wird ergänzt. "
            "Die Anzahl kannst du per Doppelklick korrigieren."
        )
        self.summary.setText(
            f"{len(rows)} verschiedene Teile, {pieces} Stück · Wert: <b>{_fmt(total_plat)} Platin</b> "
            f"oder <b>{_fmt(total_ducats)} Ducats</b><br>"
            f"<b>Ducats pro Platin</b>: Wie viele Ducats du für 1 Platin Marktwert bekommst. "
            f"Ab etwa {GOOD_RATIO:.0f} (grün) lohnt sich Baro Ki'Teer, darunter lieber an Spieler verkaufen."
        )
