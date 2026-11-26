import QtQuick
import "../theme"
import "../controls"

// Módulo Piano roll (Teclas S-61): edita el MIDI de la pista de instrumento activa y la toca.
Column {
    id: root
    property var seq
    readonly property var t: seq.active("inst")
    width: parent ? parent.width : 700
    spacing: 0

    function pad3(n) { return (n < 10 ? "00" : n < 100 ? "0" : "") + n }

    Column {                                    // sin pista de instrumento
        visible: !root.t
        width: root.width; spacing: 8
        DashedBox { width: root.width; strokeColor: Theme.ink; textColor: Theme.ink
                    text: "No hay pista de instrumento. El piano roll edita el MIDI de la pista activa." }
        NeoButton { text: "+ Pista de instrumento"; onClicked: root.seq.addTrack("inst") }
    }

    Item {                                      // .ytop
        visible: !!root.t
        width: root.width; height: visible ? ytop.height + 3 + 10 : 0
        Rectangle { x: 3; y: 3; width: ytop.width; height: ytop.height; color: Theme.shadowColor; visible: Theme.buttonShadow > 0 }
        Rectangle {
            id: ytop
            width: parent.width; height: Math.max(lcd.height, ybtn.height) + 22
            border.width: Theme.border; border.color: Theme.line
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.deviceHead }
                GradientStop { position: 1; color: Theme.device }
            }
            Rectangle {                         // .ylcd
                id: lcd
                x: 11; anchors.verticalCenter: parent.verticalCenter
                width: Math.max(190, lcdCol.width + 26); height: lcdCol.height + 18
                color: Theme.lcdBg; border.width: Theme.border; border.color: Theme.line
                Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line }
                Column {
                    id: lcdCol
                    x: 13; anchors.verticalCenter: parent.verticalCenter
                    Text { text: "MIDI de: " + (root.t ? root.t.name : ""); color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                    Text { text: root.t ? root.pad3(root.t.cfg.v + 1) + " " + root.seq.insts[root.t.cfg.v][0] : ""
                           color: Theme.lcd; font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                    Text { text: "Octava " + root.seq.oct + (root.seq.sus ? ", sostenido" : ""); color: Theme.lcdSoft
                           font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                }
            }
            Flow {                              // .ybtn
                id: ybtn
                x: lcd.x + lcd.width + 14; anchors.verticalCenter: parent.verticalCenter
                width: Math.min(300, parent.width - x - 11); spacing: 6
                NeoButton { text: "◀ Voz"; fontSize: 13; padX: 8; padY: 4; color: Theme.button
                            onClicked: root.seq.setVoice(root.t.cfg.v - 1) }
                NeoButton { text: "Voz ▶"; fontSize: 13; padX: 8; padY: 4; color: Theme.button
                            onClicked: root.seq.setVoice(root.t.cfg.v + 1) }
                NeoButton { text: "Octava −"; fontSize: 13; padX: 8; padY: 4; color: Theme.button
                            onClicked: root.seq.setOct(-1) }
                NeoButton { text: "Octava +"; fontSize: 13; padX: 8; padY: 4; color: Theme.button
                            onClicked: root.seq.setOct(1) }
                NeoButton { text: "Sostenido"; fontSize: 13; padX: 8; padY: 4; pressedState: root.seq.sus
                            color: root.seq.sus ? Theme.lcd : Theme.button
                            textColor: root.seq.sus ? Theme.inkOnAccent : Theme.ink
                            onClicked: root.seq.toggleSus() }
            }
        }
    }

    Rectangle {                                 // .roll: 44 px de teclas + 16 pasos
        visible: !!root.t
        width: Math.max(root.width, 480); height: visible ? 13 * 20 + 6 : 0
        color: Theme.screen; border.width: Theme.border; border.color: Theme.line
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.screenLine; z: 3 }
        Column {
            x: 3; y: 3
            Repeater {
                model: root.seq.notes
                Row {
                    id: noteRow
                    required property string modelData
                    required property int index
                    Rectangle {                 // .k
                        width: 44; height: 20
                        color: noteRow.modelData.indexOf("#") >= 0 ? Qt.rgba(0, 0, 0, 0.4) : "transparent"
                        Rectangle { y: 19; width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.12) }
                        Text { x: 4; anchors.verticalCenter: parent.verticalCenter; text: noteRow.modelData
                               color: Theme.screenDim; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                    }
                    Repeater {
                        model: 16
                        Rectangle {             // .cell
                            id: cell
                            required property int index
                            readonly property bool on: !!root.t && !!root.t.roll[noteRow.index + "-" + index]
                            width: (Math.max(root.width, 480) - 6 - 44) / 16; height: 20
                            color: on ? Theme.accent : (cm.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : "transparent")
                            border.width: on ? 2 : 0; border.color: Theme.line
                            Rectangle { width: 1; height: parent.height; color: cell.index === 0 ? Qt.rgba(1, 1, 1, 0.4) : Qt.rgba(1, 1, 1, 0.1); visible: !cell.on }
                            Rectangle { y: 19; width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.1); visible: !cell.on }
                            MouseArea { id: cm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: root.seq.toggleRoll(noteRow.index, cell.index) }
                        }
                    }
                }
            }
        }
    }

    Item {                                      // .kb: 2 octavas desde la octava elegida
        id: kb
        visible: !!root.t
        width: root.width; height: visible ? 130 + 12 : 0
        readonly property var whiteSemis: [0, 2, 4, 5, 7, 9, 11]
        readonly property var whiteNames: ["C", "D", "E", "F", "G", "A", "B"]
        Rectangle {
            y: 12; width: parent.width; height: 130
            color: Theme.line; border.width: Theme.border; border.color: Theme.line
            Row {
                x: 3; y: 3
                Repeater {
                    model: 14
                    Rectangle {                 // .wk
                        id: wk
                        required property int index
                        readonly property int oct: root.seq.oct + Math.floor(index / 7)
                        readonly property int note: 12 * (oct + 1) + kb.whiteSemis[index % 7]
                        width: (kb.width - 6) / 14; height: 124
                        radius: 4
                        border.width: 1; border.color: Theme.line
                        gradient: Gradient {
                            GradientStop { position: 0; color: wm.pressed ? Theme.accent : Theme.keyWhite }
                            GradientStop { position: 1; color: wm.pressed ? Theme.accent : Theme.keyWhite2 }
                        }
                        Rectangle { width: parent.width; height: 6; color: wm.pressed ? Theme.accent : Theme.keyWhite; border.width: 1; border.color: Theme.line }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 2
                               text: wk.index % 7 ? "" : "C" + wk.oct; color: Theme.keyLabel; font.family: Theme.font; font.pixelSize: 11 }
                        MouseArea { id: wm; anchors.fill: parent
                                    onPressed: root.seq.previewMidi(root.t.cfg, wk.note, 0.6) }
                    }
                }
            }
            Repeater {                          // .bk
                model: 13
                Rectangle {
                    id: bk
                    required property int index
                    readonly property int m: index % 7
                    readonly property int note: 12 * (root.seq.oct + 1 + Math.floor(index / 7)) + kb.whiteSemis[m] + 1
                    visible: m !== 2 && m !== 6
                    x: 3 + (kb.width - 6) * ((index + 1) / 14 - 0.022); y: 3
                    width: (kb.width - 6) * 0.044; height: 124 * 0.62
                    radius: 3
                    color: bm.pressed ? Theme.keyBlackDown : Theme.keyBlack; border.width: 1; border.color: Theme.line
                    MouseArea { id: bm; anchors.fill: parent; onPressed: root.seq.previewMidi(root.t.cfg, bk.note, 0.6) }
                }
            }
        }
    }
    Item { width: 1; height: root.t ? 10 : 0 }
    NeoButton { visible: !!root.t; text: "Borrar notas"; onClicked: root.seq.clearRoll() }
}
