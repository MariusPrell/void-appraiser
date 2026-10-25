"""Main window: tabs for overview, relics, inventory and drop search."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, capture
from .data import REFINEMENTS, Market, Price, RelicDB, Reward, expected_value
from .dropsearch import DropSearchTab
from .hotkey import KEYS, HotkeyListener, normalize
from .i18n import LANGUAGES, num, set_language, tr
from .inventory import InventoryTab
from .logwatch import LogWatcher, RelicEquipped, RewardScreenClosed, RewardScreenOpened
from .overlay import Item, OverlayManager
from .overview import OverviewTab
from .paths import cache_dir, find_log, load_config, save_config
from .recognize import NameMatcher
from .scanner import (
    DialogDetected,
    InventoryScanned,
    InventoryVisible,
    MissionRewards,
    RewardsDetected,
    RewardsGone,
    Scanner,
    ScannerSettings,
    ScannerStatus,
)

RARITY_COLORS = {"Common": "#c08a5a", "Uncommon": "#c0c0c0", "Rare": "#e8c547"}
BEST_COLOR = "#2d6a4f"

DEFAULTS = {
    "language": "en",
    "auto_scan": True,
    "scan_interval": 1.5,
    "hotkey": "Insert",
    "monitor": "",
    "debug_save": True,
    "overlay": True,
    "overlay_seconds": 5.0,
}


class SortItem(QTableWidgetItem):
    """Table cell that sorts by a number instead of its text."""

    def __init__(self, text: str, key: float | None):
        super().__init__(text)
        self.key = key if key is not None else -1.0

    def __lt__(self, other):
        if isinstance(other, SortItem):
            return self.key < other.key
        return super().__lt__(other)


def _make_table(columns: tuple[str, ...]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    for col in range(1, len(columns)):
        header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
    return table


class Bridge(QObject):
    """Moves results from background threads into the GUI thread."""

    data_loaded = Signal(object, object)
    data_failed = Signal(str)
    event = Signal(object)
    price_ready = Signal(str, object)
    hotkey = Signal()


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, config: dict):
        super().__init__(parent)
        self.setWindowTitle(tr("Settings"))
        form = QFormLayout(self)

        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(config["language"])))
        self.language.setToolTip(tr("Takes effect after a restart"))
        form.addRow(tr("Language"), self.language)

        self.auto = QCheckBox(tr("Detect screens automatically"))
        self.auto.setChecked(config["auto_scan"])
        form.addRow(self.auto)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 10.0)
        self.interval.setSingleStep(0.5)
        self.interval.setDecimals(1)
        self.interval.setSuffix(" s")
        self.interval.setValue(config["scan_interval"])
        form.addRow(tr("Every"), self.interval)

        self.hotkey = QComboBox()
        for label in KEYS:
            self.hotkey.addItem(tr(label), label)
        self.hotkey.setCurrentIndex(max(0, self.hotkey.findData(normalize(config["hotkey"]))))
        form.addRow(tr("Key for manual scan"), self.hotkey)

        self.monitor = QComboBox()
        self.monitor.addItem(tr("Automatic (Warframe window)"), "")
        try:
            for mon in capture.backend().monitors():
                self.monitor.addItem(f"{mon.name} ({mon.rect.w}×{mon.rect.h})", mon.name)
        except Exception:
            pass
        self.monitor.setCurrentIndex(max(0, self.monitor.findData(config["monitor"])))
        form.addRow(tr("Screen"), self.monitor)

        self.overlay = QCheckBox(tr("Show overlay on top of the game"))
        self.overlay.setChecked(config["overlay"])
        form.addRow(self.overlay)

        self.overlay_seconds = QDoubleSpinBox()
        self.overlay_seconds.setRange(1.0, 30.0)
        self.overlay_seconds.setSingleStep(1.0)
        self.overlay_seconds.setDecimals(0)
        self.overlay_seconds.setSuffix(" s")
        self.overlay_seconds.setValue(config["overlay_seconds"])
        self.overlay_seconds.setToolTip(tr("How long the relic info stays visible after the equip dialog"))
        form.addRow(tr("Show relic info for"), self.overlay_seconds)

        self.debug = QCheckBox(tr("Save detected screens for troubleshooting"))
        self.debug.setChecked(config["debug_save"])
        self.debug.setToolTip(str(cache_dir() / "scans"))
        form.addRow(self.debug)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {
            "language": self.language.currentData(),
            "auto_scan": self.auto.isChecked(),
            "scan_interval": self.interval.value(),
            "hotkey": self.hotkey.currentData(),
            "monitor": self.monitor.currentData(),
            "debug_save": self.debug.isChecked(),
            "overlay": self.overlay.isChecked(),
            "overlay_seconds": self.overlay_seconds.value(),
        }


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path | None, config: dict | None = None):
        super().__init__()
        self.setWindowTitle(f"Void Appraiser {__version__}")
        self.resize(860, 700)

        self.config = config if config is not None else load_settings()
        self.db: RelicDB | None = None
        self.market: Market | None = None
        self.rewards: list[Reward] = []
        self.choices: list[str] = []
        self.choice_x: list[float] = []
        self.overlay: OverlayManager | None = None
        self.overlay_relic_until = 0.0
        self.prices: dict[str, Price | None] = {}
        self.watcher: LogWatcher | None = None
        self.scanner: Scanner | None = None
        self.hotkey: HotkeyListener | None = None
        self.pending_relic: tuple[str, str, str] | None = None
        self.log_path = log_path
        self.pool = ThreadPoolExecutor(max_workers=2)

        self.bridge = Bridge()
        self.bridge.data_loaded.connect(self._on_data_loaded)
        self.bridge.data_failed.connect(self._on_data_failed)
        self.bridge.event.connect(self._on_event)
        self.bridge.price_ready.connect(self._on_price_ready)
        self.bridge.hotkey.connect(self._scan_now)

        self._build_ui()
        self._start_watcher()
        self._start_hotkey()
        threading.Thread(target=self._load_data, daemon=True).start()

    # --- Layout -------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        big = QFont()
        big.setPointSize(big.pointSize() + 4)
        big.setBold(True)

        # Choice on the reward screen
        self.choice_title = QLabel(tr("Reward choice: nothing detected yet"))
        self.choice_title.setFont(big)
        layout.addWidget(self.choice_title)
        self.choice_table = _make_table((tr("Part"), tr("Platinum"), tr("from"), tr("Ducats")))
        self.choice_table.setMaximumHeight(170)
        layout.addWidget(self.choice_table)

        # Relic preview
        row = QHBoxLayout()
        self.relic_edit = QLineEdit()
        self.relic_edit.setPlaceholderText(tr("Relic, e.g. Axi C12"))
        self.relic_edit.setEnabled(False)
        self.relic_edit.returnPressed.connect(self._show_from_inputs)
        self.refine_box = QComboBox()
        self.refine_box.addItems(REFINEMENTS)
        self.refine_box.currentIndexChanged.connect(self._show_from_inputs)
        row.addWidget(QLabel(tr("Relic:")))
        row.addWidget(self.relic_edit, 1)
        row.addWidget(self.refine_box)
        layout.addLayout(row)

        self.title = QLabel(tr("Loading relic data …"))
        self.title.setFont(big)
        layout.addWidget(self.title)

        self.table = _make_table(
            (tr("Part"), tr("Rarity"), tr("Chance"), tr("Platinum"), tr("from"), tr("Ducats"))
        )
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self.scan_btn = QPushButton(tr("Scan now"))
        self.scan_btn.clicked.connect(self._scan_now)
        self.refresh_btn = QPushButton(tr("Refresh prices"))
        self.refresh_btn.clicked.connect(lambda: self._fetch_prices(force=True))
        buttons.addWidget(self.scan_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.refresh_btn)
        layout.addLayout(buttons)

        # Tabs: overview first, then the relic view built above
        self.relic_page = central
        self.tabs = QTabWidget()
        self.overview = OverviewTab(self.config, save_config)
        self.tabs.addTab(self.overview, tr("Overview"))
        self.tabs.addTab(self.relic_page, tr("Relics"))
        self.parts: dict[str, str | None] = {}
        self.inventory_tab = InventoryTab(self._hotkey_text, lambda names: self._fetch_prices(names))
        self.tabs.addTab(self.inventory_tab, tr("Inventory"))
        self.drop_tab = DropSearchTab(self._open_relic)
        self.tabs.addTab(self.drop_tab, tr("Drop search"))
        self.setCentralWidget(self.tabs)

        self.scan_label = QLabel(tr("Detection: starting …"))
        self.statusBar().addPermanentWidget(self.scan_label)

        menu = self.menuBar().addMenu(tr("File"))
        settings = QAction(tr("Settings …"), self)
        settings.triggered.connect(self._open_settings)
        menu.addAction(settings)
        choose_log = QAction(tr("Choose log file …"), self)
        choose_log.triggered.connect(self._choose_log)
        menu.addAction(choose_log)

    # --- Settings -----------------------------------------------------------

    def _scanner_settings(self) -> ScannerSettings:
        return ScannerSettings(
            auto=self.config["auto_scan"],
            interval=self.config["scan_interval"],
            monitor=self.config["monitor"],
            debug_dir=cache_dir() / "scans" if self.config["debug_save"] else None,
        )

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, self.config)
        if dialog.exec() != QDialog.Accepted:
            return
        old_hotkey = self.config["hotkey"]
        old_language = self.config["language"]
        self.config.update(dialog.values())
        save_config(self.config)
        if self.scanner:
            self.scanner.settings = self._scanner_settings()
            self.scanner.settings_changed()
        if self.config["hotkey"] != old_hotkey:
            self._start_hotkey()
        if self.overlay:
            self.overlay.monitor_name = self.config["monitor"]
            self.overlay.enabled = self.config["overlay"]
            if not self.overlay.enabled:
                self.overlay.hide_all()
        if self.config["language"] != old_language:
            self.statusBar().showMessage(tr("The new language takes effect after a restart"))

    def _start_hotkey(self) -> None:
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = HotkeyListener(self.config["hotkey"], self.bridge.hotkey.emit)
        self.hotkey.start()
        if self.hotkey.error:
            self.statusBar().showMessage(tr("Could not set up the key: {error}", error=self.hotkey.error))

    def _open_relic(self, tier: str, name: str, refinement: str) -> None:
        self.tabs.setCurrentWidget(self.relic_page)
        self._show_relic(tier, name, refinement)

    def _hotkey_text(self) -> str:
        key = normalize(self.config.get("hotkey", "Off"))
        return tr("“Scan now”") if key == "Off" else tr(key)

    def _scan_now(self) -> None:
        if self.scanner:
            self.scanner.scan_now()
            self.scan_label.setText(tr("Detection: scanning …"))

    # --- Loading data -------------------------------------------------------

    def _load_data(self) -> None:
        try:
            db = RelicDB.load()
            market = Market()
        except Exception as exc:  # no network and no cache
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
            self.title.setText(tr("No relic selected"))

        self.scanner = Scanner(db.reward_names(), self.bridge.event.emit, self._scanner_settings())
        # For the inventory: all prime parts on the market (also from relics no longer available)
        self.parts = market.prime_parts()
        self.scanner.inventory_matcher = NameMatcher(list(self.parts))
        self.scanner.start()
        self.inventory_tab.ducats = market.ducats
        for name in self.inventory_tab.store.items:
            self.prices.setdefault(name, market.cached_price(name))
        self.inventory_tab.prices = self.prices
        self.inventory_tab.refresh()
        try:
            self.overlay = OverlayManager(self.config["monitor"])
            self.overlay.enabled = self.config["overlay"]
        except Exception as exc:  # the overlay is optional, the window works without it
            self.statusBar().showMessage(tr("Overlay not available: {error}", error=exc))

    def _on_data_failed(self, message: str) -> None:
        self.title.setText(tr("Could not load relic data"))
        self.statusBar().showMessage(tr("Error: {error}", error=message))

    # --- Log ----------------------------------------------------------------

    def _start_watcher(self) -> None:
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
        if self.log_path is None or not self.log_path.is_file():
            self.statusBar().showMessage(tr("Warframe log not found. File → Choose log file …"))
            return
        self.watcher = LogWatcher(self.log_path, self.bridge.event.emit)
        self.watcher.start()
        self.statusBar().showMessage(tr("Warframe log found"))
        self.statusBar().setToolTip(str(self.log_path))

    def _choose_log(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Choose EE.log"), str(Path.home()), tr("Warframe log (EE.log);;All files (*)")
        )
        if path:
            self.log_path = Path(path)
            self.config["log_path"] = path
            save_config(self.config)
            self._start_watcher()

    # --- Events from log and screen -----------------------------------------

    def _on_event(self, event: object) -> None:
        if isinstance(event, (DialogDetected, RewardsDetected)):
            # Someone opening relics right now needs the relic view
            self.tabs.setCurrentWidget(self.relic_page)
        if isinstance(event, DialogDetected):
            relic = event.relic
            self._show_relic(relic.tier, relic.name, relic.refinement)
            self.overlay_relic_until = time.monotonic() + self.config["overlay_seconds"]
            self._update_overlay()
        elif isinstance(event, RelicEquipped):
            relic = (event.tier, event.name, event.refinement)
            if self.db is None:
                self.pending_relic = relic
            elif self.config.get("last_relic") != list(relic) or not self.rewards:
                self._show_relic(*relic)
        elif isinstance(event, RewardsDetected):
            self.choices = [c.name for c in event.cards]
            self.choice_x = [float(c.x) for c in event.cards]
            self.choice_title.setText(tr("Reward choice"))
            self._fetch_prices(self.choices)
            self.raise_()
        elif isinstance(event, RewardsGone):
            if self.choices:
                self.choice_title.setText(tr("Last reward choice"))
            self.choice_x = []
            if self.overlay:
                self.overlay.hide_rewards()
        elif isinstance(event, RewardScreenClosed):
            # The log is often late; the overlay is controlled by screen detection only
            if self.choices:
                self.choice_title.setText(tr("Last reward choice"))
        elif isinstance(event, RewardScreenOpened):
            # The log is often late, the screen scan is faster
            self._scan_now()
        elif isinstance(event, InventoryVisible):
            if self.overlay:
                if event.visible and self.config["auto_scan"]:
                    self.overlay.show_hint(tr("Reading prime parts · scroll to add more"))
                elif event.visible:
                    self.overlay.show_hint(tr("Press {key}: read prime parts", key=self._hotkey_text()))
                else:
                    self.overlay.hide_hint()
        elif isinstance(event, InventoryScanned):
            new = self.inventory_tab.add_scan(list(event.items), self.parts)
            self.tabs.setCurrentWidget(self.inventory_tab)
            if self.overlay:
                self.overlay.flash_hint(
                    tr("✓ {count} parts detected, {new} new · scroll for more", count=len(event.items), new=new)
                )
        elif isinstance(event, MissionRewards):
            self.inventory_tab.add_received(list(event.items), self.parts)
            pieces = sum(i.count for i in event.items)
            names = ", ".join(i.name for i in event.items)
            self.statusBar().showMessage(tr("Added to the inventory: {names}", names=names), 15000)
            if self.overlay:
                self.overlay.flash_hint(tr("✓ {count} prime parts added to the inventory", count=pieces), 5.0)
        elif isinstance(event, ScannerStatus):
            self.scan_label.setText(event.text)

    # --- Display ------------------------------------------------------------

    def _show_from_inputs(self) -> None:
        parts = self.relic_edit.text().split()
        if len(parts) == 2 and self.db:
            tier, name = parts[0].capitalize(), parts[1].upper()
            self._show_relic(tier, name, self.refine_box.currentText())

    def _show_relic(self, tier: str, name: str, refinement: str) -> None:
        if self.db is None:
            return
        rewards = self.db.rewards(tier, name, refinement)
        # Sync the input fields without triggering the display again
        self.relic_edit.setText(f"{tier} {name}")
        self.refine_box.blockSignals(True)
        self.refine_box.setCurrentText(refinement)
        self.refine_box.blockSignals(False)
        if rewards is None:
            self.title.setText(tr("{relic}: unknown relic", relic=f"{tier} {name}"))
            self.rewards = []
            self._fill_tables()
            return
        self.config["last_relic"] = [tier, name, refinement]
        save_config(self.config)
        self.title.setText(f"{tier} {name} ({refinement})")
        self.rewards = rewards
        self._fetch_prices([r.name for r in rewards])

    def _fetch_prices(self, names: list[str] | None = None, force: bool = False) -> None:
        if not self.market:
            return
        if names is None:
            names = [r.name for r in self.rewards] + self.choices
        for name in dict.fromkeys(names):
            # Fill from the cache right away, then refresh in the background
            if force or name not in self.prices:
                self.prices[name] = self.market.cached_price(name)
            self.pool.submit(self._price_job, name, force)
        self._fill_tables()

    def _price_job(self, name: str, force: bool) -> None:
        try:
            price = self.market.price(name, force=force)
        except Exception:
            price = None
        self.bridge.price_ready.emit(name, price)

    def _on_price_ready(self, name: str, price: Price | None) -> None:
        if price is not None or name not in self.prices:
            self.prices[name] = price
        self._fill_tables()

    def _prices_missing(self, names) -> bool:
        """Are prices still missing for tradeable parts (still loading or request failed)?"""
        return bool(self.market) and any(self.market.item(n) and self.prices.get(n) is None for n in names)

    def _value(self, name: str) -> float | None:
        price = self.prices.get(name)
        return price.value if price else None

    def _fill_tables(self) -> None:
        self._fill_choices()
        self._fill_relic()
        if hasattr(self, "inventory_tab"):
            self.inventory_tab.prices = self.prices
            self.inventory_tab.refresh()
        self._update_overlay()

    def _update_overlay(self) -> None:
        if not self.overlay:
            return
        # Prices below the cards while the reward screen is open
        if self.choice_x:
            best = max(self.choices, key=lambda n: self._value(n) or 0)
            items = []
            for name, x in zip(self.choices, self.choice_x):
                ducats = self.market.ducats(name) if self.market else None
                value = self._value(name)
                items.append(
                    Item(
                        x,
                        (tr("{value} platinum", value=num(value)), tr("{value} ducats", value=num(ducats))),
                        best=bool(value) and name == best,
                    )
                )
            self.overlay.show_rewards(items)
        # Short relic info below the equip dialog
        if self.rewards and time.monotonic() < self.overlay_relic_until:
            values = {r.name: self._value(r.name) for r in self.rewards}
            best = max(self.rewards, key=lambda r: values.get(r.name) or 0)
            ev = expected_value(self.rewards, values)
            second = tr("Ø {value} platinum per opening", value=num(ev, 1))
            if self._prices_missing(r.name for r in self.rewards):
                second = tr("Loading prices …")
            if values.get(best.name):
                second += f"  ·  Top: {best.name.replace(' Blueprint', ' BP')} ({num(values[best.name])} P)"
            remaining = self.overlay_relic_until - time.monotonic()
            self.overlay.show_relic((self.title.text(), second), seconds=remaining)

    def _fill_choices(self) -> None:
        table = self.choice_table
        table.setRowCount(len(self.choices))
        best = max(self.choices, key=lambda n: self._value(n) or 0, default=None)
        for row, name in enumerate(self.choices):
            price = self.prices.get(name)
            ducats = self.market.ducats(name) if self.market else None
            cells = [
                QTableWidgetItem(name),
                QTableWidgetItem(num(self._value(name))),
                QTableWidgetItem(num(price.lowest if price else None)),
                QTableWidgetItem(num(ducats)),
            ]
            for col in range(1, len(cells)):
                cells[col].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if name == best and self._value(name):
                for cell in cells:
                    cell.setBackground(QBrush(QColor(BEST_COLOR)))
                    cell.setForeground(QBrush(QColor("white")))
                    font = cell.font()
                    font.setBold(True)
                    cell.setFont(font)
            for col, cell in enumerate(cells):
                table.setItem(row, col, cell)

    def _fill_relic(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.rewards))
        values = {r.name: self._value(r.name) for r in self.rewards}
        for row, reward in enumerate(self.rewards):
            price = self.prices.get(reward.name)
            ducats = self.market.ducats(reward.name) if self.market else None
            value = values[reward.name]
            cells = [
                QTableWidgetItem(reward.name),
                SortItem(reward.rarity, reward.chance),
                SortItem(f"{num(reward.chance, 2)} %", reward.chance),
                SortItem(num(value), value),
                SortItem(num(price.lowest if price else None), price.lowest if price else None),
                SortItem(num(ducats), ducats),
            ]
            cells[1].setForeground(QBrush(QColor(RARITY_COLORS.get(reward.rarity, "#ffffff"))))
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
        text = tr("Expected value: <b>{value} platinum</b> per opening", value=num(ev, 1))
        if self._prices_missing(r.name for r in self.rewards):
            text += tr(" (not all prices loaded yet)")
        if values.get(best.name):
            text += tr(
                " · most valuable part: <b>{name}</b> ({value} platinum)", name=best.name, value=num(values[best.name])
            )
        self.summary.setText(text)

    def closeEvent(self, event) -> None:
        if self.watcher:
            self.watcher.stop()
        if self.scanner:
            self.scanner.stop()
        if self.hotkey:
            self.hotkey.stop()
        if self.overlay:
            self.overlay.close()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def load_settings() -> dict:
    config = {**DEFAULTS, **load_config()}
    config["hotkey"] = normalize(config["hotkey"])  # German key names up to 0.8
    return config


def run(log_path: Path | None = None) -> int:
    config = load_settings()
    set_language(config["language"])  # before any window text is created
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Void Appraiser")
    app.setDesktopFileName("void-appraiser")
    app.setStyle("Fusion")
    window = MainWindow(log_path or find_log(), config)
    window.show()
    return app.exec()
