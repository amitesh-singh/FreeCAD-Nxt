import QtQuick

// Expand/collapse dart, drawn on a Canvas from the theme's branch_closed.svg
// proportions so it stays sharp at any row height.
Item {
    id: root

    property bool expanded: false
    property bool shown: true

    // Below about 8px the notch stops resolving.
    property real span: theme.fontAside

    property color ink: theme.branchInk

    // Repaint from the owner: a same-named child property would shadow it.
    onInkChanged: arrow.requestPaint()
    onSpanChanged: arrow.requestPaint()

    signal toggled()

    implicitWidth: theme.markSize
    implicitHeight: implicitWidth

    Canvas {
        id: arrow
        anchors.fill: parent
        antialiasing: true
        visible: root.shown
        opacity: hover.hovered ? 1.0 : 0.8
        rotation: root.expanded ? 90 : 0

        Behavior on rotation { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }


        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();

            // Proportions of branch_closed.svg (21-unit box).
            var c = width / 2;
            var unit = Math.max(0.4, root.span / 11);
            var along = 4 * unit;
            var across = 5 * unit;
            var notch = 1.93 * unit;

            ctx.beginPath();
            ctx.moveTo(c + along, c);
            ctx.lineTo(c - along, c + across);
            ctx.lineTo(c - notch, c);
            ctx.lineTo(c - along, c - across);
            ctx.closePath();

            ctx.fillStyle = root.ink;
            ctx.strokeStyle = root.ink;
            ctx.lineWidth = unit;
            ctx.lineJoin = "round";
            ctx.lineCap = "round";
            ctx.fill();
            ctx.stroke();
        }
    }

    HoverHandler { id: hover; enabled: root.shown; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: root.shown; onTapped: root.toggled() }
}
