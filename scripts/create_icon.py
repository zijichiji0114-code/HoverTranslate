"""Draw the app's native vector mark and export Windows shortcut icon sizes."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QImage,
                          QLinearGradient, QPainter, QPainterPath, QPen)
from PySide6.QtSvg import QSvgGenerator


def paint(painter, family):
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(40, 30, 480, 490)
    gradient.setColorAt(0, QColor("#5378E9"))
    gradient.setColorAt(1, QColor("#6B50D4"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(16, 16, 480, 480), 108, 108)

    font = QFont(family)
    font.setPixelSize(262)
    font.setWeight(QFont.Weight.Bold)
    glyph = QPainterPath()
    glyph.addText(QPointF(0, 0), font, "译")
    bounds = glyph.boundingRect()
    glyph.translate(225-bounds.center().x(), 216-bounds.center().y())
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawPath(glyph)

    cursor = QPainterPath(QPointF(338, 310))
    for x, y in [(344, 416), (370, 391), (394, 438), (417, 426), (390, 379), (426, 376)]:
        cursor.lineTo(x, y)
    cursor.closeSubpath()
    pen = QPen(QColor("#433CA3"), 12)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawPath(cursor)


def main():
    app = QGuiApplication([])
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyhbd.ttc")
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        raise RuntimeError("Microsoft YaHei Bold is required to generate the Chinese vector glyph")
    output = Path(__file__).resolve().parents[1]/"assets"
    output.mkdir(exist_ok=True)
    canvas = QImage(512, 512, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    paint(painter, families[0])
    painter.end()
    if not canvas.save(str(output/"hovertranslate.png")):
        raise RuntimeError("Could not save icon PNG")

    svg = QSvgGenerator()
    svg.setFileName(str(output/"hovertranslate.svg"))
    svg.setSize(QSize(512, 512))
    svg.setViewBox(QRect(0, 0, 512, 512))
    svg.setTitle("HoverTranslate · 悬停翻译")
    painter = QPainter(svg)
    paint(painter, families[0])
    painter.end()

    svg_path = output/"hovertranslate.svg"
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines())+"\n", encoding="utf-8")

    image = Image.open(output/"hovertranslate.png").convert("RGBA")
    image.save(output/"hovertranslate.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    image.resize((128, 128), Image.Resampling.LANCZOS).save(output/"hovertranslate-preview.png")
    print("Created SVG, PNG, preview and multi-size ICO in", output)


if __name__ == "__main__":
    main()
