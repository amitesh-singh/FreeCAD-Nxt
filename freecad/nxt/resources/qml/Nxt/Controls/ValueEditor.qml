import QtQuick

// The editor for one property, chosen by the property's kind
// (spec.kind), with spec.editor picking a template's variant.
Item {
    id: editor

    property var spec: ({})
    property bool editable: true
    //: "Document#Name" for expression help; empty for none.
    property string owner: ""

    //: Names itself (a switch's text); off where a label column does.
    property bool labelled: true
    //: Links as removable chips and a + to pick more.
    property bool editsLinks: false
    property bool picking: false

    signal edited(var value)
    signal leadEdited(var value)
    signal linkRemoved(string key)
    signal pickRequested()
    signal partEdited(string path, string text)
    signal colourRequested()
    signal nativeRequested()

    readonly property string kind: editor.spec.kind || ""
    readonly property bool locked: !!editor.spec.readOnly
    readonly property var lead: editor.spec.lead || null
    readonly property bool hasExpression:
        !!editor.spec.expression && editor.spec.expression.length > 0
    readonly property string shown: editor.hasExpression
                                    ? "= " + editor.spec.expression
                                    : (editor.spec.text || "")
    readonly property bool isField: editor.kind === "quantity"
                                    || editor.kind === "number"
                                    || editor.kind === "text"
    property bool choosing: false

    implicitWidth: body.implicitWidth
    implicitHeight: body.implicitHeight

    readonly property var leadingNumber: /^\s*[-+]?[\d.,]+(?:[eE][-+]?\d+)?/

    function selectValue() {
        var input = field.input;
        if (!input.activeFocus)
            return;
        var number = editor.kind === "quantity" && !editor.hasExpression
                     ? editor.leadingNumber.exec(input.text) : null;
        if (number)
            input.select(number[0].search(/\S/), number[0].length);
        else
            input.selectAll();
    }

    Component {
        id: choices
        ChoiceList {}
    }

    function labelOf(value, spec) {
        spec = spec || editor.spec;
        var values = spec.options || [];
        var labels = spec.optionLabels || [];
        var i = values.indexOf(value);
        return (i >= 0 && labels[i]) || value;
    }

    function openChoices(anchor, spec, done) {
        spec = spec || editor.spec;
        done = done || editor.edited;
        var root = anchor.Window.contentItem;
        // A view only as tall as its content (a task dialog's) cannot show
        // the list: its host offers a menu of its own instead.
        if (typeof nativeChoices !== "undefined" && nativeChoices) {
            var at = anchor.mapToItem(root, 0, anchor.height);
            var picked = nativeChoices.choose(
                spec.options, spec.optionLabels || [], spec.text || "",
                at.x, at.y, anchor.width);
            if (picked.length > 0 && picked !== spec.text)
                done(picked);
            return;
        }
        var list = choices.createObject(root, {
            options: spec.options,
            labels: spec.optionLabels || [],
            current: spec.text,
            below: anchor.mapToItem(root, 0, anchor.height),
            anchorHeight: anchor.height,
            minWidth: anchor.width
        });
        editor.choosing = true;
        list.chosen.connect(function (value) {
            if (value !== spec.text)
                done(value);
        });
        list.Component.destruction.connect(function () {
            editor.choosing = false;
        });
        list.forceActiveFocus();
    }

    Column {
        id: body
        width: editor.width
        spacing: 3

        Row {
            visible: editor.isField && !editor.locked
            spacing: 4
            width: parent.width
            height: theme.fieldHeight

            TextField {
                id: field
                owner: editor.kind === "text" ? "" : editor.owner
                width: parent.width
                leading: leadBox.visible ? leadBox.width : 0
                // The unit sits inside the field, after the number.
                suffix: !!editor.spec.unit && !editor.hasExpression
                        ? editor.spec.unit : ""
                placeholder: editor.spec.mixed ? qsTr("— mixed") : ""
                Component.onCompleted: field.text = editor.spec.mixed
                                                    ? "" : editor.shown
                onAccepted: {
                    editor.edited(field.text);
                    field.input.focus = false;
                }
                onDismissed: {
                    field.text = editor.spec.mixed ? "" : editor.shown;
                    field.input.focus = false;
                }
                Connections {
                    target: editor
                    function onShownChanged() {
                        if (!field.input.activeFocus)
                            field.text = editor.spec.mixed ? ""
                                                           : editor.shown;
                    }
                }
                // What the value means (Type before Length), inside the field.
                DropBox {
                    id: leadBox
                    visible: !!editor.lead
                    inset: true
                    x: 1
                    y: 1
                    height: parent.height - 2
                    text: editor.lead ? editor.labelOf(editor.lead.text, editor.lead) : ""
                    onOpened: editor.openChoices(field, editor.lead, editor.leadEdited)
                }
                Connections {
                    target: field.input
                    // Deferred: the focusing press places the cursor later.
                    function onActiveFocusChanged() {
                        if (field.input.activeFocus)
                            Qt.callLater(editor.selectValue);
                    }
                }
            }

        }

        Row {
            visible: editor.kind === "bool" && !editor.spec.editor
            spacing: 5
            height: theme.fieldHeight

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: theme.markSize
                height: theme.markSize
                radius: 2
                opacity: editor.locked ? 0.5 : 1.0
                color: editor.spec.checked && !editor.spec.mixed
                       ? theme.accent : "transparent"
                border.width: 1
                border.color: editor.spec.checked || checkHover.hovered
                              ? theme.accent : theme.border

                Text {
                    anchors.centerIn: parent
                    visible: !!editor.spec.checked || !!editor.spec.mixed
                    text: editor.spec.mixed ? "–" : "✓"
                    font.pixelSize: theme.fontAside
                    color: editor.spec.mixed ? theme.textDim
                                             : theme.accentText
                }
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: editor.spec.mixed ? qsTr("mixed")
                      : (editor.spec.checked ? qsTr("on") : qsTr("off"))
                font.pixelSize: theme.fontSmall
                font.italic: editor.locked
                color: editor.locked ? theme.textDim : theme.text
            }

            HoverHandler {
                id: checkHover
                enabled: !editor.locked
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                enabled: !editor.locked
                onTapped: editor.edited(!editor.spec.checked)
            }
        }

        Segmented {
            id: joined
            visible: editor.spec.editor === "segmented"
                     && (editor.kind === "enum" || editor.kind === "bool")
            enabled: !editor.locked
            width: parent.width
            height: theme.fieldHeight
            value: editor.spec.mixed ? undefined
                 : editor.kind === "bool" ? !!editor.spec.checked
                 : editor.spec.text
            options: {
                var labels = editor.spec.optionLabels || [];
                if (editor.kind === "bool")
                    return [{value: false, label: labels[0] || qsTr("Off")},
                            {value: true, label: labels[1] || qsTr("On")}];
                var out = [];
                var values = editor.spec.options || [];
                for (var i = 0; i < values.length; ++i)
                    out.push({value: values[i], label: labels[i] || values[i]});
                return out;
            }
            onPicked: function (value) {
                if (value !== joined.value)
                    editor.edited(value);
            }
        }

        NxtSwitch {
            id: toggle
            visible: editor.kind === "bool" && editor.spec.editor === "switch"
            enabled: !editor.locked
            width: editor.labelled ? parent.width : implicitWidth
            height: theme.fieldHeight
            text: editor.labelled ? editor.spec.label || "" : ""
            checked: !!editor.spec.checked && !editor.spec.mixed
            onToggled: {
                editor.edited(toggle.checked);
                toggle.checked = Qt.binding(function () {
                    return !!editor.spec.checked && !editor.spec.mixed;
                });
            }
        }

        DropBox {
            id: dropBox
            visible: !editor.labelled && editor.kind === "enum"
                     && editor.spec.editor !== "segmented" && !editor.locked
            width: parent.width
            text: editor.spec.mixed ? qsTr("— mixed") : editor.labelOf(editor.spec.text || "")
            active: editor.choosing
            onOpened: if (!editor.choosing) editor.openChoices(dropBox)
        }

        Chip {
            id: choice
            visible: editor.kind === "enum" && editor.spec.editor !== "segmented"
                     && !dropBox.visible
            text: (editor.spec.mixed ? qsTr("— mixed")
                   : editor.labelOf(editor.spec.text || ""))
                  + (editor.locked ? "" : "  ▾")
            active: editor.choosing
            interactive: !editor.locked
            onClicked: if (!editor.choosing) editor.openChoices(choice)
        }

        Row {
            visible: editor.kind === "color"
            spacing: 6
            height: theme.fieldHeight

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: theme.markSize + 2
                height: theme.markSize + 2
                radius: 2
                color: editor.spec.text || "transparent"
                border.width: 1
                border.color: colourHover.hovered ? theme.accent : theme.border
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: editor.spec.mixed ? qsTr("mixed") : (editor.spec.text || "")
                font.pixelSize: theme.fontSmall
                color: theme.text
            }
            HoverHandler {
                id: colourHover
                enabled: !editor.locked
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                enabled: !editor.locked
                onTapped: editor.colourRequested()
            }
        }

        Repeater {
            model: editor.kind === "placement" ? [qsTr("Position"), qsTr("Rotation")]
                 : editor.kind === "vector" ? [""] : []

            Column {
                id: line
                required property string modelData
                required property int index
                width: body.width
                spacing: 2

                Text {
                    visible: line.modelData.length > 0
                    text: line.modelData
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }

                Flow {
                    width: parent.width
                    spacing: 4

                    Repeater {
                        model: {
                            var parts = editor.spec.parts || [];
                            if (editor.kind !== "placement")
                                return parts;
                            return line.index === 0 ? parts.slice(0, 3)
                                                    : parts.slice(3);
                        }

                        Row {
                            id: part
                            required property var modelData
                            spacing: 3
                            height: theme.fieldHeight

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: part.modelData.label
                                font.pixelSize: theme.fontAside
                                font.bold: true
                                color: theme.textDim
                            }
                            TextField {
                                id: partField
                                width: 58
                                Component.onCompleted:
                                    partField.text = part.modelData.text
                                onAccepted: {
                                    editor.partEdited(part.modelData.path,
                                                      partField.text);
                                    partField.input.focus = false;
                                }
                                onDismissed: {
                                    partField.text = part.modelData.text;
                                    partField.input.focus = false;
                                }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: part.modelData.unit.length > 0
                                text: part.modelData.unit
                                font.pixelSize: theme.fontAside
                                color: theme.textDim
                            }
                        }
                    }
                }
            }
        }

        LinkChips {
            visible: editor.kind === "link" && editor.editsLinks
            width: parent.width
            items: editor.spec.chips || []
            editable: !editor.locked
            picking: editor.picking
            onRemoved: function (key) { editor.linkRemoved(key); }
            onPickRequested: editor.pickRequested()
        }

        Flow {
            visible: editor.kind === "link" && !editor.editsLinks
            width: parent.width
            spacing: 3

            Repeater {
                model: editor.kind === "link" ? editor.spec.links : []
                Chip {
                    required property string modelData
                    text: modelData
                    interactive: false
                }
            }
            Text {
                visible: editor.kind === "link"
                         && (!editor.spec.links
                             || editor.spec.links.length === 0)
                text: qsTr("none")
                font.pixelSize: theme.fontSmall
                font.italic: true
                color: theme.textDim
            }
        }

        Row {
            visible: (editor.isField && editor.locked)
                     || editor.kind === "other"
                     || (editor.kind === "link" && !editor.locked
                         && !editor.editsLinks)
            spacing: 6
            width: parent.width

            Text {
                width: Math.min(implicitWidth,
                                parent.width - (edit.visible
                                                ? edit.width + 6 : 0))
                visible: editor.kind !== "link"
                text: editor.shown + (editor.spec.unit
                                      ? " " + editor.spec.unit : "")
                elide: Text.ElideRight
                font.pixelSize: theme.fontSmall
                font.italic: editor.locked
                color: theme.textDim
                Accessible.name: qsTr("%1, read only").arg(editor.spec.label || "")
            }

            // FreeCAD's own editor, for unknown kinds and links.
            Text {
                id: edit
                visible: !editor.locked && (editor.kind === "other"
                                            || editor.kind === "link")
                text: qsTr("Edit…")
                font.pixelSize: theme.fontSmall
                font.underline: editHover.hovered
                color: theme.link
                Accessible.role: Accessible.Button
                Accessible.name: qsTr("Edit %1").arg(editor.spec.label || "")

                HoverHandler {
                    id: editHover
                    cursorShape: Qt.PointingHandCursor
                }
                TapHandler { onTapped: editor.nativeRequested() }
            }
        }
    }
}
