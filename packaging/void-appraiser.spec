# PyInstaller build spec for Windows and Linux.
# Build:  pyinstaller packaging/void-appraiser.spec --noconfirm
# Result: dist/void-appraiser/ (folder with the program and its libraries)
import os
import sys

# OCR models and their licenses (void_appraiser/models/)
datas = [(os.path.join(SPECPATH, "..", "void_appraiser", "models", "*"), os.path.join("void_appraiser", "models"))]
hiddenimports = []
if sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg"]
elif sys.platform == "win32":
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]

# Large Qt parts we do not need
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtQuick3D", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtDesigner",
    "tkinter", "matplotlib", "pytest", "cv2", "rapidocr", "shapely", "pyclipper", "omegaconf",
]

a = Analysis(
    [os.path.join(SPECPATH, "start.py")],
    pathex=[os.path.join(SPECPATH, "..")],  # SPECPATH: folder of this file
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
)
# Remove Qt parts the program does not need (package size).
# Case-insensitive match on the destination path, works for Windows and Linux.
_QT_UNUSED = [
    "/translations/",
    # Libraries (Linux: libQt6Quick.so.6, Windows: Qt6Quick.dll)
    "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "qt6network",
    "qt6eglfs",  # OpenGL and Svg stay: Wayland graphics and window decorations need them
    "pyside6/qtnetwork",
    # Plugins
    "plugins/imageformats/", "plugins/iconengines/", "plugins/generic/", "plugins/tls/",
    "plugins/networkinformation/", "plugins/egldeviceintegrations/", "qtvirtualkeyboardplugin",
    "platforms/libqeglfs", "platforms/libqlinuxfb", "platforms/libqminimalegl",
    "platforms/libqvkkhrdisplay", "platforms/libqvnc",
    # The GTK theme pulls in GTK and many system libraries on Linux; we use the Fusion style
    "platformthemes/libqgtk3",
]


def _keep(entry):
    dest = entry[0].replace("\\", "/").lower()
    return not any(part in dest for part in _QT_UNUSED)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

# Linux: drop system libraries nothing needs anymore after filtering
# (e.g. GTK and its dependencies, used only by the removed GTK theme plugin).
if sys.platform.startswith("linux"):
    from PyInstaller.depend import bindepend

    def _toplevel(dest):
        dest = dest.replace("\\", "/")
        return "/" not in dest and ".so" in dest and not dest.startswith(("libpython", "libQt6", "libpyside6", "libshiboken6"))

    _by_name = {os.path.basename(b[0]): b for b in a.binaries}
    _todo = [b for b in a.binaries if not _toplevel(b[0])]
    _needed = set()
    while _todo:
        _b = _todo.pop()
        try:
            _imports = bindepend.get_imports(_b[1])
        except Exception:
            continue
        for _name, _ in _imports:
            _dep = _by_name.get(_name)
            if _dep and _toplevel(_dep[0]) and _dep[0] not in _needed:
                _needed.add(_dep[0])
                _todo.append(_dep)
    _dropped = [b[0] for b in a.binaries if _toplevel(b[0]) and b[0] not in _needed]
    a.binaries = [b for b in a.binaries if not _toplevel(b[0]) or b[0] in _needed]
    print(f"Dropped {len(_dropped)} unused system libraries")

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="void-appraiser",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="void-appraiser")

# Put the third-party licenses next to the program
import subprocess

subprocess.run(
    [sys.executable, os.path.join(SPECPATH, "licenses.py"), os.path.join(DISTPATH, "void-appraiser", "THIRD-PARTY-LICENSES.txt")],
    check=True,
)

# Put our own license next to the program as well
import shutil

shutil.copy(os.path.join(SPECPATH, "..", "LICENSE"), os.path.join(DISTPATH, "void-appraiser", "LICENSE.txt"))
