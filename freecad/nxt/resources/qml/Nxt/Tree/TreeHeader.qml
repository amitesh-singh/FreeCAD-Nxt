import QtQuick
import Nxt.Controls

// The tree's header: the document's name, sketch problems, search,
// and the collapse, dock and settings buttons.
Item {
    id: header

    //: The drag in progress, for the document name's drop target.
    property Item ghost
    property bool settingsOpen: false
    readonly property alias gear: gear
    // What the search field is never squeezed below, including its margins.
    // Below about this it stops being able to show a query and stops being
    // worth the space it takes from the document name.
    readonly property int searchFloor: 128

    signal settingsClicked()

    // The header needs a backdrop of its own in overlay mode for the
    // same reason the rows do. Full width rather than content width:
    // it holds the search field, which is a target, not a label.
    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        radius: 4
        visible: theme.overlay
        color: theme.pill
        border.width: 1
        border.color: theme.pillBorder
    }

    // The document's name is the top level of its tree: drop a row on
    // it to move the object out of its container, as onto the stock
    // tree's document row.
    Rectangle {
        anchors.fill: docLabel
        anchors.margins: -3
        radius: 4
        color: theme.hover
        border.width: 1
        border.color: theme.accent
        visible: docDrop.accepting
    }
    RootDropArea {
        id: docDrop
        anchors.fill: docLabel
        anchors.margins: -3
        ghost: header.ghost
    }

    Text {
        id: docLabel
        anchors.verticalCenter: parent.verticalCenter
        x: 9
        // The name gets the room it asks for, and only gives way once
        // the search field is down to something usable. A flat
        // percentage truncated "PartDesignExample" while the field beside
        // it sat half empty - the field is elastic and the name is not,
        // so the name is what should be measured first.
        width: Math.min(implicitWidth,
                        Math.max(52, parent.width - x - header.searchFloor
                                 - (problems.visible ? problems.width + 8
                                                     : 0)))
        text: nxt.hasDocument ? nxt.documentLabel : qsTr("No document")
        elide: Text.ElideMiddle
        font.pixelSize: theme.fontRow
        font.bold: true
        color: nxt.hasDocument ? theme.text : theme.textDim
    }

    // How many sketches need attention, and a way to the first of them.
    // The plain profile count that used to sit beside it was cut: it was
    // large, stable and had nothing for the user to do about it. This
    // one is none of those things.
    Row {
        id: problems
        anchors.left: docLabel.right
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        visible: nxt.problemCount > 0

        SeverityMark {
            anchors.verticalCenter: parent.verticalCenter
            level: 2
            size: theme.markSizeSmall
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: nxt.problemCount
            font.pixelSize: theme.fontSmall
            font.bold: true
            color: theme.textDim
        }

        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: nxt.revealFirstProblem() }
    }

    SearchBox {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: problems.visible ? problems.right : docLabel.right
        anchors.leftMargin: 10
        anchors.right: collapseButton.left
        anchors.rightMargin: 4
        placeholder: qsTr("search")
        results: nxt.searchResults
        onQueryChanged: function (value) { nxt.setSearch(value); }
        onChosen: function (name) { nxt.revealObject(name); }
    }

    // Collapse the whole tree, keeping the way to the active Body; with
    // Shift, open everything. For long trees.
    IconButton {
        id: collapseButton
        objectName: "collapseButton"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: dockButton.visible ? dockButton.left : gear.left
        anchors.rightMargin: 2
        enabled: nxt.hasDocument
        tip: qsTr("Collapse all") + "\n" + qsTr("Shift-click: expand all")
        // Two chevrons closing on a line: everything folded up.
        paint: function (ctx, w, h, ink) {
            ctx.strokeStyle = ink;
            ctx.lineWidth = Math.max(1.2, w / 9);
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.beginPath();
            ctx.moveTo(w * 0.2, h * 0.08);
            ctx.lineTo(w * 0.5, h * 0.34);
            ctx.lineTo(w * 0.8, h * 0.08);
            ctx.moveTo(w * 0.2, h * 0.92);
            ctx.lineTo(w * 0.5, h * 0.66);
            ctx.lineTo(w * 0.8, h * 0.92);
            ctx.moveTo(w * 0.1, h * 0.5);
            ctx.lineTo(w * 0.9, h * 0.5);
            ctx.stroke();
        }
        onClicked: function (mouse) {
            nxt.collapseTree((mouse.modifiers & Qt.ShiftModifier) !== 0);
        }
    }

    // Inside the 3D view (Nxt's overlay) the dock and its title bar are
    // hidden, so the way back is here: put the panel back in its dock.
    IconButton {
        id: dockButton
        objectName: "dockButton"
        visible: host.viewOverlay
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: gear.left
        anchors.rightMargin: 2
        tip: qsTr("Back to the dock")
        iconScale: 0.66
        iconAspect: 0.8
        // A window with its left side filled: the panel, docked.
        paint: function (ctx, w, h, ink) {
            var line = Math.max(1, Math.round(w / 12));
            ctx.strokeStyle = ink;
            ctx.fillStyle = ink;
            ctx.lineWidth = line;
            ctx.strokeRect(line / 2, line / 2, w - line, h - line);
            ctx.fillRect(0, 0, Math.round(w * 0.36), h);
        }
        onClicked: host.leaveViewOverlay()
    }

    // The tree's quick settings. In the header rather than the title
    // bar: FreeCAD's overlay mode replaces the title bar, and the
    // header is the one part of the panel that is always there.
    IconButton {
        id: gear
        objectName: "gear"
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right
        anchors.rightMargin: 6
        name: qsTr("Tree settings")
        highlighted: header.settingsOpen
        iconScale: 0.7
        paint: function (ctx, w, h, ink) {
            var c = w / 2, outer = w / 2, inner = outer * 0.72;
            var teeth = 8;
            ctx.fillStyle = ink;
            ctx.beginPath();
            for (var i = 0; i < teeth * 2; ++i) {
                var r = i % 2 === 0 ? outer : inner;
                var a0 = (i - 0.5) * Math.PI / teeth;
                var a1 = (i + 0.5) * Math.PI / teeth;
                ctx.lineTo(c + r * Math.cos(a0), c + r * Math.sin(a0));
                ctx.lineTo(c + r * Math.cos(a1), c + r * Math.sin(a1));
            }
            ctx.closePath();
            // The hub, cut out.
            ctx.moveTo(c + outer * 0.32, c);
            ctx.arc(c, c, outer * 0.32, 0, 2 * Math.PI, true);
            ctx.fill("evenodd");
        }
        onClicked: header.settingsClicked()
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: header.parent ? header.parent.width : width  // the divider spans the panel
        height: 1
        visible: !theme.overlay
        color: theme.border
    }
}
