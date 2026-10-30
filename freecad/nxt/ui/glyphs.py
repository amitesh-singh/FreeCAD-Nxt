"""Small drawn icons Nxt shares between its widgets and its QML."""

from __future__ import annotations

from ..core.qt import QtCore, QtGui


def pin_icon(size: int, pinned: bool, colour: QtGui.QColor,
             ratio: float = 1.0) -> QtGui.QIcon:
    """A pushpin: upright and filled when pinned, tilted and hollow if not."""
    ratio = ratio or 1.0
    pixmap = QtGui.QPixmap(round(size * ratio), round(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2, size / 2)
    if not pinned:
        painter.rotate(45)
    painter.scale(size, size)
    painter.translate(-0.5, -0.5)

    pen = QtGui.QPen(colour)
    pen.setWidthF(0.08)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtGui.QBrush(colour) if pinned
                     else QtCore.Qt.BrushStyle.NoBrush)

    head = QtGui.QPainterPath()
    head.addRoundedRect(QtCore.QRectF(0.30, 0.08, 0.40, 0.12), 0.04, 0.04)
    body = QtGui.QPolygonF([QtCore.QPointF(0.38, 0.20),
                            QtCore.QPointF(0.62, 0.20),
                            QtCore.QPointF(0.60, 0.50),
                            QtCore.QPointF(0.40, 0.50)])
    collar = QtGui.QPainterPath()
    collar.addRoundedRect(QtCore.QRectF(0.22, 0.50, 0.56, 0.10), 0.04, 0.04)
    painter.drawPath(head)
    painter.drawPolygon(body)
    painter.drawPath(collar)
    painter.drawLine(QtCore.QPointF(0.5, 0.60), QtCore.QPointF(0.5, 0.94))
    painter.end()
    return QtGui.QIcon(pixmap)
