import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Vista ARREGLO (como Studio One / Ableton): la canción entera de un vistazo. Arriba la regla de
// compases; por pista su cabecera (color, nombre, tipo, M/S, inserts) y sus clips con la forma de
// onda o las notas; debajo de cada pista sus carriles de automatización con la curva real que el
// motor reproduce y el valor que tiene ahora bajo el cursor. Es el único panel de pistas: aquí se
// editan los clips de audio (mover, recortar, dividir, fundidos, volumen, normalizar, rehacer con IA,
// deshacer). La consola (inserts, envíos, paneo y fader) es la vista Mezclador. Todo sale del motor
// (puente: dawLanes y clipEdit); nada es decorativo.
Rectangle {
    id: root
    property var studio
    color: Theme.device

    property var lanes: ({})                  // id de pista (0 = master) → {inserts, lanes}
    property var closed: ({})                 // uid → carriles de automatización plegados
    property real pps: 8                      // píxeles por segundo
    readonly property int headW: 260
    readonly property int rowH: 70
    readonly property int laneH: 58
    readonly property real beat: 60 / Math.max(40, studio ? studio.bpm : 96)
    readonly property var rows: {
        var t = studio ? studio.tracks : [], shut = {}
        t.forEach(function (k) { if (k.fold) shut[k.uid] = true })
        // F4: una carpeta plegada esconde sus pistas en el Arreglo (siguen sonando: ocultar ≠ silenciar)
        return t.filter(function (k) { return !(k.folder && shut[k.folder]) })
                .concat([{ uid: "master", id: 0, type: "master", name: "Master" }])
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
    readonly property var auxes: (studio ? studio.tracks : []).filter(function (t) { return t.type === "aux" && t.id >= 0 })

    function refresh() {
        if (!studio || !studio.engineOk || !visible) return
        var ids = studio.tracks.filter(function (t) { return t.id >= 0 }).map(function (t) { return t.id })
        ids.push(0)
        var r = studio.call("dawLanes", JSON.stringify(ids))
        if (!r.ok) return
        lanes = r.tracks
    }
    function addAux() {
        var t = studio.seq.addTrack("aux")
        if (t && t.id >= 0)
            studio.toast("Bus «" + t.name + "» creado: ponle una reverb o un eco y súbele los envíos en el Mezclador")
        return t
    }

    // ---------------- edición de clips de audio (antes, la pestaña «Clips») ----------------
    property string tool: "move"            // move | cut
    property bool snap: true                // ajustar a los tiempos del compás
    property real clipSel: 0                // id del clip elegido (0 = ninguno)
    property string clipUid: ""             // pista del clip elegido
    property var undoStack: []
    property var redoStack: []
    readonly property var selTrack: clipUid && studio ? studio.seq.trackOf(clipUid) : null
    // Vocal Align: pistas que pueden ser la guía (las de audio, menos la del clip elegido)
    readonly property var alignGuides: (studio ? studio.tracks : []).filter(function (t) {
        return (t.type === "audio" || t.type === "voz") && t.id > 0 && !t.lab && (!selTrack || t.uid !== selTrack.uid) })
    readonly property var alignGuide: {
        var g = alignGuides.filter(function (t) { return studio && t.uid === studio.seq.alignOpts.guide })
        return g.length ? g[0] : (alignGuides.length ? alignGuides[0] : null)
    }
    readonly property var selInfo: {
        var cs = selTrack ? selTrack.aclips || [] : []
        for (var i = 0; i < cs.length; i++) if (cs[i].id === clipSel) return cs[i]
        return null
    }
    function snapT(t) { return snap ? Math.round(t / beat) * beat : t }
    function fmtS(s) {
        s = Math.max(0, s)
        var m = Math.floor(s / 60), r = s - 60 * m
        return m + ":" + (r < 10 ? "0" : "") + r.toFixed(2)
    }
    function dbTxt(v) { return (v > 0 ? "+" : "") + v.toFixed(1) + " dB" }
    function pick(uid, id) {
        clipUid = uid; clipSel = id
        var i = studio.seq.indexOf(uid)
        if (i >= 0) studio.seq.pick(i)
    }
    // Una edición en el motor; antes guarda los clips de la pista para deshacer
    function edit(uid, op, noUndo) {
        var t = studio.seq.trackOf(uid)
        if (!t || !studio.engineOk) return null
        if (!noUndo) { undoStack = undoStack.concat([{ uid: uid, clips: t.aclips || [] }]).slice(-60); redoStack = [] }
        var r = studio.call("clipEdit", t.id, JSON.stringify(op))
        if (!r.ok) { studio.toast(r.error); if (!noUndo) undoStack = undoStack.slice(0, -1); return null }
        studio.seq.replace(uid, { aclips: r.clips })
        if (clipUid === uid && !r.clips.some(function (c) { return c.id === clipSel })) clipSel = 0
        return r
    }
    // F7: el análisis del proyecto se deshace como una edición más (acordes, secciones y tonalidad)
    function songState() { return { song: true, chords: studio.chords, markers: studio.markers, key: studio.songKey } }
    function pushSong() { undoStack = undoStack.concat([songState()]).slice(-60); redoStack = [] }
    function songLaneInfo() {               // autoprueba (F7)
        return { visible: songLane.visible, height: songLane.height, chords: chordRep.count, markers: markRep.count,
                 flickTop: flick.y - songLane.y - songLane.height }
    }
    function restore(fromStack) {
        if (!fromStack.length) return null
        return restoreEntry(fromStack[fromStack.length - 1])
    }
    // Una entrada de deshacer; devuelve la contraria (para rehacer). F8: «multi» junta varias (un script
    // entero es un solo paso), «trk» devuelve fader, paneo, mute, solo, nombre y color, y «mix» las
    // cadenas de efectos con la instantánea del Mezclador.
    function restoreEntry(e) {
        if (e.multi) {
            var backs = []
            for (var i = e.multi.length - 1; i >= 0; i--) { var b = restoreEntry(e.multi[i]); if (b) backs.unshift(b) }
            return { multi: backs, label: e.label }
        }
        if (e.trk) {
            var bt = { trk: [] }
            e.trk.forEach(function (s) {
                var x = studio.seq.trackOf(s.uid); if (!x) return
                bt.trk.push({ uid: s.uid, vol: x.vol === undefined ? 70 : x.vol, pan: x.pan === undefined ? 50 : x.pan, mute: !!x.mute,
                              solo: !!x.solo, name: x.name, color: x.color || "" })
                studio.setTrackMixUid(s.uid, s.vol, s.pan)
                studio.seq.replace(s.uid, { mute: s.mute, solo: s.solo, name: s.name, color: s.color })
            })
            studio.syncTrackStates()
            return bt
        }
        if (e.mix) {
            var now = studio.mixer.call("snapshot")
            var rr = studio.mixer.call("restore", { tracks: e.mix })
            if (!rr.ok) { studio.toast(rr.error); return null }
            studio.refreshRacks()
            return now.ok ? { mix: now.tracks } : null
        }
        if (e.song) { var bs = songState(); studio.setSongInfo(e.chords, e.markers, e.key.key ? e.key : { key: "", scale: "" }); return bs }
        var t = studio.seq.trackOf(e.uid)
        if (!t) return null
        var back = { uid: e.uid, clips: t.aclips || [] }
        var op = { op: "set", clips: e.clips }
        if (e.source) op.source = e.source                 // deshacer / rehacer un «Rehacer con IA»
        if (e.takes !== undefined) { back.takes = t.takes || []; back.take = t.take || 0 }
        var r = studio.call("clipEdit", t.id, JSON.stringify(op))
        if (!r.ok) { studio.toast(r.error); return null }
        if (e.source) { back.now = r.source; back.source = e.now; studio.seq.replace(e.uid, { aclips: r.clips, peaks: r.peaks || [] }) }
        else studio.seq.replace(e.uid, { aclips: r.clips })
        if (e.takes !== undefined) studio.seq.replace(e.uid, { takes: e.takes, take: e.take })   // F4: la toma se va o vuelve
        clipSel = 0
        return back
    }
    function undo() {
        var b = restore(undoStack); if (!b) return
        undoStack = undoStack.slice(0, -1); redoStack = redoStack.concat([b])
    }
    function redo() {
        var b = restore(redoStack); if (!b) return
        redoStack = redoStack.slice(0, -1); undoStack = undoStack.concat([b])
    }
    // Dividir: el clip elegido en el cursor; si el cursor no lo cruza, el clip de esa pista bajo el cursor
    function splitAt(uid, id, at) {
        if (!uid) { studio.toast("Elige un clip de audio para dividir"); return }
        var t = studio.seq.trackOf(uid), cs = t ? t.aclips || [] : []
        var c = cs.filter(function (k) { return k.id === id && at > k.start && at < k.start + k.length })[0]
             || cs.filter(function (k) { return at > k.start + 0.01 && at < k.start + k.length - 0.01 })[0]
        if (!c) { studio.toast("El cursor no está sobre un clip de " + (t ? t.name : "la pista")); return }
        edit(uid, { op: "split", clip: c.id, at: at })
    }
    function toolTexts() {                  // autoprueba (F4): lo que hay en la barra de herramientas
        var o = []
        for (var i = 0; i < toolFlow.children.length; i++) { var c = toolFlow.children[i]; if (c.text !== undefined) o.push(String(c.text)) }
        return o
    }
    function removeSel() { if (selInfo) edit(clipUid, { op: "remove", clip: clipSel }) }
    function dupSel() { if (selInfo) { var r = edit(clipUid, { op: "dup", clip: clipSel }); if (r) clipSel = r.clips[r.clips.length - 1].id } }
    function gainSel(d) { if (selInfo) edit(clipUid, { op: "gain", clip: clipSel, db: Math.round((selInfo.gain_db + d) * 10) / 10 }) }
    function fadeSel(which, d) {
        if (!selInfo) return
        var fi = selInfo.fade_in, fo = selInfo.fade_out
        if (which === "in") fi = Math.max(0, fi + d); else fo = Math.max(0, fo + d)
        edit(clipUid, { op: "fades", clip: clipSel, "in": fi, out: fo })
    }
    readonly property bool keys: visible && !!studio && !studio.typing
    Shortcut { sequence: "S"; enabled: root.keys && !!root.clipUid; onActivated: root.splitAt(root.clipUid, root.clipSel, root.studio.posSec) }
    Shortcut { sequences: [StandardKey.Delete, "Backspace"]; enabled: root.keys && !!root.selInfo; onActivated: root.removeSel() }
    Shortcut { sequence: "Ctrl+D"; enabled: root.keys && !!root.selInfo; onActivated: root.dupSel() }
    Shortcut { sequences: [StandardKey.Undo]; enabled: root.keys && root.undoStack.length > 0; onActivated: root.undo() }
    Shortcut { sequences: [StandardKey.Redo, "Ctrl+Y"]; enabled: root.keys && root.redoStack.length > 0; onActivated: root.redo() }
    // «Rehacer con IA»: la pista cambió de archivo; Deshacer vuelve al anterior con sus clips
    Connections {
        target: root.studio ? root.studio.seq : null
        function onSourceReplaced(uid, previous, clips, extra) {
            var e = { uid: uid, clips: clips, source: previous, now: extra && extra.now ? extra.now : "" }
            if (extra && extra.takes !== undefined) { e.takes = extra.takes; e.take = extra.take }
            root.undoStack = root.undoStack.concat([e]).slice(-60)
            root.redoStack = []
        }
    }
    function info(id) { return lanes[String(id)] || { inserts: [], lanes: [] } }
    function colorOf(t) {
        if (t.color && Theme.pc[t.color]) return Theme.pc[t.color]     // F8: color puesto por un script (de la paleta del tema)
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
    function openInFx(id) {                    // 0 = el master: en Efectos es un canal más
        studio.rackTrack = id
        studio.goTo("fx")
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
                width: Math.max(0, barBtns.x - 24 - x); elide: Text.ElideRight
                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13; font.weight: 500
                text: root.studio.tracks.length + " pistas · " + root.insertCount + " inserts · "
                      + (root.auxes.length ? root.auxes.length + " Aux · " : "")
                      + root.laneCount + " curvas de automatización · " + root.fmtTime(root.songLen)
            }
        }
        Row {
            id: barBtns
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 6
            NeoButton { objectName: "arrNewTrack"; text: "+ Pista"; tip: "Pista nueva: audio, instrumento, batería, voz, Intérprete IA o Generar con IA"
                        onClicked: root.studio.newTrack("") }
            NeoButton { text: "+ Aux"; tip: "Nuevo bus Aux (reverb o eco compartidos): las pistas le mandan señal con sus envíos"
                        enabled: root.studio.engineOk; onClicked: root.addAux() }
            NeoButton { text: "Curvas: todas"; tip: "Desplegar los carriles de automatización de todas las pistas"
                        onClicked: root.setAllOpen(true) }
            NeoButton { text: "ninguna"; tip: "Plegar todos los carriles de automatización"; onClicked: root.setAllOpen(false) }
            NeoButton { text: "−"; tip: "Alejar (menos segundos por pantalla)"; onClicked: root.pps = Math.max(1, root.pps / 1.4) }
            NeoButton { text: "+"; tip: "Acercar"; onClicked: root.pps = Math.min(120, root.pps * 1.4) }
            NeoButton { text: "Ajustar"; tip: "Ver la canción entera a lo ancho"; onClicked: root.fitAll() }
            NeoButton { objectName: "arrToMixer"; text: "Mezclador"
                        tip: "Ir al Mezclador: tiras con inserts, envíos, paneo, fader y medidores (F6; Tab cambia de vista)"
                        onClicked: root.studio.goTo("mezcla") }
        }
    }

    // ---------------- herramientas de clips ----------------
    Rectangle {
        id: tools
        y: bar.height; width: parent.width; height: toolFlow.height + 10
        color: Theme.deviceHead
        Rectangle { y: parent.height - 1; width: parent.width; height: 1; color: Theme.deviceBorder }
        Flow {
            id: toolFlow
            x: 8; y: 5; width: parent.width - 16; spacing: 5
            Tb { objectName: "arrMove"; text: "↖ Mover"; on: root.tool === "move"; tip: "Arrastra un clip para moverlo y sus bordes para recortarlo"; onClicked: root.tool = "move" }
            Tb { objectName: "arrCut"; text: "✂ Cortar"; on: root.tool === "cut"; tip: "Clic sobre un clip: lo divide en ese punto"; onClicked: root.tool = "cut" }
            Sep {}
            Tb { objectName: "arrSplit"; text: "Dividir"; active: !!root.clipUid; tip: "Divide el clip en el cursor de reproducción (S)"
                 onClicked: root.splitAt(root.clipUid, root.clipSel, root.studio.posSec) }
            Tb { text: "Duplicar"; active: !!root.selInfo; tip: "Copia el clip detrás del último de la pista (Ctrl+D)"; onClicked: root.dupSel() }
            Tb { text: "Borrar"; active: !!root.selInfo; tip: "Quita el clip (Supr)"; onClicked: root.removeSel() }
            Tb { text: "Normalizar"; active: !!root.selInfo; tip: "Sube o baja el clip para que su pico quede en −1 dBFS"
                 onClicked: root.edit(root.clipUid, { op: "normalize", clip: root.clipSel, target: -1 }) }
            Sep {}
            Tb { text: "Vol −"; active: !!root.selInfo; tip: "Baja 1 dB el clip elegido (también se arrastra su etiqueta de dB)"; onClicked: root.gainSel(-1) }
            Tb { text: "Vol +"; active: !!root.selInfo; tip: "Sube 1 dB el clip elegido"; onClicked: root.gainSel(1) }
            Tb { text: "Fade in"; active: !!root.selInfo; tip: "Clic: +0,25 s · también se arrastra el cuadrito de la esquina del clip"
                 onClicked: root.fadeSel("in", 0.25) }
            Tb { text: "Fade out"; active: !!root.selInfo; tip: "Clic: +0,25 s · también se arrastra el cuadrito de la esquina del clip"
                 onClicked: root.fadeSel("out", 0.25) }
            Tb { text: "Sin fades"; active: !!root.selInfo && (root.selInfo.fade_in > 0 || root.selInfo.fade_out > 0)
                 tip: "Quita los fundidos del clip elegido"
                 onClicked: root.edit(root.clipUid, { op: "fades", clip: root.clipSel, "in": 0, out: 0 }) }
            Sep {}
            Tb { text: "⌗ Rejilla"; on: root.snap; tip: "Ajustar mover, recortar y cortar a los tiempos del compás"; onClicked: root.snap = !root.snap }
            Tb { text: "Deshacer"; active: root.undoStack.length > 0; tip: "Deshacer la última edición de clips (Ctrl+Z)"; onClicked: root.undo() }
            Tb { text: "Rehacer"; active: root.redoStack.length > 0; tip: "Rehacer (Ctrl+Y)"; onClicked: root.redo() }
            Text {
                height: 26; verticalAlignment: Text.AlignVCenter
                width: Math.min(implicitWidth, toolFlow.width)
                elide: Text.ElideRight
                text: root.selInfo
                      ? (root.selTrack ? root.selTrack.name : "") + " · inicio " + root.fmtS(root.selInfo.start) + " · dura " + root.fmtS(root.selInfo.length)
                        + " · " + root.dbTxt(root.selInfo.gain_db) + " · fades " + root.selInfo.fade_in.toFixed(2) + " / " + root.selInfo.fade_out.toFixed(2) + " s"
                      : "Clic en un clip de audio para editarlo"
                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
            }
        }
    }

    // ---------------- regla de compases ----------------
    Rectangle {
        id: ruler
        y: tools.y + tools.height; width: parent.width; height: 30
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

    // ---------------- F7: secciones y pista de acordes (Editar › Analizar el proyecto) ----------------
    Rectangle {
        id: songLane
        objectName: "songLane"
        readonly property bool has: !!root.studio && (root.studio.chords.length > 0 || root.studio.markers.length > 0)
        anchors { top: ruler.bottom; left: parent.left; right: parent.right }
        height: has ? 50 : 0
        visible: has
        color: Theme.deviceHead
        clip: true
        Column {
            x: 12; y: 3; spacing: 4
            Text { height: 20; verticalAlignment: Text.AlignVCenter; text: "Secciones"; color: Theme.deviceInk
                   font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
            Text { height: 22; verticalAlignment: Text.AlignVCenter; text: "Acordes"; color: Theme.deviceInk
                   font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
        }
        Item {
            x: root.headW; width: parent.width - root.headW; height: parent.height
            clip: true
            Repeater {
                id: markRep
                model: root.studio ? root.studio.markers : []
                Rectangle {
                    required property var modelData
                    x: modelData.start * root.pps - flick.contentX; y: 3
                    width: Math.max(3, (modelData.end - modelData.start) * root.pps - 2); height: 20; radius: 2
                    color: Theme.button; border.width: 1; border.color: Theme.line
                    Text { x: 6; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                           text: modelData.label; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 800 }
                    MouseArea { id: mkM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: root.seek(modelData.start) }
                    ToolTipLite { show: mkM.containsMouse
                                  text: "Sección " + modelData.label + " · " + root.fmtTime(modelData.start) + " – " + root.fmtTime(modelData.end)
                                        + ". Las secciones con la misma letra se parecen. Clic: ir allí" }
                }
            }
            Repeater {
                id: chordRep
                model: root.studio ? root.studio.chords : []
                Rectangle {
                    required property var modelData
                    x: modelData.start * root.pps - flick.contentX; y: 26
                    width: Math.max(3, (modelData.end - modelData.start) * root.pps - 2); height: 22; radius: 2
                    color: Theme.input; border.width: 1; border.color: Theme.line
                    Text { x: 5; width: parent.width - 7; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                           text: modelData.name_es; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                    MouseArea { id: chM; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: root.seek(modelData.start) }
                    ToolTipLite { show: chM.containsMouse
                                  text: modelData.name_es + " (" + modelData.name + ") · " + root.fmtTime(modelData.start) + " – "
                                        + root.fmtTime(modelData.end) + ". Detectado en el audio; Ctrl+Z deshace el análisis" }
                }
            }
        }
        Rectangle { y: parent.height - 2; width: parent.width; height: 2; color: Theme.deviceBorder }
    }

    // ---------------- pistas y carriles ----------------
    Flickable {
        id: flick
        anchors { top: songLane.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
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
                            MouseArea { anchors.fill: parent; onClicked: function (m) { root.clipSel = 0; root.seek(m.x / root.pps) } }
                            // clips de audio editables: elegir, mover, recortar, cortar, volumen y fundidos
                            Repeater {
                                model: trk.t.aclips || []
                                Item {
                                    id: ac
                                    required property var modelData
                                    property bool busy: false
                                    property var live: ({})
                                    readonly property var v: busy ? live : modelData
                                    readonly property bool picked: root.clipSel === modelData.id && root.clipUid === trk.t.uid
                                    readonly property Item lane: parent
                                    x: v.start * root.pps; y: 4
                                    width: Math.max(4, v.length * root.pps); height: lane.height - 8
                                    z: picked ? 2 : 1
                                    function begin() { live = Object.assign({}, modelData); busy = true; root.pick(trk.t.uid, modelData.id) }
                                    function set(k) { live = Object.assign({}, live, k) }
                                    function commitRange() {
                                        busy = false
                                        if (live.start === modelData.start && live.length === modelData.length && live.offset === modelData.offset) return
                                        root.edit(trk.t.uid, { op: "range", clip: modelData.id, start: live.start, length: live.length, offset: live.offset })
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        color: Qt.darker(trk.c, trk.t.mute ? 2.2 : 1.0); radius: 3
                                        border.width: ac.picked ? 3 : Theme.buttonBorder; border.color: ac.picked ? Theme.accent : Theme.line
                                        clip: true
                                        Text { x: 5; y: 2; width: parent.width - 10; elide: Text.ElideRight
                                               text: trk.t.name + (Math.abs(ac.v.gain_db || 0) > 0.05 ? "  " + root.dbTxt(ac.v.gain_db) : "")
                                               color: Theme.inkOnColor; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                        Canvas {             // forma de onda del trozo que suena, con su volumen y fundidos
                                            y: 16; width: parent.width; height: parent.height - 18
                                            property var peaks: trk.t.peaks || []
                                            property var cv: ac.v
                                            property real p: root.pps
                                            onPeaksChanged: requestPaint(); onCvChanged: requestPaint(); onWidthChanged: requestPaint(); onPChanged: requestPaint()
                                            onPaint: {
                                                var ctx = getContext("2d"); ctx.reset()
                                                var pk = peaks, c = cv, src = Math.max(0.01, c.source_length || trk.t.len || 1)
                                                var g = Math.pow(10, (c.gain_db || 0) / 20), n = Math.max(1, Math.floor(width / 2))
                                                var fin = c.fade_in || 0, fout = c.fade_out || 0
                                                ctx.fillStyle = "rgba(0,0,0,0.8)"
                                                for (var j = 0; j < n && pk.length; j++) {
                                                    var tt = c.length * j / n, env = 1
                                                    if (fin > 0 && tt < fin) env = tt / fin
                                                    if (fout > 0 && tt > c.length - fout) env = Math.min(env, (c.length - tt) / fout)
                                                    var v = (pk[Math.min(pk.length - 1, Math.floor((c.offset + tt) / src * pk.length))] || 0) * g * env
                                                    var h = Math.min(height - 2, 1 + v * (height - 4))
                                                    ctx.fillRect(width * j / n, (height - h) / 2, 1.4, h)
                                                }
                                                ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.strokeStyle = "rgba(0,0,0,0.9)"; ctx.lineWidth = 1.5
                                                var fi = fin * p, fo = fout * p
                                                if (fi > 1) { ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(fi, 0); ctx.lineTo(0, height); ctx.closePath(); ctx.fill()
                                                              ctx.beginPath(); ctx.moveTo(0, height); ctx.lineTo(fi, 0); ctx.stroke() }
                                                if (fo > 1) { ctx.beginPath(); ctx.moveTo(width, 0); ctx.lineTo(width - fo, 0); ctx.lineTo(width, height); ctx.closePath(); ctx.fill()
                                                              ctx.beginPath(); ctx.moveTo(width - fo, 0); ctx.lineTo(width, height); ctx.stroke() }
                                            }
                                        }
                                    }
                                    MouseArea {              // cuerpo: elegir, mover o cortar
                                        anchors.fill: parent
                                        preventStealing: true
                                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        cursorShape: root.tool === "cut" ? Qt.IBeamCursor : pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                        property real px0
                                        onPressed: function (m) {
                                            if (m.button === Qt.RightButton) {     // clic derecho: elige el clip y abre su menú
                                                root.pick(trk.t.uid, ac.modelData.id)
                                                root.studio.openContext("clip", ac, m.x, m.y)
                                                return
                                            }
                                            if (root.tool === "cut") {
                                                root.pick(trk.t.uid, ac.modelData.id)
                                                root.splitAt(trk.t.uid, ac.modelData.id, root.snapT(ac.modelData.start + m.x / root.pps))
                                                return
                                            }
                                            px0 = mapToItem(ac.lane, m.x, 0).x; ac.begin()
                                        }
                                        onPositionChanged: function (m) {
                                            if (!ac.busy) return
                                            var d = (mapToItem(ac.lane, m.x, 0).x - px0) / root.pps
                                            ac.set({ start: Math.max(0, root.snapT(ac.modelData.start + d)) })
                                        }
                                        onReleased: if (ac.busy) ac.commitRange()
                                    }
                                    Rectangle {              // asa del volumen: arrastrar arriba/abajo
                                        visible: ac.picked && ac.width > 70
                                        x: (parent.width - width) / 2; y: 18
                                        width: gainTxt.implicitWidth + 12; height: 18; radius: 9
                                        color: gm.pressed ? Theme.accent : Theme.button; border.width: Theme.buttonBorder; border.color: Theme.line
                                        Text { id: gainTxt; anchors.centerIn: parent; text: root.dbTxt(ac.v.gain_db || 0); color: gm.pressed ? Theme.inkOnColor : Theme.ink
                                               font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                        MouseArea {
                                            id: gm; anchors.fill: parent; anchors.margins: -3; preventStealing: true; cursorShape: Qt.SizeVerCursor
                                            property real y0
                                            onPressed: function (m) { y0 = mapToItem(ac.lane, 0, m.y).y; ac.begin() }
                                            onPositionChanged: function (m) {
                                                var d = (y0 - mapToItem(ac.lane, 0, m.y).y) * 0.25
                                                ac.set({ gain_db: Math.max(-60, Math.min(24, Math.round((ac.modelData.gain_db + d) * 10) / 10)) })
                                            }
                                            onReleased: { ac.busy = false; root.edit(trk.t.uid, { op: "gain", clip: ac.modelData.id, db: ac.live.gain_db }) }
                                        }
                                    }
                                    Repeater {               // cuadritos de fundido (entrada y salida)
                                        model: ac.picked ? ["in", "out"] : []
                                        Rectangle {
                                            required property string modelData
                                            readonly property bool isIn: modelData === "in"
                                            width: 12; height: 12
                                            x: isIn ? Math.min(ac.width - 12, ac.v.fade_in * root.pps) : Math.max(0, ac.width - 12 - ac.v.fade_out * root.pps)
                                            y: 16
                                            color: fm.pressed ? Theme.accent : Theme.button; border.width: Theme.buttonBorder; border.color: Theme.line
                                            MouseArea {
                                                id: fm; anchors.fill: parent; anchors.margins: -6; preventStealing: true; cursorShape: Qt.SizeHorCursor
                                                property real px0
                                                onPressed: function (m) { px0 = mapToItem(ac.lane, m.x, 0).x; ac.begin() }
                                                onPositionChanged: function (m) {
                                                    var d = (mapToItem(ac.lane, m.x, 0).x - px0) / root.pps, L0 = ac.modelData.length
                                                    if (parent.isIn) ac.set({ fade_in: Math.max(0, Math.min(L0 - ac.modelData.fade_out, ac.modelData.fade_in + d)) })
                                                    else ac.set({ fade_out: Math.max(0, Math.min(L0 - ac.modelData.fade_in, ac.modelData.fade_out - d)) })
                                                }
                                                onReleased: { ac.busy = false
                                                              root.edit(trk.t.uid, { op: "fades", clip: ac.modelData.id, "in": ac.live.fade_in, out: ac.live.fade_out }) }
                                            }
                                        }
                                    }
                                    Repeater {               // bordes: recortar el principio o el final
                                        model: ["l", "r"]
                                        MouseArea {
                                            required property string modelData
                                            readonly property bool isLeft: modelData === "l"
                                            x: isLeft ? -3 : ac.width - 5; y: 30; width: 8; height: Math.max(8, ac.height - 30)
                                            preventStealing: true
                                            cursorShape: Qt.SizeHorCursor
                                            hoverEnabled: true
                                            property real px0
                                            Rectangle { anchors.fill: parent; color: Theme.accent; opacity: parent.containsMouse || parent.pressed ? 0.7 : 0 }
                                            onPressed: function (m) { px0 = mapToItem(ac.lane, m.x, 0).x; ac.begin() }
                                            onPositionChanged: function (m) {
                                                if (!ac.busy) return
                                                var c = ac.modelData, d = (mapToItem(ac.lane, m.x, 0).x - px0) / root.pps
                                                if (isLeft) {
                                                    var s = root.snapT(c.start + d)
                                                    s = Math.max(c.start - c.offset, Math.min(c.start + c.length - 0.05, s))   // no antes del principio del archivo
                                                    ac.set({ start: Math.max(0, s), offset: c.offset + (Math.max(0, s) - c.start), length: c.length - (Math.max(0, s) - c.start) })
                                                } else {
                                                    var e = root.snapT(c.start + c.length + d)
                                                    e = Math.max(c.start + 0.05, Math.min(c.start + (c.source_length - c.offset), e))
                                                    ac.set({ length: e - c.start })
                                                }
                                            }
                                            onReleased: if (ac.busy) ac.commitRange()
                                        }
                                    }
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
                                       text: trk.t.name + " · patrón de 16 compases (se repite)"; color: Theme.inkOnColor
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
                            MouseArea { anchors.fill: parent; enabled: !trk.master; acceptedButtons: Qt.LeftButton | Qt.RightButton
                                        onClicked: function (m) {
                                            var i = root.studio.seq.indexOf(trk.t.uid); if (i >= 0) root.studio.seq.pick(i)
                                            if (m.button === Qt.RightButton) root.studio.openContext("track", parent, m.x, m.y)
                                        } }
                            Column {
                                readonly property int kids: trk.master ? 0 : root.studio.seq.folderKids(trk.t.uid).length
                                id: headCol
                                x: trk.t.folder ? 30 : 16; y: 6; width: parent.width - x - btns.width - 10; spacing: 1
                                Row {
                                    width: parent.width; spacing: 4
                                    Rectangle {                    // F4: carpeta (Separar, Versión con IA)
                                        visible: headCol.kids > 0
                                        objectName: "folderBtn"
                                        width: 24; height: 20; radius: Theme.radius; anchors.verticalCenter: parent.verticalCenter
                                        color: fh.hovered ? Theme.s3 : Theme.chip; border.width: 1; border.color: Theme.line
                                        Text { anchors.centerIn: parent; text: trk.t.fold ? "▸" : "▾"; color: Theme.chipInk
                                               font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                                        HoverHandler { id: fh; cursorShape: Qt.PointingHandCursor }
                                        ToolTipLite { text: (trk.t.fold ? "Desplegar" : "Plegar") + " la carpeta: " + headCol.kids + " pistas (siguen sonando)"; show: fh.hovered }
                                        MouseArea { anchors.fill: parent; onClicked: root.studio.seq.toggleFold(trk.t.uid) }
                                    }
                                    Text { width: parent.width - (headCol.kids > 0 ? 28 : 0); elide: Text.ElideRight
                                           text: (trk.t.folder ? "↳ " : "") + trk.t.name; color: Theme.deviceInk
                                           font.family: Theme.font; font.pixelSize: 14; font.weight: 800 }
                                }
                                Text { visible: !(trk.t.takes && trk.t.takes.length > 1)
                                       width: parent.width; elide: Text.ElideRight
                                       text: root.kindOf(trk.t) + (headCol.kids > 0 ? " · carpeta de " + headCol.kids : ""); color: Theme.deviceInk
                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                                Select {                           // F4: tomas (Rehacer y Alinear con IA dejan una nueva)
                                    objectName: "takeSel"
                                    visible: !!trk.t.takes && trk.t.takes.length > 1
                                    width: parent.width; fontSize: 11; padY: 1
                                    options: (trk.t.takes || []).map(function (k, i) { return (i + 1) + ". " + k.name })
                                    current: trk.t.takes && trk.t.takes.length > 1 ? ((trk.t.take || 0) + 1) + ". " + trk.t.takes[trk.t.take || 0].name : ""
                                    tip: "Tomas de la pista: elige cuál suena (las demás se guardan con el proyecto)"
                                    onPicked: function (v) { root.studio.seq.useTake(trk.t.uid, parseInt(v) - 1) }
                                }
                                Text {
                                    width: parent.width; elide: Text.ElideRight; visible: !trk.master || trk.inf.inserts.length
                                    color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 600
                                    text: trk.inf.inserts.length
                                          ? "FX: " + trk.inf.inserts.map(function (e) { return e.label }).join(" › ")
                                          : "FX: sin inserts"
                                }
                            }
                            Column {
                                id: btns
                                anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                                spacing: 4
                            Row {
                                x: btns.width - width
                                spacing: 4
                                NeoButton { visible: !trk.master; text: "M"; padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: !!trk.t.mute
                                            color: trk.t.mute ? Theme.pressedBg : Theme.button; textColor: trk.t.mute ? Theme.pressedInk : Theme.ink
                                            tip: "Silenciar esta pista"; onClicked: root.studio.toggleTrackFlag(trk.t.uid, "mute") }
                                NeoButton { visible: !trk.master; text: "S"; padX: 7; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: !!trk.t.solo
                                            color: trk.t.solo ? Theme.accent : Theme.button; textColor: trk.t.solo ? Theme.inkOnAccent : Theme.ink
                                            tip: "Solo: escuchar solo esta pista (y las demás en solo)"; onClicked: root.studio.toggleTrackFlag(trk.t.uid, "solo") }
                                NeoButton { visible: !trk.master
                                            readonly property string m: trk.inf.mode || "read"
                                            text: m === "read" ? "R" : m === "touch" ? "T" : m === "latch" ? "L" : "W"
                                            padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            pressedState: m !== "read"
                                            color: m === "read" ? Theme.button : m === "write" ? Theme.pressedBg : Theme.accent
                                            textColor: m === "read" ? Theme.ink : m === "write" ? Theme.pressedInk : Theme.inkOnAccent
                                            tip: "Automatización: " + root.modeName[m] + ". " + root.modeHelp[m] + ". Clic: siguiente modo (Read → Touch → Latch → Write)"
                                            onClicked: root.cycleMode(trk.t) }
                                NeoButton { visible: trk.inf.lanes.length > 0
                                            text: (root.isOpen(trk.t) ? "▾ " : "▸ ") + "∿ " + trk.inf.lanes.length; padX: 6; padY: 3; fontSize: 12; shadow: 2
                                            tip: "Mostrar u ocultar sus " + trk.inf.lanes.length + " curvas de automatización"
                                            onClicked: root.toggleOpen(trk.t) }
                            }
                            Row {
                                visible: !trk.master
                                x: btns.width - width
                                spacing: 4
                                NeoButton { text: "✕"; padX: 6; padY: 3; fontSize: 12; shadow: 2; confirm: "¿Quitar?"
                                            tip: "Quitar la pista (y su canal y efectos). Pide confirmación"
                                            onClicked: { var i = root.studio.seq.indexOf(trk.t.uid); if (i >= 0) root.studio.removeTrackAt(i) } }
                            }
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
        x: px - 1; y: ruler.y; width: 2; height: root.height - ruler.y
        color: Theme.knobArc; z: 5
        Rectangle { x: -5; width: 12; height: 10; color: Theme.knobArc }
    }
    // barra horizontal mínima (la rueda con Mayús también desplaza)
    Rectangle {
        visible: flick.contentWidth > flick.width
        x: root.headW + (flick.width - root.headW) * flick.contentX / flick.contentWidth
        width: Math.max(30, (flick.width - root.headW) * flick.width / flick.contentWidth)
        y: root.height - 8; height: 6; radius: 3; color: Theme.deviceInk; opacity: 0.45; z: 6
    }

    component Tb: NeoButton {
        property bool on: false
        property bool active: true
        fontSize: 12; padX: 7; padY: 2; shadow: 0
        color: on ? Theme.accent : Theme.button; textColor: on ? Theme.inkOnAccent : Theme.ink
        opacity: active ? 1 : 0.45
        enabled: active
    }
    component Sep: Rectangle { width: 2; height: 26; color: Theme.deviceBorder }
}
