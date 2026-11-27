import QtQuick
import "../theme"
import "../controls"

// Master IA (F6): con el canal Master en Efectos, un dispositivo más con el mismo marco que los otros.
// El motor mide la sesión en memoria y pone en el master una cadena real (EQ, compresión si hace falta,
// color y nivel final, cada efecto con la marca «IA») hasta el objetivo del preset. Cada resultado
// queda como versión (Inspector › Master). Su A/B está también en la tira MASTER del Mezclador.
Rectangle {
    id: root
    property var mixer
    width: parent ? parent.width : 600
    height: col.height + 20
    color: Theme.device; radius: Theme.radius; border.width: 1; border.color: Theme.deviceBorder
    readonly property var st: mixer ? mixer.masterStats : null

    Column {
        id: col
        x: 10; y: 10; width: parent.width - 20
        spacing: 8
        Row {
            spacing: 8
            Text { text: "Master IA"; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 15; font.weight: 700
                   anchors.verticalCenter: parent.verticalCenter }
            AiMark { anchors.verticalCenter: parent.verticalCenter; tip: "Cadena del master decidida por la IA midiendo la mezcla" }
        }
        Row {
            width: col.width; spacing: 8
            Select {
                objectName: "masterIaPreset"
                width: Math.min(260, col.width - 8 - go.width - ab.width - un.width - 24)
                options: root.mixer.masterNames.map(function (n, i) { return [String(i), n] })
                current: String(root.mixer.masterSel)
                tip: "Objetivo del master"
                onPicked: function (v) { root.mixer.masterSel = +v }
            }
            NeoButton {
                id: go
                objectName: "masterIaRun"
                text: root.mixer.mastering ? "Masterizando…" : "Masterizar"
                enabled: !root.mixer.mastering && !root.mixer.busy
                tip: "Mide la sesión en el motor y pone la cadena del master (queda como versión)"
                onClicked: root.mixer.masterAuto(root.mixer.masterSel)
            }
            NeoButton {
                id: ab
                text: root.mixer.masterAb === "A" ? "A/B: sin Master IA" : "A/B: con Master IA"
                enabled: !!root.st; pressedState: root.mixer.masterAb === "A"
                color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                tip: "Escuchar el master con o sin la cadena de Master IA"
                onClicked: root.mixer.bypassMaster(root.mixer.masterAb === "A" ? "B" : "A")
            }
            NeoButton {
                id: un
                text: "Quitar"; enabled: !!root.st; confirm: "¿Quitar?"
                tip: "Quita la cadena de Master IA del master (pide confirmación: pulsa otra vez)"
                onClicked: root.mixer.unmaster()
            }
        }
        Text {
            width: col.width; wrapMode: Text.Wrap
            text: root.st ? "Último: " + root.st.preset + " · entrada " + root.st.input_lufs.toFixed(1) + " → " + root.st.lufs_i.toFixed(1)
                            + " LUFS · pico " + root.st.max_peak_db.toFixed(1) + " dB" + (root.st.compressed ? " · con compresión" : "")
                          : "Objetivos: " + root.mixer.masterNames.join(" · ") + ". «Según referencia» usa la canción de referencia de la mezcla automática."
            color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
        }
    }
}
