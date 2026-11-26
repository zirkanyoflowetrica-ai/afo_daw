import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"

// F13: botón «?» que explica un panel o un efecto. Sustituye a los párrafos fijos de ayuda: la
// explicación sale al pulsarlo y se cierra con Esc, al pulsar fuera o al volver a pulsarlo.
Rectangle {
    id: root
    property string title: ""
    property string text: ""
    property int size: 24
    readonly property bool opened: pop.visible
    function show() { pop.open() }
    function hide() { pop.close() }

    width: size; height: size; radius: size / 2
    color: pop.visible || hh.hovered ? Theme.accent : Theme.chip
    border.width: 1; border.color: Theme.line
    Text {
        anchors.centerIn: parent; text: "?"
        color: pop.visible || hh.hovered ? Theme.inkOnAccent : Theme.chipInk
        font.family: Theme.font; font.pixelSize: Math.round(root.size * 0.58); font.weight: 800
    }
    HoverHandler { id: hh; cursorShape: Qt.PointingHandCursor }
    ToolTipLite { text: "Qué es " + (root.title ? "«" + root.title + "»" : "esto") + " (clic)"; show: hh.hovered && !pop.visible }
    property double closedAt: 0                // pulsar el «?» con la ayuda abierta la cierra (no la reabre)
    MouseArea { anchors.fill: parent; onClicked: if (!pop.visible && Date.now() - root.closedAt > 250) pop.open() }

    B.Popup {
        id: pop
        objectName: "helpPopup"
        parent: B.Overlay.overlay
        modal: false
        focus: true
        width: 360
        padding: 12
        closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
        onClosed: root.closedAt = Date.now()
        onAboutToShow: {
            var o = parent, p = root.mapToItem(o, 0, 0)
            x = Math.max(8, Math.min(o.width - width - 8, p.x + root.width - width))
            var below = p.y + root.height + 6
            y = below + implicitHeight + 8 <= o.height ? below : Math.max(8, p.y - implicitHeight - 6)
        }
        background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.accent; radius: Theme.radius }
        contentItem: Column {
            spacing: 6
            Text {
                visible: root.title.length > 0
                width: parent.width; wrapMode: Text.Wrap
                text: root.title; color: Theme.ink
                font.family: Theme.font; font.pixelSize: 14; font.weight: 800
            }
            Text {
                objectName: "helpText"
                width: parent.width; wrapMode: Text.Wrap; textFormat: Text.StyledText
                text: root.text; color: Theme.ink; lineHeight: 1.15
                font.family: Theme.font; font.pixelSize: 13
            }
        }
    }
}
