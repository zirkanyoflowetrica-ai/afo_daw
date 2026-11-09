import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Módulo Mezcla (Consola 6C): CANALES / MIXER con una tira por pista (cabecera de su color, rol de voz,
// paneo, dB del fader, fader con medidor estéreo del motor en dB de pico, LUFS o RMS, Solo y Mute) y la
// tira del master; clic en el nombre de una tira = su rack en Efectos. Debajo, la mezcla automática V4.2.
Column {
    id: root
    property var studio
    property var mixer
    width: parent ? parent.width : 700
    spacing: 0

    // ---------------- consola: CANALES / MIXER ----------------
    Rectangle {
        width: root.width
        height: console_.height + 6
        color: Theme.dark ? "#1b1822" : "#ffffff"
        border.width: 3; border.color: "#000"
        Column {
            id: console_
            x: 3; y: 3; width: parent.width - 6
            Rectangle {                              // cabecera: título, canal en el rack y medidores
                width: parent.width; height: 40
                color: Theme.dark ? "#1b1822" : "#ffffff"
                Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: "CANALES / MIXER"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 15; font.weight: 700; font.letterSpacing: 0.6 }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Chip {
                        visible: !!root.rackName
                        text: root.rackName.toUpperCase(); fill: "#ffc233"
                        tip: "Canal cuyo rack se ve en Efectos (clic en el nombre de una tira para cambiarlo)"
                        onClicked: root.studio.goTo("fx")
                    }
                    Repeater {
                        model: [["dB", "Pico de muestra (dBFS)"], ["LUFS", "Sonoridad BS.1770 a corto plazo (3 s)"], ["RMS", "RMS de 300 ms (dBFS)"]]
                        Chip {
                            required property var modelData
                            text: modelData[0]; tip: "Medidores: " + modelData[1]
                            fill: root.studio.meterMode === modelData[0] ? Theme.pc.mezcla : (Theme.dark ? "#2a2533" : "#ffffff")
                            onClicked: root.studio.meterMode = modelData[0]
                        }
                    }
                }
                Rectangle { y: parent.height - 3; width: parent.width; height: 3; color: "#000" }
            }
            Flickable {                              // tiras (desplazamiento horizontal)
                width: parent.width
                height: strips.height + 20
                contentWidth: strips.width + 20; contentHeight: height
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentWidth > width
                clip: true
                onContentXChanged: root.studio.stripScroll = contentX     // los cables del Afinador siguen a las tiras
                Row {
                    id: strips
                    x: 10; y: 10
                    spacing: 8
                    Repeater {
                        model: root.studio.tracks
                        Strip {
                            required property var modelData
                            required property int index
                            track: modelData
                        }
                    }
                    Item {                           // tira del master
                        id: ms
                        width: 96; height: stripH
                        Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000" }
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.dark ? "#26222e" : "#ffffff"; border.width: 2; border.color: "#000"
                            Rectangle {
                                x: 2; y: 2; width: parent.width - 4; height: 30; color: Theme.pc.mezcla
                                Text { anchors.centerIn: parent; text: "MASTER"; color: "#000"
                                       font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                                Rectangle { y: parent.height; width: parent.width; height: 2; color: "#000" }
                            }
                            Column {
                                x: 6; y: 40; width: parent.width - 12; spacing: 6
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "SALIDA"; color: Theme.ink
                                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700; topPadding: 22; bottomPadding: 22 }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                                       text: MD.faderDbText(root.studio.masterPos); color: Theme.ink
                                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                                Row {
                                    spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                                    Fader { height: 170; value: root.studio.masterPos; tip: "Volumen master (70 = 0 dB)"
                                            onMoved: function (v) { root.studio.setMaster(v) } }
                                    StereoMeter { height: 170; color2: Theme.pc.mezcla
                                                  l: root.studio.playing ? MD.dbToPct(root.studio.masterDb[0]) : 0
                                                  r: root.studio.playing ? MD.dbToPct(root.studio.masterDb[1]) : 0 }
                                }
                                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                                       readonly property real val: root.studio.meterMode === "dB" ? Math.max(root.studio.masterDb[0], root.studio.masterDb[1])
                                                                   : root.studio.meterMode === "RMS" ? root.studio.masterLoud[1] : root.studio.masterLoud[3]
                                       text: (root.studio.playing && val > -99 ? val.toFixed(1) : "—") + " " + root.studio.meterMode
                                       color: "#c98f00"; font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
                            }
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
            opacity: root.mixer.busy || !root.mixer.runs ? 0.5 : 1
            onClicked: if (!root.mixer.busy && root.mixer.runs) root.mixer.mix(true)
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
    Row {                                         // A/B y master automático
        spacing: 6; topPadding: 8
        NeoButton { text: "A · sin mezcla auto"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                    readonly property bool on: root.mixer.abState === "A"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    tip: "Puentea los efectos que puso la mezcla automática (faders y paneo se quedan)"
                    onClicked: root.mixer.bypass("A") }
        NeoButton { text: "B · con mezcla auto"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                    readonly property bool on: root.mixer.abState === "B"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    onClicked: root.mixer.bypass("B") }
        NeoButton { text: (root.mixer.autoMaster ? "☑" : "☐") + " masterizar al terminar"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                    tip: "Al terminar la mezcla, Master IA aplica en vivo el preset elegido"
                    onClicked: root.mixer.autoMaster = !root.mixer.autoMaster }
    }
    Text {
        width: root.width; topPadding: 8; wrapMode: Text.Wrap; textFormat: Text.StyledText
        text: "La mezcla es <b>en vivo</b>: el V4.2 analiza cada pista y deja su <b>fader, paneo y cadena de efectos reales</b> (EQ, de-esser, compresión, saturación, espacio, eco) en el motor. Ábrelos en Efectos y ajústalos; no se generan WAVs."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    readonly property real stripH: 372
    readonly property string rackName: {
        var t = root.studio.tracks
        for (var i = 0; i < t.length; i++) if (t[i].id === root.studio.rackTrack) return t[i].name
        return ""
    }

    // Tira de canal: cabecera de su color (clic = su rack en Efectos), rol, paneo, dB del fader,
    // fader con medidor estéreo de su color y Solo / Mute. La tira del rack se resalta.
    component Strip: Item {
        id: strip
        property var track
        readonly property int tid: track.id
        readonly property var item: { root.mixer.items; return root.mixer.itemOfTrack(tid) }
        readonly property var live: root.mixer.live[tid]
        readonly property bool working: root.mixer.workingTrack === tid
        readonly property bool racked: root.studio.rackTrack === tid && tid > 0
        readonly property color cc: Theme.pc[root.studio.seqSrc(track.type)] || Theme.pc.pistas
        readonly property var lr: root.studio.trackLR(tid)
        width: 96; height: root.stripH
        Rectangle {                              // brillo de «trabajando» (mezcla automática)
            visible: strip.working
            anchors.fill: parent; anchors.margins: -5
            color: "transparent"; border.width: 3; border.color: "#ff9f45"
            SequentialAnimation on opacity { running: strip.working; loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.45; duration: 700 } NumberAnimation { from: 0.45; to: 1; duration: 700 } }
        }
        Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000" }
        Rectangle {
            anchors.fill: parent
            color: strip.racked ? (Theme.dark ? "#4a3d1c" : "#ffe7a6") : (Theme.dark ? "#26222e" : "#ffffff")
            border.width: strip.racked ? 3 : 2; border.color: "#000"
            Rectangle {                          // cabecera con el nombre
                x: 2; y: 2; width: parent.width - 4; height: 30; color: strip.cc
                Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter
                       horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                       text: strip.track.name.toUpperCase(); color: "#000"
                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                Rectangle { y: parent.height; width: parent.width; height: 2; color: "#000" }
                MouseArea { anchors.fill: parent; enabled: strip.tid > 0; cursorShape: Qt.PointingHandCursor
                            onClicked: root.studio.rackTrack = strip.tid }
                ToolTipLite { text: "Clic: ver el rack de " + strip.track.name + " en Efectos"; show: false }
            }
            Column {
                x: 6; y: 38; width: parent.width - 12
                spacing: 5
                Item {                           // rol de voz (o DEMO para IA)
                    width: parent.width; height: 18
                    Rectangle {
                        visible: strip.track.type === "ia"
                        anchors.fill: parent; color: "#000"
                        Text { anchors.centerIn: parent; text: "DEMO · sin audio"; color: "#ffb000"
                               font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                    }
                    Row {
                        visible: !!strip.item && strip.track.type !== "ia"
                        spacing: 3
                        Rectangle {
                            width: parent.parent.width - 44 - 3; height: 18
                            color: MD.kindColor(strip.item ? strip.item.kind : ""); border.width: 2; border.color: "#000"
                            Text { x: 3; width: parent.width - 6; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: MD.kindShort(strip.item ? strip.item.kind : ""); color: "#000"
                                   font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                        }
                        Select {
                            width: 44; options: MD.ROLES; current: strip.item ? strip.item.role : "—"
                            fontSize: 10; fontWeight: 700; padX: 2; padY: 0; centered: true
                            fill: "#fff"; ink: "#000"; tip: MD.roleTip()
                            onPicked: function (v) { root.mixer.setTrackRole(strip.tid, v) }
                        }
                    }
                }
                Knob {
                    anchors.horizontalCenter: parent.horizontalCenter
                    label: "PAN"; value: strip.track.pan
                    tip: "Paneo " + strip.track.name
                    onMoved: function (v) { root.studio.setTrackMixUid(strip.track.uid, strip.track.vol, v) }
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       text: MD.faderDbText(strip.track.vol); color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Row {
                    spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                    Fader { height: 150; value: strip.track.vol; tip: "Volumen " + strip.track.name
                            onMoved: function (v) { root.studio.setTrackMixUid(strip.track.uid, v, strip.track.pan) } }
                    StereoMeter { height: 150; color2: strip.cc
                                  l: root.studio.playing ? MD.dbToPct(root.studio.meterMode === "dB" ? strip.lr[0] : root.studio.stripValue(strip.tid)) : 0
                                  r: root.studio.playing ? MD.dbToPct(root.studio.meterMode === "dB" ? strip.lr[1] : root.studio.stripValue(strip.tid)) : 0 }
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       readonly property real val: root.studio.stripValue(strip.tid)
                       text: (root.studio.playing && val > -99 ? val.toFixed(1) : "—") + " " + root.studio.meterMode
                              + (strip.live ? " · " + (strip.live.chain || []).length + " FX" : "")
                       color: "#c98f00"; font.family: Theme.font; font.pixelSize: 9; font.weight: 700
                       HoverHandler { id: lh }
                       ToolTipLite { text: strip.live ? ((strip.live.chain || []).join(" → ") + "\n" + (strip.live.note || "")).trim() : ""
                                     show: lh.hovered && text.length > 0 } }
                Row {
                    spacing: 6; anchors.horizontalCenter: parent.horizontalCenter
                    Chip { text: "S"; fill: strip.track.solo ? Theme.pc.mezcla : (Theme.dark ? "#2a2533" : "#ffffff"); tip: "Solo"
                           onClicked: root.studio.toggleTrackFlag(strip.track.uid, "solo") }
                    Chip { text: "M"; fill: strip.track.mute ? "#ff7a70" : (Theme.dark ? "#2a2533" : "#ffffff"); tip: "Silenciar"
                           onClicked: root.studio.toggleTrackFlag(strip.track.uid, "mute") }
                }
            }
        }
    }
    // Medidor estéreo del color del canal (dos barras, -60..0 dBFS; la zona alta en ámbar y rojo)
    component StereoMeter: Rectangle {
        id: sm
        property real l: 0
        property real r: 0
        property color color2: "#5ee0b0"
        width: 22; height: 150
        color: "#120f0a"; border.width: 2; border.color: "#000"
        Repeater {
            model: [sm.l, sm.r]
            Rectangle {
                required property real modelData
                required property int index
                x: 3 + index * 9; width: 7
                height: (sm.height - 6) * Math.max(0, Math.min(100, modelData)) / 100
                y: sm.height - 3 - height
                gradient: Gradient {
                    GradientStop { position: 0.0; color: modelData > 95 ? "#ff4d3d" : sm.color2 }
                    GradientStop { position: 0.12; color: sm.color2 }
                    GradientStop { position: 1.0; color: sm.color2 }
                }
            }
        }
    }
    component Chip: Rectangle {
        id: ch
        property string text
        property string tip
        property color fill: "#ffffff"
        signal clicked()
        width: Math.max(26, ct.implicitWidth + 16); height: 24
        color: fill; border.width: 2; border.color: "#000"
        Text { id: ct; anchors.centerIn: parent; text: ch.text; color: Qt.colorEqual(ch.fill, "#2a2533") ? "#efe9ff" : "#000"
               font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
        MouseArea { id: chm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ch.clicked() }
        ToolTipLite { text: ch.tip; show: chm.containsMouse && ch.tip.length > 0 }
    }
}
