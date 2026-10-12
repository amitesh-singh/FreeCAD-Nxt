import QtQuick

// A drop target for the document's top level (bridge.dropOnRoot).
DropArea {
    id: area

    property Item ghost
    property bool accepting: false
    //: Optional (x, y) -> bool: whether a drop there is the top level's.
    property var allowAt: null

    function wanted(x, y) {
        return (allowAt === null || allowAt(x, y))
               && nxt.canDropOnRoot(names());
    }

    function names() {
        return ghost && !ghost.sliding ? ghost.names : [];
    }

    property string hint: qsTr("To the top of the document")

    onAcceptingChanged: {
        if (!ghost || ghost.sliding)
            return;
        // Cleared only if still ours: a row over this area may have spoken since.
        if (accepting)
            ghost.say(area.hint, true);
        else if (ghost.hint === area.hint)
            ghost.say("", true);
    }
    onEntered: function (drag) {
        accepting = wanted(drag.x, drag.y);
    }
    onPositionChanged: function (drag) {
        accepting = wanted(drag.x, drag.y);
    }
    onExited: accepting = false
    onDropped: function (drop) {
        if (accepting && wanted(drop.x, drop.y))
            nxt.dropOnRoot(names());
        accepting = false;
    }
}
