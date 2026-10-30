# PyInstaller spec for the desktop app.  Build with:  pyinstaller packaging/ovito-tachyon.spec
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

import ovito_tachyon

HERE = Path(SPECPATH)
APP = "OVITO-Tachyon"
VERSION = ovito_tachyon.__version__

datas, binaries, hiddenimports = [], [], []
for package in ("ovito", "imageio_ffmpeg"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
# The bundled ray tracer is an executable, not a module: ship it as a binary next to the package.
exe_name = "tachyon.exe" if sys.platform == "win32" else "tachyon"
binaries.append((str(Path(ovito_tachyon.__file__).parent / "bin" / exe_name), "ovito_tachyon/bin"))
datas.append((str(Path(ovito_tachyon.__file__).parent / "assets"), "ovito_tachyon/assets"))
# ovito.qt_compat imports these Qt modules by name at runtime, which PyInstaller cannot see.
hiddenimports += [f"PySide6.{m}" for m in ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtXml", "QtSvg")]
hiddenimports += ["ovito_tachyon.app"]

a = Analysis(
    [str(HERE / "launcher.py")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
)
pyz = PYZ(a.pure)
icon = str(HERE / "icon.png")
# OVT_CONSOLE=1 builds a console variant whose output can be captured (CI diagnostics).
console = os.environ.get("OVT_CONSOLE") == "1"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP, console=console, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name=APP)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon=icon,
        bundle_identifier="io.github.erwanjun.ovito-tachyon",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
