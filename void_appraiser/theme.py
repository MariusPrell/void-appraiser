"""Dark "void" look: deep blue-black, Warframe gold as accent, cyan for highlights."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

BG = "#0b0f1a"
PANEL = "#121828"
PANEL_2 = "#182036"
BORDER = "#25304d"
TEXT = "#d8dde9"
MUTED = "#8a93a8"
GOLD = "#e3b94f"
GOLD_DARK = "#a8862f"
CYAN = "#5fc8e8"
GREEN = "#2f8f5b"
RED = "#d9534f"

STYLE = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow::separator {{ background: {BORDER}; }}
QMenuBar {{ background: {BG}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {PANEL_2}; color: {GOLD}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; }}
QStatusBar {{ background: {BG}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 18px;
    margin-right: 4px;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {GOLD}; border-bottom: 2px solid {GOLD}; }}

QLabel#title {{ font-size: 15pt; font-weight: 700; color: {TEXT}; }}
QLabel#section {{ font-size: 11pt; font-weight: 700; color: {GOLD}; letter-spacing: 1px; }}
QLabel#hint {{ color: {MUTED}; }}
QFrame#card, QLabel#card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 12px;
}}
QLabel#summary {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-left: 3px solid {GOLD};
    border-radius: 6px;
    padding: 8px 12px;
}}

QTableWidget {{
    background: {PANEL};
    alternate-background-color: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: #26355c;
    selection-color: {TEXT};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {PANEL_2};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {PANEL_2}; border: none; }}

QPushButton {{
    background: {PANEL_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {GOLD_DARK}; color: {GOLD}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton#primary {{ background: {GOLD}; color: #1a1406; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: #f0c95e; color: #1a1406; }}

QLineEdit, QComboBox, QDoubleSpinBox {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {GOLD_DARK};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{ border-color: {GOLD_DARK}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {PANEL_2}; }}
QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD_DARK}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.Window, BG),
        (QPalette.WindowText, TEXT),
        (QPalette.Base, PANEL),
        (QPalette.AlternateBase, PANEL_2),
        (QPalette.Text, TEXT),
        (QPalette.Button, PANEL_2),
        (QPalette.ButtonText, TEXT),
        (QPalette.Highlight, "#26355c"),
        (QPalette.HighlightedText, TEXT),
        (QPalette.ToolTipBase, PANEL_2),
        (QPalette.ToolTipText, TEXT),
        (QPalette.PlaceholderText, MUTED),
        (QPalette.Link, CYAN),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(icon())


def icon(size: int = 256) -> QIcon:
    """App icon: a stylized void relic (gold diamond with a cyan core), drawn in code."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    c = size / 2

    background = QPainterPath()
    background.addRoundedRect(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92), size * 0.22, size * 0.22)
    p.fillPath(background, QColor(BG))

    diamond = QPainterPath()
    r = size * 0.36
    diamond.moveTo(QPointF(c, c - r))
    diamond.lineTo(QPointF(c + r * 0.78, c))
    diamond.lineTo(QPointF(c, c + r))
    diamond.lineTo(QPointF(c - r * 0.78, c))
    diamond.closeSubpath()
    gradient = QLinearGradient(QPointF(c, c - r), QPointF(c, c + r))
    gradient.setColorAt(0, QColor("#f6d77a"))
    gradient.setColorAt(1, QColor(GOLD_DARK))
    p.fillPath(diamond, QBrush(gradient))
    p.setPen(QPen(QColor("#fff1c2"), size * 0.02))
    p.drawPath(diamond)

    core = QPainterPath()
    k = r * 0.38
    core.moveTo(QPointF(c, c - k))
    core.lineTo(QPointF(c + k * 0.78, c))
    core.lineTo(QPointF(c, c + k))
    core.lineTo(QPointF(c - k * 0.78, c))
    core.closeSubpath()
    p.fillPath(core, QColor(CYAN))
    p.end()
    return QIcon(pixmap)


def style_table(table) -> None:
    """Common table look: alternating rows, no grid, a bit more height per row."""
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(30)
    table.setFocusPolicy(Qt.NoFocus)


def wordmark():
    """Small "VOID APPRAISER" label with icon for the corner of the tab bar."""
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

    box = QWidget()
    box.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(6)
    logo = QLabel()
    logo.setPixmap(icon().pixmap(20, 20))
    text = QLabel("VOID APPRAISER")
    text.setStyleSheet(f"color: {GOLD}; font-weight: 800; letter-spacing: 3px; background: transparent;")
    layout.addWidget(logo)
    layout.addWidget(text)
    return box
