import QtQuick

// Drag image and bookkeeping for tree drags: drop target, sliding,
// edge scrolling, cancel.
Item {
    id: ghost

    property ListView list
    z: 1000
    width: sliding ? shot.width : label.implicitWidth + 34
    height: theme.rowHeight
    visible: Drag.active

    property var names: []
    //: Drop hint text; empty when no target.
    property string hint: ""
    property bool hintOk: true

    function say(text, ok) {
        hint = text;
        hintOk = ok;
    }
    // Sliding: reorder within a container, ghost locked to its column.
    property bool sliding: false
    property string slideTarget: ""
    property var verdicts: ({})
    property string slideInto: ""
    property var intoVerdicts: ({})
    // Set by the row that starts the drag.
    property string container: ""
    // May leave its container: false for a Body's features.
    property bool canLeave: true
    property int sourceDepth: 0

    // A free drag draws the pill this far right of and below the cursor;
    // the hot spot stays on the cursor, so a drop lands where it points.
    readonly property point cursorGap: Qt.point(10, 6)
    // Sliding over the header: the document's top level.
    property bool slideRoot: false
    property var rootVerdict: undefined

    Drag.active: false
    Drag.hotSpot.x: -cursorGap.x
    Drag.hotSpot.y: -cursorGap.y

    function begin(objectNames, text, icon, grabbedAt) {
        names = objectNames;
        label.text = text;
        ghostIcon.source = icon;
        sliding = grabbedAt !== null && grabbedAt !== undefined;
        shot.sourceItem = null;
        slideTarget = "";
        slideInto = "";
        verdicts = ({});
        intoVerdicts = ({});
        Drag.hotSpot.x = sliding ? grabbedAt.x : -cursorGap.x;
        Drag.hotSpot.y = sliding ? grabbedAt.y : -cursorGap.y;
        slideRoot = false;
        rootVerdict = undefined;
        ghost.list.dragSources = objectNames;
        ghost.list.reorderDrag = sliding;
        hint = "";
        cancelled = false;
        host.takeKeyboard();
        ghost.list.forceActiveFocus();
        // Keep delegates alive: the dragged row holds the pointer and must not be recycled.
        ghost.list.cacheBuffer = 100000;
        Drag.active = true;
    }

    // Scene-graph copy, not grabToImage: that is async and may never answer
    // in a panel that is not repainting.
    function picture(item, left, w, h) {
        if (!Drag.active)
            return;
        shot.width = w;
        shot.height = h;
        shot.sourceRect = Qt.rect(left, 0, w, h);
        shot.sourceItem = item;
        shot.scheduleUpdate();
    }

    //: Escape cancelled; the following release is not a click.
    property bool cancelled: false

    function cancel() {
        if (!Drag.active)
            return;
        Drag.cancel();
        Drag.active = false;
        cancelled = true;
        intoSpring.stop();
        names = [];
        sliding = false;
        slideRoot = false;
        slideTarget = "";
        slideInto = "";
        hint = "";
        shot.sourceItem = null;
        ghost.list.dropGap = -1;
        ghost.list.intoRow = -1;
        ghost.list.dragSources = [];
        ghost.list.reorderDrag = false;
        ghost.list.cacheBuffer = 400;
    }

    function finish() {
        if (sliding) {
            Drag.active = false;
            if (slideRoot)
                nxt.dropOnRoot(names);
            else if (slideInto !== "")
                nxt.dropInto(names, slideInto);
            else if (slideTarget !== "")
                nxt.reorderOn(names, slideTarget);
            ghost.list.dropGap = -1;
            ghost.list.intoRow = -1;
            slideInto = "";
            slideRoot = false;
            intoSpring.stop();
        } else {
            Drag.drop();
            Drag.active = false;
        }
        names = [];
        sliding = false;
        hint = "";
        shot.sourceItem = null;
        ghost.list.dragSources = [];
        ghost.list.reorderDrag = false;
        ghost.list.cacheBuffer = 400;
    }

    onYChanged: {
        if (!Drag.active)
            return;
        if (sliding)
            slide();
        if (theme.overlay)
            host.repaintBehind();
    }

    function allowed(target) {
        if (verdicts[target] === undefined)
            verdicts[target] = nxt.canReorderOn(names, target);
        return verdicts[target];
    }

    function leavesToRoot() {
        if (rootVerdict === undefined)
            rootVerdict = nxt.canDropOnRoot(names);
        return rootVerdict;
    }

    function takesIt(target) {
        if (intoVerdicts[target] === undefined)
            intoVerdicts[target] = nxt.canDropInto(names, target);
        return intoVerdicts[target];
    }

    // Left the container: becomes a free drag.
    function unslide() {
        sliding = false;
        shot.sourceItem = null;
        slideTarget = "";
        slideInto = "";
        intoSpring.stop();
        ghost.list.reorderDrag = false;
        ghost.list.dropGap = -1;
        ghost.list.intoRow = -1;
        slideRoot = false;
        // Keep the cursor where it is; the pill moves to sit beside it.
        x += Drag.hotSpot.x + cursorGap.x;
        y += Drag.hotSpot.y + cursorGap.y;
        Drag.hotSpot.x = -cursorGap.x;
        Drag.hotSpot.y = -cursorGap.y;
        say("", true);
    }

    function slideAcross() {
        if (!canLeave)
            return false;
        var at = ghost.mapToItem(ghost.list.contentItem,
                                 Drag.hotSpot.x, Drag.hotSpot.y);
        slideRoot = ghost.mapToItem(ghost.list, Drag.hotSpot.x,
                                    Drag.hotSpot.y).y < 0 && leavesToRoot();
        if (slideRoot) {
            slideTarget = "";
            slideInto = "";
            intoSpring.stop();
            ghost.list.dropGap = -1;
            ghost.list.intoRow = -1;
            say(qsTr("To the top of the document"), true);
            return true;
        }
        var under = ghost.list.itemAt(10, at.y);
        if (!under || names.indexOf(under.name) >= 0)
            return false;
        if (under.depth < sourceDepth && under.name !== container) {
            unslide();
            return true;
        }
        var within = (at.y - under.y) / Math.max(1, under.height);
        if (within > 0.25 && within < 0.75 && takesIt(under.name)) {
            if (slideInto !== under.name) {
                slideInto = under.name;
                if (!under.expanded && under.hasChildren)
                    intoSpring.restart();
                else
                    intoSpring.stop();
            }
            ghost.list.intoRow = under.index;
            ghost.list.dropGap = -1;
            slideTarget = "";
            say(qsTr("Into %1").arg(under.label), true);
            return true;
        }
        return false;
    }

    // Spring-open a collapsed container hovered over.
    Timer {
        id: intoSpring
        interval: 700
        onTriggered: {
            var item = ghost.list.intoRow >= 0
                       ? ghost.list.itemAtIndex(ghost.list.intoRow) : null;
            if (item && item.name === ghost.slideInto && !item.expanded)
                nxt.toggleExpanded(item.name);
        }
    }

    // Measured as if no gap were open; otherwise the gap's own movement
    // makes the answer flicker.
    function slide() {
        if (slideAcross())
            return;
        if (slideInto !== "") {
            slideInto = "";
            intoSpring.stop();
        }
        ghost.list.intoRow = -1;
        var want = ghost.mapToItem(ghost.list.contentItem, 0, 0).y;
        var first = ghost.list.indexAt(10, ghost.list.contentY);
        var last = ghost.list.indexAt(10, ghost.list.contentY
                                        + ghost.list.height);
        if (first < 0) first = 0;
        if (last < 0) last = ghost.list.count - 1;
        var gapRow = ghost.list.dropGap;
        var open = gapRow >= 0 ? ghost.list.itemAtIndex(gapRow) : null;
        var shift = open ? open.gap : 0;
        var best = -1, bestDistance = 1e9;
        for (var i = first; i <= last; ++i) {
            var item = ghost.list.itemAtIndex(i);
            if (!item)
                continue;
            var top = item.y - (gapRow >= 0 && i > gapRow ? shift : 0);
            var bottom = top + item.height - (i === gapRow ? shift : 0);
            var distance = Math.abs(bottom - want);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = i;
            }
        }
        var item = best >= 0 ? ghost.list.itemAtIndex(best) : null;
        var target = item ? item.name : "";
        var ok = target !== "" && allowed(target);
        slideTarget = ok ? target : "";
        ghost.list.dropGap = ok ? best : -1;
        say(!ok ? qsTr("Can't move here")
            : item.name === container ? qsTr("To the start of %1")
                                         .arg(item.label)
            : qsTr("After %1").arg(item.label), ok);
    }

    // A drag whose release never came back (the press was taken away,
    // or its row went with a model reset) ends once no button is down,
    // rather than leaving the ghost behind.
    Timer {
        interval: 250
        repeat: true
        running: ghost.Drag.active
        onTriggered: {
            if (nxt.mouseHeld())
                return;
            ghost.cancel();
            ghost.cancelled = false;    // no release left to swallow
        }
    }

    Timer {
        id: edgeScroll
        interval: 16
        repeat: true
        running: ghost.Drag.active
        onTriggered: {
            var at = ghost.mapToItem(ghost.list, ghost.Drag.hotSpot.x,
                                     ghost.Drag.hotSpot.y);
            var edge = theme.rowHeight * 1.5;
            var step = 0;
            if (at.y < edge)
                step = -Math.min(1, (edge - at.y) / edge);
            else if (at.y > ghost.list.height - edge)
                step = Math.min(1, (at.y - ghost.list.height + edge)
                                   / edge);
            if (step === 0)
                return;
            var top = ghost.list.originY;
            var bottom = ghost.list.originY + ghost.list.contentHeight
                         - ghost.list.height;
            var next = Math.max(top, Math.min(bottom,
                                ghost.list.contentY + step * 14));
            if (next === ghost.list.contentY)
                return;
            ghost.list.contentY = next;
            if (ghost.sliding)
                ghost.slide();
        }
    }

    Rectangle {
        id: hintPill
        z: 2
        visible: ghost.hint.length > 0
        x: ghost.sliding ? shot.width + 8 : 0
        y: ghost.sliding ? (ghost.height - height) / 2
                         : ghost.height + 3
        width: hintText.implicitWidth + 12
        height: theme.chipHeight
        radius: height / 2
        color: theme.surface
        border.width: 1
        border.color: ghost.hintOk ? theme.accent : theme.border

        Text {
            id: hintText
            anchors.centerIn: parent
            text: ghost.hint
            font.pixelSize: theme.fontSmall
            color: ghost.hintOk ? theme.text : theme.textDim
        }
    }

    ShaderEffectSource {
        id: shot
        // Not live: keeps the row as it was before being dimmed.
        live: false
        hideSource: false
        visible: ghost.sliding && sourceItem !== null

        opacity: 0.95
        Rectangle {
            anchors.fill: parent
            z: -1
            radius: 4
            color: theme.surface
            border.width: 1
            border.color: ghost.slideTarget !== "" ? theme.accent
                                                   : theme.border
        }

        Rectangle {
            visible: ghost.names.length > 1
            anchors.right: parent.right
            anchors.rightMargin: -6
            anchors.verticalCenter: parent.top
            width: Math.max(height, count.implicitWidth + 8)
            height: theme.chipHeight
            radius: height / 2
            color: theme.accent

            Text {
                id: count
                anchors.centerIn: parent
                text: ghost.names.length
                font.pixelSize: theme.fontSmall
                font.bold: true
                color: theme.accentText
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: !shot.visible
        radius: 4
        color: theme.accent
        opacity: 0.92

        Image {
            id: ghostIcon
            x: 6
            anchors.verticalCenter: parent.verticalCenter
            width: theme.markSize
            height: width
            sourceSize.width: width * 2
            sourceSize.height: width * 2
        }

        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            x: ghostIcon.x + ghostIcon.width + 6
            font.pixelSize: theme.fontRow
            color: theme.accentText
        }
    }
}
