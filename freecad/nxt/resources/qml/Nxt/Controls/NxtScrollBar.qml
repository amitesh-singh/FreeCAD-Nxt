import QtQuick

// A scrollbar for any Flickable: drag the thumb, click or hold on the track
// to page. Thin at rest, wider under the pointer; dims when idle but stays
// in view while there is more to scroll to. Drawn by hand, so the host's
// QtQuick.Controls style cannot reach it.
Item {
    id: bar

    property Flickable target
    //: Width when the pointer is near; the bar is drawn thinner at rest.
    property real wideWidth: theme.scrollBarWidth || 10

    readonly property bool scrollable: target !== null
                                       && target.contentHeight > target.height
    readonly property bool engaged: area.containsMouse || area.dragging
    readonly property real travel: Math.max(1, height - thumb.height)

    implicitWidth: wideWidth
    width: implicitWidth
    visible: scrollable

    function scrollTo(contentY) {
        var top = target.originY;
        var bottom = top + target.contentHeight - target.height;
        target.contentY = Math.max(top, Math.min(bottom, contentY));
    }

    function page(direction) {
        scrollTo(target.contentY + direction * target.height * 0.9);
    }

    property bool idle: true
    Timer {
        id: idleTimer
        interval: 1500
        onTriggered: bar.idle = true
    }
    Connections {
        target: bar.target
        function onContentYChanged() {
            bar.idle = false;
            idleTimer.restart();
        }
    }

    Rectangle {
        id: track
        anchors.fill: parent
        radius: width / 2
        color: theme.hover
        opacity: bar.engaged ? 0.6 : 0.0
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }

    Rectangle {
        id: thumb
        readonly property real restWidth: Math.max(3, bar.wideWidth * 0.4)
        width: bar.engaged ? bar.wideWidth - 2 : restWidth
        x: (bar.width - width) / 2
        height: bar.target
                ? Math.max(24, bar.target.visibleArea.heightRatio * bar.height)
                : 0
        y: bar.target
           ? Math.max(0, Math.min(bar.travel,
                 bar.target.visibleArea.yPosition * bar.height))
           : 0
        radius: width / 2
        color: area.dragging ? theme.accent : theme.textDim
        opacity: bar.engaged || !bar.idle ? 0.85 : 0.35
        Behavior on width { NumberAnimation { duration: 120 } }
        Behavior on opacity { NumberAnimation { duration: 250 } }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true

        property bool dragging: false
        property real grabbedAt: 0
        property int paging: 0

        onPressed: function (mouse) {
            if (mouse.y >= thumb.y && mouse.y <= thumb.y + thumb.height) {
                dragging = true;
                grabbedAt = mouse.y - thumb.y;
            } else {
                paging = mouse.y < thumb.y ? -1 : 1;
                bar.page(paging);
                pageRepeat.start();
            }
        }
        onPositionChanged: function (mouse) {
            if (!dragging)
                return;
            var fraction = (mouse.y - grabbedAt) / bar.travel;
            bar.scrollTo(bar.target.originY + fraction
                         * (bar.target.contentHeight - bar.target.height));
        }
        onReleased: {
            dragging = false;
            paging = 0;
            pageRepeat.stop();
        }
        onCanceled: {
            dragging = false;
            paging = 0;
            pageRepeat.stop();
        }

        Timer {
            id: pageRepeat
            interval: 350
            repeat: true
            onTriggered: {
                interval = 80;
                var stillBefore = area.paging < 0
                    && area.mouseY < thumb.y;
                var stillAfter = area.paging > 0
                    && area.mouseY > thumb.y + thumb.height;
                if (stillBefore || stillAfter)
                    bar.page(area.paging);
            }
            onRunningChanged: if (!running) interval = 350
        }
    }
}
