import QtQuick
import Nxt.Controls

// The section frame's buttons, floating at the frame's corner in the 3D
// view while the section is edited (tools/section_field.py): flip, done
// and delete.
Rectangle {
    width: buttons.width + 6
    height: buttons.height + 6
    radius: height / 2
    color: theme.background
    border.width: 1
    border.color: theme.border

    Row {
        id: buttons
        anchors.centerIn: parent
        spacing: 1

        IconButton {
            tip: qsTr("Flip section")
            iconScale: 0.7
            // Two arrows head to head across a line: keep the other side.
            paint: function (ctx, w, h, ink) {
                ctx.strokeStyle = ink;
                ctx.lineWidth = Math.max(1.2, w / 9);
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
                ctx.beginPath();
                ctx.moveTo(w * 0.1, h * 0.5);
                ctx.lineTo(w * 0.9, h * 0.5);
                ctx.moveTo(w * 0.5, h * 0.05);
                ctx.lineTo(w * 0.5, h * 0.38);
                ctx.moveTo(w * 0.33, h * 0.22);
                ctx.lineTo(w * 0.5, h * 0.38);
                ctx.lineTo(w * 0.67, h * 0.22);
                ctx.moveTo(w * 0.5, h * 0.95);
                ctx.lineTo(w * 0.5, h * 0.62);
                ctx.moveTo(w * 0.33, h * 0.78);
                ctx.lineTo(w * 0.5, h * 0.62);
                ctx.lineTo(w * 0.67, h * 0.78);
                ctx.stroke();
            }
            onClicked: actions.flip()
        }

        IconButton {
            tip: qsTr("Done") + "\n" + qsTr("Esc")
            iconScale: 0.6
            paint: function (ctx, w, h, ink) {
                ctx.strokeStyle = ink;
                ctx.lineWidth = Math.max(1.4, w / 8);
                ctx.lineCap = "round";
                ctx.lineJoin = "round";
                ctx.beginPath();
                ctx.moveTo(w * 0.1, h * 0.55);
                ctx.lineTo(w * 0.4, h * 0.85);
                ctx.lineTo(w * 0.9, h * 0.15);
                ctx.stroke();
            }
            onClicked: actions.done()
        }

        IconButton {
            tip: qsTr("Remove section")
            iconScale: 0.5
            paint: function (ctx, w, h, ink) {
                ctx.strokeStyle = ink;
                ctx.lineWidth = Math.max(1.4, w / 8);
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(w * 0.15, h * 0.15);
                ctx.lineTo(w * 0.85, h * 0.85);
                ctx.moveTo(w * 0.85, h * 0.15);
                ctx.lineTo(w * 0.15, h * 0.85);
                ctx.stroke();
            }
            onClicked: actions.remove()
        }
    }
}
