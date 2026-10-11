import QtQuick

// One property in the Property Inspector: its label, and the editor for its
// kind (ValueEditor). Edits go to the `inspector` bridge on the context.
Column {
    id: field

    property var spec: ({})

    spacing: 2

    Row {
        // A switch carries its own label.
        visible: field.spec.editor !== "switch"
        spacing: 4
        Text {
            text: field.spec.label || ""
            font.pixelSize: theme.fontAside
            color: theme.textDim
            width: Math.min(implicitWidth, field.width - 12)
            elide: Text.ElideRight
        }
        Text {
            // An expression drives this value.
            visible: !!field.spec.expression && field.spec.expression.length > 0
            text: "ƒ"
            font.pixelSize: theme.fontAside
            font.italic: true
            font.bold: true
            color: theme.textDim
        }
    }

    ValueEditor {
        width: field.width
        spec: field.spec
        owner: inspector.owner
        onEdited: function (value) {
            inspector.setValue(field.spec.name, value, field.spec.unit);
        }
        onPartEdited: function (path, text) {
            inspector.setPart(field.spec.name, path, text);
        }
        onColourRequested: inspector.pickColour(field.spec.name,
                                                field.spec.text)
        onNativeRequested: inspector.editNative(field.spec.name)
    }
}
