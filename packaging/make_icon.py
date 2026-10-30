"""Render packaging/icon.png (1024x1024) from the logo symbol. Run once; the PNG is committed."""

from pathlib import Path

from PySide6 import QtCore, QtGui, QtSvg

HERE = Path(__file__).resolve().parent
LOGO = HERE.parent / "src" / "ovito_tachyon" / "assets" / "logo.svg"
SIZE = 1024
TILE = 824  # macOS icon grid: 824 px rounded square on a 1024 px canvas
RADIUS = 185
GLYPH = 520

app = QtGui.QGuiApplication([])
svg = LOGO.read_text(encoding="utf-8").replace('fill="#000000"', 'fill="#fafafa"')
renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))

image = QtGui.QImage(SIZE, SIZE, QtGui.QImage.Format_ARGB32_Premultiplied)
image.fill(QtCore.Qt.transparent)
painter = QtGui.QPainter(image)
painter.setRenderHint(QtGui.QPainter.Antialiasing)
offset = (SIZE - TILE) / 2
painter.setPen(QtCore.Qt.NoPen)
painter.setBrush(QtGui.QColor("#0a0a0a"))
painter.drawRoundedRect(QtCore.QRectF(offset, offset, TILE, TILE), RADIUS, RADIUS)
g = (SIZE - GLYPH) / 2
renderer.render(painter, QtCore.QRectF(g, g, GLYPH, GLYPH))
painter.end()
image.save(str(HERE / "icon.png"))
print(HERE / "icon.png")
