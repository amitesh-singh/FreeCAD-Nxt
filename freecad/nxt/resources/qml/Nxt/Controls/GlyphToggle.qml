import QtQuick

// A square on/off button showing a glyph: a yes/no that qualifies the
// value before it (Reversed, beside Direction).
Rectangle {
    id: button

    property string glyph: ""
    property string tip: ""
    property bool checked: false
    signal toggled()

    width: theme.fieldHeight
    height: theme.fieldHeight
    radius: 3
    activeFocusOnTab: enabled
    color: checked ? theme.accent : hover.hovered && enabled ? theme.hover : theme.background
    border.width: activeFocus ? 2 : 1
    border.color: checked || activeFocus ? theme.accent
                : hover.hovered && enabled ? theme.textDim : theme.border
    opacity: enabled ? 1.0 : 0.45

    Text {
        anchors.centerIn: parent
        text: button.glyph
        font.pixelSize: theme.fontRow
        color: button.checked ? theme.accentText : theme.text
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        enabled: button.enabled
        onTapped: { button.forceActiveFocus(); button.toggled() }
    }
    Keys.onSpacePressed: button.toggled()

    NxtToolTip {
        shown: hover.hovered && button.tip.length > 0
        text: button.tip
    }

    Accessible.role: Accessible.CheckBox
    Accessible.name: button.tip
    Accessible.checked: button.checked
}
