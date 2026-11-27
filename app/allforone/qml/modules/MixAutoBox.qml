import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"
import "../controls"

// Mezcla automática (F6, FLUJO_PROFESIONAL §3.1): una orden del Mezclador, como «Normalizar» o
// «Exportar». Se abre desde la barra del Mezclador o el menú Mezcla; aquí solo van sus ajustes. Lo que
// hace se ve en las tiras (fader, paneo y efectos con la marca «IA»), el progreso en la barra de estado,
// el A/B en la barra del Mezclador y Ctrl+Z (en el Mezclador) la deshace. Mezcla automática por debajo.
B.Popup {
    id: root
    property var studio
    property var mixer
    readonly property bool can: !!mixer && mixer.items.length > 0 && !mixer.busy

    modal: false
    focus: true
    width: Math.min(560, (parent ? parent.width : 900) - 40)
    x: ((parent ? parent.width : 900) - width) / 2
    y: 80
    padding: 14
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    function run(remix) {
        if (!root.can) return
        root.mixer.mix(remix)
        if (root.mixer.busy) close()
    }

    contentItem: Column {
        spacing: 10
        Row {
            spacing: 8
            Text { text: "Mezcla automática"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 16; font.weight: 800
                   anchors.verticalCenter: parent.verticalCenter }
            AiMark { anchors.verticalCenter: parent.verticalCenter }
        }
        Text {
            width: root.availableWidth; wrapMode: Text.Wrap
            text: "Pone fader, paneo y efectos en cada tira (los efectos llevan la marca «IA»); no masteriza ni crea archivos. "
                  + "Ctrl+Z en el Mezclador la deshace y «A/B» de la barra compara con y sin ella."
            color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
        }
        Row {
            width: root.availableWidth; spacing: 8
            Column {
                width: (parent.width - 8) / 2; spacing: 4
                Text { text: "Estilo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                Select { objectName: "mixAutoProfile"; width: parent.width; options: root.mixer.data.profiles; current: root.mixer.profile
                         tip: "Plantilla artística de la mezcla"
                         onPicked: function (v) { root.mixer.profile = v } }
            }
            Column {
                width: (parent.width - 8) / 2; spacing: 4
                Text { text: "Uso en el motor"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                Select { width: parent.width; options: root.mixer.data.modes; current: root.mixer.mode
                         tip: "Cuántos efectos del motor puede usar la mezcla"
                         onPicked: function (v) { root.mixer.mode = v } }
            }
        }
        Row {                                     // los dos ajustes de la orden
            spacing: 24
            Knob { objectName: "mixAutoStep"; label: "Escalón L/R"; value: root.mixer.stepKnob
                   tip: "Cuánto bajan las voces de los lados bajo la voz principal (5 a 10 dB)"
                   onMoved: function (v) { root.mixer.stepKnob = v } }
            Knob { label: "Espacio vocal"; value: root.mixer.spaceKnob
                   tip: "Profundidad de la reverb y el eco compartidos de las voces"
                   onMoved: function (v) { root.mixer.spaceKnob = v } }
            Text {
                anchors.verticalCenter: parent.verticalCenter; textFormat: Text.StyledText
                text: "<b>" + root.mixer.stepDb().toFixed(1) + " dB</b> bajo la voz principal<br>profundidad <b>" + Math.round(root.mixer.spaceKnob) + "</b>"
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
            }
        }
        Text {
            visible: !root.mixer.items.length
            width: root.availableWidth; wrapMode: Text.Wrap
            text: "No hay audios en la mezcla: importa audio en una pista (Archivo › Importar) y vuelve aquí."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
        }
        Row {
            spacing: 8
            NeoButton { objectName: "mixAutoRun"; text: root.mixer.busy ? "Mezclando…" : "Mezclar"; enabled: root.can
                        tip: "Mezcla automática de todas las pistas de audio"
                        onClicked: root.run(false) }
            NeoButton { text: "Volver a mezclar"; enabled: root.can && root.mixer.runs > 0
                        tip: "Repite la mezcla automática con los ajustes de ahora"
                        onClicked: root.run(true) }
            NeoButton { text: "Cerrar"; tip: "Esc"; onClicked: root.close() }
        }
    }
}
