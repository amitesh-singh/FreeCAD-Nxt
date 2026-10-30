"""Serve ViewObject icons to QML.

URLs: image://nxticon/<doc>/<object>/<revision>[/gray],
image://nxticon/@cmd/<Command> and image://nxticon/@pin/<pinned>/<rgb>.
The revision only busts QML's cache.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

# Imported only when the panel builds its QML (see qtquick.py).
from PySide6.QtQuick import QQuickImageProvider

from ..core.qt import QtCore, QtGui, QtWidgets

_IMAGE_TYPE = QQuickImageProvider.ImageType.Pixmap

PROVIDER_ID = "nxticon"
#: Cannot clash with a document name, which starts with a letter.
COMMAND_PREFIX = "@cmd"
#: image://nxticon/@pin/<1 pinned, 0 not>/<colour, hex without #>
PIN_PREFIX = "@pin"
VIRTUAL_PREFIX = "~"      # scene.VIRTUAL_PREFIX; no scene import here
DEFAULT_ICON_PX = 16


def url_for(doc_name: str, obj_name: str, revision: int = 0,
            gray: bool = False) -> str:
    url = "image://%s/%s/%s/%d" % (PROVIDER_ID, doc_name, obj_name, revision)
    return url + "/gray" if gray else url


class IconProvider(QQuickImageProvider):
    """Pixmap provider backed by live ViewObject icons."""

    def __init__(self) -> None:
        super().__init__(_IMAGE_TYPE)
        self._fallback: QtGui.QIcon | None = None

    # QQuickImageProvider
    def requestPixmap(self, image_id: str, size: QtCore.QSize | None,
                      requested_size: QtCore.QSize) -> QtGui.QPixmap:
        width = requested_size.width() or DEFAULT_ICON_PX
        height = requested_size.height() or DEFAULT_ICON_PX
        pixmap = self._render(image_id, width, height)
        if size is not None:
            size.setWidth(pixmap.width())
            size.setHeight(pixmap.height())
        return pixmap

    # internals
    def _render(self, image_id: str, width: int,
                height: int) -> QtGui.QPixmap:
        try:
            parts = (image_id or "").split("/")
            if len(parts) < 2:
                return self._blank(width, height)
            doc_name, obj_name = parts[0], parts[1]
            if doc_name == PIN_PREFIX and len(parts) > 2:
                from ..ui.glyphs import pin_icon
                return pin_icon(min(width, height), obj_name == "1",
                                QtGui.QColor("#" + parts[2])
                                ).pixmap(width, height)
            if doc_name == COMMAND_PREFIX:
                from ..menus import runner
                command_icon = runner.command_icon(obj_name)
                if command_icon is None:
                    return self._blank(width, height)
                return command_icon.pixmap(width, height)
            gray = parts[-1] == "gray"
            if obj_name.startswith(VIRTUAL_PREFIX):
                return self._folder().pixmap(width, height)
            icon = self._live_icon(doc_name, obj_name)
            if icon is None:
                return self._blank(width, height)
            if isinstance(icon, str):
                icon = (Gui.getIcon(icon) if hasattr(Gui, "getIcon")
                        else QtGui.QIcon(icon))
            pixmap = icon.pixmap(width, height)
            if pixmap.isNull():
                return self._blank(width, height)
            return self._desaturate(pixmap) if gray else pixmap
        except Exception:
            App.Console.PrintError(
                "Nxt: icon render failed for %r\n" % image_id)
            App.Console.PrintError(traceback.format_exc())
            return self._blank(width, height)

    @staticmethod
    def _live_icon(doc_name: str, obj_name: str) -> Any:
        """The object's icon, or None while it is not there to draw.

        QML asks for rows the document has just closed, and while one
        opens it asks before every view provider is ready: neither is an
        error, so neither is reported.
        """
        try:
            doc: Any = App.listDocuments().get(doc_name)
            obj = doc.getObject(obj_name) if doc is not None else None
            vo = getattr(obj, "ViewObject", None)
            return getattr(vo, "Icon", None) if vo is not None else None
        except (RuntimeError, ReferenceError):  # deleted mid-request
            return None

    @staticmethod
    def _folder() -> QtGui.QIcon:
        icon = QtGui.QIcon(":/icons/folder.svg")
        if icon.isNull():
            icon = QtWidgets.QApplication.style().standardIcon(
                QtWidgets.QStyle.StandardPixmap.SP_DirIcon)
        return icon

    @staticmethod
    def _desaturate(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
        """The same icon in grey, alpha intact (Grayscale8 drops alpha)."""
        image = pixmap.toImage().convertToFormat(
            QtGui.QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                colour = image.pixelColor(x, y)
                if colour.alpha() == 0:
                    continue
                grey = QtGui.qGray(colour.rgb())
                image.setPixelColor(x, y, QtGui.QColor(grey, grey, grey,
                                                       colour.alpha()))
        return QtGui.QPixmap.fromImage(image)

    def _blank(self, width: int, height: int) -> QtGui.QPixmap:
        pixmap = QtGui.QPixmap(max(width, 1), max(height, 1))
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        return pixmap
