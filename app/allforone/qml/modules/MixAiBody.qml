import QtQuick
import "../theme"
import "../controls"

// Mezcla IA V4.2 (X17): plantilla, uso en el motor, escalón L/R y espacio vocal, MEZCLAR / REMEZCLAR y el
// A/B de la mezcla automática. Vive en el Inspector › Asistente IA, junto al Master IA y el Antes / Después.
Column {
    id: root
    property var studio
    property var mixer
    width: parent ? parent.width : 400
    spacing: 0
    // ---------------- mezcla IA (arriba de la consola) ----------------
    Text { bottomPadding: 8; text: "MEZCLA IA · AUTO-MIX V4.2 (solo mezcla; el master va debajo)"
           color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.52 }
    Row {                                         // .afo-row2
        width: root.width; spacing: 8; bottomPadding: 10
        Column {
            width: (root.width - 8) / 2; spacing: 4
            Text { text: "Plantilla artística"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.data.profiles; current: root.mixer.profile
                     onPicked: function (v) { root.mixer.profile = v } }
        }
        Column {
            width: (root.width - 8) / 2; spacing: 4
            Text { text: "Uso en el motor"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.data.modes; current: root.mixer.mode
                     onPicked: function (v) { root.mixer.mode = v } }
        }
    }
    Row {                                         // .krow
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
        Knob { label: "Escalón L/R"; value: root.mixer.stepKnob; onMoved: function (v) { root.mixer.stepKnob = v } }
        Knob { label: "Espacio vocal"; value: root.mixer.spaceKnob; onMoved: function (v) { root.mixer.spaceKnob = v } }
    }
    Text {
        width: root.width; topPadding: 8; horizontalAlignment: Text.AlignHCenter; textFormat: Text.StyledText
        text: "<b>" + root.mixer.stepDb().toFixed(1) + " dB</b> bajo la voz principal · profundidad <b>" + Math.round(root.mixer.spaceKnob) + "</b>"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
    Row {                                         // .afo-big
        width: root.width; spacing: 8; topPadding: 10; bottomPadding: 10 + 4
        NeoButton {
            width: (root.width - 8) / 2; text: "MEZCLAR AUTOMÁTICAMENTE"
            fontSize: 15; fontWeight: 700; padY: 10; shadow: 4
            color: root.mixer.busy ? "#e0c0a0" : Theme.lcdSoft; textColor: "#000"
            onClicked: if (!root.mixer.busy) root.mixer.mix(false)
        }
        NeoButton {
            width: (root.width - 8) / 2; text: "↻ REMEZCLAR"
            fontSize: 15; fontWeight: 700; padY: 10; shadow: 4
            opacity: root.mixer.busy || !root.mixer.runs ? 0.5 : 1
            onClicked: if (!root.mixer.busy && root.mixer.runs) root.mixer.mix(true)
        }
    }
    Rectangle {                                   // .afo-prog
        width: root.width; height: 16
        color: "#120f0a"; border.width: Theme.border; border.color: Theme.line
        Item {
            x: 3; y: 3; height: 10; clip: true
            width: (parent.width - 6) * Math.max(0, Math.min(100, root.mixer.progress)) / 100
            Behavior on width { NumberAnimation { duration: 200 } }
            Row {
                Repeater {
                    model: Math.max(0, Math.ceil(root.width / 10))
                    Row { Rectangle { width: 8; height: 10; color: Theme.lcd } Rectangle { width: 2; height: 10; color: Theme.lcdSoft } }
                }
            }
        }
    }
    Text {                                        // .afo-status
        width: root.width; topPadding: 6; wrapMode: Text.Wrap
        text: root.mixer.status; color: Theme.ink
        font.family: Theme.font; font.pixelSize: 12; font.weight: 600
    }
    Row {                                         // A/B de la mezcla automática
        spacing: 6; topPadding: 8; bottomPadding: 8
        NeoButton { text: "A · sin mezcla auto"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                    readonly property bool on: root.mixer.abState === "A"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    tip: "Puentea los efectos que puso la mezcla automática (faders y paneo se quedan)"
                    onClicked: root.mixer.bypass("A") }
        NeoButton { text: "B · con mezcla auto"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                    readonly property bool on: root.mixer.abState === "B"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    onClicked: root.mixer.bypass("B") }
    }
    Text {
        width: root.width; bottomPadding: 10; wrapMode: Text.Wrap; textFormat: Text.StyledText
        text: "En vivo: el V4.2 deja en cada canal su <b>fader, paneo y cadena de efectos reales</b> (se ven en Efectos). No masteriza ni genera WAVs."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
}
