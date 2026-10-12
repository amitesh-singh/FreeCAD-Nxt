import QtQuick

// A small square button with a drawn icon, a hover backdrop and a tooltip.
// The icon is painted by `paint(ctx, width, height, ink)`, so it takes the
// theme's colour in light and dark.
Item {
    id: button

    property var paint: null
    property string tip: ""
    property string name: tip
    //: Drawn as hovered while true, e.g. while what it opens is open.
    property bool highlighted: false
    property real iconScale: 0.62
    property real iconAspect: 1.0
    readonly property bool hovered: mouse.containsMouse

    signal clicked(var mouse)

    width: Math.round(theme.rowHeight * 0.9)
    height: width

    Rectangle {
        anchors.fill: parent
        radius: 4
        color: theme.hover
        visible: button.hovered || button.highlighted
    }

    Canvas {
        anchors.centerIn: parent
        width: Math.round(button.width * button.iconScale)
        height: Math.round(width * button.iconAspect)
        antialiasing: true
        property color ink: button.hovered ? theme.text : theme.textDim
        onInkChanged: requestPaint()
        onWidthChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            if (button.paint)
                button.paint(ctx, width, height, ink);
        }
    }

    // A MouseArea, for the click's modifiers: a TapHandler's event point
    // does not carry them.
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: function (event) { button.clicked(event); }
    }

    NxtToolTip {
        shown: button.hovered && button.tip !== ""
        text: button.tip
    }

    Accessible.role: Accessible.Button
    Accessible.name: button.name.split("\n")[0]
}
