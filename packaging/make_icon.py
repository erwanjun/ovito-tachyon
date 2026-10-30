"""Render packaging/icon.png (1024x1024) from the logo symbol. Run once; the PNG is committed."""

from pathlib import Path

from PySide6 import QtGui

from ovito_tachyon.app import app_icon_image

HERE = Path(__file__).resolve().parent

app = QtGui.QGuiApplication([])
app_icon_image(1024).save(str(HERE / "icon.png"))
print(HERE / "icon.png")
