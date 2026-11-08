import QtQuick

// .tabs de la plantilla: una pestaña por pista del tipo (la activa en negro) y «+ Pista».
Flow {
    id: root
    property var seq
    property string type
    width: parent ? parent.width : 300
    spacing: 6
    bottomPadding: 10 + 2
    Repeater {
        model: root.seq.studio.tracks.filter(function (t) { return t.type === root.type })
        NeoButton {
            required property var modelData
            readonly property bool on: root.seq.act[root.type] === modelData.uid
            text: modelData.name; fontSize: 12; padX: 8; padY: 2
            color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
            onClicked: root.seq.pick(root.seq.indexOf(modelData.uid))
        }
    }
    NeoButton { text: "+ Pista"; fontSize: 12; padX: 8; padY: 2; onClicked: root.seq.addTrack(root.type) }
}
