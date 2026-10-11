"""Qt widget helpers."""

from __future__ import annotations

from typing import Any


def alive(obj: Any) -> bool:
    """Whether a Qt object still exists on the C++ side."""
    if obj is None:
        return False
    try:
        import shiboken6
        return bool(shiboken6.isValid(obj))
    except ImportError:
        return True
