import QtQuick

// Dotted tree connector lines (the "TreeLines" preference); the model
// (branch_lines in tree/models.py) decides what each column draws.
Item {
    id: lines

    //: Per column: 0 nothing, 1 through, 2 tee, 3 last.
    property var branches: []
    //: Column the accent starts at, or -1.
    property int activeFrom: -1
    property real firstX: 0
    property real step: 16
    property real armEnd: 0
    property real headHeight: height
    //: Row y in the list, so dots line up across rows.
    property real offset: 0
    property color ink: theme.border

    readonly property int period: 3
    readonly property int phase: (period - (Math.round(offset) % period))
                                 % period

    component Dots: Item {
        id: run
        property bool vertical: true
        property color ink
        property int phase: 0
        // Its own copy: an inline component cannot see the file's ids.
        property int period: 3
        readonly property real extent: vertical ? height : width
        Repeater {
            model: Math.max(0, Math.ceil((run.extent - run.phase)
                                         / run.period))
            Rectangle {
                required property int index
                x: run.vertical ? 0 : run.phase + index * run.period
                y: run.vertical ? run.phase + index * run.period : 0
                width: 1
                height: 1
                color: run.ink
            }
        }
    }

    Repeater {
        model: lines.branches
        Item {
            id: column
            required property int index
            required property int modelData
            readonly property color ink:
                lines.activeFrom >= 0 && index >= lines.activeFrom
                    ? theme.accent : lines.ink
            readonly property real middle: Math.round(lines.headHeight / 2)
            x: Math.round(lines.firstX + index * lines.step)
            height: lines.height

            Dots {
                visible: column.modelData > 0
                width: 1
                height: column.modelData === 0 ? 0
                      : column.modelData === 3 ? column.middle + 1
                      : lines.height
                phase: lines.phase
                ink: column.ink
            }
            Dots {
                visible: column.modelData >= 2
                vertical: false
                x: 1
                y: column.middle
                height: 1
                width: column.modelData >= 2
                       ? Math.max(0, lines.armEnd - column.x - 1) : 0
                phase: 1
                ink: column.ink
            }
        }
    }
}
