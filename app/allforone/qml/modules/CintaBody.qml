import QtQuick
import "../theme"
import "../controls"
import "../state/layout.js" as L
import "../state/mixdata.js" as MD

// Grabador de cintas (Cinta RX-2). Graba el motor: Tracktion escribe el WAV desde la entrada del
// dispositivo de audio elegido en «⚙ Audio»; aquí solo se arma la pista, se manda grabar o parar y
// se lee el medidor de entrada real. La toma aparece como onda en Pistas y como tira en Mezcla.
Column {
    id: root
    property var seq
    property var studio
    readonly property var t: seq.active("voz")
    readonly property var rec: studio.rec
    readonly property bool go: seq.recording || studio.playing || studio.previewing
    width: parent ? parent.width : 380
    spacing: 0

    Rectangle {                                 // .reels
        width: root.width; height: 92 + 28 + 6
        color: Theme.screen; border.width: Theme.border; border.color: Theme.line
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.screenLine }
        Row {
            anchors.centerIn: parent
            spacing: 34
            Repeater {
                model: 2
                Canvas {                         // .reel: radios claros y oscuros alternos, buje central
                    width: 92; height: 92
                    onPaint: {
                        var ctx = getContext("2d"), c = 46, r = 42
                        ctx.reset()
                        var seg = [[0, .12, String(Theme.screen)], [.12, .33, String(Theme.inkDim)], [.33, .45, String(Theme.screen)], [.45, .66, String(Theme.inkDim)],
                                   [.66, .78, String(Theme.screen)], [.78, 1, String(Theme.inkDim)]]
                        for (var i = 0; i < seg.length; i++) {
                            ctx.beginPath(); ctx.moveTo(c, c)
                            ctx.arc(c, c, r, -Math.PI / 2 + seg[i][0] * 2 * Math.PI, -Math.PI / 2 + seg[i][1] * 2 * Math.PI)
                            ctx.closePath(); ctx.fillStyle = seg[i][2]; ctx.fill()
                        }
                        ctx.beginPath(); ctx.arc(c, c, r * .22, 0, 2 * Math.PI); ctx.fillStyle = String(Theme.ink); ctx.fill()
                        ctx.beginPath(); ctx.arc(c, c, r * .12, 0, 2 * Math.PI); ctx.fillStyle = String(Theme.line); ctx.fill()
                        ctx.beginPath(); ctx.arc(c, c, 44, 0, 2 * Math.PI); ctx.lineWidth = 4; ctx.strokeStyle = String(Theme.line); ctx.stroke()
                    }
                    RotationAnimation on rotation { from: 0; to: 360; duration: Math.round(120000 / Math.max(1, root.studio.bpm)); loops: Animation.Infinite; running: root.go }
                }
            }
        }
    }
    Item { width: 1; height: 10 }

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd {
            id: cnt
            anchors.verticalCenter: parent.verticalCenter
            text: L.fmt(root.seq.recording && root.rec ? root.rec.seconds : (root.t ? root.t.len : 0))
        }
        Text {
            width: root.width - cnt.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
            text: !root.t ? "Crea una pista de voz para grabar."
                  : root.seq.armedUid === root.t.uid ? "Pista armada: " + root.t.name
                  : root.t.name + ": sin entrada para armar"
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 500
        }
    }
    TrackTabs { seq: root.seq; type: "voz" }

    Row {                                       // entrada del dispositivo, escucha y configuración de audio
        width: root.width; spacing: 6; bottomPadding: 4
        Select {
            id: inSel
            width: root.width - mon.width - cfg.width - 12
            options: root.seq.inputs.length ? root.seq.inputs : [["", "Sin entradas en este dispositivo"]]
            current: root.seq.input
            fontSize: 12; padY: 5
            tip: "Entrada que graba la pista armada"
            onPicked: function (v) { if (v) root.seq.setInput(v) }
        }
        NeoButton {
            id: mon
            text: "Monitor"; fontSize: 12; padX: 8
            pressedState: root.seq.monitor
            color: root.seq.monitor ? Theme.pressedBg : Theme.button; textColor: root.seq.monitor ? Theme.pressedInk : Theme.ink
            tip: "Oír la entrada por la salida mientras está armada (con auriculares)"
            onClicked: root.seq.setMonitor(!root.seq.monitor)
        }
        NeoButton { id: cfg; text: "⚙ Audio"; fontSize: 12; padX: 8; tip: "Driver, dispositivo, frecuencia y búfer"
                    onClicked: root.studio.openAudioSettings() }
    }

    Rectangle {                                 // .tvu: nivel real de la entrada armada
        width: root.width; height: 12
        color: Theme.lcdBg; border.width: Theme.buttonBorder; border.color: Theme.line
        Rectangle {
            x: 2; y: 2; height: parent.height - 4
            width: (parent.width - 4) * Math.min(1, root.rec ? MD.dbToPct(root.rec.db) / 100 : 0)
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.meterOk }
                GradientStop { position: 0.7; color: Theme.meterOk }
                GradientStop { position: 0.85; color: Theme.meterWarn }
                GradientStop { position: 1.0; color: Theme.meterPeak }
            }
        }
    }
    Item { width: 1; height: 8 }

    // G3: grabar varias pistas a la vez, punch dentro del bucle y tomas de cada pasada
    Flow {
        id: armRow
        objectName: "armRow"
        width: root.width; spacing: 6; bottomPadding: visible ? 8 : 0
        readonly property var voz: root.studio.tracks.filter(function (x) { return x.type === "voz" })
        visible: voz.length > 1
        Text { text: "Grabar en:"; height: 28; verticalAlignment: Text.AlignVCenter
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        Repeater {
            model: armRow.voz
            NeoButton {
                required property var modelData
                objectName: "armTrack_" + modelData.uid
                readonly property bool on: root.seq.isArmed(modelData.uid)
                text: (on ? "● " : "") + modelData.name; fontSize: 12; padX: 8; padY: 4
                pressedState: on
                color: on ? Theme.rec : Theme.button; textColor: on ? Theme.inkOnColor : Theme.ink; hoverColor: on ? Theme.rec : Theme.pn2
                tip: modelData.uid === root.seq.armedUid ? "Pista activa: siempre graba (elige otra en las pestañas para cambiarla)"
                     : on ? "Clic: no grabar en " + modelData.name : "Grabar también en " + modelData.name + " en la misma pasada"
                onClicked: root.seq.armExtra(modelData.uid, !on)
            }
        }
    }
    Flow {
        width: root.width; spacing: 6; bottomPadding: 8
        NeoButton {
            objectName: "punchBtn"
            text: "Punch"; fontSize: 12; padX: 8; padY: 4
            pressedState: root.seq.punch
            color: root.seq.punch ? Theme.pressedBg : Theme.button; textColor: root.seq.punch ? Theme.pressedInk : Theme.ink
            tip: root.studio.loopSet ? "Graba solo entre " + L.fmt(root.studio.loop.start) + " y " + L.fmt(root.studio.loop.end)
                                       + " (el tramo del bucle, con el bucle apagado) y conserva lo de fuera. Con el bucle encendido (≥ 2 s) cada vuelta es una toma: se eligen en la cabecera de la pista"
                                     : "Graba solo dentro del tramo del bucle: márcalo arrastrando en la regla del Arreglo"
            onClicked: root.seq.setPunch(!root.seq.punch)
        }
    }

    Flow {                                      // .tbtn
        width: root.width; spacing: 6; bottomPadding: 10
        NeoButton {
            text: "● Grabar"; color: Theme.rec; textColor: Theme.inkOnColor; hoverColor: Theme.rec
            pressedState: root.seq.recording
            tip: "Graba la entrada en las pistas armadas desde la posición del cursor"
            onClicked: root.seq.startTake()
        }
        NeoButton { text: "■ Parar"; onClicked: root.seq.stopTake(false) }
        NeoButton { text: "▶ Escuchar toma"; onClicked: root.seq.listenTake() }
    }
    Text {                                      // .hint
        width: root.width; wrapMode: Text.Wrap
        text: root.seq.inputs.length
              ? "La toma la escribe el motor en un WAV, se ve como onda en Pistas y entra en Mezcla. Entrada: " + (root.rec ? root.rec.input : "—") + "."
              : "El dispositivo de audio actual no tiene entradas. Pulsa «Audio» (arriba o aquí) y elige uno que sí (ASIO4ALL, Windows Audio con micrófono…)."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 500
    }
    Component.onCompleted: seq.refreshInputs()
}
