"""Filters that see every event in the application."""

from __future__ import annotations

from .qt import QtCore, QtWidgets


class ApplicationEventFilter(QtCore.QObject):
    """Application-wide filter; subclasses define eventFilter.

    Every event passes through it, so reject with the cheapest test first.
    """

    def install(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
