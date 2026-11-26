import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"

// Paleta de órdenes (Ctrl+K, F1): escribes lo que quieres hacer y la lista se filtra por nombre, menú
// y ayuda; ↑ ↓ eligen e Intro la ejecuta. Son las mismas órdenes del registro (actions.py) que los menús.
B.Popup {
    id: root
    property var studio
    property string query: ""
    property int cur: 0
    readonly property var hits: {
        var q = query.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim()
        var all = studio ? studio.actionsReg : []
        if (!q) return all
        var words = q.split(/\s+/)
        return all.filter(function (a) {
            var s = (a.label + " " + a.menu + " " + a.tip).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
            return words.every(function (w) { return s.indexOf(w) >= 0 })
        })
    }
    property string armed: ""
    onHitsChanged: { cur = 0; armed = "" }
    onCurChanged: armed = ""
    modal: true
    focus: true
    width: Math.min(620, (parent ? parent.width : 800) - 40)
    height: Math.min(460, (parent ? parent.height : 600) - 80)
    x: ((parent ? parent.width : 800) - width) / 2
    y: 60
    padding: 8
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.accent; radius: Theme.radius }
    B.Overlay.modal: Rectangle { color: Theme.rgba(Theme.s0, 0.55) }
    onOpened: { query = ""; field.text = ""; field.forceActiveFocus() }

    function run(i) {
        var a = hits[i]
        if (!a || !studio.actionEnabled(a.id)) return
        if (a.confirm && armed !== a.id) { armed = a.id; return }      // lo que borra: Intro otra vez
        close()
        studio.runAction(a.id)
    }

    contentItem: Column {
        spacing: 6
        Rectangle {
            width: parent.width; height: 34; color: Theme.input; radius: Theme.radius
            border.width: 1; border.color: Theme.line
            TextInput {
                id: field
                objectName: "paletteField"
                x: 10; width: parent.width - 20; anchors.verticalCenter: parent.verticalCenter
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; clip: true
                selectByMouse: true
                onTextChanged: root.query = text
                Keys.onDownPressed: { root.cur = Math.min(root.hits.length - 1, root.cur + 1); list.positionViewAtIndex(root.cur, ListView.Contain) }
                Keys.onUpPressed: { root.cur = Math.max(0, root.cur - 1); list.positionViewAtIndex(root.cur, ListView.Contain) }
                Keys.onReturnPressed: root.run(root.cur)
                Keys.onEnterPressed: root.run(root.cur)
                Text { visible: !field.text; text: "Escribe una orden: dividir, separar, mezcla, tema…"; color: Theme.inkDim
                       font: field.font; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        ListView {
            id: list
            objectName: "paletteList"
            width: parent.width; height: root.availableHeight - 40
            clip: true
            model: root.hits
            delegate: Rectangle {
                id: d
                required property var modelData
                required property int index
                readonly property bool on: root.studio.actionEnabled(modelData.id)
                readonly property bool hl: index === root.cur
                readonly property bool asking: root.armed === modelData.id
                width: ListView.view.width; height: 30; radius: Theme.radius
                color: asking ? Theme.rec : hl ? Theme.accent : "transparent"
                readonly property color fg: asking ? Theme.inkOnColor : hl ? Theme.inkOnAccent : on ? Theme.ink : Theme.inkDim
                Text { x: 8; width: 70; anchors.verticalCenter: parent.verticalCenter; text: d.modelData.menu
                       color: d.hl ? Theme.inkOnAccent : Theme.inkDim; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                Text { x: 80; width: parent.width - 80 - keys.implicitWidth - 50; elide: Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
                       text: d.asking ? d.modelData.confirm : d.modelData.label; color: d.fg; font.family: Theme.font; font.pixelSize: 14; font.weight: 600 }
                Rectangle { visible: !!d.modelData.ai; width: 22; height: 16; radius: 3; color: Theme.ai
                            anchors.right: keys.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            Text { anchors.centerIn: parent; text: "IA"; color: Theme.inkOnColor; font.family: Theme.font; font.pixelSize: 10; font.weight: 800 } }
                Text { id: keys; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                       text: d.modelData.keys || ""; color: d.fg; font.family: Theme.font; font.pixelSize: 12 }
                MouseArea { anchors.fill: parent; hoverEnabled: true; onEntered: root.cur = d.index; onClicked: root.run(d.index) }
            }
        }
    }
}
