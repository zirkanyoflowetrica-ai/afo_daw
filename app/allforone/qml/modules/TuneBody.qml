import QtQuick
import "../theme"
import "../controls"

// Módulo Afinador (PSOLA AT-1): tonalidad y BPM (analizar → confirmar), intensidad y voces a afinar.
// Con intensidad > 0 % tira un cable a la tira de cada voz marcada.
Column {
    id: root
    property var mixer
    readonly property var tn: mixer.tune
    readonly property var conf: tn.confirmed
    readonly property var strips: { mixer.items; mixer.studio.tracks; mixer.tune; return mixer.tunedStrips() }
    width: parent ? parent.width : 480
    spacing: 0

    function shortScale(s) { return String(s).replace("Menor natural", "m").replace("Mayor", "") }

    Rectangle {                                 // .afo-lcdbig
        width: root.width; height: 62
        color: "#120f0a"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#3a3020" }
        Column {
            x: 15; anchors.verticalCenter: parent.verticalCenter
            Text { text: root.conf ? "CONFIRMADO" : "SIN CONFIRMAR"; color: "#c98f00"
                   font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
            Text { text: (root.conf ? root.conf.key : root.tn.key) + " " + root.shortScale(root.conf ? root.conf.scale : root.tn.scale)
                   color: "#ffb000"; font.family: Theme.font; font.pixelSize: 24; font.weight: 700; font.letterSpacing: 1.44 }
        }
        Column {
            anchors.right: parent.right; anchors.rightMargin: 15; anchors.verticalCenter: parent.verticalCenter
            Text { anchors.right: parent.right; text: "BPM"; color: "#c98f00"; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
            Text { anchors.right: parent.right; text: (+(root.conf ? root.conf.bpm : root.tn.bpm)).toFixed(1)
                   color: "#ffb000"; font.family: Theme.font; font.pixelSize: 24; font.weight: 700; font.letterSpacing: 1.44 }
        }
    }
    Item { width: 1; height: 10 }

    Row {                                       // .tabs
        spacing: 6; bottomPadding: 10 + 2
        Repeater {
            model: ["Automático", "Asistido", "Manual"]
            NeoButton {
                required property string modelData
                text: modelData; fontSize: 12; padX: 8; padY: 2
                readonly property bool on: root.tn.mode === modelData
                color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                onClicked: root.mixer.setTuneParam("mode", modelData)
            }
        }
    }

    Row {                                       // .afo-row3
        width: root.width; spacing: 8; bottomPadding: 10
        readonly property real cw: (width - 16) / 3
        Column {
            width: parent.cw; spacing: 4
            Text { text: "Tónica"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.keys; current: root.tn.key
                     onPicked: function (v) { root.mixer.setTuneParam("key", v) } }
        }
        Column {
            width: parent.cw; spacing: 4
            Text { text: "Escala"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.scales; current: root.tn.scale
                     onPicked: function (v) { root.mixer.setTuneParam("scale", v) } }
        }
        Column {
            width: parent.cw; spacing: 4
            Text { text: "BPM"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Rectangle {                         // .afo-num
                width: parent.width; height: 34
                color: Theme.input; border.width: 2; border.color: "#000"
                TextInput {
                    x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter
                    text: String(root.tn.bpm); selectByMouse: true; color: Theme.ink
                    font.family: Theme.font; font.pixelSize: 13; font.weight: 500
                    validator: DoubleValidator { bottom: 0; top: 230; decimals: 1 }
                    onEditingFinished: { var v = parseFloat(text); if (v >= 50 && v <= 230) root.mixer.setTuneParam("bpm", v) }
                }
            }
        }
    }

    Row {                                       // .tb
        spacing: 6; bottomPadding: 10 + 3
        NeoButton { text: "Analizar música"; onClicked: root.mixer.analyze() }
        NeoButton { text: "✔ Confirmar"; onClicked: root.mixer.confirmTune() }
    }

    Note { width: root.width; text: root.tn.status }

    Item { width: 1; height: 10 }
    Knob {
        anchors.horizontalCenter: parent.horizontalCenter
        label: "Intensidad"; value: root.mixer.tuneStrength
        onMoved: function (v) { root.mixer.tuneStrength = v }
    }
    Text {
        width: root.width; topPadding: 8; horizontalAlignment: Text.AlignHCenter; textFormat: Text.StyledText
        text: "<b>" + Math.round(root.mixer.tuneStrength) + " %</b> · 0 % = sin afinación"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    Grid {                                      // .afo-toggles
        columns: 2; columnSpacing: 6; rowSpacing: 6
        topPadding: 10; bottomPadding: 10 + 3
        Repeater {
            model: [["lead", "Voz principal · P"], ["l", "Voces L · izquierda"], ["r", "Voces R · derecha"], ["b", "Dobles / coros / _B"]]
            NeoButton {
                id: tg
                required property var modelData
                readonly property bool on: !!root.tn.voices[modelData[0]]
                width: (root.width - 6) / 2
                text: modelData[1]; fontSize: 12; leftAlign: true
                color: on ? Theme.pc.afina : Theme.button; textColor: on ? "#000" : Theme.ink; pressedState: on
                onClicked: root.mixer.toggleVoice(modelData[0])
                Rectangle { width: 12; height: 12; border.width: 2; border.color: "#000"; color: tg.on ? "#000" : (Theme.dark ? "#1b1822" : "#fff") }
            }
        }
    }

    Rectangle {                                 // .afo-wires
        width: root.width; height: wires.height + 14 + 6
        color: "#16130e"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
        Flow {
            id: wires
            x: 11; y: 10; width: parent.width - 22; spacing: 5
            Text {
                width: parent.width; wrapMode: Text.Wrap; textFormat: Text.StyledText
                text: root.strips.length ? "<b>Conectado a " + root.strips.length + " tira(s) de la consola:</b>"
                    : (root.mixer.tuneStrength > 0 ? "<b>Sin tiras conectadas:</b> ninguna pista tiene todavía el rol de las voces marcadas arriba."
                                                   : "<b>Intensidad 0 %:</b> sube la intensidad y los cables llegarán a las tiras de esas voces.")
                color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
            }
            Repeater {
                model: root.strips
                Rectangle {
                    required property var modelData
                    width: Math.min(wires.width, wt.implicitWidth + 20); height: wt.implicitHeight + 6
                    color: "#2b2720"; border.width: 2; border.color: "#000"
                    Rectangle { x: 2; y: 2; width: 6; height: parent.height - 4; color: Theme.pc.afina }
                    Text { id: wt; x: 12; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                           text: parent.modelData.name + " · " + parent.modelData.role
                           color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                }
            }
        }
    }
    Item { width: 1; height: 10 }

    Rectangle {                                 // .afo-pitch: aún sin curva (lo dice)
        width: root.width; height: 70
        color: "#16130e"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
        Repeater { model: [14, 28, 42, 56]
                   Rectangle { required property real modelData; x: 3; y: 3 + (64 * modelData / 70); width: parent.width - 6; height: 1.5; color: Qt.rgba(1, 1, 1, 0.12) } }
        Text { x: 3 + 8 * (parent.width - 6) / 300; y: 3 + 40 * 64 / 70 - 11; text: "Curva de tono antes/después: pendiente (V0.6)"
               color: "#bdb398"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
    }
    Text {
        width: root.width; topPadding: 8 + 10; wrapMode: Text.Wrap
        text: "PSOLA por archivo separado. Puede omitir pistas si detecta riesgo de artefactos."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
}
