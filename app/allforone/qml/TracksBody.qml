import QtQuick
import "layout.js" as L
import "mixdata.js" as MD

// Módulo Pistas: las pistas reales del motor (audio importado y tono de prueba), con su forma
// de onda leída del archivo, M / S / ✕ y el cursor de reproducción del motor.
Column {
    id: root
    property var tracks: []              // [{id, name, len, peaks, note, mute, solo, vol, pan}]
    property var mixer                      // fichas del mezclador: tipo y rol de voz de cada pista
    property int selected: -1
    property real headPos: 0             // 0..1 dentro de los 16 compases del carril
    property real bar16: 40              // segundos que ocupa el 100 % del carril
    signal addAudio()
    signal addTone()
    signal notYet(string what)
    signal toggleMute(int i)
    signal toggleSolo(int i)
    signal removeTrack(int i)
    signal selectTrack(int i)
    width: parent ? parent.width : 600
    spacing: 0

    readonly property color laneColor: Theme.pc.pistas

    Flow {                                // .tb
        width: root.width
        spacing: 6
        bottomPadding: 10 + 3
        NeoButton { text: "+ Audio"; tip: "Importar WAV/AIFF/FLAC al motor nativo"; onClicked: root.addAudio() }
        NeoButton { text: "+ Tono de prueba"; tip: "Señal sintética de 440 Hz para comprobar el motor"; onClicked: root.addTone() }
        Repeater {
            model: ["Instrumento", "Batería", "IA", "Voz"]
            NeoButton {
                text: "+ " + modelData
                tip: "Llega en la fase 3/4 de la interfaz nativa"
                onClicked: root.notYet(modelData)
            }
        }
    }

    Rectangle {                           // .scroll
        id: scroll
        width: root.width
        height: content.height + 6
        color: "#16130e"
        border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
        Flickable {
            id: hflick
            x: 3; y: 3
            width: parent.width - 6
            height: content.height
            contentWidth: Math.max(width, 170 + 560)
            contentHeight: height
            flickableDirection: Flickable.HorizontalFlick
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentWidth > width
            clip: true
            Column {
                id: content
                width: hflick.contentWidth
                Repeater {
                    model: root.tracks
                    delegate: Item {
                        id: row
                        required property var modelData
                        required property int index
                        width: content.width
                        height: Math.max(64, th.implicitHeight) + 2
                        opacity: 1
                        // .th
                        Rectangle {
                            id: th
                            width: 170; height: row.height - 2
                            implicitHeight: thCol.implicitHeight + 12
                            color: row.index === root.selected ? "#51452e" : "#2b2720"
                            Rectangle { width: 8; height: parent.height; color: root.laneColor }
                            Rectangle { x: parent.width - 2; width: 2; height: parent.height; color: "#000" }
                            MouseArea { anchors.fill: parent; onClicked: root.selectTrack(row.index) }
                            Column {
                                id: thCol
                                x: 16; y: 6; width: 170 - 16 - 10
                                spacing: 3
                                Text { width: parent.width; text: row.modelData.name; elide: Text.ElideRight
                                       color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                                Text { width: parent.width; wrapMode: Text.Wrap
                                       text: "Audio: " + L.fmt(row.modelData.len) + " · motor nativo" + (row.modelData.note ? " · " + row.modelData.note : "")
                                       color: "#bdb398"; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
                                Row {
                                    spacing: 4
                                    NeoButton { text: "M"; fontSize: 12; padX: 6; padY: 0; shadow: 2; pressedState: row.modelData.mute
                                                color: row.modelData.mute ? Theme.accent : Theme.button
                                                textColor: row.modelData.mute ? "#000" : Theme.ink
                                                tip: "Silenciar"; onClicked: root.toggleMute(row.index) }
                                    NeoButton { text: "S"; fontSize: 12; padX: 6; padY: 0; shadow: 2; pressedState: row.modelData.solo
                                                color: row.modelData.solo ? Theme.accent : Theme.button
                                                textColor: row.modelData.solo ? "#000" : Theme.ink
                                                tip: "Solo"; onClicked: root.toggleSolo(row.index) }
                                    NeoButton { text: "✕"; fontSize: 12; padX: 6; padY: 0; shadow: 2
                                                tip: "Quitar pista"; onClicked: root.removeTrack(row.index) }
                                }
                                Row {                       // .afo-trole: tipo y rol de voz
                                    id: trole
                                    readonly property var item: { root.mixer.items; return root.mixer.itemOfTrack(row.modelData.id) }
                                    visible: !!item
                                    width: parent.width; spacing: 4; topPadding: 2
                                    Rectangle {
                                        width: parent.width - 58 - 4; height: 14; anchors.verticalCenter: parent.verticalCenter
                                        color: MD.kindColor(trole.item ? trole.item.kind : ""); border.width: 2; border.color: "#000"
                                        Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                               text: MD.kindShort(trole.item ? trole.item.kind : ""); color: "#000"
                                               font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                    }
                                    Select {
                                        width: 58; options: MD.ROLES; current: trole.item ? trole.item.role : "—"
                                        fontSize: 11; fontWeight: 700; padX: 2; padY: 1; centered: true
                                        fill: "#fff"; ink: "#000"; tip: MD.roleTip()
                                        onPicked: function (v) { root.mixer.setTrackRole(row.modelData.id, v) }
                                    }
                                }
                            }
                        }
                        // .lane
                        Item {
                            id: lane
                            x: 170; width: row.width - 170; height: row.height - 2
                            opacity: row.modelData.mute ? 0.3 : 1
                            Repeater {               // rejilla de 16 compases
                                model: 16
                                Rectangle { x: (index + 1) * lane.width / 16 - 1; width: 1; height: lane.height; color: Qt.rgba(1, 1, 1, 0.14) }
                            }
                            Rectangle {              // .clip
                                id: clipRect
                                readonly property real frac: Math.max(0.01, Math.min(1, row.modelData.len / root.bar16))
                                x: 0; y: 5; width: lane.width * frac; height: lane.height - 10
                                color: root.laneColor; border.width: 2; border.color: "#000"
                                Rectangle { x: 2; y: 2; z: -1; width: parent.width; height: parent.height; color: "#000" }
                            }
                            Canvas {                 // .wf: forma de onda real (picos del motor)
                                id: wave
                                x: 0; y: 0; width: clipRect.width; height: lane.height
                                property var peaks: row.modelData.peaks || []
                                onPeaksChanged: requestPaint()
                                onWidthChanged: requestPaint()
                                onPaint: {
                                    var ctx = getContext("2d"); ctx.reset()
                                    var p = peaks; if (!p.length) return
                                    var n = Math.max(1, Math.round(clipRect.frac * 100 * 3))
                                    var bw = Math.max(1, lane.width * 0.0026)
                                    ctx.fillStyle = "#000"
                                    for (var j = 0; j < n; j++) {
                                        var v = p[Math.floor(j / n * p.length)] || 0, h = 4 + v * 44
                                        ctx.fillRect(width * j / n, (height - h) / 2, bw, h)
                                    }
                                }
                            }
                        }
                        Rectangle { y: row.height - 2; width: row.width; height: 2; color: "#000" }
                    }
                }
                DashedBox {
                    visible: root.tracks.length === 0
                    x: 8; width: content.width - 16
                    height: visible ? implicitHeight : 0
                    strokeColor: "#f3e7c4"; textColor: "#f3e7c4"; fill: "transparent"
                    text: "Sin pistas. Agrega una arriba o arrastra archivos de audio a la ventana."
                }
                Item { width: 1; height: root.tracks.length === 0 ? 8 : 0 }
            }
            Rectangle {                     // .ph-line: cursor de reproducción
                visible: root.tracks.length > 0
                x: 170 + (content.width - 170) * root.headPos
                width: 3; height: content.height
                color: "#ffd34d"
                Behavior on x { NumberAnimation { duration: 150 } }
                Rectangle { anchors.centerIn: parent; width: 9; height: parent.height; color: "#ffd34d"; opacity: 0.25 }
            }
        }
    }

    Text {                                 // .hint
        width: root.width; topPadding: 8
        wrapMode: Text.Wrap
        text: "Cada pista se conecta con su módulo y guarda solo su configuración. Toca una pista para cargarla en el módulo."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
}
