import QtQuick
import Nxt.Controls

// The Nxt fillet's and chamfer's task panel. `task` is tools/fillet_task.py's bridge;
// FreeCAD draws OK and Cancel above it.
Item {
    id: root

    readonly property int gap: 10
    readonly property color amber: theme.warning
    readonly property color amberWash: Qt.rgba(amber.r, amber.g, amber.b, 0.14)

    implicitWidth: 320
    implicitHeight: column.implicitHeight + 2 * gap

    Rectangle { anchors.fill: parent; color: theme.background }

    Column {
        id: column
        x: root.gap
        y: root.gap
        width: root.width - 2 * root.gap
        spacing: root.gap

        // -- radius --
        Card {
            Row {
                width: parent.width
                Text {
                    width: parent.width / 2
                    text: task.flat ? qsTr("Distance") : qsTr("Radius")
                    color: theme.textDim
                    font.pixelSize: theme.fontSmall
                }
                Text {
                    width: parent.width / 2
                    horizontalAlignment: Text.AlignRight
                    text: task.fits >= 0 ? qsTr("fits up to %1").arg(task.fitsText) : ""
                    color: root.amber
                    font.pixelSize: theme.fontSmall
                }
            }
            Row {
                width: parent.width
                spacing: root.gap

                TextField {
                    id: radiusField
                    width: 104
                    height: theme.fieldHeight
                    text: task.radiusText
                    onAccepted: if (!task.setRadiusText(text)) text = task.radiusText
                    input.onActiveFocusChanged: if (!input.activeFocus) task.setRadiusText(text)
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: "transparent"
                        border.width: 1
                        border.color: root.amber
                        visible: task.failing > 0
                    }
                }

                // Slider with a marker where the radius stops fitting.
                Item {
                    id: slider
                    width: parent.width - radiusField.width - root.gap
                    height: theme.fieldHeight
                    readonly property real span: task.sliderMax
                    function at(value) { return Math.max(0, Math.min(1, value / span)) * width }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width; height: 4; radius: 2
                        color: theme.border
                    }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: slider.at(task.radius); height: 4; radius: 2
                        color: theme.accent
                    }
                    Rectangle {
                        visible: task.fits >= 0
                        x: slider.at(task.fits) - 1
                        anchors.verticalCenter: parent.verticalCenter
                        width: 2; height: 14
                        color: root.amber
                    }
                    Rectangle {
                        x: slider.at(task.radius) - width / 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 14; height: 14; radius: 7
                        color: theme.text
                    }
                    MouseArea {
                        anchors.fill: parent
                        function pick(mouse) {
                            task.setRadius(Math.max(0.01, mouse.x / width * slider.span))
                        }
                        onPressed: function (mouse) { pick(mouse) }
                        onPositionChanged: function (mouse) { if (pressed) pick(mouse) }
                    }
                }
            }
        }

        // -- edges --
        Card {
            Row {
                width: parent.width
                spacing: 8
                Text {
                    width: parent.width - sourceLabel.width - clearButton.width - 16
                    text: task.useAllEdges ? qsTr("All edges · %1").arg(task.edges.length)
                                           : qsTr("Edges · %1").arg(task.edges.length)
                    color: theme.text
                    font.pixelSize: theme.fontRow
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    id: sourceLabel
                    text: task.source
                    color: theme.textDim
                    font.pixelSize: theme.fontSmall
                    anchors.verticalCenter: parent.verticalCenter
                }
                PanelButton {
                    id: clearButton
                    text: qsTr("Clear")
                    enabled: task.edges.length > 0 && !task.useAllEdges
                    onClicked: task.clear()
                }
            }

            Flow {
                width: parent.width
                spacing: 6
                visible: !task.useAllEdges
                Repeater {
                    model: task.edges
                    delegate: Rectangle {
                        required property var modelData
                        height: theme.chipHeight + 4
                        width: chipLabel.implicitWidth + remove.width + 16
                        radius: height / 2
                        color: modelData.short ? root.amberWash : theme.chip
                        border.width: 1
                        border.color: modelData.short ? root.amber : theme.border

                        HoverHandler {
                            onHoveredChanged: task.hover(hovered ? modelData.name : "")
                        }
                        Text {
                            id: chipLabel
                            x: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.short ? modelData.name + " · " + modelData.limit
                                                  : modelData.name
                            color: modelData.short ? root.amber : theme.text
                            font.pixelSize: theme.fontSmall
                        }
                        Text {
                            id: remove
                            anchors.right: parent.right
                            anchors.rightMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: 14
                            text: "×"
                            color: theme.textDim
                            font.pixelSize: theme.fontRow
                            horizontalAlignment: Text.AlignHCenter
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -4
                                cursorShape: Qt.PointingHandCursor
                                onClicked: task.remove(modelData.name)
                            }
                        }
                    }
                }
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: task.useAllEdges
                      ? qsTr("Every edge of %1 is rounded.").arg(task.source)
                      : task.edges.length === 0
                        ? qsTr("Pick edges in the 3D view; a face adds all its edges.")
                        : qsTr("Pick again to remove. Hover a chip to find its edge.")
                color: theme.textDim
                font.pixelSize: theme.fontSmall
            }
        }

        // -- edges that do not fit --
        Rectangle {
            width: parent.width
            visible: task.failing > 0
            height: visible ? notice.implicitHeight + 24 : 0
            radius: 6
            color: root.amberWash
            border.width: 1
            border.color: root.amber

            Column {
                id: notice
                x: 12; y: 12
                width: parent.width - 24
                spacing: 8
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: (task.flat ? qsTr("%1 of %2 edges won't chamfer at %3.")
                                     : qsTr("%1 of %2 edges won't fillet at %3."))
                          .arg(task.failing).arg(task.edges.length).arg(task.radiusText)
                    color: root.amber
                    font.pixelSize: theme.fontSmall
                }
                PanelButton {
                    visible: task.fits > 0
                    text: qsTr("Use %1 for all").arg(task.fitsText)
                    ink: root.amber
                    onClicked: task.useFits()
                }
            }
        }

        // -- options --
        Card {
            Item {
                width: parent.width
                height: optionsTitle.implicitHeight
                Disclosure {
                    id: dart
                    anchors.verticalCenter: parent.verticalCenter
                    expanded: options.visible
                }
                Text {
                    id: optionsTitle
                    x: dart.width + 6
                    text: qsTr("Options")
                    color: theme.text
                    font.pixelSize: theme.fontRow
                    font.bold: true
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: options.visible = !options.visible
                }
            }
            Column {
                id: options
                width: parent.width
                spacing: 6
                visible: false
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Use all edges")
                    checked: task.useAllEdges
                    onToggled: task.setUseAllEdges(checked)
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Include tangent edges")
                    checked: task.tangentEdges
                    onToggled: task.setTangentEdges(checked)
                }
                NxtSwitch {
                    width: parent.width
                    visible: task.flat
                    text: qsTr("Triangular corners")
                    checked: task.triangleCorners
                    onToggled: task.setTriangleCorners(checked)
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Show what changes")
                    checked: task.preview
                    onToggled: task.setPreview(checked)
                }
                NxtSwitch {
                    width: parent.width
                    text: qsTr("Refine result")
                    checked: task.refine
                    onToggled: task.setRefine(checked)
                }
            }
        }
    }

    // A rounded group of controls.
    component Card: Rectangle {
        default property alias content: inner.children
        width: column.width
        height: inner.implicitHeight + 24
        radius: 6
        color: theme.surface
        border.width: 1
        border.color: theme.border
        Column {
            id: inner
            x: 12; y: 12
            width: parent.width - 24
            spacing: 10
        }
    }

    // A small outlined text button.
    component PanelButton: Rectangle {
        property alias text: label.text
        property color ink: theme.text
        signal clicked()
        height: theme.fieldHeight
        width: label.implicitWidth + 20
        radius: 4
        color: area.containsMouse && enabled ? theme.hover : "transparent"
        border.width: 1
        border.color: ink
        opacity: enabled ? 1.0 : 0.4
        Text {
            id: label
            anchors.centerIn: parent
            color: parent.ink
            font.pixelSize: theme.fontSmall
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            enabled: parent.enabled
            onClicked: parent.clicked()
        }
    }
}
