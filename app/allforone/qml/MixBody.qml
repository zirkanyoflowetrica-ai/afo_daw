import QtQuick
import "mixdata.js" as MD

// Módulo Mezcla (Consola 6C): una tira por pista con rol de voz, la decisión real del mezclador,
// paneo, fader y medidor del motor; debajo, la mezcla automática del V4.2.
Column {
    id: root
    property var studio
    property var mixer
    width: parent ? parent.width : 700
    spacing: 0

    Flickable {                                  // .strips (desplazamiento horizontal)
        width: root.width
        height: strips.height + 6 + 3
        contentWidth: strips.width + 3; contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentWidth > width
        clip: true
        onContentXChanged: root.studio.stripScroll = contentX     // los cables del Afinador siguen a las tiras
        Row {
            id: strips
            spacing: 8
            Repeater {
                model: root.studio.tracks
                Item {
                    id: strip
                    required property var modelData
                    required property int index
                    readonly property int tid: modelData.id
                    readonly property var item: { root.mixer.items; return root.mixer.itemOfTrack(tid) }
                    readonly property var live: root.mixer.live[tid]
                    readonly property bool working: root.mixer.workingTrack === tid
                    width: 84; height: col.height + 8 + 8 + 10
                    Rectangle {                  // contorno y brillo de «trabajando»
                        visible: strip.working
                        anchors.fill: parent; anchors.margins: -5
                        color: "transparent"; border.width: 3; border.color: "#ff9f45"
                        SequentialAnimation on opacity { running: strip.working; loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.45; duration: 700 } NumberAnimation { from: 0.45; to: 1; duration: 700 } }
                    }
                    Rectangle { x: 3; y: 3; width: 84; height: parent.height; color: "#000" }
                    Rectangle {
                        width: 84; height: parent.height
                        color: Theme.dark ? "#26222e" : "#d9d2bd"
                        border.width: 2; border.color: "#000"
                        Rectangle { width: parent.width; height: 8; color: Theme.pc[root.studio.seqSrc(strip.modelData.type)] }
                        Column {
                            id: col
                            x: 10; y: 8 + 8; width: 64
                            spacing: 6
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                                   text: strip.modelData.name; color: Theme.ink
                                   font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                            Rectangle {                 // pista de IA: demostración sin audio
                                visible: strip.modelData.type === "ia"
                                width: parent.width; height: visible ? 14 : 0
                                color: "#000"
                                Text { anchors.centerIn: parent; text: "DEMO · sin audio"; color: "#ffb000"
                                       font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                            }
                            Column {                    // .afo-smeta
                                width: parent.width; spacing: 3
                                visible: !!strip.item
                                Rectangle {
                                    width: parent.width; height: 14
                                    color: MD.kindColor(strip.item ? strip.item.kind : ""); border.width: 2; border.color: "#000"
                                    Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                           text: MD.kindShort(strip.item ? strip.item.kind : ""); color: "#000"
                                           font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                }
                                Select {
                                    width: parent.width
                                    options: MD.ROLES; current: strip.item ? strip.item.role : "—"
                                    fontSize: 11; fontWeight: 700; padX: 2; padY: 1; centered: true
                                    fill: "#fff"; ink: "#000"; tip: MD.roleTip()
                                    onPicked: function (v) { root.mixer.setTrackRole(strip.tid, v) }
                                }
                                Rectangle {                 // .afo-slcd: ganancia y posición reales
                                    visible: !!strip.live
                                    width: parent.width; height: visible ? lc.height + 4 : 0
                                    color: "#120f0a"; border.width: 2; border.color: "#000"
                                    Column {
                                        id: lc; y: 2; width: parent.width
                                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                                               text: strip.live ? (strip.live.gain_db >= 0 ? "+" : "") + (+strip.live.gain_db).toFixed(1) : ""
                                               color: "#ffb000"; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                        Text { x: 2; width: parent.width - 4; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                                               text: strip.live ? strip.live.position || "" : ""
                                               color: "#c98f00"; font.family: Theme.font; font.pixelSize: 8; font.weight: 700 }
                                    }
                                    HoverHandler { id: lh }
                                    ToolTipLite { text: strip.live ? strip.live.note || "" : ""; show: lh.hovered && text.length > 0 }
                                }
                            }
                            Knob {
                                anchors.horizontalCenter: parent.horizontalCenter
                                label: "Pan"; value: strip.modelData.pan
                                onMoved: function (v) { root.studio.setTrackMixUid(strip.modelData.uid, strip.modelData.vol, v) }
                            }
                            Row {                       // .fad
                                spacing: 6; anchors.horizontalCenter: parent.horizontalCenter
                                Fader { value: strip.modelData.vol; tip: "Volumen " + strip.modelData.name
                                        onMoved: function (v) { root.studio.setTrackMixUid(strip.modelData.uid, v, strip.modelData.pan) } }
                                Meter { level: root.studio.playing ? MD.dbToPct(root.studio.trackLevel(strip.tid)) : 0 }
                            }
                            Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                                   text: Math.round(strip.modelData.vol); color: Theme.ink
                                   font.family: Theme.font; font.pixelSize: 14; font.weight: 500 }
                        }
                    }
                }
            }
        }
    }
    DashedBox { visible: root.studio.tracks.length === 0; width: root.width; height: visible ? implicitHeight : 0; text: "Sin pistas." }

    // ---------------- mezcla automática (.afo-sep …) ----------------
    Item { width: 1; height: 14 }
    Rectangle { width: root.width; height: 3; color: Theme.ink }
    Text { topPadding: 8; bottomPadding: 10; text: "MEZCLA AUTOMÁTICA · AUTO-MIX V4.2"
           color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.52 }
    Row {                                         // .afo-row2
        width: root.width; spacing: 8; bottomPadding: 10
        Column {
            width: (root.width - 8) / 2; spacing: 4
            Text { text: "Plantilla artística"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.data.profiles; current: root.mixer.profile
                     onPicked: function (v) { root.mixer.profile = v } }
        }
        Column {
            width: (root.width - 8) / 2; spacing: 4
            Text { text: "Uso en el motor"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.mixer.data.modes; current: root.mixer.mode
                     onPicked: function (v) { root.mixer.mode = v } }
        }
    }
    Row {                                         // .krow
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
        Knob { label: "Escalón L/R"; value: root.mixer.stepKnob; onMoved: function (v) { root.mixer.stepKnob = v } }
        Knob { label: "Espacio vocal"; value: root.mixer.spaceKnob; onMoved: function (v) { root.mixer.spaceKnob = v } }
    }
    Text {
        width: root.width; topPadding: 8; horizontalAlignment: Text.AlignHCenter; textFormat: Text.StyledText
        text: "<b>" + root.mixer.stepDb().toFixed(1) + " dB</b> bajo la voz principal · profundidad <b>" + Math.round(root.mixer.spaceKnob) + "</b>"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
    Row {                                         // .afo-big
        width: root.width; spacing: 8; topPadding: 10; bottomPadding: 10 + 4
        NeoButton {
            width: (root.width - 8) / 2; text: "MEZCLAR AUTOMÁTICAMENTE"
            fontSize: 15; fontWeight: 700; padY: 10; shadow: 4
            color: root.mixer.busy ? "#e0c0a0" : "#ff9f45"; textColor: "#000"
            onClicked: if (!root.mixer.busy) root.mixer.mix(false)
        }
        NeoButton {
            width: (root.width - 8) / 2; text: "↻ REMEZCLAR"
            fontSize: 15; fontWeight: 700; padY: 10; shadow: 4
            opacity: root.mixer.busy || !root.mixer.runs.length ? 0.5 : 1
            onClicked: if (!root.mixer.busy && root.mixer.runs.length) root.mixer.mix(true)
        }
    }
    Rectangle {                                   // .afo-prog
        width: root.width; height: 16
        color: "#120f0a"; border.width: 3; border.color: "#000"
        Item {
            x: 3; y: 3; height: 10; clip: true
            width: (parent.width - 6) * Math.max(0, Math.min(100, root.mixer.progress)) / 100
            Behavior on width { NumberAnimation { duration: 200 } }
            Row {
                Repeater {
                    model: Math.max(0, Math.ceil(root.width / 10))
                    Row { Rectangle { width: 8; height: 10; color: "#ffb000" } Rectangle { width: 2; height: 10; color: "#ff9f45" } }
                }
            }
        }
    }
    Text {                                        // .afo-status
        width: root.width; topPadding: 6; wrapMode: Text.Wrap
        text: root.mixer.status; color: Theme.ink
        font.family: Theme.font; font.pixelSize: 12; font.weight: 600
    }
    Column {                                      // .afo-hist
        width: root.width; spacing: 4; topPadding: 6
        Repeater {
            model: root.mixer.runs
            NeoButton {
                required property var modelData
                required property int index
                width: root.width - 2
                text: "#" + (index + 1) + " · " + modelData.label
                fontSize: 12; padX: 8; padY: 3; shadow: 2
                color: root.mixer.run === index ? "#ffb000" : "#2b2720"
                textColor: root.mixer.run === index ? "#000" : "#f3e7c4"
                hoverColor: color
                onClicked: root.mixer.run = index
            }
        }
    }
    Text {
        width: root.width; topPadding: 8; wrapMode: Text.Wrap; textFormat: Text.StyledText
        text: "Al mezclar, cada tira se enciende cuando le toca y acaba con el <b>nivel y el paneo reales</b> que decidió el mezclador. La EQ, la compresión y los efectos solo están en el audio renderizado (Master IA · Antes/Después)."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
}
