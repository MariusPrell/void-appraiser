"""Schlanke Texterkennung direkt auf der ONNX-Runtime, ohne OpenCV.

Nutzt dieselben PaddleOCR-Modelle (PP-OCRv6 small, Apache-2.0) wie RapidOCR
und bildet dessen Ablauf nach:

1. Textsuche (DBNet): Wahrscheinlichkeitskarte, Schwelle, zusammenhängende
   Flächen, Rechteck um jede Fläche, leicht vergrößert ("unclip").
2. Texterkennung (CRNN mit CTC): jede Zeile auf 48 px Höhe skalieren,
   Zeichen mit der höchsten Wahrscheinlichkeit, Wiederholungen und Lücken weg.

Der Ablauf ist an RapidOCR (Apache-2.0, RapidOCR Authors) und PaddleOCR
(Apache-2.0) angelehnt; Modelle und Lizenzen liegen in models/.

Vereinfachung gegenüber RapidOCR: Rechtecke statt gedrehter Vierecke. In
Warframe steht Text immer waagerecht, dafür braucht es kein OpenCV.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Im fertigen Paket liegen die Modelle neben dem Code (PyInstaller: sys._MEIPASS)
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
MODEL_DIR = _BASE / "warframe_helper" / "models"
DET_MODEL = "PP-OCRv6_det_small.onnx"
REC_MODEL = "PP-OCRv6_rec_small.onnx"

# Werte wie in RapidOCR (config.yaml)
MAX_SIDE_LEN = 2000  # größere Bilder vorher verkleinern
MIN_SIDE_LEN = 30
PAD_MIN_HEIGHT = 30  # sehr flache/breite Bilder oben und unten auffüllen
PAD_RATIO = 8
DET_THRESH = 0.3
DET_BOX_THRESH = 0.5
DET_UNCLIP = 1.6
DET_MIN_SIZE = 3
REC_HEIGHT = 48
REC_MIN_RATIO = 320 / 48
REC_BATCH = 6
TEXT_SCORE = 0.5


@dataclass(frozen=True)
class Line:
    text: str
    score: float
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 im Eingabebild


def _resize(img: np.ndarray, width: int, height: int) -> np.ndarray:
    return np.asarray(Image.fromarray(img).resize((width, height), Image.BILINEAR))


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int, np.ndarray]]:
    """Zusammenhängende Flächen (8er-Nachbarschaft) über Lauflängen.

    Gibt pro Fläche (x0, y0, x1, y1, Zeilen-Spalten-Indizes) zurück.
    """
    runs = []  # (zeile, start, ende)
    for y in range(mask.shape[0]):
        row = mask[y]
        if not row.any():
            continue
        diff = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.flatnonzero(diff == 1)
        ends = np.flatnonzero(diff == -1)
        runs.extend((y, s, e) for s, e in zip(starts.tolist(), ends.tolist()))

    parent = list(range(len(runs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Läufe in benachbarten Zeilen verbinden, wenn sie sich (auch diagonal) berühren
    prev_start = 0
    for i, (y, s, e) in enumerate(runs):
        while prev_start < i and runs[prev_start][0] < y - 1:
            prev_start += 1
        j = prev_start
        while j < i and runs[j][0] == y - 1:
            _, ps, pe = runs[j]
            if ps <= e and pe >= s:  # e und pe sind exklusiv, daher <= für Diagonalen
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
            j += 1

    groups: dict[int, list[int]] = {}
    for i in range(len(runs)):
        groups.setdefault(find(i), []).append(i)
    result = []
    for members in groups.values():
        ys = [runs[m][0] for m in members]
        x0 = min(runs[m][1] for m in members)
        x1 = max(runs[m][2] for m in members)
        result.append((x0, min(ys), x1, max(ys) + 1, np.array(members)))
    return result


class OcrEngine:
    def __init__(self, threads: int = 1, model_dir: Path | None = None):
        import onnxruntime as ort

        model_dir = model_dir or MODEL_DIR
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        providers = ["CPUExecutionProvider"]
        self.det = ort.InferenceSession(str(model_dir / DET_MODEL), options, providers=providers)
        self.rec = ort.InferenceSession(str(model_dir / REC_MODEL), options, providers=providers)
        chars = self.rec.get_modelmeta().custom_metadata_map["character"].splitlines()
        self.chars = ["<blank>"] + chars + [" "]

    # --- Textsuche ----------------------------------------------------------

    def _prepare(self, img: np.ndarray) -> tuple[np.ndarray, float, int]:
        """Größe begrenzen und flache Bilder auffüllen (wie RapidOCR).

        Gibt (Bild, Skalierung, Rand oben) zurück, um Boxen zurückzurechnen.
        """
        h, w = img.shape[:2]
        scale = 1.0
        if max(h, w) > MAX_SIDE_LEN:
            scale = MAX_SIDE_LEN / max(h, w)
        if min(h, w) * scale < MIN_SIDE_LEN:
            scale = MIN_SIDE_LEN / min(h, w)
        if scale != 1.0:
            img = _resize(img, max(1, int(w * scale)), max(1, int(h * scale)))
            h, w = img.shape[:2]
        top = 0
        if h <= PAD_MIN_HEIGHT or w / h > PAD_RATIO:
            new_h = max(int(w / PAD_RATIO), PAD_MIN_HEIGHT) * 2
            top = abs(new_h - h) // 2
            padded = np.zeros((h + 2 * top, w, 3), dtype=img.dtype)
            padded[top : top + h] = img
            img = padded
        return img, scale, top

    def detect(self, img: np.ndarray, limit_side_len: int = 1600) -> list[tuple[int, int, int, int]]:
        prepared, scale, top = self._prepare(img)
        h, w = prepared.shape[:2]
        ratio = limit_side_len / max(h, w) if max(h, w) > limit_side_len else 1.0
        rh = max(32, int(round(int(h * ratio) / 32) * 32))
        rw = max(32, int(round(int(w * ratio) / 32) * 32))
        x = _resize(prepared, rw, rh).astype(np.float32) / 255.0
        x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None]
        pred = self.det.run(None, {"x": x})[0][0, 0]

        mask = pred > DET_THRESH
        # Dilatation mit 2×2 wie in RapidOCR
        grown = mask.copy()
        grown[1:, :] |= mask[:-1, :]
        grown[:, 1:] |= mask[:, :-1]
        grown[1:, 1:] |= mask[:-1, :-1]

        boxes = []
        for x0, y0, x1, y1, _ in _components(grown):
            bw, bh = x1 - x0, y1 - y0
            if min(bw, bh) < DET_MIN_SIZE:
                continue
            if pred[y0:y1, x0:x1].mean() < DET_BOX_THRESH:
                continue
            # "unclip": Rechteck um d = Fläche × 1,6 / Umfang vergrößern
            d = bw * bh * DET_UNCLIP / (2 * (bw + bh))
            fx0, fy0, fx1, fy1 = x0 - d, y0 - d, x1 + d, y1 + d
            if min(fx1 - fx0, fy1 - fy0) < DET_MIN_SIZE + 2:
                continue
            # zurück in Koordinaten des Eingabebilds
            sx, sy = w / pred.shape[1], h / pred.shape[0]
            bx0 = max(0, round(fx0 * sx) / scale)
            bx1 = min(img.shape[1], round(fx1 * sx) / scale)
            by0 = max(0, (round(fy0 * sy) - top) / scale)
            by1 = min(img.shape[0], (round(fy1 * sy) - top) / scale)
            if bx1 - bx0 >= 2 and by1 - by0 >= 2:
                boxes.append((int(bx0), int(by0), int(math.ceil(bx1)), int(math.ceil(by1))))
        boxes.sort(key=lambda b: (b[1], b[0]))
        return boxes

    # --- Texterkennung ------------------------------------------------------

    def recognize(self, crops: list[np.ndarray]) -> list[tuple[str, float]]:
        results: list[tuple[str, float]] = [("", 0.0)] * len(crops)
        ratios = [c.shape[1] / max(1, c.shape[0]) for c in crops]
        order = np.argsort(ratios)
        for start in range(0, len(crops), REC_BATCH):
            batch = order[start : start + REC_BATCH]
            max_ratio = max([REC_MIN_RATIO] + [ratios[i] for i in batch])
            width = int(REC_HEIGHT * max_ratio)
            x = np.zeros((len(batch), 3, REC_HEIGHT, width), dtype=np.float32)
            for k, i in enumerate(batch):
                rw = min(width, int(math.ceil(REC_HEIGHT * ratios[i])))
                part = _resize(crops[i], max(1, rw), REC_HEIGHT).astype(np.float32) / 255.0
                x[k, :, :, :rw] = ((part - 0.5) / 0.5).transpose(2, 0, 1)
            probs = self.rec.run(None, {"x": x})[0]
            for k, i in enumerate(batch):
                results[i] = self._decode(probs[k])
        return results

    def _decode(self, probs: np.ndarray) -> tuple[str, float]:
        idx = probs.argmax(axis=1)
        conf = probs.max(axis=1)
        keep = idx != 0
        keep[1:] &= idx[1:] != idx[:-1]  # Wiederholungen zusammenfassen (CTC)
        if not keep.any():
            return "", 0.0
        text = "".join(self.chars[i] for i in idx[keep])
        return text, float(conf[keep].mean())

    # --- Zusammen -----------------------------------------------------------

    def read(self, img: np.ndarray) -> list[Line]:
        boxes = self.detect(img)
        crops = [img[y0:y1, x0:x1] for x0, y0, x1, y1 in boxes]
        lines = []
        for box, (text, score) in zip(boxes, self.recognize(crops)):
            if text and score >= TEXT_SCORE:
                lines.append(Line(text, score, box))
        return lines

    def read_line(self, img: np.ndarray) -> tuple[str, float]:
        """Ganzes Bild als eine Zeile lesen, ohne Textsuche."""
        return self.recognize([img])[0]
