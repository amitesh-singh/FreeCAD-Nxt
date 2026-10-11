"""What kind of editor each FreeCAD property type needs."""

from __future__ import annotations

from typing import Any, TypeGuard

QUANTITY_TYPES = frozenset({
    "App::PropertyLength", "App::PropertyDistance", "App::PropertyAngle",
    "App::PropertyQuantity", "App::PropertyQuantityConstraint",
    "App::PropertyArea", "App::PropertyVolume", "App::PropertySpeed",
    "App::PropertyAcceleration", "App::PropertyForce",
    "App::PropertyPressure", "App::PropertyPercent",
})
NUMBER_TYPES = frozenset({
    "App::PropertyFloat", "App::PropertyFloatConstraint",
    "App::PropertyPrecision", "App::PropertyInteger",
    "App::PropertyIntegerConstraint",
})
TEXT_TYPES = frozenset({
    "App::PropertyString", "App::PropertyFont", "App::PropertyFile",
    "App::PropertyFileIncluded", "App::PropertyPath", "App::PropertyUUID",
})
VECTOR_TYPES = frozenset({
    "App::PropertyVector", "App::PropertyVectorDistance",
    "App::PropertyPosition", "App::PropertyDirection",
})
LENGTH_VECTORS = frozenset({
    "App::PropertyVectorDistance", "App::PropertyPosition",
})
LINK_PREFIX = "App::PropertyLink"
OTHER_KINDS: dict[str, str] = {
    "App::PropertyBool": "bool",
    "App::PropertyEnumeration": "enum",
    "App::PropertyColor": "color",
    "App::PropertyPlacement": "placement",
}

EXPRESSION_PREFIX = "="


def kind_of(type_id: str) -> str:
    if type_id in QUANTITY_TYPES:
        return "quantity"
    if type_id in NUMBER_TYPES:
        return "number"
    if type_id in TEXT_TYPES:
        return "text"
    if type_id in VECTOR_TYPES:
        return "vector"
    if type_id.startswith(LINK_PREFIX):
        return "link"
    return OTHER_KINDS.get(type_id, "other")


def editor_modes(container: Any, prop: str) -> list[str]:
    try:
        return list(container.getEditorMode(prop) or ())
    except Exception:
        return []


def is_expression(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and value.strip().startswith(
        EXPRESSION_PREFIX)


def is_hidden(container: Any, prop: str) -> bool:
    return "Hidden" in editor_modes(container, prop)


def is_read_only(container: Any, prop: str) -> bool:
    return "ReadOnly" in editor_modes(container, prop)


def expression_of(value: str) -> str:
    """The expression typed as "=..." , without its prefix."""
    return value.strip()[len(EXPRESSION_PREFIX):].strip()
