import QtQuick

// "Bracket › Body › Pocket001": containers of the top visible row, pinned
// over the list once their rows have scrolled away.
Item {
    id: bar

    //: [{row, label}], outermost first.
    property var crumbs: []
    signal crumbClicked(int row)

    readonly property int pad: theme.rowPad + 4
    readonly property int gap: 6
    readonly property bool overflows: path.width > width - 2 * pad
    //: Scroll back from the end; reset on every new trail.
    property real scroll: 0
    readonly property real maxScroll:
        Math.max(0, path.width - (width - 2 * pad))
    //: Hovered; the overlay's wheel handler asks this (NxtTree.qml).
    readonly property bool hovered: hover.hovered

    function scrollBy(distance) {
        scroll = Math.max(0, Math.min(maxScroll, scroll + distance));
    }

    onCrumbsChanged: scroll = 0
    onMaxScrollChanged: scrollBy(0)

    height: theme.rowHeight + 4
    visible: crumbs.length > 0
    clip: true

    Rectangle {
        anchors.fill: parent
        anchors.margins: theme.overlay ? 2 : 0
        radius: theme.overlay ? 4 : 0
        color: theme.overlay ? theme.pill : theme.background
        border.width: theme.overlay ? 1 : 0
        border.color: theme.pillBorder
    }
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        visible: !theme.overlay
        color: theme.border
    }

    HoverHandler { id: hover }

    WheelHandler {
        enabled: bar.overflows
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function (event) {
            var d = event.pixelDelta.x || event.pixelDelta.y;
            if (!d)
                d = (event.angleDelta.x || event.angleDelta.y) / 120 * 40;
            bar.scrollBy(d);
        }
    }
    DragHandler {
        id: drag
        enabled: bar.overflows
        target: null
        yAxis.enabled: false
        property real from: 0
        onActiveChanged: if (active) from = bar.scroll
        onTranslationChanged: if (active) {
            bar.scroll = Math.max(0, Math.min(bar.maxScroll,
                                               from + translation.x));
        }
    }

    Row {
        id: path
        anchors.verticalCenter: parent.verticalCenter
        x: bar.overflows ? bar.width - bar.pad - width + bar.scroll
                         : bar.pad
        spacing: bar.gap

        Repeater {
            model: bar.crumbs

            Row {
                required property int index
                required property var modelData
                readonly property bool innermost:
                    index === bar.crumbs.length - 1

                spacing: bar.gap

                Text {
                    visible: index > 0
                    text: "›"
                    font.pixelSize: theme.fontRow
                    color: theme.textDim
                }
                Text {
                    objectName: "crumb"
                    text: modelData.label
                    font.pixelSize: theme.fontRow
                    font.bold: innermost
                    font.underline: crumbMouse.containsMouse
                    opacity: crumbMouse.pressed ? 0.6 : 1.0
                    color: innermost ? theme.text : theme.textDim

                    MouseArea {
                        id: crumbMouse
                        anchors.fill: parent
                        anchors.margins: -3
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bar.crumbClicked(modelData.row)
                    }
                    Accessible.role: Accessible.Link
                    Accessible.name: modelData.label
                }
            }
        }
    }

    component Fade: Rectangle {
        property bool leading: true
        width: Math.min(40, bar.width / 4)
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: theme.overlay ? 3 : 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: leading ? bar.ground
                                                         : "transparent" }
            GradientStop { position: 1.0; color: leading ? "transparent"
                                                         : bar.ground }
        }
    }
    readonly property color ground: theme.overlay ? theme.pill
                                                  : theme.background
    Fade {
        visible: bar.overflows && bar.scroll < bar.maxScroll
        anchors.left: parent.left
    }
    Fade {
        leading: false
        visible: bar.overflows && bar.scroll > 0
        anchors.right: parent.right
    }
}
