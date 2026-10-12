import QtQuick

// The picture of what is being dragged in the tree, and the drag's
// bookkeeping: where a drop would go, sliding within a container,
// edge scrolling and cancelling.
Item {
    id: ghost

    //: The tree's list, which the ghost scrolls and measures against.
    property ListView list
    z: 1000
    width: sliding ? shot.width : label.implicitWidth + 34
    height: theme.rowHeight
    visible: Drag.active

    property var names: []
    //: Where a drop would put what is in hand, in words ("Into Body",
    //: "After Pad"); empty when nothing is under the pointer.
    property string hint: ""
    //: False when the hint says a drop is refused, and is drawn so.
    property bool hintOk: true

    function say(text, ok) {
        hint = text;
        hintOk = ok;
    }
    // Sliding: a reorder within a Body. The ghost is then a picture of
    // the row itself, locked to its column and held at the point it was
    // grabbed, so the row moves rather than a label beside the pointer.
    property bool sliding: false
    // While sliding: the row it would be dropped after, if the drop
    // is allowed there, and what the panel said about each row asked.
    property string slideTarget: ""
    property var verdicts: ({})
    // While sliding: the row it would drop into instead - the middle
    // of a sibling that takes it - and what was said of each asked.
    property string slideInto: ""
    property var intoVerdicts: ({})
    // Set by the row that starts the drag: the container it slides in,
    // whether that is a Body (whose members only reorder), and how
    // deep its rows sit - a row shallower than that, other than the
    // container, is outside it.
    property string container: ""
    property bool inBody: false
    property int sourceDepth: 0

    Drag.active: false
    Drag.hotSpot.x: 12
    Drag.hotSpot.y: height / 2

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
        // The drop target is the row under the pointer, so the hot spot
        // is the point that was grabbed.
        Drag.hotSpot.x = sliding ? grabbedAt.x : 12;
        Drag.hotSpot.y = sliding ? grabbedAt.y : height / 2;
        ghost.list.dragSources = objectNames;
        ghost.list.reorderDrag = sliding;
        hint = "";
        cancelled = false;
        // The keyboard, so Escape reaches the panel to cancel.
        host.takeKeyboard();
        ghost.list.forceActiveFocus();
        // Rows scrolled out of view are kept while a drag lasts: the
        // row being dragged holds the pointer, and must not be
        // recycled when the list scrolls under it (edgeScroll).
        ghost.list.cacheBuffer = 100000;
        Drag.active = true;
    }

    // The row's picture: the part of `item` from `left`, `w` wide.
    // Drawn by the scene graph in the next frame, not grabbed to an
    // image: grabToImage answers asynchronously, and in a panel that
    // was not repainting it could fail to answer at all - the label
    // stood in until something (switching windows) made the panel
    // redraw. Cropped, so in an overlay the picture is the pill, not
    // a bar the width of the 3D view.
    function picture(item, left, w, h) {
        if (!Drag.active)
            return;
        shot.width = w;
        shot.height = h;
        shot.sourceRect = Qt.rect(left, 0, w, h);
        shot.sourceItem = item;
        shot.scheduleUpdate();
    }

    //: Set when Escape called the drag off: the release that follows
    //: is not a click.
    property bool cancelled: false

    // Escape: everything put back as it was, nothing dropped.
    function cancel() {
        if (!Drag.active)
            return;
        Drag.cancel();
        Drag.active = false;
        cancelled = true;
        intoSpring.stop();
        names = [];
        sliding = false;
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
            if (slideInto !== "")
                nxt.dropInto(names, slideInto);
            else if (slideTarget !== "")
                nxt.reorderOn(names, slideTarget);
            ghost.list.dropGap = -1;
            ghost.list.intoRow = -1;
            slideInto = "";
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

    // A drag moves pixels over the translucent surface in overlay mode;
    // see ghost.list's onContentYChanged.
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

    function takesIt(target) {
        if (intoVerdicts[target] === undefined)
            intoVerdicts[target] = nxt.canDropInto(names, target);
        return intoVerdicts[target];
    }

    // Out of a Part or group: the drag stops sliding and becomes a
    // free one, the label following the pointer and any row a target.
    function unslide() {
        sliding = false;
        shot.sourceItem = null;
        slideTarget = "";
        slideInto = "";
        intoSpring.stop();
        ghost.list.reorderDrag = false;
        ghost.list.dropGap = -1;
        ghost.list.intoRow = -1;
        Drag.hotSpot.x = 12;
        Drag.hotSpot.y = height / 2;
        say("", true);
    }

    // Over the middle of a sibling that would take it: into that row.
    // Over a row outside the container: no longer a slide. Returns
    // true when either decided the matter.
    function slideAcross() {
        if (inBody)
            return false;
        var at = ghost.mapToItem(ghost.list.contentItem,
                                 Drag.hotSpot.x, Drag.hotSpot.y);
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

    // Held over the middle of a closed container for a moment, it
    // opens, to drop deeper.
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

    // Opens the gap where the dragged row is, so it sits over the
    // space it will drop into. Worked out on the list as it would be
    // with no gap open: the gap moves rows, and measuring rows that
    // are moving because of the answer would make the answer flicker.
    // The slot chosen is the row boundary nearest the dragged row's
    // top edge; the gap opens there, a row high, under the ghost.
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
        // Onto the Body itself is to its start; onto a member, after it.
        say(!ok ? qsTr("Can't move here")
            : item.name === container ? qsTr("To the start of %1")
                                         .arg(item.label)
            : qsTr("After %1").arg(item.label), ok);
    }

    // While a drag is near the top or bottom of the list, the list
    // scrolls, faster the further in; a reorder keeps finding its
    // slot as the rows pass under it.
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

    // Where it will land, beside the pointer.
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
        // Once taken, not redrawn: the row it shows is dimmed while it
        // is being dragged, and the copy keeps it as it was. (A copy
        // leaves out its source's own opacity, so the dimming would
        // not show in it anyway.)
        live: false
        hideSource: false
        visible: ghost.sliding && sourceItem !== null

        // Lifted: a shadow line under it and a little transparency, so
        // it reads as held above the list rather than part of it.
        opacity: 0.95
        Rectangle {
            anchors.fill: parent
            z: -1
            radius: 4
            color: theme.surface
            border.width: 1
            // Accent where it can drop; plain where it cannot.
            border.color: ghost.slideTarget !== "" ? theme.accent
                                                   : theme.border
        }

        // How many are in hand, when the picture shows only the one
        // that was grabbed.
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
