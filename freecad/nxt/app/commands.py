"""The addon's GUI commands.

Work is imported in `Activated`, so registering pulls in no QtQuick.
"""

from __future__ import annotations

import FreeCADGui as Gui

from .i18n import QT_TRANSLATE_NOOP

ICON = "FreeCAD-Nxt.svg"


class _Command:
    """Resources from class attributes."""

    menu_text: str = ""
    tool_tip: str = ""
    pixmap: str = ""

    def GetResources(self) -> dict[str, str]:  # noqa: N802 - FreeCAD command API
        resources = {"MenuText": self.menu_text, "ToolTip": self.tool_tip}
        if self.pixmap:
            resources["Pixmap"] = self.pixmap
        return resources

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return True


class ModelPanel(_Command):
    """Show or hide the Nxt model panel."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_ModelPanel", "Nxt model panel")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_ModelPanel",
        "Model history as a timeline, with a draggable rollback bar")
    pixmap = ICON

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tree import panel
        panel.toggle()


class ModelPanelOverlay(_Command):
    """Draw the panel as floating labels over the 3D view."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_ModelPanelOverlay",
                                  "Nxt panel overlay")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_ModelPanelOverlay",
        "Draw the model panel as floating labels with no background")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tree import panel
        panel.toggle_overlay()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        from ..tree import panel
        return panel.is_open()


class PropertyInspector(_Command):
    """Open FreeCAD's Property editor in an inspector beside the panel."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_PropertyInspector",
                                  "Nxt Property Inspector")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_PropertyInspector",
        "Show the selection's properties beside the model panel")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..inspector import host as property_inspector
        property_inspector.toggle()


class Isolate(_Command):
    """Show only the selection in the 3D view, until told otherwise."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_Isolate", "Isolate")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_Isolate",
        "Show only the selected objects in the 3D view; again to exit")
    pixmap = "Std_ShowSelection"

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from . import services
        isolation = services.isolation()
        if isolation is not None:
            isolation.toggle_selection()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        from . import services
        isolation = services.isolation()
        if isolation is None:
            return False
        return isolation.active() or bool(Gui.Selection.getSelection())


class ShowAll(_Command):
    """Show everything but datums, coordinate systems and joints."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_ShowAll", "Show all")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_ShowAll",
        "Show every object except datums, coordinate systems and "
        "Assembly joints; inside a Body only its tip")
    pixmap = "Std_ShowObjects"

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tools import show_all
        show_all.run()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return Gui.ActiveDocument is not None


class SectionView(_Command):
    """Cut the 3D view with a plane; its cut faces are hatched."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionView", "Section view")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_SectionView",
        "Cut the view with a plane facing you, or on the selected face, "
        "datum plane or three points; drag its frame to move it. Again "
        "to finish editing; up to three sections can cut at once")
    pixmap = "nxt_section"

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tools import section_view
        section_view.toggle()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return Gui.ActiveDocument is not None


class SectionFlip(_Command):
    """Keep the other side of the section plane."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionFlip", "Flip section")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_SectionFlip",
                                 "Show the other side of the section plane")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tools import section_view
        section_view.flip()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return _section_open()


def _section_open() -> bool:
    import sys
    module = sys.modules.get("freecad.nxt.tools.section_view")
    return module is not None and module.current() is not None


class SectionAlign(_Command):
    """Re-aim the section at the selection, or square to the view."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionAlign",
                                  "Align section to selection")
    tool_tip = QT_TRANSLATE_NOOP(
        "Nxt_SectionAlign",
        "Put the section plane on the selected face or datum plane, or "
        "through three selected points; with nothing selected, square to "
        "the view")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tools import section_view
        section_view.align_to_selection()

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return _section_open()


class _SectionAxis(_Command):
    axis = "x"

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from ..tools import section_view
        section_view.set_axis(self.axis)

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return _section_open()


class SectionX(_SectionAxis):
    """Cut across X."""

    axis = "x"
    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionX", "Section across X")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_SectionX",
                                 "Turn the section plane square to X")


class SectionY(_SectionAxis):
    """Cut across Y."""

    axis = "y"
    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionY", "Section across Y")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_SectionY",
                                 "Turn the section plane square to Y")


class SectionZ(_SectionAxis):
    """Cut across Z."""

    axis = "z"
    menu_text = QT_TRANSLATE_NOOP("Nxt_SectionZ", "Section across Z")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_SectionZ",
                                 "Turn the section plane square to Z")


class Reload(_Command):
    """Hot-reload the addon's Python modules during development."""

    menu_text = QT_TRANSLATE_NOOP("Nxt_Reload", "Reload Nxt")
    tool_tip = QT_TRANSLATE_NOOP("Nxt_Reload",
                                 "Hot-reload the addon's Python modules")

    def Activated(self) -> None:  # noqa: N802 - FreeCAD command API
        from .. import reload_all
        reload_all()


class MenuGroup:
    """The FreeCAD-Nxt submenu of the View menu.

    DropDownMenu makes FreeCAD draw this command group as a submenu.
    """

    def GetCommands(self) -> list[str]:  # noqa: N802 - FreeCAD command API
        return list(MENU)

    def GetResources(self) -> dict[str, object]:  # noqa: N802
        return {"MenuText": "FreeCAD-Nxt",
                "ToolTip": QT_TRANSLATE_NOOP("Nxt_Menu",
                                             "The Nxt model panel's commands"),
                "Pixmap": ICON,
                "DropDownMenu": True,
                "Exclusive": False}

    def IsActive(self) -> bool:  # noqa: N802 - FreeCAD command API
        return True


COMMANDS: dict[str, type[_Command]] = {
    "Nxt_ModelPanel": ModelPanel,
    "Nxt_ModelPanelOverlay": ModelPanelOverlay,
    "Nxt_PropertyInspector": PropertyInspector,
    "Nxt_Isolate": Isolate,
    "Nxt_ShowAll": ShowAll,
    "Nxt_SectionView": SectionView,
    "Nxt_SectionFlip": SectionFlip,
    "Nxt_SectionAlign": SectionAlign,
    "Nxt_SectionX": SectionX,
    "Nxt_SectionY": SectionY,
    "Nxt_SectionZ": SectionZ,
    "Nxt_Reload": Reload,
}

#: Reload is listed only during development.
MENU = ("Nxt_ModelPanel", "Nxt_ModelPanelOverlay", "Nxt_PropertyInspector",
        "Nxt_Isolate", "Nxt_ShowAll",
        "Nxt_SectionView", "Nxt_SectionFlip",
        "Nxt_SectionAlign", "Nxt_SectionX",
        "Nxt_SectionY", "Nxt_SectionZ",
        "Nxt_Reload")

GROUP = "Nxt_Menu"


def register() -> None:
    for name, command in COMMANDS.items():
        Gui.addCommand(name, command())
    Gui.addCommand(GROUP, MenuGroup())
