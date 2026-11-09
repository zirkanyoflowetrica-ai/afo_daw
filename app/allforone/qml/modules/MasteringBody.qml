import QtQuick
import "../theme"
import "../controls"

// Módulo Master IA (Master M-4): el master() del V4.2 EN VIVO. Al elegir un preset, el motor procesa
// la sesión en memoria, mide LUFS integrada y pico, y deja en el master una cadena real (entrada a
// −18 LUFS, EQ, compresión si hace falta, color y nivel final) con el techo del limitador del preset.
// Se ve y se ajusta en «Efectos master». Sonoridad del master en vivo: LUFS, RMS y pico.
Column {
    id: root
    property var mixer
    property var studio
    readonly property var st: mixer.masterStats
    readonly property var ml: studio.masterLoud            // [pico, RMS, LUFS M, LUFS S, LUFS I]
    property string ab: "B"
    width: parent ? parent.width : 400
    spacing: 0

    function f(v) { return v > -99 ? v.toFixed(1) : "—" }
    function bypassMaster(which) {
        var r = mixer.call("bypass", { bypass: which === "A", track: 0 })
        if (r.ok) { ab = which; studio.refreshRacks() } else mixer.fail(r)
    }

    Row {                                       // sonoridad del master en vivo (las 3 medidas)
        width: root.width; spacing: 6; bottomPadding: 10
        Repeater {
            model: [["LUFS", 3, "corto plazo"], ["RMS", 1, "300 ms"], ["PICO", 0, "dBFS"]]
            Column {
                required property var modelData
                width: (root.width - 12) / 3; spacing: 2
                Lcd { text: root.f(root.ml[modelData[1]]); fontSize: 16; width: parent.width }
                Text { text: modelData[0] + " · " + modelData[2]; width: parent.width; elide: Text.ElideRight; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
            }
        }
    }
    Text {
        width: root.width; bottomPadding: 10; wrapMode: Text.Wrap
        text: "Integrada desde que suena: " + root.f(root.ml[4]) + " LUFS · momentánea " + root.f(root.ml[2]) + " LUFS"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 600
    }

    Column {                                    // .afo-presets: un clic = masterizar en vivo
        width: root.width; spacing: 6; bottomPadding: 10
        Repeater {
            model: root.mixer.masterNames
            Item {
                id: pr
                required property string modelData
                required property int index
                readonly property bool on: !!root.st && root.mixer.masterSel === index
                width: root.width - 3; height: prCol.height + 12 + 4
                opacity: root.mixer.mastering ? 0.6 : 1
                Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000"; visible: !pm.pressed }
                Rectangle {
                    x: pm.pressed ? 3 : 0; y: pm.pressed ? 3 : 0
                    width: parent.width; height: parent.height
                    color: "#2b2720"; border.width: 2; border.color: "#000"
                    Rectangle {                      // piloto
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: 12; height: 12; radius: 6; border.width: 2; border.color: "#000"
                        color: pr.on ? "#ff4d3d" : "#4a1d1a"
                        Rectangle { anchors.centerIn: parent; width: 22; height: 22; radius: 11; color: "#ff4d3d"; opacity: 0.25; visible: pr.on; z: -1 }
                    }
                    Column {
                        id: prCol
                        x: 36; y: 6; width: parent.width - 36 - prLcd.width - 18
                        Text { width: parent.width; elide: Text.ElideRight; text: pr.modelData
                               color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                        Text { width: parent.width; elide: Text.ElideRight
                               text: pr.on ? root.st.lufs_i.toFixed(1) + " LUFS · pico " + root.st.max_peak_db.toFixed(1) + " dB · techo " + root.st.ceiling_db.toFixed(1) + " dB"
                                           : (pr.index === 4 ? "objetivo de la canción de referencia" : "clic: masterizar en vivo")
                               color: "#bdb398"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                    }
                    Lcd { id: prLcd; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                          text: pr.on ? root.st.lufs_i.toFixed(1) : "--.-"; fontSize: 12; padX: 6; padY: 1; spacing: 0.04 }
                }
                MouseArea { id: pm; anchors.fill: parent; enabled: !root.mixer.mastering && !root.mixer.busy; cursorShape: Qt.PointingHandCursor
                            onClicked: root.mixer.masterAuto(pr.index) }
            }
        }
    }

    Row {                                       // .afo-ab: puentear la cadena del master IA
        width: root.width; spacing: 6; bottomPadding: 8 + 3
        Repeater {
            model: [["A", "A · sin master IA"], ["B", "B · con master IA"]]
            NeoButton {
                required property var modelData
                readonly property bool on: root.ab === modelData[0]
                width: (root.width - 6) / 2 - 1; text: modelData[1]; fontWeight: 700
                color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                opacity: root.st ? 1 : 0.5
                onClicked: if (root.st) root.bypassMaster(modelData[0])
            }
        }
    }
    Flow {
        width: root.width; spacing: 6; bottomPadding: 8
        NeoButton { text: "Quitar master IA"; opacity: root.st ? 1 : 0.5; onClicked: if (root.st) root.mixer.unmaster() }
        NeoButton { text: "Exportar mezcla"; tip: "WAV con el master en vivo, solo cuando lo pides"; onClicked: root.studio.exportMix() }
    }
    Note {
        width: root.width
        text: root.st ? "Entrada " + (root.st.input_lufs).toFixed(1) + " LUFS → ganancia de entrada " + root.st.pre_gain_db.toFixed(1) +
                        " dB, nivel final " + root.st.final_gain_db.toFixed(1) + " dB (presupuesto de limitación " + root.st.limit_budget_db.toFixed(1) +
                        " dB)" + (root.st.compressed ? ", compresión de master" : "") + ". Objetivo " + root.st.target_lufs.toFixed(1) + " LUFS: " + root.st.note
                      : "Elige un preset: el motor mide la sesión (en memoria, sin archivos) y pone la cadena del master. Ábrela en «Efectos master»."
    }
}
