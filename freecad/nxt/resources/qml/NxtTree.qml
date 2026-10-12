import QtQuick
import Nxt.Controls
import Nxt.Tree

// Root of the Nxt model panel.
//
// One list. A container's children are drawn in the order they were made,
// so a Body reads as a record of the work: sketch, the feature that used
// it, the next sketch, the next feature. Sketches are lifted out of the
// feature that claims them and placed as siblings, because a consumer does
// not own a sketch - the next feature may use the same one - and nesting
// would file a sketch at the point it was first used rather than when it
// was drawn.
//
// This replaced a two-pane layout with the sketches in a shelf below. The
// shelf made reuse obvious and sequence impossible to see; since a sketch
// is built on geometry that existed at one moment, sequence turned out to
// be the thing worth showing. Reuse is now carried by the reference chips
// on the consuming feature.
//
// Deliberately free of QtQuick.Controls: this widget is embedded in a host
// whose Qt style we do not control, and the handful of primitives we need
// are cheaper to draw than to restyle.
Rectangle {
    id: root
    color: theme.canvas
    implicitWidth: 280
    implicitHeight: 520

    readonly property int headerHeight: Math.round(theme.rowHeight * 1.25)

    // The widest the header and a row's detail strip may grow: a share of
    // the screen, so it adapts to resolution and follows the panel to
    // another monitor, with a floor that keeps them usable on small
    // screens. Screen.width is 0 until the panel is shown, so it waits.
    readonly property real contentCap: Screen.width > 0
        ? Math.max(theme.headerMinWidth,
                   Screen.width * theme.headerMaxPercent / 100)
        : width

    // Nxt's overlay (view_overlay.py): does a press at (x, y) land on
    // something the panel draws? Asked for every press before it is
    // delivered: a point on a pill, the header, a strip or a rollback bar
    // is the panel's; anything else goes straight to the 3D view. Asked,
    // not inferred from whether the scene accepted the press - a tap
    // handler on a chip takes a press without accepting it, and the chip's
    // click was lost to the model.
    function wantsPoint(x, y) {
        if (header.contains(header.mapFromItem(root, x, y)))
            return true;
        if (breadcrumb.visible
                && breadcrumb.contains(breadcrumb.mapFromItem(root, x, y)))
            return true;
        if (scrollBar.visible
                && scrollBar.contains(scrollBar.mapFromItem(root, x, y)))
            return true;
        var bar = tipContent.childAt(x - tipLayer.x,
                                     y - treePane.y - tipContent.y);
        if (bar !== null)
            return true;
        var p = treeList.mapFromItem(root, x, y);
        var index = treeList.indexAt(p.x + treeList.contentX,
                                     p.y + treeList.contentY);
        if (index < 0)
            return false;
        var row = treeList.itemAtIndex(index);
        if (!row)
            return false;
        var r = row.mapFromItem(root, x, y);
        return row.wantsPoint(r.x, r.y);
    }

    // Nxt's overlay: the wheel over the panel scrolls the list (see
    // view_overlay.py; the list itself takes no input there, so that the
    // wheel elsewhere zooms the model). `angle` is in eighths of a degree,
    // as Qt reports a wheel; `pixel` is a touchpad's own distance, if any.
    property real wheelBoost: 1
    property double lastWheel: 0

    function scrollWheel(angle, pixel, paging) {
        // Over a breadcrumb too long for its strip, the wheel scrolls the
        // trail, as it does docked.
        if (breadcrumb.visible && breadcrumb.hovered && breadcrumb.overflows) {
            breadcrumb.scrollBy(pixel !== 0 ? pixel : angle / 120 * 40);
            return;
        }
        var now = Date.now();
        wheelBoost = now - lastWheel < 150 ? Math.min(5, wheelBoost + 0.5)
                                           : 1;
        lastWheel = now;
        var step;
        if (paging)
            step = Math.sign(angle || pixel) * treeList.height * 0.9;
        else if (pixel !== 0)
            step = pixel;
        else
            step = angle / 120 * theme.rowHeight * 3 * wheelBoost;
        var top = treeList.originY;
        var bottom = Math.max(top, top + treeList.contentHeight
                                   - treeList.height);
        treeList.contentY = Math.max(top, Math.min(bottom,
                                                   treeList.contentY - step));
    }

    // ================================================================ header

    TreeHeader {
        id: header
        objectName: "header"
        width: Math.min(parent.width, root.contentCap)
        height: root.headerHeight
        // Above the list, so the search results can hang over it.
        z: 100
        ghost: ghost
        settingsOpen: root.settingsOpen
        onSettingsClicked: root.toggleSettings()
    }

    // ================================================================== tree

    Item {
        id: treePane
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        width: parent.width

        readonly property real overlayBarSpace:
            host.viewOverlay ? theme.scrollBarWidth : 0

        // Docked, empty space below the rows is the document's top level:
        // a row dropped there leaves its container. Beneath the list, so a
        // row under the pointer is always the target first. Not in Nxt's
        // overlay, where empty space is the model's - the header's name is
        // the way there.
        RootDropArea {
            anchors.fill: parent
            z: -1
            enabled: !host.viewOverlay
            ghost: ghost
            allowAt: function (x, y) {
                return treeList.indexAt(x, y - treeList.y
                                           + treeList.contentY) < 0;
            }
        }

        ListView {
            id: treeList
            anchors.fill: parent
            anchors.leftMargin: treePane.overlayBarSpace
            anchors.topMargin: 3
            clip: true
            model: nxt.treeModel
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            cacheBuffer: 400
            focus: true
            // Up and Down are the panel's, not the list's: they move the
            // selection, which the list's own key navigation does not.
            keyNavigationEnabled: false
            // Inside the 3D view (Nxt's own overlay) the list does not
            // take presses or drags on its empty space - they belong to
            // the model behind, and reach it by propagation
            // (view_overlay.py).
            interactive: !host.viewOverlay

            // Ahead of the list's own wheel handling, which has no
            // acceleration or paging.
            WheelHandler {
                target: null
                enabled: !host.viewOverlay
                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                onWheel: function (event) {
                    root.scrollWheel(event.angleDelta.y, event.pixelDelta.y,
                                     event.modifiers & Qt.ShiftModifier);
                    event.accepted = true;
                }
            }

            // Which row, if any, has opened a space under it for something
            // being dragged. Two sources that cannot both be active - you
            // are either dragging an object or dragging the bar - kept
            // separate so neither has to clear the other's state.
            property int barGap: -1
            property int dropGap: -1
            readonly property int gapAfterRow: barGap >= 0 ? barGap : dropGap
            // The rows being dragged, and whether the drag is a reorder
            // within a Body (see the drag ghost below).
            property var dragSources: []
            // A row kept where it is on screen while strips above it
            // open and close (auto-show; see the bridge's rowHeld).
            property int heldRow: -1
            property real heldOffset: 0
            property bool reorderDrag: false
            // The row a sliding drag would drop into, or -1.
            property int intoRow: -1

            delegate: TreeRow { dragGhost: ghost; detailCap: root.contentCap }

            // One empty row after the last: scrolled to the end, the last
            // row - and a rollback bar under it - is never jammed against
            // the bottom edge.
            footer: Item {
                width: treeList.width
                height: theme.rowHeight
            }

            // A translucent QQuickWidget composites over what is behind it,
            // but changing content does not ask that surface to redraw - so
            // without this, the previous frame's pills stay stranded in the
            // transparent gaps until something unrelated repaints. Scrolling
            // moves them; expanding a branch and resizing move them too, so
            // every signal that can is wired up. The call is coalesced on
            // the other side, so this is cheap.
            onContentYChanged: if (theme.overlay) host.repaintBehind()
            onContentHeightChanged: if (theme.overlay) host.repaintBehind()
            onCountChanged: if (theme.overlay) host.repaintBehind()
            onHeightChanged: if (theme.overlay) host.repaintBehind()
        }

        // The containers the top of the list is inside, once their rows
        // have scrolled away: pinned over the top of the list.
        Breadcrumb {
            id: breadcrumb
            objectName: "breadcrumb"
            z: 50
            // Docked it spans the panel, as the header's divider does; in
            // Nxt's overlay it is a pill the width of the header's.
            width: theme.overlay ? header.width : parent.width

            //: The row just under the strip, and every container of it.
            property int under: -1
            property var containers: []

            // `changed`: the rows themselves did, so the same row number
            // may be another object now.
            function refresh(changed) {
                var at = treeList.indexAt(0, treeList.contentY + height);
                if (at === under && !changed)
                    return;
                under = at;
                containers = (at >= 0 && nxt.breadcrumb(at)) || [];
            }

            // Only those out of sight: a container still on screen is
            // its own heading. A row too far off to exist is out of sight.
            crumbs: containers.filter(function (crumb) {
                var item = treeList.itemAtIndex(crumb.row);
                return item === null || item.y < treeList.contentY;
            })
            // Under the strip, not behind it.
            onCrumbClicked: function (row) {
                treeList.positionViewAtIndex(row, ListView.Beginning);
                treeList.contentY = Math.max(treeList.originY,
                                             treeList.contentY - height);
            }

            Connections {
                target: treeList
                function onContentYChanged() { breadcrumb.refresh(false); }
            }
            Connections {
                target: nxt.treeModel
                function onModelReset() { breadcrumb.refresh(true); }
                function onRowsInserted() { breadcrumb.refresh(true); }
                function onRowsRemoved() { breadcrumb.refresh(true); }
                function onDataChanged() { breadcrumb.refresh(true); }
            }
        }

        // Timeline bars, one per Body with a visible history. An overlay
        // rather than list rows: rows are a uniform height, so a row's y is
        // arithmetic, and the model stays a plain sequence of objects.
        Item {
            id: tipLayer
            anchors.fill: parent
            anchors.leftMargin: treePane.overlayBarSpace
            clip: true
            z: 5

            // The bars ride with the rows: scrolling moves this one item,
            // instead of re-placing every bar on every frame.
            Item {
                id: tipContent
                y: -treeList.contentY
                width: parent.width
                height: treeList.contentHeight

                // Advances every few rows scrolled, so bars re-measure
                // rows the list has realised since.
                readonly property int realised:
                    Math.floor(treeList.contentY / (theme.rowHeight * 5))

            Repeater {
                model: nxt.tipBars

                TimelineBar {
                    required property var modelData

                    // Starts at the Body's indent, because it is a
                    // position in that Body's history rather than a handle
                    // attached to one row. Where it *ends* is the bar's own
                    // business - see TimelineBar.
                    x: theme.rowPad + modelData.depth * theme.indent
                    body: modelData.body
                    pos: modelData.pos
                    minPos: modelData.minPos
                    maxPos: modelData.maxPos
                    rowHeight: theme.rowHeight
                    list: treeList
                    fullWidth: treeList.width
                    listContentY: 0
                    realised: tipContent.realised
                    listTopMargin: treeList.anchors.topMargin
                    visible: y + height >= treeList.contentY
                             && y <= treeList.contentY + treeList.height

                    onDragPosChanged: if (dragging) treeList.barGap = dragPos
                    onDraggingChanged: treeList.barGap = dragging ? dragPos : -1
                }
            }
            }
        }

        // The selection's dependencies, over the list's right edge.
        DependencyArrows {
            anchors.fill: treeList
            list: treeList
            z: 4
        }

        NxtScrollBar {
            id: scrollBar
            target: treeList
            z: 6
            anchors.top: treeList.top
            anchors.bottom: parent.bottom
            x: host.viewOverlay ? 0 : parent.width - width
        }


        Text {
            anchors.centerIn: parent
            visible: treeList.count === 0
            text: nxt.hasDocument ? qsTr("This document is empty")
                                  : qsTr("Open or create a document")
            color: theme.textDim
            font.pixelSize: theme.fontRow
        }
    }

    // ============================================================ drag ghost

    DragGhost {
        id: ghost
        list: treeList
    }

    // ========================================================= context menu

    Component {
        id: contextMenuComponent
        ContextMenu {}
    }

    // What the context menu opens from: a point, not a control. Under
    // Wayland a menu in a window of its own is placed against the whole
    // rectangle of the item it opens from - opened from the panel, it sat
    // at the panel's bottom-left corner - so it opens from this one-pixel
    // item, moved to the click first. See host.menuAnchorOffset().
    Item {
        id: menuAnchor
        width: 1
        height: 1
    }

    // Built afresh for each opening, from the selection as it is now:
    // where the row was right-clicked, or under a row from the keyboard.
    // The menu is a window of its own (see ContextMenu.qml).
    // The gear's quick settings: one at a time, opened below the gear with
    // its right edge on the gear's, from the same anchor the context menu
    // uses (see menuAnchor).
    property bool settingsOpen: false
    property var settingsPopup: null
    // When the popup last closed, in ms. A press on the gear while the
    // popup is open closes it (a press outside it) before the gear's click
    // arrives - and the click then opened it again. A click that lands
    // just after a close is that same press, so it does not reopen.
    property double settingsClosedAt: 0

    // The gear: open the settings, or close them if they are open.
    function toggleSettings() {
        if (settingsOpen) {
            if (settingsPopup)
                settingsPopup.close();
            return;
        }
        if (Date.now() - settingsClosedAt < 300)
            return;
        openSettings();
    }

    function openSettings() {
        if (settingsOpen)
            return;
        var popup = settingsComponent.createObject(root);
        settingsPopup = popup;
        var gear = header.gear;
        var at = gear.mapToItem(root, gear.width - popup.width, gear.height);
        var offset = host.menuAnchorOffset();
        menuAnchor.x = Math.max(0, at.x) + offset.x;
        menuAnchor.y = at.y + 2 + offset.y;
        popup.parent = menuAnchor;
        popup.x = 0;
        popup.y = 0;
        settingsOpen = true;
        popup.closed.connect(function () {
            root.settingsOpen = false;
            root.settingsPopup = null;
            root.settingsClosedAt = Date.now();
            treeList.forceActiveFocus();
        });
        popup.open();
    }

    Component {
        id: settingsComponent
        TreeSettings {}
    }

    function openContextMenu(rowItem, x, y) {
        var data = nxt.contextMenu();
        if (!data || !data.bar)
            return;
        var menu = contextMenuComponent.createObject(root);
        menu.load(data);
        // Run once the menu has gone, so a command that opens a dialog or
        // a task panel does not start underneath it.
        menu.chosen.connect(function (command) {
            Qt.callLater(function () { nxt.runMenuItem(command); });
        });
        menu.closed.connect(function () { treeList.forceActiveFocus(); });
        var at = rowItem
            ? rowItem.mapToItem(root, theme.rowPad + theme.indent,
                                rowItem.height)
            : Qt.point(x, y);
        var offset = host.menuAnchorOffset();
        menuAnchor.x = at.x + offset.x;
        menuAnchor.y = at.y + offset.y;
        menu.parent = menuAnchor;
        menu.popup(menuAnchor, 0, 0);
    }

    function startRename(row) {
        if (row < 0)
            return;
        treeList.positionViewAtIndex(row, ListView.Contain);
        var item = treeList.itemAtIndex(row);
        if (item)
            item.beginRename();
    }

    // ============================================================= keyboard

    // Driven by the selection rather than by the list's currentIndex, so a
    // key does the same thing wherever the row happens to be - and so it
    // agrees with what the 3D view and the rest of FreeCAD consider current.
    // A focused TextInput consumes these first, so typing a space into the
    // search box or a rename field does not toggle anything.
    // Space is also a FreeCAD shortcut (toggle visibility), and a shortcut
    // is offered the key before the panel is: FreeCAD's command then ran
    // in place of the handler below, without the Part Design handling in
    // toggleSelectedVisibility. Claiming the key here keeps it for the
    // panel while the panel has the keyboard.
    // Home and End likewise: Home is FreeCAD's "home view".
    Keys.onShortcutOverride: function (event) {
        // Escape during a drag cancels it, before any shortcut sees it.
        if (event.key === Qt.Key_Escape && ghost.Drag.active) {
            event.accepted = true;
            return;
        }
        if ((event.key === Qt.Key_Space || event.key === Qt.Key_Home
             || event.key === Qt.Key_End)
                && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier
                                        | Qt.MetaModifier)))
            event.accepted = true;
    }

    Keys.onPressed: function (event) {
        if (event.key === Qt.Key_Escape && ghost.Drag.active) {
            ghost.cancel();
            event.accepted = true;
            return;
        }
        if (event.key === Qt.Key_F2) {
            root.startRename(nxt.treeRenameRow());
            event.accepted = true;
        } else if (event.key === Qt.Key_Menu
                   || (event.key === Qt.Key_F10
                       && (event.modifiers & Qt.ShiftModifier))) {
            // Beside the row it is for, under its icon.
            var at = nxt.contextMenuRow();
            if (at >= 0) {
                treeList.positionViewAtIndex(at, ListView.Contain);
                var rowItem = treeList.itemAtIndex(at);
                if (rowItem) {
                    root.openContextMenu(rowItem, 0, 0);
                }
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Escape) {
            // Only taken when it closed something, so Escape still
            // reaches FreeCAD (clearing the selection) otherwise.
            event.accepted = nxt.closeDetail() || isolation.leave();
        } else if (event.key === Qt.Key_Space) {
            nxt.toggleSelectedVisibility();
            event.accepted = true;
        } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
            var target = nxt.stepSelection(
                event.key === Qt.Key_Up ? -1 : 1,
                (event.modifiers & Qt.ShiftModifier) !== 0);
            if (target >= 0) {
                treeList.currentIndex = target;
                treeList.positionViewAtIndex(target, ListView.Contain);
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
            var end = nxt.jumpSelection(
                event.key === Qt.Key_End,
                (event.modifiers & Qt.ShiftModifier) !== 0);
            if (end >= 0) {
                treeList.currentIndex = end;
                treeList.positionViewAtIndex(end, ListView.Contain);
            }
            event.accepted = true;
        } else if (event.key === Qt.Key_Left || event.key === Qt.Key_Right) {
            var row = nxt.stepBranch(event.key === Qt.Key_Right ? 1 : -1);
            if (row >= 0) {
                treeList.currentIndex = row;
                treeList.positionViewAtIndex(row, ListView.Contain);
            }
            event.accepted = true;
        }
    }

    // ====================================================== reveal plumbing

    Connections {
        target: nxt
        function onContextMenuRequested(x, y) {
            root.openContextMenu(null, x, y);
        }
        function onRenameRowRequested(row) {
            root.startRename(row);
        }
        function onRowHeld(row) {
            var item = treeList.itemAtIndex(row);
            treeList.heldRow = item ? row : -1;
            if (item)
                treeList.heldOffset = item.y - treeList.contentY;
        }
        function onRowReleased() {
            var row = treeList.heldRow;
            treeList.heldRow = -1;
            if (row < 0)
                return;
            var offset = treeList.heldOffset;
            // After the rows have taken their new heights.
            Qt.callLater(function () {
                var item = treeList.itemAtIndex(row);
                if (!item)
                    return;
                treeList.contentY = item.y - offset;
                treeList.returnToBounds();
            });
        }
        function onRevealTreeRow(row) {
            treeList.positionViewAtIndex(row, ListView.Contain);
        }
        // The inspector opens from the row, which knows where its own edge is.
        function onPropertyInspectorRequested(row) {
            treeList.positionViewAtIndex(row, ListView.Contain);
            var item = treeList.itemAtIndex(row);
            if (item)
                item.openInspector();
            else
                nxt.openPropertyInspector("", -1, -1);
        }
    }
}
