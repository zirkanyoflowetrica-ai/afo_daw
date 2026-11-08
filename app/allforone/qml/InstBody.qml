import QtQuick

// Módulo Instrumentos (Banco VST-1): una sola instancia; cada pista guarda su preset.
Column {
    id: root
    property var seq
    readonly property var t: seq.active("inst")
    width: parent ? parent.width : 380
    spacing: 0

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: one; text: "1 instancia"; anchors.verticalCenter: parent.verticalCenter }
        Text { width: root.width - one.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
               text: "El instrumento se carga una sola vez. Cada pista guarda solo su preset."
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
    }
    TrackTabs { seq: root.seq; type: "inst" }
    DashedBox { visible: !root.t; width: root.width; height: visible ? implicitHeight : 0
                text: "Crea una pista de instrumento para cargar su preset." }

    Grid {                                      // .insts: repeat(auto-fill, minmax(120px, 1fr))
        id: grid
        visible: !!root.t
        columns: Math.max(1, Math.floor((root.width + 8) / 128))
        columnSpacing: 8; rowSpacing: 8
        topPadding: 10; bottomPadding: 10 + 3
        readonly property real cw: (root.width - (columns - 1) * 8) / columns - 3
        Repeater {
            model: root.seq.insts
            Item {
                id: card
                required property var modelData
                required property int index
                readonly property bool on: !!root.t && root.t.cfg.v === index
                width: grid.cw; height: col.height + 12 + 4
                Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000"; visible: !cm.pressed }
                Rectangle {
                    x: cm.pressed ? 3 : 0; y: cm.pressed ? 3 : 0
                    width: parent.width; height: parent.height
                    color: "#2b2720"; border.width: 2; border.color: "#000"
                    Column {
                        id: col
                        x: 12; y: 7; width: parent.width - 24; spacing: 2
                        Item {
                            width: 11; height: 15
                            Rectangle { anchors.centerIn: parent; anchors.verticalCenterOffset: -2; width: 20; height: 20; radius: 10
                                        color: "#ff4d3d"; opacity: 0.25; visible: card.on }
                            Rectangle { width: 11; height: 11; radius: 5.5; border.width: 2; border.color: "#000"
                                        color: card.on ? "#ff4d3d" : "#4a1d1a" }
                        }
                        Text { width: parent.width; elide: Text.ElideRight; text: card.modelData[0]
                               color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                        Text { width: parent.width; elide: Text.ElideRight; text: card.modelData[1]
                               color: "#bdb398"; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
                    }
                }
                MouseArea {
                    id: cm; anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: { root.seq.setCfg("inst", "v", card.index); root.seq.previewMidi(root.t.cfg, 69) }
                }
            }
        }
    }
    Row {                                       // .krow
        visible: !!root.t
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
        Knob { label: "Velocidad"; value: root.t ? root.t.cfg.vel : 70; onMoved: function (v) { root.seq.setCfg("inst", "vel", v) } }
        Knob { label: "Brillo"; value: root.t ? root.t.cfg.bri : 50; onMoved: function (v) { root.seq.setCfg("inst", "bri", v) } }
        Knob { label: "Reverb"; value: root.t ? root.t.cfg.rev : 30; tip: "Reverb de sala del motor (0 = seca)"
               onMoved: function (v) { root.seq.setCfg("inst", "rev", v) } }
    }
}
