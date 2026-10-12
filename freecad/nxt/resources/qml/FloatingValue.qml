import QtQuick
import Nxt.Controls

// A value field in the 3D view beside a feature's drag arrow, bound to the
// task panel's own field through `field` (tools/float_input.py).
Rectangle {
    id: box

    // Handed over by float_input.py: Qt takes Tab for its focus chain first.
    function tab(backward) {
        input.tabOn(backward);
    }

    function takeKeyboard(selectAll) {
        field.grab();
        input.forceActiveFocus();
        if (selectAll)
            input.selectAll();
    }

    // Above the text, so a double click selects the whole value, not a word.
    MouseArea {
        anchors.fill: parent
        z: 1
        cursorShape: Qt.IBeamCursor
        onPressed: function (mouse) {
            box.takeKeyboard(false);
            input.cursorPosition = input.positionAt(
                mouse.x - input.x, input.height / 2);
        }
        onDoubleClicked: box.takeKeyboard(true)
    }

    // Only the text changes while the wheel turns; the value is set once it
    // rests, so the model is not recomputed on every notch.
    WheelHandler {
        id: wheel
        property real pending: 0
        property int steps: 0
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function (event) {
            box.turn(event.angleDelta.y,
                     (event.modifiers & Qt.ControlModifier) !== 0);
        }
    }
    // Called by float_input.py, which takes the wheel so the 3D view does not zoom.
    function turn(angle, tenfold) {
        wheel.pending += angle / 120;
        var notches = wheel.pending > 0 ? Math.floor(wheel.pending)
                                        : Math.ceil(wheel.pending);
        if (notches === 0)
            return;
        wheel.pending -= notches;
        wheel.steps += notches * (tenfold ? 10 : 1);
        input.text = field.stepped(wheel.steps);
        wheelRest.restart();
    }
    Timer {
        id: wheelRest
        interval: 400
        onTriggered: {
            wheel.steps = 0;
            wheel.pending = 0;
            if (input.text !== field.text) {
                field.commit(input.text);
                input.text = field.text;
            }
        }
    }

    implicitWidth: Math.max(96, input.contentWidth + caption.width + 22)
    implicitHeight: theme.fieldHeight + 6
    radius: 4
    color: theme.background
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? theme.accent : theme.border

    Text {
        id: caption
        anchors.left: parent.left
        anchors.leftMargin: 7
        anchors.verticalCenter: parent.verticalCenter
        text: field.label
        font.pixelSize: theme.fontAside
        color: theme.textDim
    }

    TextInput {
        id: input
        anchors.left: caption.right
        anchors.leftMargin: 6
        anchors.right: parent.right
        anchors.rightMargin: 7
        anchors.verticalCenter: parent.verticalCenter
        font.pixelSize: theme.fontRow
        color: theme.text
        clip: true
        horizontalAlignment: TextInput.AlignRight

        text: field.text
        Connections {
            target: field
            function onTextChanged() {
                if (!input.activeFocus)
                    input.text = field.text;
            }
            function onFocusRequested(selectAll) {
                box.takeKeyboard(selectAll);
            }
        }

        onActiveFocusChanged: {
            if (activeFocus)
                selectAll();
            else if (text !== field.text)
                field.commit(text);
        }
        // The panel's formatting is shown back first, so focus loss finds nothing changed.
        Keys.onReturnPressed: function (event) {
            if (assist.handleKey(event))
                return;
            field.finish(text); text = field.text; field.release();
        }
        Keys.onEnterPressed: function (event) {
            if (assist.handleKey(event))
                return;
            field.finish(text); text = field.text; field.release();
        }
        function tabOn(backward) {
            if (text !== field.text) {
                field.commit(text);
                text = field.text;
            }
            field.tab(backward);
        }
        Keys.onTabPressed: tabOn(false)
        Keys.onBacktabPressed: tabOn(true)
        Keys.onEscapePressed: function (event) {
            if (assist.handleKey(event))
                return;
            text = field.text; field.release();
        }
        onTextEdited: field.preview(text)
        // Tab is not seen here: float_input.py takes it before QML.
        Keys.onPressed: function (event) {
            if (assist.handleKey(event))
                event.accepted = true;
        }
    }

    ExpressionAssist {
        id: assist
        input: input
        owner: field.owner
    }

    Accessible.role: Accessible.EditableText
    Accessible.name: field.label
}
