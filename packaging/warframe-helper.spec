# PyInstaller-Bauplan für Windows und Linux.
# Bauen:  pyinstaller packaging/warframe-helper.spec --noconfirm
# Ergebnis: dist/warframe-helper/ (Ordner mit Programm und Bibliotheken)
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# RapidOCR bringt Modelle und Konfiguration als Dateien mit
datas = collect_data_files("rapidocr")
# Nur die ONNX-Runtime nutzen, die anderen Rechenwerke (PyTorch, Paddle, ...) weglassen
_unused = ("pytorch", "tensorrt", "paddle", "openvino", "mnn")
hiddenimports = collect_submodules("rapidocr", filter=lambda name: not any(u in name for u in _unused))
if sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
elif sys.platform == "win32":
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]

# Große Qt-Teile, die wir nicht brauchen
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtQuick3D", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtDesigner",
    "tkinter", "matplotlib", "pytest", "torch", "paddle", "openvino", "tensorrt",
]

a = Analysis(
    [os.path.join(SPECPATH, "start.py")],
    pathex=[os.path.join(SPECPATH, "..")],  # SPECPATH: Ordner dieser Datei
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="warframe-helper",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="warframe-helper")
