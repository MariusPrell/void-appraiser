"""Hauptfenster: zeigt Inhalt und Wert des aktuellen Relikts."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .data import REFINEMENTS, Market, Price, RelicDB, Reward, expected_value
from .logwatch import Event, LogWatcher, RelicEquipped, RewardScreenClosed, RewardScreenOpened
from .paths import find_log, load_config, save_config

RARITY_COLORS = {"Common": "#c08a5a", "Uncommon": "#c0c0c0", "Rare": "#e8c547"}
COLUMNS = ("Teil", "Seltenheit", "Chance", "Platin", "ab", "Ducats")


def _fmt_num(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "–"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


class SortItem(QTableWidgetItem):
    """Tabellenzelle, die nach einem Zahlenwert statt nach dem Text sortiert."""

    def __init__(self, text: str, key: float | None):
        super().__init__(text)
        self.key = key if key is not None else -1.0

    def __lt__(self, other):
        if isinstance(other, SortItem):
            return self.key < other.key
        return super().__lt__(other)


class Bridge(QObject):
    """Bringt Ergebnisse aus Hintergrund-Threads in den GUI-Thread."""

    data_loaded = Signal(object, object)
    data_failed = Signal(str)
    log_event = Signal(object)
    price_ready = Signal(str, object)


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path | None):
        super().__init__()
        self.setWindowTitle(f"Warframe Helper {__version__}")
        self.resize(720, 420)

        self.config = load_config()
        self.db: RelicDB | None = None
        self.market: Market | None = None
        self.rewards: list[Reward] = []
        self.prices: dict[str, Price | None] = {}
        self.watcher: LogWatcher | None = None
        self.log_path = log_path
        self.pool = ThreadPoolExecutor(max_workers=2)

        self.bridge = Bridge()
        self.bridge.data_loaded.connect(self._on_data_loaded)
        self.bridge.data_failed.connect(self._on_data_failed)
        self.bridge.log_event.connect(self._on_log_event)
        self.bridge.price_ready.connect(self._on_price_ready)

        self._build_ui()
        self._start_watcher()
        threading.Thread(target=self._load_data, daemon=True).start()

    # --- Aufbau -----------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        row = QHBoxLayout()
        self.relic_edit = QLineEdit()
        self.relic_edit.setPlaceholderText("Relikt, z. B. Axi C12")
        self.relic_edit.setEnabled(False)
        self.relic_edit.returnPressed.connect(self._show_from_inputs)
        self.refine_box = QComboBox()
        self.refine_box.addItems(REFINEMENTS)
        self.refine_box.currentIndexChanged.connect(self._show_from_inputs)
        self.refresh_btn = QPushButton("Preise aktualisieren")
        self.refresh_btn.clicked.connect(lambda: self._fetch_prices(force=True))
        row.addWidget(QLabel("Relikt:"))
        row.addWidget(self.relic_edit, 1)
        row.addWidget(self.refine_box)
        row.addWidget(self.refresh_btn)
        layout.addLayout(row)

        self.banner = QLabel()
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet("background:#2d6a4f;color:white;padding:6px;border-radius:4px;font-weight:bold")
        self.banner.hide()
        layout.addWidget(self.banner)

        self.title = QLabel("Lade Relikt-Daten …")
        font = QFont()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.title.setFont(font)
        layout.addWidget(self.title)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        self.setCentralWidget(central)

        menu = self.menuBar().addMenu("Datei")
        choose_log = QAction("Log-Datei wählen …", self)
        choose_log.triggered.connect(self._choose_log)
        menu.addAction(choose_log)

    # --- Daten laden ------------------------------------------------------

    def _load_data(self) -> None:
        try:
            db = RelicDB.load()
            market = Market()
        except Exception as exc:  # Netzwerk weg und kein Cache
            self.bridge.data_failed.emit(str(exc))
            return
        self.bridge.data_loaded.emit(db, market)

    def _on_data_loaded(self, db: RelicDB, market: Market) -> None:
        self.db, self.market = db, market
        completer = QCompleter(db.names(), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(lambda _: self._show_from_inputs())
        self.relic_edit.setCompleter(completer)
        self.relic_edit.setEnabled(True)
        last = self.config.get("last_relic")
        if self.pending_relic:
            self._show_relic(*self.pending_relic)
        elif last:
            self._show_relic(*last)
        else:
            self.title.setText("Kein Relikt gewählt")

    def _on_data_failed(self, message: str) -> None:
        self.title.setText("Relikt-Daten konnten nicht geladen werden")
        self.statusBar().showMessage(f"Fehler: {message}")

    pending_relic: tuple[str, str, str] | None = None

    # --- Log --------------------------------------------------------------

    def _start_watcher(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if self.log_path is None or not self.log_path.is_file():
            self.statusBar().showMessage("Warframe-Log nicht gefunden. Datei → Log-Datei wählen …")
            return
        self.watcher = LogWatcher(self.log_path, self.bridge.log_event.emit)
        self.watcher.start()
        self.statusBar().showMessage(f"Log: {self.log_path}")

    def _choose_log(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "EE.log wählen", str(Path.home()), "Warframe-Log (EE.log);;Alle Dateien (*)")
        if path:
            self.log_path = Path(path)
            self.config["log_path"] = path
            save_config(self.config)
            self._start_watcher()

    def _on_log_event(self, event: Event) -> None:
        if isinstance(event, RelicEquipped):
            relic = (event.tier, event.name, event.refinement)
            if self.db is None:
                self.pending_relic = relic
            else:
                self._show_relic(*relic)
        elif isinstance(event, RewardScreenOpened):
            self.banner.setText("Belohnungsbildschirm offen")
            self.banner.show()
        elif isinstance(event, RewardScreenClosed):
            self.banner.hide()

    # --- Anzeige ----------------------------------------------------------

    def _show_from_inputs(self) -> None:
        parts = self.relic_edit.text().split()
        if len(parts) == 2 and self.db:
            tier, name = parts[0].capitalize(), parts[1].upper()
            self._show_relic(tier, name, self.refine_box.currentText())

    def _show_relic(self, tier: str, name: str, refinement: str) -> None:
        if self.db is None:
            return
        rewards = self.db.rewards(tier, name, refinement)
        # Eingabefelder angleichen, ohne die Anzeige erneut auszulösen
        self.relic_edit.setText(f"{tier} {name}")
        self.refine_box.blockSignals(True)
        self.refine_box.setCurrentText(refinement)
        self.refine_box.blockSignals(False)
        if rewards is None:
            self.title.setText(f"{tier} {name}: unbekanntes Relikt")
            self.rewards = []
            self._fill_table()
            return
        self.config["last_relic"] = [tier, name, refinement]
        save_config(self.config)
        self.title.setText(f"{tier} {name} ({refinement})")
        self.rewards = rewards
        self._fetch_prices()

    def _fetch_prices(self, force: bool = False) -> None:
        if not self.market:
            return
        for reward in self.rewards:
            # Sofort mit dem Cache füllen, dann im Hintergrund nachladen
            self.prices[reward.name] = self.market.cached_price(reward.name)
            self.pool.submit(self._price_job, reward.name, force)
        self._fill_table()

    def _price_job(self, name: str, force: bool) -> None:
        try:
            price = self.market.price(name, force=force)
        except Exception:
            price = None
        self.bridge.price_ready.emit(name, price)

    def _on_price_ready(self, name: str, price: Price | None) -> None:
        if any(r.name == name for r in self.rewards):
            self.prices[name] = price
            self._fill_table()

    def _fill_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rewards))
        values: dict[str, float | None] = {}
        for row, reward in enumerate(self.rewards):
            price = self.prices.get(reward.name)
            ducats = self.market.ducats(reward.name) if self.market else None
            value = price.value if price else None
            values[reward.name] = value
            color = QBrush(QColor(RARITY_COLORS.get(reward.rarity, "#ffffff")))
            cells = [
                QTableWidgetItem(reward.name),
                SortItem(reward.rarity, reward.chance),
                SortItem(f"{_fmt_num(reward.chance, 2)} %", reward.chance),
                SortItem(_fmt_num(value), value),
                SortItem(_fmt_num(price.lowest if price else None), price.lowest if price else None),
                SortItem(_fmt_num(ducats), ducats),
            ]
            cells[1].setForeground(color)
            for col in range(2, len(cells)):
                cells[col].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for col, cell in enumerate(cells):
                self.table.setItem(row, col, cell)
        self.table.setSortingEnabled(True)
        self.table.sortItems(3, Qt.DescendingOrder)

        if not self.rewards:
            self.summary.clear()
            return
        best = max(self.rewards, key=lambda r: values.get(r.name) or 0)
        ev = expected_value(self.rewards, values)
        text = f"Erwartungswert: <b>{_fmt_num(ev, 1)} Platin</b> pro Öffnung"
        if values.get(best.name):
            text += f" · wertvollstes Teil: <b>{best.name}</b> ({_fmt_num(values[best.name])} Platin)"
        self.summary.setText(text)

    def closeEvent(self, event) -> None:
        if self.watcher:
            self.watcher.stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def run(log_path: Path | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Warframe Helper")
    app.setStyle("Fusion")
    window = MainWindow(log_path or find_log())
    window.show()
    return app.exec()
