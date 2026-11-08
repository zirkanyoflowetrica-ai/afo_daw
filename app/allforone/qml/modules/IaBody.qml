import QtQuick
import "../theme"
import "../controls"

// Módulo Pistas con IA (Cerebro AI-1): DEMOSTRACIÓN de la plantilla. «Generar» crea una pista con
// clips de ejemplo (sin audio); aquí se conectará un modelo real.
Column {
    id: root
    property var seq
    readonly property var t: seq.active("ia")
    readonly property var c: { seq.draftIa; seq.studio.tracks; return seq.cfgOf("ia") }
    width: parent ? parent.width : 340
    spacing: 0

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: one; text: "1 modelo"; anchors.verticalCenter: parent.verticalCenter }
        Text { width: root.width - one.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
               text: "Un solo modelo. Cada pista de IA guarda su descripción y estilo."
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
    }
    TrackTabs { seq: root.seq; type: "ia" }

    Column {                                    // .stack
        width: root.width; spacing: 10
        Column {
            width: parent.width; spacing: 4
            Text { text: "Describe lo que quieres"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Rectangle {                         // textarea verde de terminal
                width: parent.width; height: 3 * 20 + 20
                color: "#08170f"; border.width: 3; border.color: "#000"
                Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 4; border.color: Qt.rgba(0, 0, 0, 0.5) }
                TextEdit {
                    id: prompt
                    x: 10; y: 9; width: parent.width - 20; height: parent.height - 18
                    text: root.c.prompt || ""
                    wrapMode: TextEdit.Wrap; selectByMouse: true
                    color: "#7dffb0"; font.family: "Consolas"; font.pixelSize: 14
                    onTextChanged: if (text !== (root.c.prompt || "")) root.seq.setCfg("ia", "prompt", text)
                    Text { visible: !prompt.text.length; text: "Línea de bajo oscura con swing"; color: "#3c7a56"
                           font: prompt.font }
                }
            }
        }
        Column {
            width: parent.width; spacing: 4
            Text { text: "Estilo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.seq.styles; current: root.c.style
                     onPicked: function (v) { root.seq.setCfg("ia", "style", v) } }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
            Knob { label: "Creatividad"; value: root.c.cre; onMoved: function (v) { root.seq.setCfg("ia", "cre", v) } }
            Knob { label: "Densidad"; value: root.c.den; onMoved: function (v) { root.seq.setCfg("ia", "den", v) } }
        }
        Flow {
            width: parent.width; spacing: 6
            NeoButton { text: root.seq.generating ? "Generando…" : "Generar pista nueva"
                        color: "#6ab8ff"; textColor: "#000"; padX: 12; padY: 8; shadow: 4
                        opacity: root.seq.generating ? 0.6 : 1
                        onClicked: root.seq.generate() }
            NeoButton { visible: !!root.t; text: "Regenerar la activa"; onClicked: root.seq.regenerate() }
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: "Demostración: agrega clips de ejemplo, sin audio. Aquí conectas tu modelo."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
        }
    }
}
