import QtQuick

// A Body's rollback bar, draggable through the timeline. See DESIGN.md rule 10.
Item {
    id: bar

    property string body: ""
    property int pos: 0
    property int minPos: 0
    property int maxPos: 0
    property real rowHeight: 20
    property real listTopMargin: 0
    property int realised: 0
    // Rows vary in height; row-height arithmetic is only a fallback.
    property var list: null
    property real fullWidth: 200

    property color ink: theme.branchInk

    property bool dragging: false
    property int dragPos: pos
    readonly property int effectivePos: dragging ? dragPos : pos

    // Drawn position follows the pointer; only the slot quantises.
    property real dragY: 0
    property real grabOffset: 0

    height: Math.max(9, Math.round(rowHeight * 0.45), knob + 3)

    // itemAtIndex() is not reactive; reading contentHeight and realised
    // makes bindings re-run when rows move.
    function rowAt(index) {
        var watch = bar.realised
                  + (bar.list ? bar.list.contentHeight : 0);
        return bar.list ? bar.list.itemAtIndex(index) : null;
    }

    function boundaryY(index) {
        var item = bar.rowAt(index);
        var edge = item ? item.y + item.height
                        : (index + 1) * bar.rowHeight;
        // Middle of a gap this bar opened.
        var opened = (item && item.gap) ? item.gap : 0;
        return bar.listTopMargin + edge - opened / 2
             - bar.height / 2;
    }

    readonly property real topY: boundaryY(minPos)
    readonly property real bottomY: boundaryY(maxPos)

    function clampY(value) {
        return Math.max(bar.topY, Math.min(bar.bottomY, value));
    }

    // Rest position in content coordinates so scrolling isn't animated;
    // only resting-place changes are eased via settleOffset.
    readonly property real restContentY: bar.boundaryY(bar.effectivePos)
    property real settleOffset: 0
    property real lastRest: NaN

    y: bar.dragging ? bar.dragY
                    : bar.restContentY + bar.settleOffset

    function settleFrom(offset) {
        bar.settleOffset = offset;
        settle.restart();
    }

    onRestContentYChanged: {
        if (!bar.dragging && !isNaN(bar.lastRest))
            bar.settleFrom(bar.settleOffset + bar.lastRest - bar.restContentY);
        bar.lastRest = bar.restContentY;
    }
    Component.onCompleted: bar.lastRest = bar.restContentY
    onDraggingChanged: if (!bar.dragging)
        bar.settleFrom(bar.dragY - bar.restContentY)

    NumberAnimation {
        id: settle
        target: bar
        property: "settleOffset"
        to: 0
        duration: 110
        easing.type: Easing.OutCubic
    }

    // In overlay mode, stop just past the wider neighbouring pill.
    readonly property real neighbourEdge: {
        if (!theme.overlay)
            return 0;       // docked, the bar spans the list and never asks
        var above = bar.rowAt(bar.effectivePos);
        var below = bar.rowAt(bar.effectivePos + 1);
        var edge = 0;
        if (above && above.pillRight !== undefined)
            edge = Math.max(edge, above.pillRight);
        if (below && below.pillRight !== undefined)
            edge = Math.max(edge, below.pillRight);
        return edge;
    }

    width: neighbourEdge > 0 ? Math.max(60, neighbourEdge + 12 - x)
                             : Math.max(40, fullWidth - x - 6)

    // Translucent QQuickWidget: repaint behind on move.
    onYChanged: if (theme.overlay) host.repaintBehind()
    onWidthChanged: if (theme.overlay) host.repaintBehind()

    // -- line and knobs --

    readonly property real knob: Math.max(6, Math.round(rowHeight * 0.34))

    Rectangle {
        id: line
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: bar.knob / 2
        anchors.rightMargin: bar.knob / 2
        height: bar.dragging ? 3 : 2
        radius: height / 2
        color: bar.ink
        opacity: bar.dragging ? 1.0 : (hover.hovered ? 0.95 : 0.8)

        Behavior on opacity { NumberAnimation { duration: 90 } }
    }

    Repeater {
        model: 2

        Rectangle {
            required property int index

            anchors.verticalCenter: parent.verticalCenter
            anchors.left: index === 0 ? parent.left : undefined
            anchors.right: index === 0 ? undefined : parent.right
            width: bar.knob + (bar.dragging || hover.hovered ? 2 : 0)
            height: width
            radius: width / 2
            color: bar.ink
            opacity: bar.dragging ? 1.0 : (hover.hovered ? 0.95 : 0.8)

            Behavior on width { NumberAnimation { duration: 90 } }
            Behavior on opacity { NumberAnimation { duration: 90 } }
        }
    }

    function slotAt(localY) {
        var cy = localY - listTopMargin;
        var slot;
        if (list) {
            var idx = list.indexAt(4, cy);
            if (idx < 0) {
                slot = cy < 0 ? minPos - 1 : maxPos;
            } else {
                var item = list.itemAtIndex(idx);
                slot = (item && cy > item.y + item.height / 2) ? idx : idx - 1;
            }
        } else {
            slot = Math.round(cy / rowHeight) - 1;
        }
        return Math.max(minPos, Math.min(maxPos, slot));
    }

    HoverHandler {
        id: hover
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: bar.dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        preventStealing: true

        onPressed: function (mouse) {
            // dragY before dragging, or one frame draws at y = 0.
            bar.grabOffset = mouse.y;
            bar.dragY = bar.y;
            bar.dragPos = bar.pos;
            bar.dragging = true;
            nxt.beginTipDrag(bar.body);
        }

        onPositionChanged: function (mouse) {
            if (!bar.dragging)
                return;
            // Parent coordinates: this item moves during the drag.
            var y = mapToItem(bar.parent, mouse.x, mouse.y).y;
            bar.dragY = bar.clampY(y - bar.grabOffset);
            var slot = bar.slotAt(y);
            if (slot === bar.dragPos)
                return;
            bar.dragPos = slot;
            // Once per row crossed.
            nxt.previewTipRow(bar.body, slot);
        }

        onReleased: {
            bar.dragging = false;
            nxt.endTipDrag(bar.body);
        }

        onCanceled: {
            bar.dragging = false;
            bar.dragPos = bar.pos;
            nxt.cancelTipDrag(bar.body);
        }
    }
}
