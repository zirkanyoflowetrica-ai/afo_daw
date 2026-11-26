import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Vista Mezclador, la única consola: CANALES / MIXER con una tira por pista (cabecera de su color, rol
// de voz, inserts en orden de la señal, envíos a los buses Aux, paneo, fader con medidor estéreo del
// motor en dB de pico, LUFS o RMS, Solo y Mute) y la tira del master con sus inserts. Clic en el nombre
// de una tira = su rack en Efectos (el master es un canal más); doble clic en un insert lo abre ahí.
// Inserts y envíos se leen del motor (puente: dawLanes). La mezcla IA V4.2 está en el Inspector › Asistente IA.
Column {
    id: root
    property var studio
    property var mixer
    width: parent ? parent.width : 700
    spacing: 0

    // ---------------- inserts y envíos (del motor) ----------------
    property var lanes: ({})                    // id de pista (0 = master) → {inserts, sends}
    property var sends: ({})                    // id de pista → [{aux, db, pre}]
    readonly property var auxes: (studio ? studio.tracks : []).filter(function (t) { return t.type === "aux" && t.id >= 0 })
    readonly property int sendRows: Math.min(4, auxes.length)
    readonly property int sendsH: auxes.length ? 20 + sendRows * 28 : 0
    readonly property int sendCount: { var n = 0; for (var k in sends) n += (sends[k] || []).length; return n }
    readonly property int insertCount: { var n = 0; for (var k in lanes) n += (lanes[k].inserts || []).length; return n }
    readonly property int insertsH: 112
    function refresh() {
        if (!studio || !studio.engineOk) return
        var ids = studio.tracks.filter(function (t) { return t.id >= 0 }).map(function (t) { return t.id })
        ids.push(0)
        var r = studio.call("dawLanes", JSON.stringify(ids))
        if (!r.ok) return
        lanes = r.tracks
        var s = {}
        for (var k in r.tracks) s[k] = r.tracks[k].sends || []
        sends = s
    }
    function info(id) { return lanes[String(id)] || { inserts: [], sends: [] } }
    // Envío de una pista a un bus: −∞ (db <= −100) lo quita
    function sendOf(tid, auxId) {
        var a = sends[String(tid)] || []
        for (var i = 0; i < a.length; i++) if (a[i].aux === auxId) return a[i]
        return null
    }
    function setSend(tid, auxId, db, pre) {
        var r = studio.call("sendSet", tid, auxId, db, pre)
        if (!r.ok) { studio.toast(r.error); return }
        var c = Object.assign({}, sends); c[String(tid)] = r.sends; sends = c
        studio.dirty = true
    }
    // Posición 0..1 del nivel de envío ↔ dB (0 = apagado; resto de −48 a +6 dB)
    function sendDb(pos) { return pos <= 0.02 ? -100 : -48 + 54 * pos }
    function sendPos(db) { return db <= -99 ? 0 : Math.max(0.03, Math.min(1, (db + 48) / 54)) }
    function sendsTo(auxId) {
        var n = 0
        for (var k in sends) (sends[k] || []).forEach(function (e) { if (e.aux === auxId) n++ })
        return n
    }
    function addAux() {
        var t = studio.seq.addTrack("aux")
        if (t && t.id >= 0)
            studio.toast("Bus «" + t.name + "» creado: ponle una reverb o un eco (clic en el nombre de su tira) y súbele los envíos en las otras tiras")
        Qt.callLater(refresh)
        return t
    }
    function openInFx(id, library) {            // 0 = el master: en Efectos es un canal más
        studio.rackTrack = id
        studio.goTo("fx")
        if (library && studio.fxBody) studio.fxBody.libOpen = true
    }
    onVisibleChanged: if (visible) refresh()
    Component.onCompleted: refresh()
    Connections {
        target: root.studio
        function onFxRevChanged() { root.refresh() }
        function onTracksChanged() { Qt.callLater(root.refresh) }
        function onEngineOkChanged() { root.refresh() }
    }
    Timer { interval: 2000; repeat: true; running: root.visible && !!root.studio && root.studio.engineOk; onTriggered: root.refresh() }

    // La Mezcla IA vive en el Inspector › Asistente IA (X17)
    Row {
        spacing: 8; bottomPadding: 10
        Text { anchors.verticalCenter: parent.verticalCenter; text: "Mezcla IA y Master IA: en el Inspector › Asistente IA"
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        NeoButton { text: "Abrir"; fontSize: 12; padX: 8; padY: 2; shadow: 2; tip: "Muestra el Asistente IA en el Inspector"
                    onClicked: root.studio.goTo("asist") }
    }
    // ---------------- consola: CANALES / MIXER ----------------
    Rectangle {
        width: root.width
        height: console_.height + 6
        color: Theme.panelBody
        border.width: Theme.border; border.color: Theme.line
        Column {
            id: console_
            x: 3; y: 3; width: parent.width - 6
            Rectangle {                              // cabecera: título, canal en el rack y medidores
                width: parent.width; height: 40
                color: Theme.panelBody
                Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: "CANALES / MIXER"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 15; font.weight: 700; font.letterSpacing: 0.6 }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Chip {
                        objectName: "mixAddAux"
                        text: "+ AUX"; tip: "Nuevo bus Aux (reverb o eco compartidos): las pistas le mandan señal con sus envíos"
                        onClicked: if (root.studio.engineOk) root.addAux(); else root.studio.toast("Motor nativo no disponible")
                    }
                    Chip {
                        visible: !!root.rackName
                        text: root.rackName.toUpperCase(); fill: Theme.accent; ink: Theme.inkOnAccent
                        tip: "Canal cuyo rack se ve en Efectos (clic en el nombre de una tira para cambiarlo)"
                        onClicked: root.studio.goTo("fx")
                    }
                    Repeater {
                        model: [["dB", "Pico de muestra (dBFS)"], ["LUFS", "Sonoridad BS.1770 a corto plazo (3 s)"], ["RMS", "RMS de 300 ms (dBFS)"]]
                        Chip {
                            required property var modelData
                            text: modelData[0]; tip: "Medidores: " + modelData[1]
                            fill: root.studio.meterMode === modelData[0] ? Theme.pc.mezcla : Theme.button; ink: root.studio.meterMode === modelData[0] ? Theme.inkOnColor : Theme.ink
                            onClicked: root.studio.meterMode = modelData[0]
                        }
                    }
                }
                Rectangle { y: parent.height - 3; width: parent.width; height: 3; color: Theme.line }
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
                        readonly property bool racked: root.studio.rackTrack === 0
                        width: 112; height: stripH
                        Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: Theme.shadowColor; visible: Theme.buttonShadow > 0 }
                        Rectangle {
                            anchors.fill: parent
                            color: ms.racked ? Theme.pn2 : Theme.device
                            border.width: ms.racked ? 3 : Theme.buttonBorder; border.color: Theme.line
                            Rectangle {
                                x: 2; y: 2; width: parent.width - 4; height: 30; color: Theme.pc.mezcla
                                Text { anchors.centerIn: parent; text: "MASTER"; color: Theme.inkOnColor
                                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                                Rectangle { y: parent.height; width: parent.width; height: 2; color: Theme.line }
                                MouseArea { id: msMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: root.studio.rackTrack = 0 }
                                ToolTipLite { text: "Clic: ver el rack del master en Efectos"; show: msMouse.containsMouse }
                            }
                            Column {
                                x: 6; y: 38; width: parent.width - 12; spacing: 6
                                Inserts { tid: 0; name: "Master" }
                                Item { width: 1; height: root.sendsH }
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
                                       color: Theme.knobValue; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                            }
                        }
                    }
                }
            }
        }
    }
    DashedBox { visible: root.studio.tracks.length === 0; width: root.width; height: visible ? implicitHeight : 0; text: "Sin pistas." }

    readonly property real stripH: 384 + insertsH + sendsH
    readonly property string rackName: {
        if (root.studio.rackTrack === 0) return "Master"
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
        readonly property bool isAux: track.type === "aux"
        readonly property color cc: Theme.pc[root.studio.seqSrc(track.type)] || Theme.pc.pistas
        readonly property var lr: root.studio.trackLR(tid)
        width: 112; height: root.stripH
        Rectangle {                              // brillo de «trabajando» (mezcla automática)
            visible: strip.working
            anchors.fill: parent; anchors.margins: -5
            color: "transparent"; border.width: Theme.border; border.color: Theme.lcdSoft
            SequentialAnimation on opacity { running: strip.working; loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.45; duration: 700 } NumberAnimation { from: 0.45; to: 1; duration: 700 } }
        }
        Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: Theme.shadowColor; visible: Theme.buttonShadow > 0 }
        Rectangle {
            anchors.fill: parent
            color: strip.racked ? Theme.pn2 : Theme.device
            border.width: strip.racked ? 3 : 2; border.color: Theme.line
            Rectangle {                          // cabecera con el nombre
                x: 2; y: 2; width: parent.width - 4; height: 30; color: strip.cc
                Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter
                       horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                       text: strip.track.name.toUpperCase(); color: Theme.inkOnColor
                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                Rectangle { y: parent.height; width: parent.width; height: 2; color: Theme.line }
                MouseArea { id: rackMouse; anchors.fill: parent; hoverEnabled: true; enabled: strip.tid > 0; cursorShape: Qt.PointingHandCursor
                            onClicked: root.studio.rackTrack = strip.tid }
                ToolTipLite { text: "Clic: ver el rack de " + strip.track.name + " en Efectos"; show: rackMouse.containsMouse }
            }
            Column {
                x: 6; y: 38; width: parent.width - 12
                spacing: 5
                Item {                           // rol de voz (o DEMO para IA)
                    width: parent.width; height: 18
                    Rectangle {
                        visible: strip.track.type === "ia" && !(strip.track.aclips || []).length && !(strip.track.len > 0)
                        anchors.fill: parent; color: Theme.lcdBg
                        Text { anchors.centerIn: parent; text: "DEMO · sin audio"; color: Theme.lcd
                               font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                    }
                    Row {
                        visible: !!strip.item && strip.track.type !== "ia"
                        spacing: 3
                        Rectangle {
                            width: parent.parent.width - 44 - 3; height: 18
                            color: MD.kindColor(strip.item ? strip.item.kind : "", Theme.tracks); border.width: Theme.buttonBorder; border.color: Theme.line
                            Text { x: 3; width: parent.width - 6; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: MD.kindShort(strip.item ? strip.item.kind : ""); color: Theme.inkOnColor
                                   font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                        }
                        Select {
                            width: 44; options: MD.ROLES; current: strip.item ? strip.item.role : "—"
                            fontSize: 10; fontWeight: 700; padX: 2; padY: 0; centered: true
                            fill: Theme.input; ink: Theme.ink; tip: MD.roleTip()
                            onPicked: function (v) { root.mixer.setTrackRole(strip.tid, v) }
                        }
                    }
                }
                Inserts { tid: strip.tid; name: strip.track.name; enabled: strip.tid >= 0 }
                Sends { tid: strip.tid; name: strip.track.name; isAux: strip.isAux; visible: root.sendsH > 0 }
                Knob {
                    anchors.horizontalCenter: parent.horizontalCenter
                    label: "PAN"; value: strip.track.pan
                    tip: "Paneo " + strip.track.name
                    onMoved: function (v) { root.studio.setTrackMixUid(strip.track.uid, strip.track.vol, v) }
                    onReleased: root.studio.trackRelease(strip.track.uid)
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       text: MD.faderDbText(strip.track.vol); color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Row {
                    spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                    Fader { height: 150; value: strip.track.vol; tip: "Volumen " + strip.track.name
                            onMoved: function (v) { root.studio.setTrackMixUid(strip.track.uid, v, strip.track.pan) }
                            onReleased: root.studio.trackRelease(strip.track.uid) }
                    StereoMeter { height: 150; color2: strip.cc
                                  l: root.studio.playing ? MD.dbToPct(root.studio.meterMode === "dB" ? strip.lr[0] : root.studio.stripValue(strip.tid)) : 0
                                  r: root.studio.playing ? MD.dbToPct(root.studio.meterMode === "dB" ? strip.lr[1] : root.studio.stripValue(strip.tid)) : 0 }
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       readonly property real val: root.studio.stripValue(strip.tid)
                       text: (root.studio.playing && val > -99 ? val.toFixed(1) : "—") + " " + root.studio.meterMode
                              + (strip.live ? " · " + (strip.live.chain || []).length + " FX" + ((strip.live.automated || []).length ? " ∿" : "") : "")
                       color: Theme.knobValue; font.family: Theme.font; font.pixelSize: 11; font.weight: 700
                       HoverHandler { id: lh }
                       ToolTipLite { text: strip.live ? ((strip.live.chain || []).join(" → ") + "\n" + (strip.live.note || "")
                                                          + ((strip.live.automated || []).length ? "\n∿ Automatizado: " + strip.live.automated.join(", ") : "")).trim() : ""
                                     show: lh.hovered && text.length > 0 } }
                Row {
                    spacing: 6; anchors.horizontalCenter: parent.horizontalCenter
                    Chip { text: "S"; fill: strip.track.solo ? Theme.pc.mezcla : Theme.button; ink: strip.track.solo ? Theme.inkOnColor : Theme.ink; tip: "Solo"
                           onClicked: root.studio.toggleTrackFlag(strip.track.uid, "solo") }
                    Chip { text: "M"; fill: strip.track.mute ? Theme.pc.inst : Theme.button; ink: strip.track.mute ? Theme.inkOnColor : Theme.ink; tip: "Silenciar"
                           onClicked: root.studio.toggleTrackFlag(strip.track.uid, "mute") }
                }
            }
        }
    }
    // Inserts de una tira en orden de la señal (● encendido, tachado = puenteado, ∿ = automatizado).
    // Doble clic: abrirlo en Efectos; «+»: Efectos con la biblioteca para añadir uno.
    component Inserts: Item {
        id: ins
        property int tid: -1
        property string name: ""
        readonly property var list: root.info(tid).inserts || []
        width: parent ? parent.width : 100; height: root.insertsH
        Row {
            id: insHead
            width: parent.width; height: 24; spacing: 4
            Text { width: parent.width - addIns.width - 4; anchors.verticalCenter: parent.verticalCenter
                   text: "INSERTS" + (ins.list.length ? " · " + ins.list.length : ""); color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
            Chip { id: addIns; text: "+"; enabled: ins.enabled
                   tip: "Añadir un efecto a " + ins.name + " (abre Efectos con la biblioteca)"
                   onClicked: root.openInFx(ins.tid, true) }
        }
        Flickable {
            id: insF
            y: insHead.height + 2; width: parent.width; height: parent.height - y
            contentHeight: insCol.height; clip: true
            boundsBehavior: Flickable.StopAtBounds; flickableDirection: Flickable.VerticalFlick
            Column {
                id: insCol
                width: parent.width; spacing: 2
                Repeater {
                    model: ins.list
                    Rectangle {
                        required property var modelData
                        width: insCol.width; height: 24; radius: 3
                        color: modelData.enabled ? Theme.button : Theme.input
                        border.width: 1; border.color: Theme.line
                        Rectangle { x: 5; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4
                                    color: modelData.enabled ? Theme.meterOk : Theme.inkDim; border.width: 1; border.color: Theme.line }
                        Text { x: 17; width: parent.width - 21 - (aut.visible ? aut.width + 2 : 0); anchors.verticalCenter: parent.verticalCenter
                               elide: Text.ElideRight; text: modelData.label; color: Theme.ink
                               font.family: Theme.font; font.pixelSize: 11; font.weight: 600
                               font.strikeout: !modelData.enabled }
                        Text { id: aut; visible: modelData.automated > 0; anchors.right: parent.right; anchors.rightMargin: 4
                               anchors.verticalCenter: parent.verticalCenter; text: "∿"; color: Theme.ink
                               font.pixelSize: 13; font.weight: 800 }
                        MouseArea { id: ima; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onDoubleClicked: root.openInFx(ins.tid, false) }
                        ToolTipLite { show: ima.containsMouse
                                      text: modelData.label + (modelData.enabled ? "" : " (puenteado)")
                                            + (modelData.automated ? " · " + modelData.automated + " parámetro(s) automatizado(s)" : "")
                                            + (modelData.auto ? " · puesto por la mezcla automática" : "") + ". Doble clic: abrirlo en Efectos" }
                    }
                }
                Text { visible: ins.list.length === 0; width: insCol.width; wrapMode: Text.Wrap
                       text: "Sin inserts"; color: Theme.ink; opacity: 0.8
                       font.family: Theme.font; font.pixelSize: 11 }
            }
        }
        Text { visible: insF.contentHeight > insF.height + 1
               anchors.right: parent.right; anchors.bottom: parent.bottom
               text: "↓ más"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 700
               Rectangle { anchors.fill: parent; anchors.margins: -2; z: -1; color: Theme.device } }
    }
    // Envíos de una tira a los buses Aux (arrastrar = nivel, doble clic = apagado, PRE = antes del fader).
    // En un bus Aux, cuántos envíos recibe.
    component Sends: Item {
        id: sd
        property int tid: -1
        property string name: ""
        property bool isAux: false
        width: parent ? parent.width : 100; height: root.sendsH
        Text { y: 0; text: sd.isAux ? "RETORNO" : "ENVÍOS"; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
        Text { visible: sd.isAux; y: 18; width: parent.width; wrapMode: Text.Wrap
               text: { var n = root.sendsTo(sd.tid); return n ? "Recibe " + n + (n === 1 ? " envío" : " envíos") : "Sin envíos: súbelos en las otras tiras" }
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
        Flickable {
            visible: !sd.isAux
            y: 18; width: parent.width; height: parent.height - 18
            contentHeight: sendCol.height; clip: true
            boundsBehavior: Flickable.StopAtBounds; flickableDirection: Flickable.VerticalFlick
            Column {
                id: sendCol
                width: parent.width; spacing: 4
                Repeater {
                    model: root.auxes
                    Item {
                        id: sr
                        required property var modelData
                        readonly property var snd: root.sendOf(sd.tid, modelData.id)
                        readonly property real pos: snd ? root.sendPos(snd.db) : 0
                        readonly property bool pre: !!(snd && snd.pre)
                        width: sendCol.width; height: 24
                        Rectangle {                  // nivel del envío
                            width: parent.width - 36; height: 24; radius: 3
                            color: Theme.input; border.width: 1; border.color: Theme.line
                            Rectangle { x: 1; y: 1; height: parent.height - 2; radius: 2
                                        width: Math.max(0, (parent.width - 2) * sr.pos)
                                        color: Qt.tint(Theme.input, Qt.rgba(Qt.color(Theme.pc.fx).r, Qt.color(Theme.pc.fx).g, Qt.color(Theme.pc.fx).b, 0.55)) }
                            Text { x: 4; width: parent.width - 8 - sdb.width - 2; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: sr.modelData.name; color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                            Text { id: sdb; anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                                   text: sr.snd ? (sr.snd.db > 0.05 ? "+" : "") + sr.snd.db.toFixed(0) : "−∞"
                                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
                            MouseArea {
                                id: sma
                                anchors.fill: parent; hoverEnabled: true; preventStealing: true
                                function at(mx) { root.setSend(sd.tid, sr.modelData.id, root.sendDb(Math.max(0, Math.min(1, mx / width))), sr.pre) }
                                onPressed: function (m) { at(m.x) }
                                onPositionChanged: function (m) { if (pressed) at(m.x) }
                                onDoubleClicked: root.setSend(sd.tid, sr.modelData.id, -100, sr.pre)
                            }
                            ToolTipLite { show: sma.containsMouse && !sma.pressed
                                          text: "Envío de " + sd.name + " al bus «" + sr.modelData.name + "» ("
                                                + (sr.pre ? "pre-fader: no sigue al volumen de la pista" : "post-fader: sigue al volumen de la pista")
                                                + "). Arrastra para el nivel; doble clic lo apaga." }
                        }
                        Rectangle {                  // pre / post fader
                            x: parent.width - 32; width: 32; height: 24; radius: 3
                            color: sr.pre ? Theme.pressedBg : Theme.button
                            border.width: 1; border.color: Theme.line
                            Text { anchors.centerIn: parent; text: "PRE"; color: sr.pre ? Theme.pressedInk : Theme.ink
                                   font.family: Theme.font; font.pixelSize: 10; font.weight: 800 }
                            MouseArea { id: pma; anchors.fill: parent; hoverEnabled: true
                                        onClicked: root.setSend(sd.tid, sr.modelData.id, sr.snd ? sr.snd.db : -12, !sr.pre) }
                            ToolTipLite { show: pma.containsMouse
                                          text: sr.pre ? "Pre-fader (activo): el envío no depende del fader. Clic: post-fader"
                                                       : "Post-fader: el envío sigue al fader. Clic: pre-fader (para cascos o efectos que no deben bajar con la pista)" }
                        }
                    }
                }
            }
        }
    }
    // Medidor estéreo del color del canal (dos barras, -60..0 dBFS; la zona alta en ámbar y rojo)
    component StereoMeter: Rectangle {
        id: sm
        property real l: 0
        property real r: 0
        property color color2: Theme.pc.mezcla
        width: 22; height: 150
        color: Theme.lcdBg; border.width: Theme.buttonBorder; border.color: Theme.line
        Repeater {
            model: [sm.l, sm.r]
            Rectangle {
                required property real modelData
                required property int index
                x: 3 + index * 9; width: 7
                height: (sm.height - 6) * Math.max(0, Math.min(100, modelData)) / 100
                y: sm.height - 3 - height
                gradient: Gradient {
                    GradientStop { position: 0.0; color: modelData > 95 ? Theme.meterPeak : sm.color2 }
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
        property color fill: Theme.button
        property color ink: Theme.ink
        opacity: enabled ? 1 : 0.45
        signal clicked()
        width: Math.max(26, ct.implicitWidth + 16); height: 24
        color: fill; border.width: Theme.buttonBorder; border.color: Theme.line
        Text { id: ct; anchors.centerIn: parent; text: ch.text; color: ch.ink
               font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
        MouseArea { id: chm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: ch.clicked() }
        ToolTipLite { text: ch.tip; show: chm.containsMouse && ch.tip.length > 0 }
    }
}
