import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"

// Menú de órdenes (F1): la barra de menús y el clic derecho de clips y pistas. Las órdenes salen del
// registro único (actions.py → `studio.actionsReg`); cada fila dice qué hace en su ayuda, muestra su
// atajo y la marca «IA» si la hace la IA en el equipo. Lo que ahora no se puede hacer sale atenuado.
B.Popup {
    id: root
    property var studio
    property var items: []                    // órdenes del registro, en orden
    property string ctx: ""                   // «clip», «track» o «» (barra de menús): para el selftest
    readonly property int count: items.length
    property string armed: ""                 // orden que borra, esperando el segundo clic
    onClosed: armed = ""
    padding: 4
    width: 330
    modal: false
    focus: true
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    function openAt(item, x, y) {
        var p = item.mapToItem(root.parent, x, y)
        var w = root.parent ? root.parent.width : 2000, h = root.parent ? root.parent.height : 2000
        root.x = Math.max(0, Math.min(p.x, w - root.width - 4))
        root.y = Math.max(0, Math.min(p.y, h - col.implicitHeight - 12))
        root.open()
    }

    contentItem: Column {
        id: col
        width: root.width - 2 * root.padding
        Repeater {
            model: root.items
            Column {
                id: rowItem
                required property var modelData
                required property int index
                readonly property bool on: !!root.studio && root.studio.actionEnabled(modelData.id)
                readonly property bool checked: !!root.studio && root.studio.actionChecked(modelData.id)
                width: col.width
                Rectangle {                     // separador entre grupos
                    visible: rowItem.index > 0 && root.items[rowItem.index - 1].group !== rowItem.modelData.group
                    width: parent.width; height: visible ? 9 : 0; color: "transparent"
                    Rectangle { y: 4; width: parent.width; height: 1; color: Theme.line }
                }
                Rectangle {
                    width: parent.width; height: 28; radius: Theme.radius
                    readonly property bool asking: root.armed === rowItem.modelData.id
                    color: asking ? Theme.rec : ma.containsMouse && rowItem.on ? Theme.accent : "transparent"
                    readonly property color fg: asking ? Theme.inkOnColor : ma.containsMouse && rowItem.on ? Theme.inkOnAccent : rowItem.on ? Theme.ink : Theme.inkDim
                    Text { x: 6; width: 16; anchors.verticalCenter: parent.verticalCenter; text: rowItem.checked ? "✓" : ""
                           color: parent.fg; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                    Text { x: 24; width: parent.width - 24 - keysTxt.implicitWidth - aiChip.width - 18; elide: Text.ElideRight
                           anchors.verticalCenter: parent.verticalCenter; text: parent.asking ? rowItem.modelData.confirm : rowItem.modelData.label
                           color: parent.fg; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                    Rectangle {
                        id: aiChip
                        visible: !!rowItem.modelData.ai
                        width: visible ? 22 : 0; height: 16; radius: 3; color: Theme.ai
                        anchors.right: keysTxt.left; anchors.rightMargin: keysTxt.text ? 8 : 0; anchors.verticalCenter: parent.verticalCenter
                        Text { anchors.centerIn: parent; text: "IA"; color: Theme.inkOnColor; font.family: Theme.font; font.pixelSize: 10; font.weight: 800 }
                    }
                    Text { id: keysTxt; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                           text: rowItem.modelData.keys || ""; color: parent.fg; font.family: Theme.font; font.pixelSize: 12 }
                    MouseArea {
                        id: ma; anchors.fill: parent; hoverEnabled: true
                        cursorShape: rowItem.on ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (!rowItem.on) return
                            if (rowItem.modelData.confirm && root.armed !== rowItem.modelData.id) { root.armed = rowItem.modelData.id; return }
                            root.close(); root.studio.runAction(rowItem.modelData.id)
                        }
                    }
                    ToolTipLite { text: rowItem.modelData.tip + (rowItem.modelData.keys ? " (" + rowItem.modelData.keys + ")" : "")
                                  show: ma.containsMouse }
                }
            }
        }
    }
}
