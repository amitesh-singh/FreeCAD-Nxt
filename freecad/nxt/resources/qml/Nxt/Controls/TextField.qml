import QtQuick

// A single-line text field, drawn by hand so the host's QtQuick.Controls
// style cannot reach it. Keys are surfaced as signals for the owner.
Item {
    id: field

    property alias text: input.text
    property alias input: input
    property string placeholder: ""
    //: Enables "=" expression help.
    property string owner: ""
    //: A clear (x) button while there is text: for searches and filters.
    property bool clearable: false
    //: Shown after the text inside the field, not editable (a unit).
    property string suffix: ""
    //: Room kept at the start for something drawn over the field.
    property real leading: 0

    signal edited(string value)
    signal accepted()
    signal dismissed()
    signal upPressed()
    signal downPressed()

    implicitHeight: theme.fieldHeight

    Rectangle {
        anchors.fill: parent
        radius: 3
        color: theme.overlay ? theme.chip : theme.background
        border.width: 1
        border.color: input.activeFocus ? theme.accent
                    : fieldHover.hovered ? theme.textDim
                    : theme.overlay ? theme.pillBorder
                    : theme.border
    }

    HoverHandler {
        id: fieldHover
        cursorShape: Qt.IBeamCursor
    }

    Text {
        anchors.verticalCenter: parent.verticalCenter
        x: 6 + field.leading
        visible: input.text.length === 0
        text: field.placeholder
        font.pixelSize: theme.fontSmall
        color: theme.textDim
        opacity: 0.8
    }

    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 6 + field.leading
        anchors.rightMargin: (clearButton.visible ? 20 : 6)
                             + (suffixLabel.visible ? suffixLabel.width + 4
                                                    : 0)
        verticalAlignment: TextInput.AlignVCenter
        font.pixelSize: theme.fontSmall
        color: theme.text
        selectionColor: theme.accent
        selectedTextColor: theme.accentText
        selectByMouse: true
        clip: true

        onTextChanged: field.edited(text)

        // Assist asked in each key handler too: Qt runs those before
        // Keys.onPressed, which would never see these keys.
        Keys.onPressed: function (event) {
            if (assist.handleKey(event))
                event.accepted = true;
        }
        Keys.onReturnPressed: function (event) {
            if (!assist.handleKey(event)) field.accepted();
        }
        Keys.onEnterPressed: function (event) {
            if (!assist.handleKey(event)) field.accepted();
        }
        Keys.onEscapePressed: function (event) {
            if (!assist.handleKey(event)) field.dismissed();
        }
        Keys.onUpPressed: function (event) {
            if (!assist.handleKey(event)) field.upPressed();
        }
        Keys.onDownPressed: function (event) {
            if (!assist.handleKey(event)) field.downPressed();
        }
    }

    ExpressionAssist {
        id: assist
        input: input
        owner: field.owner
    }

    Text {
        id: suffixLabel
        visible: field.suffix.length > 0
        anchors.right: parent.right
        anchors.rightMargin: clearButton.visible ? 20 : 6
        anchors.verticalCenter: parent.verticalCenter
        text: field.suffix
        font.pixelSize: theme.fontSmall
        color: theme.textDim
    }

    Item {
        id: clearButton
        visible: field.clearable && input.text.length > 0
        width: 16
        height: 16
        anchors.right: parent.right
        anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter

        Canvas {
            anchors.fill: parent
            antialiasing: true
            opacity: clearHover.hovered ? 1.0 : 0.55

            onPaint: {
                var ctx = getContext("2d");
                ctx.reset();
                var c = width / 2;
                var a = width * 0.22;
                ctx.strokeStyle = theme.textDim;
                ctx.lineWidth = 1.6;
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(c - a, c - a);
                ctx.lineTo(c + a, c + a);
                ctx.moveTo(c + a, c - a);
                ctx.lineTo(c - a, c + a);
                ctx.stroke();
            }
        }

        HoverHandler { id: clearHover; cursorShape: Qt.PointingHandCursor }
        TapHandler {
            onTapped: {
                input.text = "";
                field.dismissed();
            }
        }
    }
}
