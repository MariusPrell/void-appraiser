"""A small homage to a famous Warframe community moment. No photo, just a drawn shirt.

Trigger: search for "rebecca" in the drop search.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from . import theme

TRIGGERS = ("rebecca", "definitely rebecca", "definitely rebecca ford", "rebecca ford")


def is_trigger(query: str) -> bool:
    return " ".join(query.lower().split()) in TRIGGERS


class _Shirt(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 300)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2
        s = min(w / 320, h / 300)

        def pt(x, y):
            return QPointF(cx + x * s, 20 * s + y * s)

        shirt = QPainterPath()
        shirt.moveTo(pt(-45, 0))
        shirt.quadTo(pt(0, 28), pt(45, 0))  # collar
        shirt.lineTo(pt(110, 25))
        shirt.lineTo(pt(150, 85))  # right sleeve
        shirt.lineTo(pt(110, 105))
        shirt.lineTo(pt(100, 85))
        shirt.lineTo(pt(100, 265))
        shirt.lineTo(pt(-100, 265))
        shirt.lineTo(pt(-100, 85))
        shirt.lineTo(pt(-110, 105))
        shirt.lineTo(pt(-150, 85))  # left sleeve
        shirt.lineTo(pt(-110, 25))
        shirt.closeSubpath()
        p.fillPath(shirt, QColor("#f4f4f2"))
        p.setPen(QPen(QColor("#c9c9c4"), 2))
        p.drawPath(shirt)

        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(19 * s))
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(font)
        p.setPen(QColor("#2b2b2b"))
        p.drawText(QRectF(cx - 95 * s, 70 * s, 190 * s, 70 * s), Qt.AlignCenter, "DEFINITELY\nREBECCA FORD")
        p.end()


def show(parent: QWidget) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Definitely not a bug")
    layout = QVBoxLayout(dialog)
    layout.addWidget(_Shirt())
    caption = QLabel("Thanks, Rebecca. 💛")
    caption.setAlignment(Qt.AlignCenter)
    caption.setStyleSheet(f"color: {theme.GOLD}; font-weight: 700; font-size: 12pt;")
    layout.addWidget(caption)
    dialog.resize(380, 380)
    dialog.exec()
