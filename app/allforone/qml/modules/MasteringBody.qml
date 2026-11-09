import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Módulo Mastering (Master M-4): la mesa del master. VU, sonoridad en vivo (LUFS, RMS, pico), fader
// master con medidores L/R del motor, saturación, tono y limitador, y A/B de la cadena automática.
// Los efectos del master están en «Efectos master» (allí, abajo, Masterizar automáticamente); cada
// master se guarda como versión en «Rebobinado», donde se elige y se exporta.
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

    VuMeter { width: Math.min(root.width, 300); vu: root.studio.vu; anchors.horizontalCenter: parent.horizontalCenter }

    Row {                                       // sonoridad del master en vivo (las 3 medidas)
        width: root.width; spacing: 6; bottomPadding: 6
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
        width: root.width; bottomPadding: 12; wrapMode: Text.Wrap
        text: "Integrada desde que suena: " + root.f(root.ml[4]) + " LUFS · momentánea " + root.f(root.ml[2]) + " LUFS"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 600
    }

    Row {                                       // fader master, medidores y sección master del motor
        spacing: 18; bottomPadding: 12
        Row {
            spacing: 6
            Fader { height: 190; value: root.studio.masterPos; tip: "Volumen master (70 = 0 dB)"
                    onMoved: function (v) { root.studio.setMaster(v) } }
            Meter { width: 16; height: 190; level: root.studio.playing ? MD.dbToPct(root.studio.masterDb[0]) : 0 }
            Meter { width: 16; height: 190; level: root.studio.playing ? MD.dbToPct(root.studio.masterDb[1]) : 0 }
        }
        Column {
            spacing: 10
            Lcd { text: MD.faderDbText(root.studio.masterPos); fontSize: 18; width: Math.max(implicitWidth, 138) }
            Row {
                spacing: 16
                Knob { label: "Saturación"; value: root.studio.masterDrive; tip: "Saturación suave del master (tanh)"
                       onMoved: function (v) { root.studio.setMasterProcessing(v, root.studio.masterTone, root.studio.limiter) } }
                Knob { label: "Tono"; value: root.studio.masterTone; tip: "EQ inclinada: 50 = plano; ±6 dB en graves y agudos"
                       onMoved: function (v) { root.studio.setMasterProcessing(root.studio.masterDrive, v, root.studio.limiter) } }
            }
            NeoButton {
                text: "Limitador: " + (root.studio.limiter ? "activo" : "apagado")
                tip: "Limitador de seguridad del master: techo −1 dBFS, o el del master automático (también al exportar)"
                onClicked: root.studio.setMasterProcessing(root.studio.masterDrive, root.studio.masterTone, !root.studio.limiter)
            }
        }
    }

    Row {                                       // A/B: puentear la cadena del master automático
        width: root.width; spacing: 6; bottomPadding: 8 + 3
        Repeater {
            model: [["A", "A · sin master auto"], ["B", "B · con master auto"]]
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
        NeoButton { text: "Guardar versión → Rebobinado"; fontWeight: 700; color: "#7ad6ff"; textColor: "#000"
                    tip: "Guarda el master tal como suena ahora (efectos, fader, saturación, tono, limitador) como versión manual"
                    onClicked: root.mixer.saveVersion("", "manual", null) }
        NeoButton { text: "Quitar master auto"; opacity: root.st ? 1 : 0.5; onClicked: if (root.st) root.mixer.unmaster() }
    }
    Note {
        width: root.width
        text: root.st ? "Último master automático: entrada " + (root.st.input_lufs).toFixed(1) + " LUFS → " + root.st.lufs_i.toFixed(1) +
                        " LUFS, pico " + root.st.max_peak_db.toFixed(1) + " dB, techo " + root.st.ceiling_db.toFixed(1) + " dB" +
                        (root.st.compressed ? ", con compresión de master" : "") + ". " + root.st.note
                      : "Los efectos del master están en «Efectos master»; abajo de ese rack, «Masterizar automáticamente». Cada master queda en «Rebobinado» para elegirlo y exportarlo."
    }
}
