import QtQuick
import Nxt.Controls

// The undo toast in the 3D view (toast.py); Python positions and hides it.
UndoToast {
    id: banner

    // Null-safe: the banner can outlive `toasts` by an event at teardown.
    actions: toasts ? toasts.labels : []
    sticky: toasts ? toasts.sticky : false
    property bool ready: false

    Component.onCompleted: {
        ready = true;
        show(toasts.message);
    }
    onActionRequested: (index) => toasts.act(index)
    onVisibleChanged: if (ready && !visible) toasts.dismissed()

    Connections {
        target: toasts
        function onShown() { banner.show(toasts.message); }
        function onCleared() { banner.dismiss(); }
    }
}
