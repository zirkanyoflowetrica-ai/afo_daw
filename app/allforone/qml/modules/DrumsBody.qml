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
    readonly property var groupColor: ["#ff4d3d", "#ff9b3d", "#ffe14d", "#fff4d6"]
    width: parent ? parent.width : 700
    spacing: 0

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: one; text: "1 instancia"; anchors.verticalCenter: parent.verticalCenter }
        Text { width: root.width - one.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
               text: "Una sola caja de ritmos. Cada pista guarda su patrón."
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
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
    function hit(i) {
        if (!root.t) return
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
                    Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000"; visible: !pad.lit }
                    Rectangle {
                        x: pad.lit ? 3 : 0; y: pad.lit ? 3 : 0
                        width: parent.width; height: parent.height
                        color: pad.lit ? root.groupColor[pad.index % 4] : "#2b2720"
                        border.width: 2; border.color: "#000"
                        Rectangle { x: 4; y: 4; width: 8; height: 8; radius: 4; color: root.groupColor[pad.index % 4] }
                        Text { x: 18; y: 6; text: pad.modelData; color: pad.lit ? "#000" : "#f3e7c4"
                               font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 6; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                               text: String(pad.index + 1); color: pad.lit ? "#000" : "#bdb398"
                               font.family: Theme.font; font.pixelSize: 16; font.weight: 700 }
                    }
                    MouseArea { id: pm; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onPressed: root.hit(pad.index) }
                }
            }
        }
    }

    Rectangle {                                 // .seq
        visible: !!root.t
        width: root.width; height: visible ? seqCol.height + 16 + 6 : 0
        color: "#16130e"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
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
                        color: "#2b2720"; textColor: "#f3e7c4"; hoverColor: "#3a352b"
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
                                color: on ? root.groupColor[index >> 2] : (sm.containsMouse ? "#4d463a" : "#3a352b")
                                border.width: 2; border.color: "#000"
                                Rectangle {     // .st.cur
                                    visible: root.curStep === st.index
                                    anchors.fill: parent; anchors.margins: 4
                                    color: "transparent"; border.width: 3; border.color: "#fff"
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
