"""Property Inspector templates: Pad and Pocket laid out by task.

Run with: python3 tests/test_inspector_templates.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.inspector import layout as inspector  # noqa: E402
from freecad.nxt.inspector import templates  # noqa: E402

TYPES = ["Length", "UpToLast", "UpToFirst", "UpToFace", "TwoLengths"]
SIDES = ["One side", "Two sides", "Symmetric"]
STARTS = ["Profile plane", "Offset", "Reference"]


Quantity = fakes.Quantity


class Feature:
    """A Pad with the properties FreeCAD 1.0 gives one, or some of them."""

    def __init__(self, type_id: str = "PartDesign::Pad",
                 **values: Any) -> None:
        self.TypeId = type_id
        self.Name = self.Label = type_id.split("::")[-1]
        self._props: dict[str, tuple[str, str, Any]] = {
            "Label": ("Base", "App::PropertyString", self.Name),
            "Type": ("Pad", "App::PropertyEnumeration", "Length"),
            "Length": ("Pad", "App::PropertyLength", Quantity("10 mm")),
            "Length2": ("Pad", "App::PropertyLength", Quantity("0 mm")),
            "Offset": ("Pad", "App::PropertyLength", Quantity("0 mm")),
            "Reversed": ("Pad", "App::PropertyBool", False),
            "Midplane": ("Pad", "App::PropertyBool", False),
            "TaperAngle": ("Pad", "App::PropertyAngle", Quantity("0 °")),
            "TaperAngle2": ("Pad", "App::PropertyAngle", Quantity("0 °")),
            "UseCustomVector": ("Pad", "App::PropertyBool", False),
            "Refine": ("Part Design", "App::PropertyBool", True),
            "Mystery": ("Pad", "App::PropertyFloat", 1.0),
        }
        self.PropertiesList = list(self._props)
        self.ExpressionEngine: list[tuple[str, str]] = []
        for name, (_g, _t, value) in self._props.items():
            setattr(self, name, value)
        for name, value in values.items():
            setattr(self, name, value)

    def getGroupOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][0]

    def getTypeIdOfProperty(self, prop: str) -> str:  # noqa: N802
        return self._props[prop][1]

    def getEditorMode(self, _prop: str) -> list[str]:  # noqa: N802
        return []

    def getDocumentationOfProperty(self, _prop: str) -> str:  # noqa: N802
        return ""

    def getEnumerationsOfProperty(self, prop: str) -> list[str]:  # noqa: N802
        return {"SideType": SIDES, "StartType": STARTS}.get(prop, TYPES)


def layout(*objects: Any, tab: str = inspector.DATA) -> list[dict]:
    return inspector.describe(list(objects), tab)


def names(group: dict) -> list[str]:
    """Every property a card shows: items, columns, then what follows."""
    out = [item["name"] for item in group["items"]]
    for column in group.get("columns", ()):
        out += [item["name"] for item in column["items"]]
    return out + [item["name"] for item in group.get("after", ())]


def modern(**values: Any) -> Feature:
    """A Pad as FreeCAD 27 has it: Sides, and a type for each side."""
    pad = Feature(**values)
    for name, kind, value in (
            ("SideType", "App::PropertyEnumeration", "One side"),
            ("Type2", "App::PropertyEnumeration", "Length"),
            ("TaperAngle2", "App::PropertyAngle", Quantity("0 °"))):
        pad._props[name] = ("Pad", kind, value)
        if name not in pad.PropertiesList:
            pad.PropertiesList.append(name)
        setattr(pad, name, values.get(name, value))
    return pad


class PadTests(unittest.TestCase):

    def test_the_cards_come_first_in_the_templates_order(self) -> None:
        groups = layout(modern())
        self.assertEqual([g["name"] for g in groups[:2]],
                         ["Extent", "Profile"])
        extent = groups[0]
        self.assertEqual([i["name"] for i in extent["items"]], ["SideType"])
        self.assertEqual(len(extent["columns"]), 1)
        self.assertEqual(extent["columns"][0]["title"], "")
        self.assertEqual([i["name"] for i in extent["columns"][0]["items"]],
                         ["Type", "Length", "TaperAngle"])
        self.assertEqual([i["name"] for i in extent["after"]],
                         ["UseCustomVector", "Reversed"])

    def test_two_sides_add_a_second_column(self) -> None:
        extent = layout(modern(SideType="Two sides"))[0]
        self.assertEqual([c["title"] for c in extent["columns"]],
                         ["First side", "Second side"])
        self.assertEqual([i["name"] for i in extent["columns"][1]["items"]],
                         ["Type2", "Length2", "TaperAngle2"])
        self.assertEqual(extent["columns"][1]["items"][1]["label"],
                         "Length")

    def test_midplane_is_gone_once_sides_exist(self) -> None:
        everything = [n for g in layout(modern()) for n in names(g)]
        self.assertNotIn("Midplane", everything)

    def test_editors(self) -> None:
        extent = layout(modern())[0]
        sides = extent["items"][0]
        self.assertEqual((sides["editor"], sides["wide"]),
                         ("segmented", True))
        kind = extent["columns"][0]["items"][0]
        self.assertEqual(kind["editor"], "dropdown")
        self.assertEqual(kind["optionLabels"][:2], ["Dimension", "To last"])
        self.assertNotIn("TwoLengths", kind["options"])
        self.assertEqual(extent["after"][-1]["editor"], "switch")

    def test_direction_is_two_named_states(self) -> None:
        direction = layout(modern())[0]["after"][0]
        self.assertEqual(direction["optionLabels"],
                         ["Sketch normal", "Custom"])

    def test_fields_follow_the_type(self) -> None:
        extent = layout(modern(Type="UpToFace"))[0]
        self.assertIn("Offset", names(extent))
        self.assertNotIn("Length", names(extent))
        self.assertNotIn("TaperAngle", names(extent))

    def test_an_older_freecad_with_two_lengths(self) -> None:
        extent = layout(Feature(Type="TwoLengths"))[0]
        self.assertEqual(len(extent["columns"]), 2)
        self.assertIn("Length2", names(extent))
        self.assertIn("TwoLengths",
                      extent["columns"][0]["items"][0]["options"])

    def test_what_it_does_not_name_is_kept_closed_below(self) -> None:
        groups = layout(modern())
        rest = [g for g in groups if g.get("template") is None]
        self.assertTrue(rest[0]["rest"])
        kept = [n for g in rest for n in names(g)]
        self.assertEqual(sorted(kept), ["Label", "Mystery"])
        self.assertFalse(any(g["open"] for g in rest))
        placed = [n for g in groups for n in names(g)]
        self.assertEqual(len(placed), len(set(placed)))

    def test_a_pocket_shares_it_and_a_mixed_selection_does_not(self) -> None:
        self.assertEqual(layout(Feature("PartDesign::Pocket"))[0]["name"],
                         "Extent")
        both = layout(Feature(), Feature("PartDesign::Fillet"))
        self.assertNotIn("Extent", [g["name"] for g in both])

    def test_the_view_tab_is_left_generic(self) -> None:
        pad = Feature()
        pad.ViewObject = Feature("Gui::ViewProvider")
        self.assertNotIn("Extent",
                         [g["name"] for g in layout(pad, tab=inspector.VIEW)])


def started(start: str = "Profile plane", offset: str = "0 mm") -> Feature:
    """A FreeCAD 27 Pad with its start type and offset."""
    pad = modern()
    for name, kind, value in (
            ("StartType", "App::PropertyEnumeration", start),
            ("StartOffset", "App::PropertyLength", Quantity(offset)),
            ("StartReference", "App::PropertyLinkSub", None)):
        pad._props[name] = ("Pad", kind, value)
        pad.PropertiesList.append(name)
        setattr(pad, name, value)
    return pad


class StartTests(unittest.TestCase):

    def setUp(self) -> None:
        self.template = templates.for_objects([started()])

    def edits(self, pad: Feature, prop: str, value: Any) -> Any:
        return templates.coupled(self.template, [pad], prop, value)

    def test_profile_plane_shows_as_an_offset_of_zero(self) -> None:
        start = next(g for g in layout(started()) if g["name"] == "Start")
        kind, offset = start["items"][:2]
        self.assertEqual(kind["options"], ["Offset", "Reference"])
        self.assertEqual(kind["optionLabels"], ["Profile", "Reference"])
        self.assertEqual(kind["text"], "Offset")
        self.assertFalse(offset["readOnly"])
        self.assertEqual(len(start["items"]), 2)    # no reference yet

    def test_typing_an_offset_makes_the_start_an_offset(self) -> None:
        self.assertEqual(self.edits(started(), "StartOffset", "2"),
                         [("StartType", "Offset"), ("StartOffset", "2")])
        self.assertEqual(self.edits(started(), "StartOffset", "0"),
                         [("StartType", "Offset"), ("StartOffset", "0")])

    def test_zero_never_goes_back_to_the_profile_plane(self) -> None:
        self.assertIsNone(self.edits(started("Offset", "2 mm"),
                                     "StartOffset", "0 mm"))

    def test_choosing_profile_writes_an_offset_start(self) -> None:
        self.assertEqual(self.edits(started("Reference", "0 mm"),
                                    "StartType", "Offset"),
                         [("StartType", "Offset")])
        self.assertEqual(self.edits(started(), "StartType", "Offset"),
                         [("StartType", "Offset")])
        self.assertEqual(self.edits(started("Offset"), "StartType",
                                    "Offset"), [])

    def test_a_reference_start_keeps_its_offset(self) -> None:
        self.assertIsNone(self.edits(started("Reference", "3 mm"),
                                     "StartOffset", "0"))

    def test_other_edits_are_left_alone(self) -> None:
        self.assertIsNone(self.edits(started(), "Length", "5"))


class ShowIfTests(unittest.TestCase):

    def test_a_missing_property_is_left_out_of_the_test(self) -> None:
        item = templates.Item(
            "Length2", show_if=(("SideType", ("Two sides",)),))
        self.assertTrue(templates.shown(item, [Feature()]))

    def test_any_test_holding_is_enough(self) -> None:
        item = templates.Item(
            "Length2", show_if=(("Type", ("TwoLengths",)),
                                ("Midplane", (True,))))
        self.assertFalse(templates.shown(item, [Feature()]))
        self.assertTrue(templates.shown(
            item, [Feature(Midplane=True)]))

    def test_the_shipped_files_load(self) -> None:
        templates.invalidate()
        ids = [t.id for t in templates.loaded()]
        self.assertIn("pd-extrude", ids)
        self.assertIn("pd-fillet", ids)


class Fillet(Feature):
    """A Fillet as FreeCAD gives one."""

    def __init__(self, **values: Any) -> None:
        super().__init__("PartDesign::Fillet")
        self._props = {
            "Label": ("Base", "App::PropertyString", "Fillet"),
            "Base": ("Base", "App::PropertyLinkSub", None),
            "SupportTransform": ("Base", "App::PropertyBool", False),
            "Radius": ("Fillet", "App::PropertyQuantityConstraint",
                       Quantity("1 mm")),
            "UseAllEdges": ("Fillet", "App::PropertyBool", False),
            "Refine": ("Part Design", "App::PropertyBool", False),
        }
        self.PropertiesList = list(self._props)
        for name, (_g, _t, value) in self._props.items():
            setattr(self, name, values.get(name, value))


class FilletTests(unittest.TestCase):

    def test_radius_and_edges_first(self) -> None:
        groups = layout(Fillet())
        self.assertEqual([g["name"] for g in groups[:2]],
                         ["Fillet", "Result"])
        self.assertEqual(names(groups[0]), ["Radius", "UseAllEdges", "Base"])
        self.assertEqual(groups[0]["items"][1]["optionLabels"],
                         ["Selected", "All"])

    def test_all_edges_hides_the_selection(self) -> None:
        self.assertEqual(names(layout(Fillet(UseAllEdges=True))[0]),
                         ["Radius", "UseAllEdges"])

    def test_result_switches(self) -> None:
        result = layout(Fillet())[1]
        self.assertEqual(names(result), ["Refine", "SupportTransform"])
        self.assertEqual({i["editor"] for i in result["items"]}, {"switch"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
