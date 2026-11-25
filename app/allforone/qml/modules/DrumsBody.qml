import QtQuick
import "../theme"
import "../controls"

// Módulo Batería (Ritmos R-16): drum pad de 8 golpes tocables (y grabables en el patrón) y secuenciador
// de 16 pasos; una sola caja de ritmos, cada pista guarda su patrón.
Column {
    id: root
    property var seq
    property int curStep: -1                     // paso que suena ahora (-1 = parado)
    readonly property var t: seq.active("drum")
    property var studio: seq ? seq.studio : null
    // carriles con golpe grabado (sampler del motor)
    readonly property var sampled: t && t.cfg.smp ? t.cfg.smp.map(function (p, i) { return p ? i : -1 }).filter(function (i) { return i >= 0 }) : []
    readonly property var groupColor: ["#ff4d3d", "#ff9b3d", "#ffe14d", "#fff4d6"]
    width: parent ? parent.width : 700
    spacing: 0

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: one; text: "1 instancia"; anchors.verticalCenter: parent.verticalCenter }
        Text { width: root.width - one.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
               text: "Una sola caja de ritmos. Cada pista guarda su patrón."
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 500 }
    }
    TrackTabs { seq: root.seq; type: "drum" }
    DashedBox { visible: !root.t; width: root.width; height: visible ? implicitHeight : 0
                text: "Crea una pista de batería para editar su patrón." }

    Item {                                      // .drtop
        visible: !!root.t
        width: root.width; height: visible ? Math.max(name.height, knobs.height) + 10 : 0
        Lcd { id: name; text: root.t ? root.t.name : ""; anchors.verticalCenter: knobs.verticalCenter }
        Row {
            id: knobs
            anchors.right: parent.right; spacing: 16
            Knob { label: "Volumen"; value: root.t ? root.t.cfg.vol : 80; onMoved: function (v) { root.seq.setCfg("drum", "vol", v) } }
            Knob { label: "Afinación"; value: root.t ? root.t.cfg.tun : 50; onMoved: function (v) { root.seq.setCfg("drum", "tun", v) } }
            Knob { label: "Swing"; value: root.t ? root.t.cfg.sw : 20; tip: "Retrasa las semicorcheas pares (100 % = media semicorchea)"
                   onMoved: function (v) { root.seq.setCfg("drum", "sw", v) } }
        }
    }

    // ---------------- drum pad: 8 pads tocables (teclas 1–8) ----------------
    property bool padRec: false                 // grabar los golpes en el patrón mientras suena
    property int flash: -1
    // Drum Synth: el último pad tocado se edita con sus propias perillas
    property int selLane: 0
    // [afinación, caída, tono, nivel, paneo, grupo de corte]: de fábrica 50, salvo el grupo (0 = ninguno)
    readonly property var laneDefault: [50, 50, 50, 50, 50, 0]
    function laneVal(i, k) {
        var l = root.t && root.t.cfg.lanes ? root.t.cfg.lanes[i] : null
        return l && l[k] !== undefined && l[k] !== null ? l[k] : laneDefault[k]
    }
    function setLane(k, v) { setLaneMany([[k, v]]) }
    function setLaneMany(pairs) {
        if (!root.t) return
        var all = []
        for (var i = 0; i < 8; ++i) {
            var row = []
            for (var k = 0; k < 6; ++k) row.push(laneVal(i, k))
            all.push(row)
        }
        pairs.forEach(function (p) { all[selLane][p[0]] = p[1] })
        root.seq.setCfg("drum", "lanes", all)
    }
    function padSample(i) { return root.t && root.t.cfg.smp && root.t.cfg.smp[i] ? root.t.cfg.smp[i] : "" }
    function setPadSample(path) {
        var paths = []
        for (var i = 0; i < 8; ++i) paths.push(i === selLane ? path : padSample(i))
        root.seq.setDrumSamples(paths, true)
    }
    function hit(i) {
        if (!root.t) return
        selLane = i
        root.seq.previewDrum(root.t.cfg, i)
        flash = i; flashTimer.restart()
        if (padRec && curStep >= 0 && !root.t.pat[i + "-" + curStep]) root.seq.toggleStep(i, curStep)
    }
    Timer { id: flashTimer; interval: 140; onTriggered: root.flash = -1 }
    Repeater {
        model: 8
        Item {
            required property int index
            Shortcut { sequence: String(index + 1); enabled: root.visible && !!root.t; onActivated: root.hit(index) }
        }
    }
    Item {
        visible: !!root.t
        width: root.width; height: visible ? padHead.height + pads.height + 14 : 0
        Row {
            id: padHead
            spacing: 8
            Text { text: "DRUM PAD"; color: Theme.ink; anchors.verticalCenter: parent.verticalCenter
                   font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.6 }
            NeoButton {
                text: (root.padRec ? "● " : "○ ") + "Grabar en el patrón"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                color: root.padRec ? "#ff4d3d" : Theme.button; textColor: root.padRec ? "#fff" : Theme.ink
                tip: "Con la canción sonando, cada golpe se escribe en el paso que suena"
                onClicked: root.padRec = !root.padRec
            }
            Text { text: "Teclas 1–8 o clic"; color: Theme.ink; opacity: 0.7; anchors.verticalCenter: parent.verticalCenter
                   font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
            NeoButton {                 // sampler (C10): golpes sueltos cortados en el Instrumental Lab
                visible: !!(root.studio && root.studio.lab && root.studio.lab.state && root.studio.lab.state.oneshots)
                text: "Golpes del laboratorio"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                tip: "Bombo, caja y platillo suenan con los golpes cortados de la batería elegida en el laboratorio"
                onClicked: root.studio.lab.hitsToPads()
            }
            NeoButton {
                visible: root.sampled.length > 0
                text: "Sonido sintetizado"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                tip: "Quita los golpes grabados: los 8 pads vuelven al sonido del sintetizador"
                onClicked: root.seq.setDrumSamples([], true)
            }
        }
        Grid {
            id: pads
            y: padHead.height + 8
            columns: 4; columnSpacing: 8; rowSpacing: 8
            readonly property real pw: (root.width - 3 * 8) / 4 - 3
            Repeater {
                model: root.seq.dn
                Item {
                    id: pad
                    required property string modelData
                    required property int index
                    readonly property bool lit: root.flash === index || pm.pressed
                    width: pads.pw; height: 54
                    Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000"; visible: Theme.buttonShadow > 0 && (!pad.lit) }
                    Rectangle {
                        x: pad.lit ? 3 : 0; y: pad.lit ? 3 : 0
                        width: parent.width; height: parent.height
                        color: pad.lit ? root.groupColor[pad.index % 4] : Theme.screenCard
                        border.width: Theme.buttonBorder; border.color: Theme.line
                        Rectangle { x: 4; y: 4; width: 8; height: 8; radius: 4; color: root.groupColor[pad.index % 4] }
                        Text { x: 18; y: 6; text: pad.modelData; color: pad.lit ? "#000" : Theme.screenInk
                               font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                        Text { x: 6; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                               visible: root.sampled.indexOf(pad.index) >= 0
                               text: "GOLPE GRABADO"; color: pad.lit ? "#000" : Theme.screenDim
                               font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 6; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                               text: String(pad.index + 1); color: pad.lit ? "#000" : Theme.screenDim
                               font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                    }
                    MouseArea { id: pm; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onPressed: root.hit(pad.index) }
                }
            }
        }
    }

    Row {                                       // Drum Synth: el pad elegido
        objectName: "drumLaneKnobs"
        visible: !!root.t
        height: visible ? implicitHeight : 0
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 16; bottomPadding: 10
        Column {
            anchors.verticalCenter: parent.verticalCenter; spacing: 2
            Text { text: "PAD " + (root.selLane + 1); color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 0.6 }
            Text { objectName: "drumLaneName"; text: root.seq.dn[root.selLane] || ""; color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
            NeoButton {
                text: "De fábrica"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                tip: "Vuelve a poner este pad como sale de fábrica (perillas a 50, centrado y sin grupo de corte)"
                onClicked: { root.setLaneMany([[0, 50], [1, 50], [2, 50], [3, 50], [4, 50], [5, 0]]); root.seq.previewDrum(root.t.cfg, root.selLane) }
            }
        }
        Column {                                // Drum Rack: golpe grabado del pad y grupo de corte
            anchors.verticalCenter: parent.verticalCenter; spacing: 4
            NeoButton {
                objectName: "padLoad"; text: root.padSample(root.selLane) ? "Cambiar golpe…" : "Cargar golpe…"
                fontSize: 11; padX: 6; padY: 2; shadow: 2
                tip: "Este pad suena con un golpe tuyo (WAV, AIFF, FLAC, OGG o MP3, hasta 10 s)"
                onClicked: {
                    var r = root.studio.call("pickPadSample", root.selLane)
                    if (r.ok) { root.setPadSample(r.path); root.studio.toast("Pad " + (root.selLane + 1) + ": " + r.name) }
                    else if (!r.cancelled && r.error) root.studio.toast(r.error)
                }
            }
            NeoButton {
                objectName: "padUnload"; visible: !!root.padSample(root.selLane)
                text: "Quitar golpe"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                tip: "Este pad vuelve al sonido sintetizado"
                onClicked: root.setPadSample("")
            }
            Select {
                objectName: "padChoke"; width: 132
                options: [["0", "Sin corte"], ["1", "Corte A"], ["2", "Corte B"]]
                current: String(Math.round(root.laneVal(root.selLane, 5)))
                tip: "Un golpe de un pad corta lo que suena en los otros pads de su grupo (p. ej. el hi-hat cerrado corta al abierto)"
                onPicked: function (v) { root.setLane(5, parseInt(v)) }
            }
        }
        Knob { objectName: "drumLaneTun"; label: "Afinación"; value: root.laneVal(root.selLane, 0)
               tip: "Afinación de este pad (±1 octava), además de la general"
               onMoved: function (v) { root.setLane(0, v) } }
        Knob { objectName: "drumLaneDec"; label: "Caída"; value: root.laneVal(root.selLane, 1)
               tip: "Lo que dura el golpe: de ¼ a 4 veces el de fábrica"
               onMoved: function (v) { root.setLane(1, v) } }
        Knob { objectName: "drumLaneTone"; label: "Tono"
               value: root.laneVal(root.selLane, 2)
               tip: root.selLane === 0 || root.selLane === 5 ? "Golpe de afinación al empezar (más = más clic)"
                    : root.selLane === 7 ? "Intervalo entre los dos tonos del cencerro" : "Filtro del ruido: más agudo o más grave"
               onMoved: function (v) { root.setLane(2, v) } }
        Knob { objectName: "drumLaneLvl"; label: "Nivel"; value: root.laneVal(root.selLane, 3)
               tip: "Volumen de este pad (0 = mudo, 50 = normal, 100 = +12 dB)"
               onMoved: function (v) { root.setLane(3, v) } }
        Knob { objectName: "drumLanePan"; label: "Paneo"; value: root.laneVal(root.selLane, 4)
               tip: "Dónde suena este pad: 0 a la izquierda, 50 en el centro, 100 a la derecha"
               onMoved: function (v) { root.setLane(4, v) } }
    }

    Rectangle {                                 // .seq
        visible: !!root.t
        width: root.width; height: visible ? seqCol.height + 16 + 6 : 0
        color: Theme.screen; border.width: Theme.border; border.color: Theme.line
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.screenLine }
        Column {
            id: seqCol
            x: 11; y: 11; width: parent.width - 22; spacing: 6
            Repeater {
                model: root.seq.dn
                Row {                           // .sr
                    id: lane
                    required property string modelData
                    required property int index
                    spacing: 8
                    NeoButton {                 // .dl: escuchar el golpe
                        width: 108; text: lane.modelData; fontSize: 12; padX: 6; padY: 3; leftAlign: true
                        color: Theme.screenCard; textColor: Theme.screenInk; hoverColor: Theme.screenHover
                        onClicked: if (root.t) root.seq.previewDrum(root.t.cfg, lane.index)
                    }
                    Grid {                      // .sc: 16 pasos
                        columns: 16; columnSpacing: 3
                        readonly property real cw: (seqCol.width - 108 - 8 - 15 * 3) / 16
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: 16
                            Rectangle {         // .st
                                id: st
                                required property int index
                                readonly property bool on: !!root.t && !!root.t.pat[lane.index + "-" + index]
                                width: parent.cw; height: 26
                                color: on ? root.groupColor[index >> 2] : (sm.containsMouse ? Theme.screenHover : Theme.screenHover)
                                border.width: Theme.buttonBorder; border.color: Theme.line
                                Rectangle {     // .st.cur
                                    visible: root.curStep === st.index
                                    anchors.fill: parent; anchors.margins: 4
                                    color: "transparent"; border.width: Theme.border; border.color: "#fff"
                                }
                                MouseArea { id: sm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: root.seq.toggleStep(lane.index, st.index) }
                            }
                        }
                    }
                }
            }
        }
    }
    Row {                                       // .drb
        visible: !!root.t
        spacing: 6; topPadding: 10
        NeoButton { text: "Borrar patrón"; onClicked: root.seq.clearPat() }
        NeoButton { text: "Patrón básico"; onClicked: root.seq.basicPat() }
    }
}
