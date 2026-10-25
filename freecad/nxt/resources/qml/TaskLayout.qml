import QtQuick

// A Part Design task dialog's parameters, as the inspector lays them out
// (task_layout.py puts this in place of FreeCAD's own box). Edits go to the
// dialog's fields, so its preview, OK and Cancel work as before.
Item {
    implicitWidth: 300
    implicitHeight: panel.cards.contentHeight + 8

    Inspector {
        id: panel
        anchors.fill: parent
        bare: true
    }
}
