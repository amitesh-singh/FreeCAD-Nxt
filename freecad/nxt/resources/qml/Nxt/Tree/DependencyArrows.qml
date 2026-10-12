import QtQuick

// The selection's dependencies as arrows in a gutter at the tree's right edge
// (links.py). Drawn over the list; never takes the mouse.
Canvas {
    id: arrows

    property ListView list
    property var arrowData: nxt.linkArrows
    readonly property int gutter: Math.round(theme.rowHeight * 1.9)

    antialiasing: true
    enabled: false

    onArrowDataChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Connections {
        target: arrows.list
        function onContentYChanged() { arrows.requestPaint(); }
        function onContentHeightChanged() { arrows.requestPaint(); }
    }
    Connections {
        target: theme
        function onChanged() { arrows.requestPaint(); }
    }

    // Row middle in this canvas, or -1 above / +1 below when not built.
    function rowY(row) {
        var item = list.itemAtIndex(row);
        if (!item)
            return row < list.indexAt(10, list.contentY) ? -1 : 1e9;
        return item.y - list.contentY + list.anchors.topMargin
               + theme.rowHeight / 2;
    }

    function rowRight(row) {
        var item = list.itemAtIndex(row);
        return item ? Math.min(item.pillRight + 4, gutterX - 2) : -1;
    }

    // Docked: the list's right edge. Overlay: past the widest pill spanned.
    property real gutterX: width - gutter + 2
    function placeGutter() {
        if (!theme.overlay) {
            gutterX = width - gutter + 2;
            return;
        }
        var d = arrows.arrowData;
        var lo = d.source, hi = d.source;
        for (var k = 0; k < d.links.length; ++k) {
            lo = Math.min(lo, d.links[k].row);
            hi = Math.max(hi, d.links[k].row);
        }
        var widest = 0;
        var first = list.indexAt(10, list.contentY);
        var last = list.indexAt(10, list.contentY + list.height);
        if (last < 0)
            last = list.count - 1;
        first = Math.max(Math.max(0, first), lo);
        last = Math.min(last, hi);
        for (var i = first; i <= last; ++i) {
            var item = list.itemAtIndex(i);
            if (item)
                widest = Math.max(widest, item.pillRight);
        }
        gutterX = Math.min(width - gutter + 2, widest + 10);
    }

    //: Arrowhead length and half-width.
    readonly property real headLength: 8
    readonly property real headHalfWidth: 3

    function dash(kind) {
        if (kind === "attachment") return [1.5, 3];
        if (kind === "expression") return [5, 3];
        if (kind === "link") return [7, 2, 1.5, 2];
        return [];
    }

    onPaint: {
        var ctx = getContext("2d");
        ctx.reset();
        var d = arrows.arrowData;
        if (!d || d.source < 0 || !d.links || d.links.length === 0)
            return;
        placeGutter();
        var x0 = gutterX;
        var src = rowY(d.source);
        if (src < 0 || src > height)
            return;         // the selection itself is out of sight
        var rows = [d.source];

        for (var i = 0; i < d.links.length; ++i) {
            var link = d.links[i];
            var colour = link.dir === "in" ? theme.arrowIn : theme.arrowOut;
            var y = rowY(link.row);
            var off = y < 0 || y > height;
            var yEnd = off ? (y < 0 ? 3 : height - 3) : y;
            if (!off)
                rows.push(link.row);
            var bulge = 10 + (i % 5) * 7;
            var ya = link.dir === "in" ? yEnd : src;
            var yb = link.dir === "in" ? src : yEnd;
            ya += link.dir === "in" ? 0 : 3;
            yb += link.dir === "in" ? -3 : 0;

            ctx.strokeStyle = colour;
            ctx.fillStyle = colour;
            ctx.lineWidth = 1.6;
            ctx.setLineDash(dash(link.kind));
            // The last control point lies on the head's axis, so the head continues the line.
            var tipX = x0 + 3, tipY = yb;
            var dx = Math.cos(Math.PI / 6);
            var dy = (ya < yb ? -1 : 1) * Math.sin(Math.PI / 6);
            var baseX = tipX + headLength * dx, baseY = tipY + headLength * dy;
            var reach = Math.max(4, bulge * 0.7);
            var c2x = baseX + reach * dx, c2y = baseY + reach * dy;
            ctx.beginPath();
            ctx.moveTo(x0, ya);
            ctx.bezierCurveTo(x0 + bulge, ya, c2x, c2y, baseX, baseY);
            ctx.stroke();
            ctx.setLineDash([]);

            if (!(off && link.dir === "out")) {
                var tilt = Math.atan2(c2y - tipY, c2x - tipX);
                ctx.save();
                ctx.translate(tipX, tipY);
                ctx.rotate(tilt);
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(headLength, -headHalfWidth);
                ctx.lineTo(headLength, headHalfWidth);
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            }
            if (off) {
                var tip = y < 0 ? 0 : height;
                var sign = y < 0 ? 1 : -1;
                ctx.beginPath();
                ctx.moveTo(x0 + bulge, tip);
                ctx.lineTo(x0 + bulge - 4, tip + sign * 6);
                ctx.lineTo(x0 + bulge + 4, tip + sign * 6);
                ctx.closePath();
                ctx.fill();
            }
            if (link.count > 1) {
                var by = (ya + yb) / 2;
                ctx.beginPath();
                ctx.arc(x0 + bulge, by, 7, 0, 2 * Math.PI);
                ctx.fill();
                ctx.fillStyle = theme.background;
                ctx.font = "bold " + Math.max(8, theme.fontAside - 2)
                           + "px sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText(String(link.count), x0 + bulge, by + 0.5);
            }
        }

        ctx.strokeStyle = theme.textDim;
        ctx.globalAlpha = 0.6;
        ctx.lineWidth = 1;
        ctx.setLineDash([1, 3]);
        for (var r = 0; r < rows.length; ++r) {
            var ly = rowY(rows[r]);
            var lx = rowRight(rows[r]);
            if (lx < 0 || lx >= x0)
                continue;
            ctx.beginPath();
            ctx.moveTo(lx, ly);
            ctx.lineTo(x0, ly);
            ctx.stroke();
        }
        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;
    }
}
