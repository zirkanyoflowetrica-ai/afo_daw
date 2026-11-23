import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Vista ARREGLO (como Studio One / Ableton): la canción entera de un vistazo. Arriba la regla de
// compases; por pista su cabecera (color, nombre, tipo, M/S, inserts) y sus clips con la forma de
// onda o las notas; debajo de cada pista sus carriles de automatización con la curva real que el
// motor reproduce y el valor que tiene ahora bajo el cursor. Abajo la consola: una tira por pista
// con sus inserts en orden, paneo, fader y medidor, y la del master. Todo sale del motor
// (puente: dawLanes); nada es decorativo.
Rectangle {
    id: root
    property var studio
    color: Theme.device

    property var lanes: ({})                  // id de pista (0 = master) → {inserts, lanes}
    property var closed: ({})                 // uid → carriles de automatización plegados
    property real pps: 8                      // píxeles por segundo
    property bool showConsole: true
    readonly property int headW: 260
    readonly property int rowH: 70
    readonly property int laneH: 58
    readonly property real beat: 60 / Math.max(40, studio ? studio.bpm : 96)
    readonly property var rows: {
        var t = studio ? studio.tracks : []
        return t.concat([{ uid: "master", id: 0, type: "master", name: "Master" }])
    }
    readonly property real songLen: {
        var m = 16 * 4 * beat
        ;(studio ? studio.tracks : []).forEach(function (t) {
            ;(t.aclips || []).forEach(function (c) { m = Math.max(m, c.start + c.length) })
            if (!(t.aclips || []).length && t.len) m = Math.max(m, (t.start || 0) + t.len)
            ;(t.midi || []).forEach(function (n) { m = Math.max(m, (n[0] + n[1]) * beat) })
        })
        for (var k in lanes) (lanes[k].lanes || []).forEach(function (l) {
            if (l.points.length) m = Math.max(m, l.points[l.points.length - 1][0])
        })
        return m + 2 * beat
    }
    readonly property int laneCount: { var n = 0; for (var k in lanes) n += (lanes[k].lanes || []).length; return n }
    readonly property int insertCount: { var n = 0; for (var k in lanes) n += (lanes[k].inserts || []).length; return n }
    // Buses Aux y envíos (pista → [{aux, db, pre}]); se leen del motor con los carriles
    property var sends: ({})
    readonly property var auxes: (studio ? studio.tracks : []).filter(function (t) { return t.type === "aux" && t.id >= 0 })
    readonly property int sendRows: Math.min(4, auxes.length)
    readonly property int sendsH: auxes.length ? 22 + sendRows * 28 : 0
    readonly property int sendCount: { var n = 0; for (var k in sends) n += (sends[k] || []).length; return n }

    function refresh() {
        if (!studio || !studio.engineOk || !visible) return
        var ids = studio.tracks.filter(function (t) { return t.id >= 0 }).map(function (t) { return t.id })
        ids.push(0)
        var r = studio.call("dawLanes", JSON.stringify(ids))
        if (!r.ok) return
        lanes = r.tracks
        var s = {}
        for (var k in r.tracks) s[k] = r.tracks[k].sends || []
        sends = s
    }
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
        if (t && t.id >= 0) {
            showConsole = true
            studio.toast("Bus «" + t.name + "» creado: ponle una reverb o un eco (doble clic en el nombre de su tira) y súbele los envíos en la consola")
        }
        return t
    }
    function info(id) { return lanes[String(id)] || { inserts: [], lanes: [] } }
    function colorOf(t) {
        if (t.type === "master") return Theme.pc.master
        if (t.type === "aux") return Theme.pc.fx || Theme.pc.pistas
        return Theme.pc[studio.seq.src[t.type]] || Theme.pc.pistas
    }
    function kindOf(t) {
        if (t.type === "master") return "Salida · " + info(0).inserts.length + " inserts"
        var it = t.id >= 0 ? studio.mixer.itemOfTrack(t.id) : null
        var s = it ? it.kind : (t.type === "audio" ? "Audio" : studio.seq.sub(t))
        return s
    }
    function isOpen(t) { return !closed[t.uid] }
    function toggleOpen(t) { var c = Object.assign({}, closed); c[t.uid] = !c[t.uid]; closed = c }
    function setAllOpen(b) {
        var c = {}
        if (!b) rows.forEach(function (t) { c[t.uid] = true })
        closed = c
    }
    // Valor de una curva en el segundo t (lineal entre puntos, como el motor)
    function valueAt(pts, t) {
        if (!pts.length) return 0
        if (t <= pts[0][0]) return pts[0][1]
        for (var i = 1; i < pts.length; i++)
            if (t < pts[i][0]) {
                var a = pts[i - 1], b = pts[i], f = (t - a[0]) / Math.max(1e-6, b[0] - a[0])
                return a[1] + (b[1] - a[1]) * f
            }
        return pts[pts.length - 1][1]
    }
    // 0..1 en el carril; los parámetros con «centro» (frecuencias) van en escala sesgada como sus perillas
    function norm(l, v) {
        var lo = l.min, hi = l.max, x = Math.max(0, Math.min(1, (v - lo) / Math.max(1e-9, hi - lo)))
        if (l.centre !== undefined && l.centre > lo && l.centre < hi) {
            var skew = Math.log(0.5) / Math.log((l.centre - lo) / (hi - lo))
            x = Math.pow(x, skew)
        }
        return x
    }
    function fmt(l, v) {
        var u = l.unit || ""
        if (u === "Hz") return v >= 1000 ? (v / 1000).toFixed(2) + " kHz" : Math.round(v) + " Hz"
        if (u === "dB") return (v > 0.05 ? "+" : "") + v.toFixed(1) + " dB"
        if (u === "%") return Math.round(v) + " %"
        if (u === "ms") return Math.round(v) + " ms"
        return (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2)) + (u ? " " + u : "")
    }
    function fmtTime(s) {
        var m = Math.floor(s / 60), r = s - 60 * m
        return m + ":" + (r < 10 ? "0" : "") + r.toFixed(1)
    }
    function seek(s) { if (studio.engineOk) studio.call("seek", Math.max(0, s)) }
    // Modos de automatización por pista (como Pro Tools): Read solo lee; Touch, Latch y Write graban
    readonly property var modes: ["read", "touch", "latch", "write"]
    readonly property var modeName: ({ read: "Read", touch: "Touch", latch: "Latch", write: "Write" })
    readonly property var modeHelp: ({
        read: "Read: la pista sigue sus curvas y mover sus controles no graba nada",
        touch: "Touch: mientras suena, graba lo que mueves mientras lo sujetas; al soltar vuelve a la curva",
        latch: "Latch: mientras suena, graba lo que mueves y mantiene el último valor hasta que paras",
        write: "Write: como Latch; al parar, la pista pasa sola a Touch para no borrar otra pasada" })
    function cycleMode(t) {
        var m = info(t.id).mode || "read"
        var next = modes[(modes.indexOf(m) + 1) % modes.length]
        var r = studio.call("autoMode", t.id, next)
        if (!r.ok) { studio.toast(r.error); return }
        studio.toast(t.name + " · " + modeHelp[r.mode])
        refresh()
    }
    // Inverso de norm: posición 0..1 en el carril → valor del parámetro
    function denorm(l, x) {
        x = Math.max(0, Math.min(1, x))
        var lo = l.min, hi = l.max
        if (l.centre !== undefined && l.centre !== null && l.centre > lo && l.centre < hi) {
            var skew = Math.log(0.5) / Math.log((l.centre - lo) / (hi - lo))
            x = Math.pow(x, 1 / skew)
        }
        return lo + x * (hi - lo)
    }
    // Guarda los puntos de un carril (efecto o fader / paneo de la pista); [] quita la curva
    function commitLane(l, pts) {
        pts = pts.slice().sort(function (a, b) { return a[0] - b[0] })
        var r = l.effect === 0 ? studio.call("trackAutoSet", l.track, l.param, JSON.stringify(pts))
                               : studio.call("fxSetAutomation", l.effect, l.param, JSON.stringify(pts))
        if (!r.ok) { studio.toast(r.error); return }
        studio.dirty = true
        refresh()
    }
    function fitAll() { pps = Math.max(2, Math.min(80, (flick.width - headW - 30) / Math.max(1, songLen))) }
    function openInFx(id) {
        studio.rackTrack = id
        studio.view = "modules"
        studio.goTo(id === 0 ? "fxm" : "fx")
    }

    onVisibleChanged: if (visible) { refresh(); if (pps === 8) Qt.callLater(fitAll) }
    Component.onCompleted: refresh()
    Connections {
        target: root.studio
        function onFxRevChanged() { root.refresh() }
        function onTracksChanged() { Qt.callLater(root.refresh) }
        function onEngineOkChanged() { root.refresh() }
        function onAutoRevChanged() { if (!pendingRefresh.running) pendingRefresh.start() }
        function onPlayingChanged() { if (!root.studio.playing) Qt.callLater(root.refresh) }
    }
    Timer { id: pendingRefresh; interval: 150; onTriggered: root.refresh() }   // redibuja lo que se va grabando
    Timer { interval: 2000; repeat: true; running: root.visible && !!root.studio && root.studio.engineOk; onTriggered: root.refresh() }

    // ---------------- barra de la vista ----------------
    Rectangle {
        id: bar
        width: parent.width; height: 48
        color: Theme.deviceHead
        Rectangle { y: parent.height - 2; width: parent.width; height: 2; color: Theme.deviceBorder }
        Row {
            x: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 10
            Text { text: "ARREGLO"; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 17; font.weight: 800
                   anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13; font.weight: 500
                text: root.studio.tracks.length + " pistas · " + root.insertCount + " inserts · "
                      + (root.auxes.length ? root.auxes.length + " Aux · " + root.sendCount + " envíos · " : "")
                      + root.laneCount + " curvas de automatización · " + root.fmtTime(root.songLen)
            }
        }
        Row {
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 6
            NeoButton { text: "+ Aux"; tip: "Nuevo bus Aux (reverb o eco compartidos): las pistas le mandan señal con sus envíos"
                        enabled: root.studio.engineOk; onClicked: root.addAux() }
            NeoButton { text: "Curvas: todas"; tip: "Desplegar los carriles de automatización de todas las pistas"
                        onClicked: root.setAllOpen(true) }
            NeoButton { text: "ninguna"; tip: "Plegar todos los carriles de automatización"; onClicked: root.setAllOpen(false) }
            NeoButton { text: "−"; tip: "Alejar (menos segundos por pantalla)"; onClicked: root.pps = Math.max(1, root.pps / 1.4) }
            NeoButton { text: "+"; tip: "Acercar"; onClicked: root.pps = Math.min(120, root.pps * 1.4) }
            NeoButton { text: "Ajustar"; tip: "Ver la canción entera a lo ancho"; onClicked: root.fitAll() }
            NeoButton { text: "Consola"; pressedState: root.showConsole
                        color: root.showConsole ? Theme.pressedBg : Theme.button; textColor: root.showConsole ? Theme.pressedInk : Theme.ink
                        tip: "Mostrar u ocultar la consola (tiras con inserts, paneo, fader y medidores)"
                        onClicked: root.showConsole = !root.showConsole }
        }
    }

    // ---------------- regla de compases ----------------
    Rectangle {
        id: ruler
        y: bar.height; width: parent.width; height: 30
        color: Theme.deviceHead
        clip: true
        Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: "Compás · tiempo"; color: Theme.deviceInk
               font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
        Canvas {
            id: rulerCv
            x: root.headW; width: parent.width - root.headW; height: parent.height
            property real off: flick.contentX
            property real p: root.pps
            property color ink: Theme.deviceInk
            onOffChanged: requestPaint(); onPChanged: requestPaint(); onWidthChanged: requestPaint(); onInkChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                var bar = 4 * root.beat, pxBar = bar * p, every = Math.max(1, Math.ceil(46 / pxBar))
                ctx.fillStyle = ink; ctx.strokeStyle = ink; ctx.font = "600 11px '" + Theme.font + "'"
                for (var b = Math.floor(off / pxBar); b * pxBar - off < width; b++) {
                    var x = b * pxBar - off
                    if (b % every === 0) {
                        ctx.fillRect(x, 14, 1.5, 16)
                        ctx.fillText(String(b + 1), x + 4, 24)
                    } else ctx.fillRect(x, 24, 1, 6)
                }
                // segundos arriba
                var stepS = [1, 2, 5, 10, 15, 30, 60].filter(function (s) { return s * p >= 60 })[0] || 60
                ctx.font = "500 11px '" + Theme.font + "'"
                for (var s = Math.floor(off / p / stepS) * stepS; s * p - off < width; s += stepS)
                    ctx.fillText(root.fmtTime(s).replace(".0", ""), s * p - off + 3, 10)
            }
        }
        MouseArea { x: root.headW; width: parent.width - root.headW; height: parent.height
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function (m) { root.seek((m.x + flick.contentX) / root.pps) } }
        Rectangle { y: parent.height - 2; width: parent.width; height: 2; color: Theme.deviceBorder }
    }

    // ---------------- pistas y carriles ----------------
    Flickable {
        id: flick
        anchors { top: ruler.bottom; left: parent.left; right: parent.right; bottom: consoleBox.top }
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        contentWidth: root.headW + root.songLen * root.pps + 40
        contentHeight: col.height + 20
        WheelHandler {                              // Ctrl + rueda: zoom horizontal; Mayús + rueda: desplazar
            acceptedModifiers: Qt.ControlModifier
            onWheel: function (e) { root.pps = Math.max(1, Math.min(120, root.pps * (e.angleDelta.y > 0 ? 1.2 : 1 / 1.2))) }
        }

        Column {
            id: col
            width: flick.contentWidth
            Repeater {
                model: root.rows
                Column {
                    id: trk
                    required property var modelData
                    required property int index
                    readonly property var t: modelData
                    readonly property var inf: root.info(t.id)
                    readonly property color c: root.colorOf(t)
                    readonly property bool master: t.type === "master"
                    width: col.width

                    // --- fila principal: cabecera + clips ---
                    Item {
                        width: parent.width; height: trk.master ? 52 : root.rowH
                        Rectangle {                     // carril (fondo con compases)
                            x: root.headW; width: parent.width - root.headW; height: parent.height
                            color: trk.index % 2 ? Theme.device : Qt.darker(Theme.device, Theme.dark ? 0.9 : 1.03)
                            Rectangle { y: parent.height - 1; width: parent.width; height: 1; color: Theme.deviceBorder; opacity: 0.4 }
                            Repeater {
                                model: Math.ceil(root.songLen / (4 * root.beat))
                                Rectangle { x: index * 4 * root.beat * root.pps; width: 1; height: parent.height
                                            color: Theme.deviceInk; opacity: index % 4 ? 0.08 : 0.2 }
                            }
                            MouseArea { anchors.fill: parent; onClicked: function (m) { root.seek(m.x / root.pps) } }
                            // clips de audio con su forma de onda
                            Repeater {
                                model: trk.t.aclips || []
                                Rectangle {
                                    required property var modelData
                                    readonly property var cl: modelData
                                    x: cl.start * root.pps; y: 4; width: Math.max(3, cl.length * root.pps); height: parent.height - 8
                                    color: Qt.darker(trk.c, trk.t.mute ? 2.2 : 1.0); border.width: Theme.buttonBorder; border.color: Theme.line; radius: 3
                                    clip: true
                                    Text { x: 5; y: 2; width: parent.width - 10; elide: Text.ElideRight; text: trk.t.name
                                           color: "#000"; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                    Canvas {
                                        y: 16; width: parent.width; height: parent.height - 18
                                        property var peaks: trk.t.peaks || []
                                        property var cv: parent.cl
                                        onPeaksChanged: requestPaint(); onCvChanged: requestPaint(); onWidthChanged: requestPaint()
                                        onPaint: {
                                            var ctx = getContext("2d"); ctx.reset()
                                            var p = peaks, c = cv, src = Math.max(0.01, c.source_length || trk.t.len || 1)
                                            var g = Math.pow(10, (c.gain_db || 0) / 20), n = Math.max(1, Math.floor(width / 2))
                                            ctx.fillStyle = "rgba(0,0,0,0.8)"
                                            for (var j = 0; j < n && p.length; j++) {
                                                var tt = c.length * j / n
                                                var v = (p[Math.min(p.length - 1, Math.floor((c.offset + tt) / src * p.length))] || 0) * g
                                                var h = Math.min(height - 2, 1 + v * (height - 4))
                                                ctx.fillRect(width * j / n, (height - h) / 2, 1.4, h)
                                            }
                                        }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: function (m) { root.seek(parent.cl.start + m.x / root.pps) } }
                                }
                            }
                            // notas MIDI (pistas de instrumento con notas de duración propia)
                            Rectangle {
                                visible: (trk.t.midi || []).length > 0
                                x: 0; y: 4; height: parent.height - 8
                                width: { var e = 0; (trk.t.midi || []).forEach(function (n) { e = Math.max(e, n[0] + n[1]) }); return e * root.beat * root.pps + 4 }
                                color: Qt.darker(trk.c, trk.t.mute ? 2.2 : 1.0); border.width: Theme.buttonBorder; border.color: Theme.line; radius: 3
                                clip: true
                                Canvas {
                                    anchors.fill: parent; anchors.margins: 3
                                    property var notes: trk.t.midi || []
                                    property real p: root.pps
                                    onNotesChanged: requestPaint(); onPChanged: requestPaint(); onWidthChanged: requestPaint()
                                    onPaint: {
                                        var ctx = getContext("2d"); ctx.reset()
                                        var lo = 127, hi = 0
                                        notes.forEach(function (n) { lo = Math.min(lo, n[2]); hi = Math.max(hi, n[2]) })
                                        var span = Math.max(12, hi - lo + 1), rh = Math.max(1.5, height / span)
                                        ctx.fillStyle = "rgba(0,0,0,0.85)"
                                        notes.forEach(function (n) {
                                            ctx.fillRect(n[0] * root.beat * p, height - (n[2] - lo + 1) * height / span,
                                                         Math.max(1.5, n[1] * root.beat * p - 1), rh)
                                        })
                                    }
                                }
                            }
                            // patrón de la rejilla de 16 pasos (Instrumento / Batería sin MIDI)
                            Rectangle {
                                visible: !trk.master && !(trk.t.aclips || []).length && !(trk.t.midi || []).length
                                         && (Object.keys(trk.t.roll || {}).length + Object.keys(trk.t.pat || {}).length) > 0
                                x: 0; y: 4; height: parent.height - 8; width: 16 * 4 * root.beat * root.pps
                                color: Qt.darker(trk.c, trk.t.mute ? 2.2 : 1.0); border.width: Theme.buttonBorder; border.color: Theme.line; radius: 3
                                Text { x: 6; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 12; elide: Text.ElideRight
                                       text: trk.t.name + " · patrón de 16 compases (se repite)"; color: "#000"
                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                            }
                            Text {
                                visible: trk.master
                                x: 10; anchors.verticalCenter: parent.verticalCenter
                                text: "Suma de todas las pistas → inserts del master → salida"
                                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12
                            }
                        }
                        // cabecera fija a la izquierda
                        Rectangle {
                            x: flick.contentX; z: 2
                            width: root.headW; height: parent.height
                            color: Theme.deviceHead
                            border.width: 1; border.color: Theme.deviceBorder
                            Rectangle { width: 8; height: parent.height; color: trk.c }
                            Column {
                                x: 16; y: 6; width: parent.width - 16 - btns.width - 10; spacing: 1
                                Text { width: parent.width; elide: Text.ElideRight; text: trk.t.name; color: Theme.deviceInk
                                       font.family: Theme.font; font.pixelSize: 14; font.weight: 800 }
                                Text { width: parent.width; elide: Text.ElideRight; text: root.kindOf(trk.t); color: Theme.deviceInk
                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                                Text {
                                    width: parent.width; elide: Text.ElideRight; visible: !trk.master || trk.inf.inserts.length
                                    color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 600
                                    text: trk.inf.inserts.length
                                          ? "FX: " + trk.inf.inserts.map(function (e) { return e.label }).join(" › ")
                                          : "FX: sin inserts"
                                }
                            }
                            Row {
                                id: btns
                                anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                                spacing: 4
                                NeoButton { visible: !trk.master; text: "M"; padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: !!trk.t.mute
                                            color: trk.t.mute ? Theme.pressedBg : Theme.button; textColor: trk.t.mute ? Theme.pressedInk : Theme.ink
                                            tip: "Silenciar esta pista"; onClicked: root.studio.toggleTrackFlag(trk.t.uid, "mute") }
                                NeoButton { visible: !trk.master; text: "S"; padX: 7; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: !!trk.t.solo
                                            color: trk.t.solo ? Theme.accent : Theme.button; textColor: trk.t.solo ? "#000" : Theme.ink
                                            tip: "Solo: escuchar solo esta pista (y las demás en solo)"; onClicked: root.studio.toggleTrackFlag(trk.t.uid, "solo") }
                                NeoButton { visible: !trk.master
                                            readonly property string m: trk.inf.mode || "read"
                                            text: m === "read" ? "R" : m === "touch" ? "T" : m === "latch" ? "L" : "W"
                                            padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: m !== "read"
                                            color: m === "read" ? Theme.button : m === "write" ? Theme.pressedBg : Theme.accent
                                            textColor: m === "read" ? Theme.ink : m === "write" ? Theme.pressedInk : "#000"
                                            tip: "Automatización: " + root.modeName[m] + ". " + root.modeHelp[m] + ". Clic: siguiente modo (Read → Touch → Latch → Write)"
                                            onClicked: root.cycleMode(trk.t) }
                                NeoButton { visible: trk.inf.lanes.length > 0
                                            text: (root.isOpen(trk.t) ? "▾ " : "▸ ") + "∿ " + trk.inf.lanes.length; padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            tip: "Mostrar u ocultar sus " + trk.inf.lanes.length + " curvas de automatización"
                                            onClicked: root.toggleOpen(trk.t) }
                            }
                        }
                    }

                    // --- carriles de automatización ---
                    Repeater {
                        model: root.isOpen(trk.t) ? trk.inf.lanes : []
                        Item {
                            id: ln
                            required property var modelData
                            readonly property var l: modelData
                            readonly property real now: root.valueAt(l.points, root.studio.posSec)
                            property var edit: null          // puntos mientras se arrastra uno (se guardan al soltar)
                            width: col.width; height: root.laneH
                            Rectangle {
                                x: root.headW; width: parent.width - root.headW; height: parent.height
                                color: Qt.tint(Theme.device, Qt.rgba(Qt.color(trk.c).r, Qt.color(trk.c).g, Qt.color(trk.c).b, 0.10))
                                Rectangle { y: parent.height - 1; width: parent.width; height: 1; color: Theme.deviceBorder; opacity: 0.3 }
                                Canvas {
                                    id: curve
                                    anchors.fill: parent
                                    property var pts: ln.edit || ln.l.points
                                    property real p: root.pps
                                    property color k: trk.c
                                    property color ink: Theme.deviceInk
                                    onPtsChanged: requestPaint(); onPChanged: requestPaint(); onWidthChanged: requestPaint(); onKChanged: requestPaint()
                                    onPaint: {
                                        var ctx = getContext("2d"); ctx.reset()
                                        var pts = curve.pts, top = 6, h = height - 12
                                        if (!pts.length) return
                                        var Y = function (v) { return top + h * (1 - root.norm(ln.l, v)) }
                                        ctx.beginPath(); ctx.moveTo(0, Y(pts[0][1]))
                                        pts.forEach(function (q) { ctx.lineTo(q[0] * p, Y(q[1])) })
                                        ctx.lineTo(width, Y(pts[pts.length - 1][1]))
                                        ctx.lineTo(width, top + h); ctx.lineTo(0, top + h); ctx.closePath()
                                        ctx.globalAlpha = 0.35; ctx.fillStyle = k; ctx.fill(); ctx.globalAlpha = 1
                                        ctx.beginPath(); ctx.moveTo(0, Y(pts[0][1]))
                                        pts.forEach(function (q) { ctx.lineTo(q[0] * p, Y(q[1])) })
                                        ctx.lineTo(width, Y(pts[pts.length - 1][1]))
                                        ctx.lineWidth = 2; ctx.strokeStyle = ink; ctx.stroke()
                                        ctx.fillStyle = ink
                                        if (pts.length * 6 < width) pts.forEach(function (q) { ctx.fillRect(q[0] * p - 2, Y(q[1]) - 2, 4, 4) })
                                    }
                                }
                                Rectangle {                 // punto del valor actual bajo el cursor
                                    width: 10; height: 10; radius: 5; color: Theme.accent; border.width: Theme.buttonBorder; border.color: Theme.line
                                    x: root.studio.posSec * root.pps - 5
                                    y: 6 + (parent.height - 12) * (1 - root.norm(ln.l, ln.now)) - 5
                                }
                                // Clic: añade un punto; arrastrar: lo mueve; clic derecho: lo borra (el cursor se lleva en la regla)
                                MouseArea {
                                    id: lma
                                    anchors.fill: parent; preventStealing: true; hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    cursorShape: Qt.CrossCursor
                                    property int hit: -1
                                    function tOf(mx) { return Math.max(0, mx / root.pps) }
                                    function vOf(my) { return root.denorm(ln.l, 1 - (my - 6) / Math.max(1, height - 12)) }
                                    function nearest(mx, my) {
                                        var pts = ln.l.points, best = -1, bd = 10
                                        for (var i = 0; i < pts.length; i++) {
                                            var dx = pts[i][0] * root.pps - mx, dy = 6 + (height - 12) * (1 - root.norm(ln.l, pts[i][1])) - my
                                            var d = Math.sqrt(dx * dx + dy * dy)
                                            if (d < bd) { bd = d; best = i }
                                        }
                                        return best
                                    }
                                    onPressed: function (m) {
                                        hit = nearest(m.x, m.y)
                                        var pts = ln.l.points.slice()
                                        if (m.button === Qt.RightButton) {
                                            if (hit >= 0) { pts.splice(hit, 1); root.commitLane(ln.l, pts) }
                                            hit = -1; return
                                        }
                                        if (hit < 0) {
                                            var q = [tOf(m.x), vOf(m.y)]
                                            pts.push(q); pts.sort(function (a, b) { return a[0] - b[0] })
                                            hit = pts.indexOf(q)
                                        }
                                        ln.edit = pts
                                    }
                                    onPositionChanged: function (m) {
                                        if (!pressed || hit < 0 || !ln.edit) return
                                        var pts = ln.edit.slice()
                                        var lo = hit > 0 ? pts[hit - 1][0] + 0.001 : 0, hi = hit < pts.length - 1 ? pts[hit + 1][0] - 0.001 : 1e9
                                        pts[hit] = [Math.max(lo, Math.min(hi, tOf(m.x))), vOf(m.y)]
                                        ln.edit = pts
                                    }
                                    onReleased: function (m) {
                                        if (ln.edit && m.button === Qt.LeftButton) root.commitLane(ln.l, ln.edit)
                                        ln.edit = null; hit = -1
                                    }
                                    onCanceled: { ln.edit = null; hit = -1 }
                                }
                                Rectangle {                 // valor del punto que se arrastra
                                    readonly property var q: ln.edit && lma.hit >= 0 && lma.hit < ln.edit.length ? ln.edit[lma.hit] : [0, 0]
                                    visible: lma.pressed && lma.hit >= 0 && !!ln.edit
                                    x: Math.min(parent.width - width, q[0] * root.pps + 10); y: 2
                                    width: dragTxt.implicitWidth + 12; height: 22; radius: 3
                                    color: Theme.deviceHead; border.width: 1; border.color: Theme.deviceBorder
                                    Text { id: dragTxt; anchors.centerIn: parent; color: Theme.deviceInk
                                           font.family: Theme.font; font.pixelSize: 12; font.weight: 700
                                           text: root.fmtTime(parent.q[0]) + " · " + root.fmt(ln.l, parent.q[1]) }
                                }
                            }
                            Rectangle {
                                x: flick.contentX; z: 2
                                width: root.headW; height: parent.height
                                color: Qt.tint(Theme.deviceHead, Qt.rgba(Qt.color(trk.c).r, Qt.color(trk.c).g, Qt.color(trk.c).b, 0.12))
                                border.width: 1; border.color: Theme.deviceBorder
                                Rectangle { width: 8; height: parent.height; color: trk.c; opacity: 0.5 }
                                Column {
                                    x: 22; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 30; spacing: 1
                                    Text { width: parent.width; elide: Text.ElideRight; text: "∿ " + ln.l.fx + " · " + ln.l.name
                                           color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                                    Row {
                                        spacing: 8
                                        Text { text: ln.l.points.length ? root.fmt(ln.l, ln.now) : "sin curva"; color: Theme.deviceInk
                                               font.family: Theme.font; font.pixelSize: 14; font.weight: 800 }
                                        Text { anchors.baseline: parent.children[0].baseline
                                               text: ln.l.points.length ? ln.l.points.length + " puntos · " + root.fmt(ln.l, ln.l.min) + " … " + root.fmt(ln.l, ln.l.max)
                                                                        : "clic en el carril: añadir punto"
                                               color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11 }
                                    }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; hoverEnabled: true
                                            onDoubleClicked: root.openInFx(trk.t.id)
                                            ToolTipLite { text: "En el carril: clic añade un punto, arrastrar lo mueve, clic derecho lo borra. Doble clic aquí: abrir los efectos de la pista"; show: parent.containsMouse } }
                            }
                        }
                    }
                }
            }
            Text {
                visible: root.studio.tracks.length === 0
                x: root.headW + 20; height: 80; verticalAlignment: Text.AlignVCenter
                text: "Sin pistas todavía: «Abrir» carga un proyecto, o suelta audios en Audios / genera con IA."
                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 14
            }
        }
    }
    // cursor de reproducción por encima de todo
    Rectangle {
        readonly property real px: root.headW + root.studio.posSec * root.pps - flick.contentX
        visible: px >= root.headW && px <= root.width
        x: px - 1; y: ruler.y; width: 2; height: consoleBox.y - ruler.y
        color: Theme.knobArc; z: 5
        Rectangle { x: -5; width: 12; height: 10; color: Theme.knobArc }
    }
    // barra horizontal mínima (la rueda con Mayús también desplaza)
    Rectangle {
        visible: flick.contentWidth > flick.width
        x: root.headW + (flick.width - root.headW) * flick.contentX / flick.contentWidth
        width: Math.max(30, (flick.width - root.headW) * flick.width / flick.contentWidth)
        y: consoleBox.y - 8; height: 6; radius: 3; color: Theme.deviceInk; opacity: 0.45; z: 6
    }

    // ---------------- consola ----------------
    Rectangle {
        id: consoleBox
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: root.showConsole ? Math.min(Math.max(320, root.height * 0.65), Math.min(400, Math.max(320, root.height * 0.42)) + root.sendsH) : 0
        visible: root.showConsole
        color: Theme.deviceHead
        Rectangle { width: parent.width; height: 3; color: Theme.deviceBorder }
        Text { x: 12; y: 8; text: "CONSOLA · inserts en orden de la señal (∿ = automatizado) · doble clic en un insert: abrirlo en Efectos"
                                  + (root.auxes.length ? " · envíos: arrastra el nivel, doble clic lo apaga" : "")
               color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
        Flickable {
            id: strips
            x: 8; y: 30; width: parent.width - 16; height: parent.height - 36
            contentWidth: stripRow.width; clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.HorizontalFlick
            Row {
                id: stripRow
                spacing: 6
                Repeater {
                    model: root.rows
                    Rectangle {
                        id: st
                        required property var modelData
                        readonly property var t: modelData
                        readonly property bool master: t.type === "master"
                        readonly property var inf: root.info(t.id)
                        readonly property color c: root.colorOf(t)
                        readonly property real fv: master ? root.studio.masterPos : (t.vol === undefined ? 70 : t.vol)
                        readonly property var lr: master ? root.studio.masterDb : root.studio.trackLR(t.id)
                        readonly property bool isAux: t.type === "aux"
                        width: master ? 150 : 132; height: strips.height
                        color: Theme.device; border.width: Theme.buttonBorder; border.color: st.master ? st.c : Theme.deviceBorder
                        Rectangle { width: parent.width; height: 26; color: st.c
                            Text { x: 6; width: parent.width - 12; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: st.t.name; color: "#000"; font.family: Theme.font; font.pixelSize: 12; font.weight: 800 }
                            MouseArea { id: hma; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: root.openInFx(st.t.id) }
                            ToolTipLite { show: hma.containsMouse; text: "Doble clic: abrir los efectos de " + st.t.name } }
                        Flickable {                      // inserts (se desplazan si no caben)
                            id: insF
                            x: 4; y: 30; width: parent.width - 8; height: parent.height - 30 - 194 - root.sendsH
                            contentHeight: insCol.height; clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            flickableDirection: Flickable.VerticalFlick
                        Column {
                            id: insCol
                            width: parent.width; spacing: 2
                            Repeater {
                                model: st.inf.inserts
                                Rectangle {
                                    required property var modelData
                                    width: parent.width; height: 24; radius: 3
                                    color: modelData.enabled ? Theme.button : Theme.deviceHead
                                    border.width: 1; border.color: Theme.deviceBorder
                                    Rectangle { x: 5; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4
                                                color: modelData.enabled ? "#2fbf71" : "#7a7a7a"; border.width: 1; border.color: Theme.line }
                                    Text { x: 17; width: parent.width - 21 - (aut.visible ? aut.width + 2 : 0); anchors.verticalCenter: parent.verticalCenter
                                           elide: Text.ElideRight; text: modelData.label; color: Theme.ink
                                           font.family: Theme.font; font.pixelSize: 11; font.weight: 600
                                           font.strikeout: !modelData.enabled }
                                    Text { id: aut; visible: modelData.automated > 0; anchors.right: parent.right; anchors.rightMargin: 4
                                           anchors.verticalCenter: parent.verticalCenter; text: "∿"; color: Theme.ink
                                           font.pixelSize: 13; font.weight: 800 }
                                    MouseArea { id: ima; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: root.openInFx(st.t.id) }
                                    ToolTipLite { show: ima.containsMouse
                                                  text: modelData.label + (modelData.enabled ? "" : " (puenteado)")
                                                        + (modelData.automated ? " · " + modelData.automated + " parámetro(s) automatizado(s)" : "")
                                                        + (modelData.auto ? " · puesto por la mezcla automática" : "") }
                                }
                            }
                            Text { visible: st.inf.inserts.length === 0; text: "sin inserts"; color: Theme.deviceInk
                                   font.family: Theme.font; font.pixelSize: 11 }
                        }
                        }
                        Text {                           // aviso de que hay más inserts abajo
                            visible: insF.contentHeight > insF.height
                            x: 6; y: insF.y + insF.height + 2
                            text: "+" + Math.max(0, st.inf.inserts.length - Math.floor((insF.height + 2) / 26)) + " más ↓ (rueda)"
                            color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 700
                        }
                        // envíos a los buses Aux (pre = antes del fader)
                        Item {
                            visible: root.sendsH > 0 && !st.master
                            x: 4; y: parent.height - 168 - root.sendsH; width: parent.width - 8; height: root.sendsH - 4
                            Text { x: 2; y: 2; text: st.isAux ? "RETORNO" : "ENVÍOS"; color: Theme.deviceInk
                                   font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
                            Text { visible: st.isAux; x: 2; y: 22; width: parent.width - 4; wrapMode: Text.Wrap
                                   text: { var n = root.sendsTo(st.t.id); return n ? "Recibe " + n + (n === 1 ? " envío" : " envíos") : "Sin envíos: súbelos en las otras tiras" }
                                   color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                            Flickable {
                                visible: !st.isAux
                                y: 20; width: parent.width; height: parent.height - 20
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
                                            readonly property var snd: root.sendOf(st.t.id, modelData.id)
                                            readonly property real pos: snd ? root.sendPos(snd.db) : 0
                                            readonly property bool pre: !!(snd && snd.pre)
                                            width: parent.width; height: 24
                                            Rectangle {                  // nivel del envío
                                                id: lvl
                                                width: parent.width - 38; height: 24; radius: 3
                                                color: Theme.input; border.width: 1; border.color: Theme.deviceBorder
                                                Rectangle { x: 1; y: 1; height: parent.height - 2; radius: 2
                                                            width: Math.max(0, (parent.width - 2) * sr.pos)
                                                            color: Qt.tint(Theme.input, Qt.rgba(Qt.color(root.colorOf(sr.modelData)).r, Qt.color(root.colorOf(sr.modelData)).g, Qt.color(root.colorOf(sr.modelData)).b, 0.45)) }
                                                Text { x: 5; width: parent.width - 10 - sdb.width - 4; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                                       text: sr.modelData.name
                                                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                                                Text { id: sdb; anchors.right: parent.right; anchors.rightMargin: 5; anchors.verticalCenter: parent.verticalCenter
                                                       text: sr.snd ? (sr.snd.db > 0.05 ? "+" : "") + sr.snd.db.toFixed(1) : "−∞"
                                                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
                                                MouseArea {
                                                    id: sma
                                                    anchors.fill: parent; hoverEnabled: true; preventStealing: true
                                                    function at(mx) { root.setSend(st.t.id, sr.modelData.id, root.sendDb(Math.max(0, Math.min(1, mx / width))), sr.pre) }
                                                    onPressed: function (m) { at(m.x) }
                                                    onPositionChanged: function (m) { if (pressed) at(m.x) }
                                                    onDoubleClicked: root.setSend(st.t.id, sr.modelData.id, -100, sr.pre)
                                                }
                                                ToolTipLite { show: sma.containsMouse && !sma.pressed
                                                              text: "Envío de " + st.t.name + " al bus «" + sr.modelData.name + "» ("
                                                                    + (sr.pre ? "pre-fader: no sigue al volumen de la pista" : "post-fader: sigue al volumen de la pista")
                                                                    + "). Arrastra para el nivel; doble clic lo apaga." }
                                            }
                                            Rectangle {                  // pre / post fader
                                                id: preB
                                                x: parent.width - 34; width: 34; height: 24; radius: 3
                                                color: sr.pre ? Theme.pressedBg : Theme.button
                                                border.width: 1; border.color: Theme.deviceBorder
                                                Text { anchors.centerIn: parent; text: "PRE"; color: sr.pre ? Theme.pressedInk : Theme.ink
                                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
                                                MouseArea { id: pma; anchors.fill: parent; hoverEnabled: true
                                                            onClicked: root.setSend(st.t.id, sr.modelData.id, sr.snd ? sr.snd.db : -12, !sr.pre) }
                                                ToolTipLite { show: pma.containsMouse
                                                              text: sr.pre ? "Pre-fader (activo): el envío no depende del fader. Clic: post-fader"
                                                                           : "Post-fader: el envío sigue al fader. Clic: pre-fader (para cascos o efectos que no deben bajar con la pista)" }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        // paneo
                        Item {
                            visible: !st.master
                            x: 8; y: parent.height - 128 - 26; width: parent.width - 16; height: 24
                            Rectangle { y: 10; width: parent.width; height: 4; color: Theme.dark ? Qt.tint(Theme.device, Qt.rgba(Qt.color(Theme.ink).r, Qt.color(Theme.ink).g, Qt.color(Theme.ink).b, 0.55)) : Theme.knobTrack }
                            Rectangle { x: parent.width / 2 - 1; y: 6; width: 2; height: 12; color: Theme.deviceInk }
                            Rectangle { width: 10; height: 18; y: 3; radius: 2; color: Theme.knobArc; border.width: Theme.buttonBorder; border.color: Theme.line
                                        x: (parent.width - 10) * (st.t.pan === undefined ? 50 : st.t.pan) / 100 }
                            MouseArea {
                                anchors.fill: parent; preventStealing: true
                                function at(mx) { root.studio.setTrackMixUid(st.t.uid, st.fv, Math.round(Math.max(0, Math.min(100, mx / width * 100)))) }
                                onPressed: function (m) { at(m.x) }
                                onPositionChanged: function (m) { if (pressed) at(m.x) }
                                onDoubleClicked: root.studio.setTrackMixUid(st.t.uid, st.fv, 50)
                                onReleased: root.studio.trackRelease(st.t.uid)
                            }
                        }
                        Text { visible: !st.master; x: 8; y: parent.height - 128 - 40; color: Theme.deviceInk
                               font.family: Theme.font; font.pixelSize: 11; font.weight: 600
                               text: { var p = st.t.pan === undefined ? 50 : st.t.pan; return p === 50 ? "Paneo C" : "Paneo " + (p < 50 ? "I " + (50 - p) * 2 : "D " + (p - 50) * 2) } }
                        // fader + medidores
                        Row {
                            x: 8; y: parent.height - 124; spacing: 4
                            Fader { height: 100; value: st.fv
                                    tip: "Volumen de " + st.t.name
                                    onMoved: function (v) { if (st.master) root.studio.setMaster(v); else root.studio.setTrackMixUid(st.t.uid, v, st.t.pan === undefined ? 50 : st.t.pan) }
                                    onReleased: if (!st.master) root.studio.trackRelease(st.t.uid) }
                            Meter { height: 100; width: 10; level: MD.dbToPct(st.lr[0]) }
                            Meter { height: 100; width: 10; level: MD.dbToPct(st.lr[1]) }
                            Column {
                                spacing: 2
                                Text { text: MD.faderDbText(st.fv); color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 800 }
                                Text { text: "pico"; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11 }
                                Text { text: Math.max(st.lr[0], st.lr[1]) <= -99 ? "−∞" : Math.max(st.lr[0], st.lr[1]).toFixed(1)
                                       color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                            }
                        }
                        Row {
                            visible: !st.master
                            x: 8; y: parent.height - 20; spacing: 4
                            Text { text: st.t.mute ? "SILENCIADA" : st.t.solo ? "SOLO" : ""; color: Theme.deviceInk
                                   font.family: Theme.font; font.pixelSize: 11; font.weight: 800 }
                        }
                    }
                }
            }
        }
    }
}
