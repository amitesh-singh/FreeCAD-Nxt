import QtQuick
import Nxt.Controls
import Nxt.Inspector

// The Property Inspector's contents: every property of the selection, laid out
// from what the objects say about themselves (see inspector.py).
//
// Groups are FreeCAD's own and sit on tinted cards. Inside one, compact
// editors take half a row and wide ones a full row, so a group reads as a
// short form rather than a long list.
Rectangle {
    id: root
    color: theme.background
    implicitWidth: 330
    implicitHeight: 480

    readonly property int pad: 8
    readonly property int gap: 8

    // --- filter and Data / View ----------------------------------------- #

    Row {
        id: top
        x: root.pad
        y: root.pad
        width: root.width - 2 * root.pad
        spacing: root.gap
        height: theme.fieldHeight

        TextField {
            id: filter
            width: parent.width - tabs.width - root.gap
            placeholder: qsTr("Filter")
            onEdited: function (value) { inspector.setFilter(value); }
            onDismissed: {
                filter.text = "";
                inspector.setFilter("");
            }
        }

        Row {
            id: tabs
            spacing: 2

            Repeater {
                // Keys to the bridge; labels to the user.
                model: [{key: "Data", label: qsTr("Data")},
                        {key: "View", label: qsTr("View")}]

                Chip {
                    required property var modelData
                    text: modelData.label
                    active: inspector.tab === modelData.key
                    onClicked: inspector.setTab(modelData.key)
                }
            }
        }
    }

    // --- the groups ------------------------------------------------------- #

    ListView {
        id: groups
        anchors.top: top.bottom
        anchors.topMargin: root.gap
        anchors.bottom: parent.bottom
        width: root.width
        clip: true
        spacing: root.gap
        boundsBehavior: Flickable.StopAtBounds
        model: inspector.groups
        bottomMargin: root.pad

        delegate: Item {
            id: slot
            required property var modelData
            readonly property bool rest: !!modelData.rest

            width: root.width
            height: group.y + group.height

            // Behind a template's cards, the generic groups it left.
            Text {
                id: restHeading
                visible: slot.rest
                x: root.pad + 2
                y: 2
                text: qsTr("Everything else")
                font.pixelSize: theme.fontAside
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 0.6
                color: theme.textDim
            }

        Rectangle {
            id: group
            readonly property var modelData: slot.modelData
            property bool opened: modelData.open

            x: root.pad
            y: slot.rest ? restHeading.height + 6 : 0
            width: root.width - 2 * root.pad
            height: groupBody.implicitHeight + 2 * root.pad
            radius: 4
            color: theme.surface

            Column {
                id: groupBody
                x: root.pad
                y: root.pad
                width: parent.width - 2 * root.pad
                spacing: root.gap

                Row {
                    spacing: 5
                    Disclosure {
                        anchors.verticalCenter: parent.verticalCenter
                        expanded: group.opened
                        onToggled: {
                            group.opened = !group.opened;
                            inspector.setGroupOpen(group.modelData.name,
                                              group.opened);
                        }
                    }
                    Text {
                        text: group.modelData.name
                        font.pixelSize: theme.fontSmall
                        font.bold: true
                        color: theme.text
                        TapHandler {
                            onTapped: {
                                group.opened = !group.opened;
                                inspector.setGroupOpen(group.modelData.name,
                                                  group.opened);
                            }
                        }
                    }
                    Text {
                        visible: !group.opened
                        text: group.modelData.count
                              || group.modelData.items.length
                        font.pixelSize: theme.fontSmall
                        color: theme.textDim
                    }
                }

                // Half-width items pair up; a wide one takes the row.
                Flow {
                    visible: group.opened
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened ? group.modelData.items : []
                        InspectorField {
                            required property var modelData
                            spec: modelData
                            width: modelData.wide
                                   ? groupBody.width
                                   : (groupBody.width - root.gap) / 2
                        }
                    }
                }

                // A template's columns: one per side of an extrusion, the
                // second beside the first when there is a second.
                Row {
                    visible: group.opened && !!group.modelData.columns
                             && group.modelData.columns.length > 0
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened && group.modelData.columns
                               ? group.modelData.columns : []

                        Column {
                            id: column
                            required property var modelData
                            width: (groupBody.width - root.gap) / 2
                            spacing: root.gap

                            Text {
                                visible: column.modelData.title.length > 0
                                text: column.modelData.title
                                font.pixelSize: theme.fontAside
                                font.bold: true
                                color: theme.textDim
                            }
                            Repeater {
                                model: column.modelData.items
                                InspectorField {
                                    required property var modelData
                                    spec: modelData
                                    width: column.width
                                }
                            }
                        }
                    }
                }

                Flow {
                    visible: group.opened && !!group.modelData.after
                             && group.modelData.after.length > 0
                    width: parent.width
                    spacing: root.gap

                    Repeater {
                        model: group.opened && group.modelData.after
                               ? group.modelData.after : []
                        InspectorField {
                            required property var modelData
                            spec: modelData
                            width: modelData.wide
                                   ? groupBody.width
                                   : (groupBody.width - root.gap) / 2
                        }
                    }
                }

                Text {
                    // A template's note on the card.
                    visible: group.opened && !!group.modelData.hint
                    width: parent.width
                    text: group.modelData.hint || ""
                    wrapMode: Text.Wrap
                    font.pixelSize: theme.fontAside
                    color: theme.textDim
                }
            }
        }
        }
    }

    Text {
        anchors.centerIn: groups
        visible: groups.count === 0
        text: inspector.title.length === 0 ? qsTr("Select an object")
                                      : qsTr("No matching properties")
        font.pixelSize: theme.fontSmall
        font.italic: true
        color: theme.textDim
    }
}
