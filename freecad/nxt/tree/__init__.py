"""Nxt model panel: a timeline view of a FreeCAD document.

Layering, each depending only on those above: scene (no Qt), icons,
models, bridge, observers, panel. See DESIGN.md.
"""

from __future__ import annotations

__all__ = ["scene", "icons", "models", "bridge", "observers", "panel"]
