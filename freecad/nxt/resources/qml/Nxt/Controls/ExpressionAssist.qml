import QtQuick
import QtQuick.Controls.Basic

// Expression help under a value field once its text starts with "=".
// The field calls handleKey() first. A ToolTip window, since a popup
// window would grab the keyboard from the field.
Item {
    id: assist

    property Item input: null
    //: "Document#Name" or "Name".
    property string owner: ""

    readonly property bool available:
        typeof expressions !== "undefined" && assist.owner.length > 0
    readonly property bool typing: available && input !== null
                                   && input.activeFocus
                                   && input.text.trim().charAt(0) === "="
    property var suggestions: []
    property int current: 0
    //: Return accepts the suggestion.
    property bool picked: false
    //: Hidden by Escape until the text changes.
    property bool hushed: false
    property var result: ({ok: false, text: ""})

    width: 0
    height: 0

    function refresh() {
        if (!assist.typing) {
            popup.close();
            return;
        }
        assist.suggestions = expressions.suggest(
            assist.owner, input.text, input.cursorPosition);
        assist.current = 0;
        assist.picked = false;
        assist.result = expressions.evaluate(assist.owner, input.text);
        if (assist.hushed) {
            popup.close();
            return;
        }
        var below = input.mapToItem(assist, 0, input.height + 2);
        var shift = expressions.anchorOffset(assist);
        // Wayland places popups against their parent item, not popup.x/y,
        // so the anchor item is moved (shifted by quick_host.window_offset).
        anchor.x = below.x + shift.x;
        anchor.y = below.y + shift.y;
        popup.open();
    }

    function accept(index) {
        var chosen = assist.suggestions[index];
        if (!chosen)
            return;
        var done = expressions.complete(input.text, input.cursorPosition,
                                        chosen.insert);
        input.text = done.text;
        input.cursorPosition = done.cursor;
    }

    function handleKey(event) {
        if (!assist.typing || !popup.visible)
            return false;
        var count = assist.suggestions.length;
        if (event.key === Qt.Key_Escape) {
            assist.hushed = true;
            popup.close();
            return true;
        }
        if (count === 0)
            return false;
        if (event.key === Qt.Key_Down) {
            assist.current = (assist.current + 1) % count;
            assist.picked = true;
            return true;
        }
        if (event.key === Qt.Key_Up) {
            assist.current = (assist.current + count - 1) % count;
            assist.picked = true;
            return true;
        }
        if (event.key === Qt.Key_Tab
                || ((event.key === Qt.Key_Return
                     || event.key === Qt.Key_Enter) && assist.picked)) {
            assist.accept(assist.current);
            return true;
        }
        return false;
    }

    Connections {
        target: assist.input
        function onTextChanged() {
            assist.hushed = false;
            assist.refresh();
        }
        function onCursorPositionChanged() { assist.refresh(); }
        function onActiveFocusChanged() { assist.refresh(); }
    }

    Item {
        id: anchor
        width: 1
        height: 1
    }

    ToolTip {
        id: popup
        parent: anchor
        x: 0
        y: 0
        popupType: Popup.Window
        focus: false
        closePolicy: Popup.NoAutoClose
        timeout: -1
        delay: 0
        enter: null
        exit: null
        margins: 4
        padding: 4
        width: Math.max(220, list.implicitWidth + 8)

        background: Rectangle {
            radius: 4
            color: theme.background
            border.width: 1
            border.color: theme.border
        }

        contentItem: Column {
            id: list
            spacing: 1

            Repeater {
                model: assist.suggestions

                Rectangle {
                    id: line
                    required property int index
                    required property var modelData
                    width: Math.max(212, row.implicitWidth + 12)
                    height: theme.fieldHeight
                    radius: 3
                    color: index === assist.current ? theme.accent
                         : lineHover.hovered ? theme.hover : "transparent"

                    Row {
                        id: row
                        x: 6
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Text {
                            text: line.modelData.kind === "function" ? "ƒ"
                                : line.modelData.kind === "object" ? "◇"
                                : line.modelData.kind === "constant" ? "π"
                                : "·"
                            width: 10
                            font.pixelSize: theme.fontSmall
                            color: line.index === assist.current
                                   ? theme.accentText : theme.textDim
                        }
                        Text {
                            text: line.modelData.label
                            font.pixelSize: theme.fontSmall
                            color: line.index === assist.current
                                   ? theme.accentText : theme.text
                        }
                        Text {
                            visible: line.modelData.detail.length > 0
                            text: line.modelData.detail
                            font.pixelSize: theme.fontAside
                            color: line.index === assist.current
                                   ? theme.accentText : theme.textDim
                        }
                    }

                    HoverHandler { id: lineHover }
                    TapHandler { onTapped: assist.accept(line.index) }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                visible: assist.suggestions.length > 0
                color: theme.border
            }
            Text {
                width: Math.max(212, implicitWidth)
                leftPadding: 6
                topPadding: 2
                bottomPadding: 2
                text: assist.result.text.length === 0
                      ? qsTr("Type an expression")
                      : (assist.result.ok ? "= " + assist.result.text
                                          : assist.result.text)
                font.pixelSize: theme.fontSmall
                font.italic: !assist.result.ok
                color: assist.result.ok ? theme.text : theme.danger
                elide: Text.ElideRight
            }
        }
    }
}
