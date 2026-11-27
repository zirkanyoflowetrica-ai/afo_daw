import QtQuick
import "../theme"
import "../controls"

// Editor de tono (AF-64): modo «Tono» del editor de abajo (F3, docs/FLUJO_PROFESIONAL.md §2). Las notas
// de la toma de la pista elegida, movidas una a una y aplicadas como copia que la pista usa con los
// mismos clips. Antes vivía dentro del Afinador; si la pista tiene el AF-60, su escala manda.
Column {
    id: root
    objectName: "pitchEditor"
    property var mixer
    readonly property var studio: mixer ? mixer.studio : null
    readonly property var tn: mixer ? mixer.tune : null
    width: parent ? parent.width : 620
    spacing: 8

    property int trackId: -1                  // la pista elegida (la pone la selección)
    property var fx: null                     // afinador AF-60 de la pista, si lo tiene
    property var desc: null
    readonly property var noteNames: ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]
    readonly property var masks: [0xFFF, 0xAB5, 0x5AD, 0x9AD, 0x295, 0x4A9]
    readonly property var tracks: studio ? studio.tracks.filter(function (t) { return t.id >= 0 && t.type !== "aux" }) : []
    function pv(id) {
        if (!fx || !desc) return 0
        for (var i = 0; i < desc.params.length; i++) if (desc.params[i].id === id) return fx.values[i] !== undefined ? fx.values[i] : desc.params[i].def
        return 0
    }
    function noteName(m) { if (m <= 0) return "—"; var n = Math.round(m); return noteNames[(n % 12 + 12) % 12] + (Math.floor(n / 12) - 1) }
    function trackName() { for (var i = 0; i < tracks.length; i++) if (tracks[i].id === trackId) return tracks[i].name; return "" }
    function load() {
        if (!studio || !studio.engineOk || trackId < 0) { fx = null; return }
        if (!desc) { var c = studio.call("fxCatalog"); if (c.ok) desc = c.catalog.filter(function (d) { return d.key === "tune" })[0] || null }
        var r = studio.call("fxList", trackId)
        fx = r.ok ? (r.chain.filter(function (e) { return e.key === "tune" })[0] || null) : null
    }
    onTrackIdChanged: { sel = []; viewStart = 0; load() }
    Component.onCompleted: load()
    Connections {
        target: root.studio
        function onFxRevChanged() { root.load() }
        function onEngineOkChanged() { root.load() }
    }

    // --- Editor de tono (AF-64): estado en Sequencer (studio.seq.pitch), selección y vista aquí ---
    readonly property var seq: studio ? studio.seq : null
    readonly property var pe: seq ? seq.pitch : null
    readonly property bool peHere: !!pe && pe.trackId === trackId && pe.notes.length > 0
    readonly property int peEdited: pe ? pe.notes.filter(function (n) { return Math.abs(n.shift) > 1e-4 || n.flatten > 0 }).length : 0
    property var sel: []                      // índices de las notas elegidas
    property real viewStart: 0                // segundos del archivo
    property real viewLen: 8
    onPeChanged: { if (!peHere) sel = []; else sel = sel.filter(function (i) { return i < pe.notes.length }) }
    // Tonalidad del editor: la del afinador si está puesto; si no, la confirmada; si no, cromática
    function peScale() {
        if (fx) return { key: Math.round(pv("key")), scale: Math.round(pv("scale")) }
        var c = tn ? tn.confirmed : null
        if (c) {
            var k = mixer.keys.indexOf(c.key)
            var sc = ({ "Cromatica": 0, "Mayor": 1, "Menor natural": 2, "Menor armonica": 3, "Pentatonica mayor": 4, "Pentatonica menor": 5 })[c.scale]
            if (k >= 0 && sc !== undefined) return { key: k, scale: sc }
        }
        return { key: 0, scale: 0 }
    }
    function peScaleName() {
        var s = peScale()
        return s.scale === 0 ? "la escala cromática (semitono más cercano)"
                             : noteNames[s.key] + " " + ["Cromática", "Mayor", "Menor natural", "Menor armónica", "Pentatónica mayor", "Pentatónica menor"][s.scale]
    }
    function peIn(n) { var s = peScale(); return (masks[s.scale] >> (((n - s.key) % 12 + 12) % 12)) & 1 }
    function peNearest(m) {
        for (var d = 0; d <= 6; d++) {
            var a = Math.round(m) - d, b = Math.round(m) + d, c = []
            if (peIn(a)) c.push(a)
            if (peIn(b)) c.push(b)
            if (c.length) { c.sort(function (x, y) { return Math.abs(x - m) - Math.abs(y - m) }); return c[0] }
        }
        return Math.round(m)
    }
    function peTargets(allIfNone) { return sel.length ? sel : (allIfNone ? pe.notes.map(function (n, i) { return i }) : []) }
    function peEdit(fn, allIfNone) {
        if (!peHere) return
        var tg = peTargets(allIfNone)
        if (!tg.length) { studio.toast("Elige una nota en el editor (clic; Mayús+clic para varias)"); return }
        seq.pitchSetNotes(pe.notes.map(function (n, i) { return tg.indexOf(i) >= 0 ? Object.assign({}, n, fn(n)) : n }))
    }
    function peNudge(st) { peEdit(function (n) { return { shift: Math.round((n.shift + st) * 100) / 100 } }) }
    function peFlat() {
        var tg = peTargets(false), on = tg.length > 0 && tg.every(function (i) { return pe.notes[i].flatten > 0 })
        peEdit(function (n) { return { flatten: on ? 0 : 1 } })
    }
    function peToScale() { peEdit(function (n) { return { shift: Math.round((peNearest(n.midi) - n.midi) * 100) / 100 } }, true) }
    function peReset() { peEdit(function (n) { return { shift: 0, flatten: 0 } }, true) }
    function peSelInfo() {
        if (!peHere) return ""
        if (!sel.length) return pe.notes.length + " notas · " + (peEdited ? peEdited + " con cambios" : "sin cambios") + " · clic en una nota para elegirla"
        if (sel.length > 1) return sel.length + " notas elegidas"
        var n = pe.notes[sel[0]], c = Math.round((n.midi - Math.round(n.midi)) * 100)
        return "Nota " + (sel[0] + 1) + ": " + noteName(n.midi) + " " + (c >= 0 ? "+" : "") + c + " cents · "
               + (pe.fileStart + n.start).toFixed(2) + " s · " + (n.end - n.start).toFixed(2) + " s"
               + (Math.abs(n.shift) > 1e-4 ? " · movida " + (n.shift > 0 ? "+" : "") + n.shift.toFixed(2) + " st → " + noteName(n.midi + n.shift) : "")
               + (n.flatten > 0 ? " · enderezada" : "")
    }


    Text {
        visible: root.trackId < 0
        width: root.width; wrapMode: Text.Wrap
        text: "Elige un clip de audio o de voz: sus notas se editan aquí."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 13
    }

    // ---------------- Editor de tono (AF-64) ----------------
    Rectangle {
        width: root.width; height: peCol.height + 16
        color: Theme.device; border.width: 1; border.color: Theme.deviceBorder; radius: Theme.radius
        Column {
            id: peCol
            x: 10; y: 8; width: parent.width - 20; spacing: 6
            Row {
                spacing: 8
                Text { anchors.verticalCenter: parent.verticalCenter; text: "Editor de tono (AF-64)" + (root.trackId >= 0 ? " · " + root.trackName() : "")
                       color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                HelpButton {
                    anchors.verticalCenter: parent.verticalCenter
                    title: "Editor de tono (AF-64)"
                    text: "Las notas de la toma, una a una. Muévelas en semitonos o cents, enderézalas (quita vibrato y deriva) o llévalas a la escala; «Aplicar» escribe una copia que la pista usa con los mismos clips (Ctrl+Z vuelve). El tiempo no cambia.<br><br>Clic: elegir nota · Mayús+clic: varias · arrastrar arriba/abajo: semitonos · ↑/↓: ±1 st · Mayús+↑/↓: ±10 cents · ←/→: nota anterior/siguiente · Ctrl+A: todas · Esc: ninguna · rueda: avanzar · Ctrl+rueda: zoom"
                }
            }
            Row {
                id: peTop
                spacing: 6
                NeoButton {
                    objectName: "pitchAnalyze"
                    text: root.seq && root.seq.pitchBusy === "analyze" ? "Analizando…" : root.peHere ? "Volver a analizar" : "Analizar notas"
                    color: root.peHere ? Theme.button : Theme.accent; textColor: root.peHere ? Theme.ink : Theme.inkOnAccent
                    enabled: root.trackId >= 0 && !!root.seq && !root.seq.pitchBusy
                    tip: "Busca las notas de «" + root.trackName() + "» en su audio (el motor lo hace en otro hilo)"
                         + (root.peHere && root.peEdited ? ". Se pierden los cambios sin aplicar" : "")
                    onClicked: { root.sel = []; root.viewStart = 0; root.seq.pitchAnalyze(root.trackId) }
                }
                NeoButton {
                    objectName: "pitchApply"
                    text: root.seq && root.seq.pitchBusy === "apply" ? "Aplicando…" : "Aplicar a la pista"
                    enabled: root.peHere && !root.seq.pitchBusy
                    color: root.peEdited ? Theme.pc.afina : Theme.button; textColor: root.peEdited ? Theme.inkOnColor : Theme.ink
                    tip: root.peEdited ? "Escribe la toma con " + root.peEdited + (root.peEdited === 1 ? " nota cambiada" : " notas cambiadas") + " y la pone en la pista (Ctrl+Z vuelve)"
                                       : "Sin cambios: la pista vuelve a la toma analizada"
                    onClicked: root.seq.pitchApply()
                }
            }
            Text { width: parent.width; elide: Text.ElideRight
                   text: root.peHere ? root.peSelInfo()
                         : root.pe && root.pe.trackId >= 0 && root.pe.trackId !== root.trackId ? "Las notas analizadas son de otra pista: analiza esta"
                         : "Analiza la pista para ver sus notas"
                   color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            // --- rollo de notas ---
            Rectangle {
                id: peBox
                width: parent.width; height: 210
                color: Theme.screen; border.width: Theme.border; border.color: peFocusItem.activeFocus ? Theme.focus : Theme.screenLine; radius: Theme.radius
                Canvas {
                    id: peCanvas
                    objectName: "pitchRoll"
                    anchors.fill: parent; anchors.margins: 4
                    property var p: root.pe
                    property var s: root.sel
                    property real v0: root.viewStart
                    property real vl: root.viewLen
                    property color ink: Theme.screenInk
                    property color dim: Theme.screenDim
                    property color lcd: Theme.lcd
                    property color hot: Theme.accent
                    property color edited: Theme.pc.afina
                    property real lo: 57
                    property real hi: 69
                    onPChanged: requestPaint(); onSChanged: requestPaint(); onV0Changed: requestPaint(); onVlChanged: requestPaint()
                    onInkChanged: requestPaint(); onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
                    function rgba(c, a) { return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }
                    function xAt(t) { return (t - v0) / vl * width }
                    function yAt(m) { return 16 + (height - 16) * (hi - m) / (hi - lo) }
                    function rowH() { return (height - 16) / (hi - lo) }
                    function noteAt(x, y) {
                        if (!root.peHere) return -1
                        var t = v0 + x / width * vl, best = -1, bd = 1e9
                        for (var i = 0; i < p.notes.length; i++) {
                            var n = p.notes[i]
                            if (t < n.start - 0.03 || t > n.end + 0.03) continue
                            var d = Math.abs(yAt(n.midi + n.shift) - y)
                            if (d < bd) { bd = d; best = i }
                        }
                        return bd <= Math.max(14, 1.5 * rowH()) ? best : -1
                    }
                    onPaint: {
                        var ctx = getContext("2d"); ctx.reset()
                        if (!root.peHere) return
                        var notes = p.notes, curve = p.curve, hop = p.hop
                        var a = 1e9, b = -1e9
                        notes.forEach(function (n) { if (n.end >= v0 && n.start <= v0 + vl) { a = Math.min(a, n.midi, n.midi + n.shift); b = Math.max(b, n.midi, n.midi + n.shift) } })
                        if (a > b) notes.forEach(function (n) { a = Math.min(a, n.midi); b = Math.max(b, n.midi) })
                        var mid = Math.round((a + b) / 2), span = Math.max(12, Math.ceil(b - a) + 4)
                        hi = mid + span / 2; lo = mid - span / 2
                        ctx.font = "11px sans-serif"
                        for (var k = Math.ceil(lo); k <= Math.floor(hi); k++) {          // filas: las de la escala más claras
                            var ins = root.peIn(k)
                            ctx.fillStyle = ins ? rgba(ink, 0.07) : "rgba(0,0,0,0)"
                            ctx.fillRect(0, yAt(k + 0.5), width, yAt(k - 0.5) - yAt(k + 0.5))
                            ctx.fillStyle = ins ? rgba(ink, 0.6) : rgba(ink, 0.3)
                            if ((k % 12 + 12) % 12 === 0 || (ins && rowH() >= 11)) ctx.fillText(root.noteName(k), 4, yAt(k) + 4)
                        }
                        ctx.fillStyle = rgba(dim, 1)                                               // regla: segundos del proyecto
                        var step = vl > 20 ? 5 : vl > 8 ? 2 : 1
                        for (var sec = Math.ceil((p.fileStart + v0) / step) * step; sec <= p.fileStart + v0 + vl; sec += step) {
                            var xs = xAt(sec - p.fileStart)
                            ctx.fillRect(xs, 0, 1, 6); ctx.fillText(sec + " s", xs + 3, 11)
                        }
                        notes.forEach(function (n, i) {                                   // notas
                            if (n.end < v0 || n.start > v0 + vl) return
                            var on = s.indexOf(i) >= 0, ch = Math.abs(n.shift) > 1e-4 || n.flatten > 0
                            var h = Math.max(6, rowH() * 0.8), w = Math.max(2, xAt(n.end) - xAt(n.start))
                            if (ch) { ctx.strokeStyle = rgba(ink, 0.5); ctx.lineWidth = 1        // de dónde viene
                                      ctx.strokeRect(xAt(n.start), yAt(n.midi) - h / 2, w, h) }
                            ctx.fillStyle = on ? rgba(hot, 1) : ch ? rgba(edited, 1) : rgba(ink, 0.28)
                            ctx.fillRect(xAt(n.start), yAt(n.midi + n.shift) - h / 2, w, h)
                        })
                        function curveLine(edit, color, lw) {                             // tono: original y con cambios
                            ctx.beginPath(); var pen = false, j = 0
                            var f0 = Math.max(0, Math.floor(v0 / hop)), f1 = Math.min(curve.length, Math.ceil((v0 + vl) / hop) + 1)
                            for (var f = f0; f < f1; f++) {
                                var m = curve[f]
                                if (m <= 0) { pen = false; continue }
                                if (edit) {
                                    var t = f * hop
                                    while (j < notes.length && notes[j].end < t) j++
                                    var n = notes[j]
                                    if (n && t >= n.start && t <= n.end) m = m + n.shift + n.flatten * (n.midi - m)
                                }
                                var x = xAt(f * hop), y = yAt(m)
                                if (!pen) { ctx.moveTo(x, y); pen = true } else ctx.lineTo(x, y)
                            }
                            ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.stroke()
                        }
                        if (root.peEdited) curveLine(false, rgba(ink, 0.35), 1)
                        curveLine(true, rgba(lcd, 1), 2)
                    }
                }
                Text { anchors.centerIn: parent; visible: !root.peHere
                       text: root.trackId < 0 ? "Sin pistas" : "«Analizar notas»: aquí salen las notas de «" + root.trackName() + "» y su tono"
                       color: Theme.screenDim; font.family: Theme.font; font.pixelSize: 13 }
                Item {
                    id: peFocusItem
                    anchors.fill: parent
                    Keys.onPressed: function (e) {
                        if (!root.peHere) return
                        var fine = e.modifiers & Qt.ShiftModifier
                        if (e.key === Qt.Key_Up) { root.peNudge(fine ? 0.1 : 1); e.accepted = true }
                        else if (e.key === Qt.Key_Down) { root.peNudge(fine ? -0.1 : -1); e.accepted = true }
                        else if (e.key === Qt.Key_Left || e.key === Qt.Key_Right) {
                            var i = root.sel.length ? root.sel[root.sel.length - 1] : -1
                            i = Math.max(0, Math.min(root.pe.notes.length - 1, i + (e.key === Qt.Key_Right ? 1 : -1)))
                            root.sel = [i]
                            var n = root.pe.notes[i]
                            if (n.start < root.viewStart || n.end > root.viewStart + root.viewLen) root.viewStart = Math.max(0, n.start - root.viewLen * 0.2)
                            e.accepted = true
                        }
                        else if (e.key === Qt.Key_A && (e.modifiers & Qt.ControlModifier)) { root.sel = root.pe.notes.map(function (n, k) { return k }); e.accepted = true }
                        else if (e.key === Qt.Key_Escape) { root.sel = []; e.accepted = true }
                    }
                }
                MouseArea {
                    anchors.fill: parent; anchors.margins: 4
                    enabled: root.peHere
                    hoverEnabled: true
                    preventStealing: true
                    property real y0: 0
                    property var base: []
                    property bool dragged: false
                    onPressed: function (m) {
                        peFocusItem.forceActiveFocus()
                        var i = peCanvas.noteAt(m.x, m.y)
                        if (m.modifiers & Qt.ShiftModifier) {
                            if (i >= 0) root.sel = root.sel.indexOf(i) >= 0 ? root.sel.filter(function (k) { return k !== i }) : root.sel.concat([i])
                        } else if (i < 0) root.sel = []
                        else if (root.sel.indexOf(i) < 0) root.sel = [i]
                        y0 = m.y; dragged = false
                        base = root.pe.notes.map(function (n) { return n.shift })
                    }
                    onPositionChanged: function (m) {
                        if (!pressed || !root.sel.length) return
                        var st = Math.round((y0 - m.y) / peCanvas.rowH())               // arrastrar: semitonos enteros
                        if (!dragged && st === 0) return
                        dragged = true
                        var b = base
                        root.seq.pitchSetNotes(root.pe.notes.map(function (n, i) {
                            return root.sel.indexOf(i) >= 0 ? Object.assign({}, n, { shift: Math.round((b[i] + st) * 100) / 100 }) : n }))
                    }
                    onWheel: function (w) {
                        if (w.modifiers & Qt.ControlModifier) {
                            var c = root.viewStart + root.viewLen / 2
                            root.viewLen = Math.max(2, Math.min(Math.max(2, root.pe.seconds), root.viewLen * (w.angleDelta.y > 0 ? 0.8 : 1.25)))
                            root.viewStart = Math.max(0, Math.min(root.pe.seconds - root.viewLen, c - root.viewLen / 2))
                        } else {
                            var d = (w.angleDelta.y !== 0 ? -w.angleDelta.y : w.angleDelta.x) / 120 * root.viewLen * 0.15
                            root.viewStart = Math.max(0, Math.min(Math.max(0, root.pe.seconds - root.viewLen), root.viewStart + d))
                        }
                    }
                    ToolTipLite { show: parent.containsMouse && !parent.pressed
                                  text: "Clic: elegir nota · Mayús+clic: varias · arrastrar arriba/abajo: semitonos · ↑/↓: ±1 st · Mayús+↑/↓: ±10 cents · ←/→: nota anterior/siguiente · Ctrl+A: todas · Esc: ninguna · rueda: avanzar · Ctrl+rueda: zoom" }
                }
            }
            // --- barra de desplazamiento ---
            Rectangle {
                objectName: "pitchScroll"
                width: parent.width; height: 24; color: Theme.input; border.width: 1; border.color: Theme.line; radius: Theme.radius
                visible: root.peHere
                readonly property real total: root.peHere ? Math.max(root.viewLen, root.pe.seconds) : 1
                Rectangle { y: 2; height: 20; radius: Theme.radius; color: Theme.button; border.width: 1; border.color: Theme.line
                            x: 2 + (parent.width - 4) * root.viewStart / parent.total
                            width: Math.max(24, (parent.width - 4) * root.viewLen / parent.total) }
                MouseArea { anchors.fill: parent; preventStealing: true
                            function at(x) { var t = x / width * parent.total - root.viewLen / 2
                                             root.viewStart = Math.max(0, Math.min(parent.total - root.viewLen, t)) }
                            onPressed: function (m) { at(m.x) }
                            onPositionChanged: function (m) { if (pressed) at(m.x) } }
            }
            Flow {
                width: parent.width; spacing: 6
                enabled: root.peHere && !!root.seq && !root.seq.pitchBusy; opacity: enabled ? 1 : 0.55
                NeoButton { text: "−1 st"; fontSize: 13; padX: 8; padY: 4; tip: "Baja un semitono las notas elegidas (↓)"; onClicked: root.peNudge(-1) }
                NeoButton { text: "+1 st"; fontSize: 13; padX: 8; padY: 4; tip: "Sube un semitono las notas elegidas (↑)"; onClicked: root.peNudge(1) }
                NeoButton { text: "−10 c"; fontSize: 13; padX: 8; padY: 4; tip: "Baja 10 cents las notas elegidas (Mayús+↓)"; onClicked: root.peNudge(-0.1) }
                NeoButton { text: "+10 c"; fontSize: 13; padX: 8; padY: 4; tip: "Sube 10 cents las notas elegidas (Mayús+↑)"; onClicked: root.peNudge(0.1) }
                NeoButton {
                    objectName: "pitchFlatten"
                    readonly property bool on: root.peHere && root.sel.length > 0 && root.sel.every(function (i) { return !!root.pe.notes[i] && root.pe.notes[i].flatten > 0 })
                    text: "Enderezar"; fontSize: 13; padX: 8; padY: 4; pressedState: on
                    color: on ? Theme.pc.afina : Theme.button; textColor: on ? Theme.inkOnColor : Theme.ink
                    tip: on ? "Clic: devolver el vibrato y la deriva a las notas elegidas" : "Lleva cada instante de las notas elegidas a su centro: quita vibrato y deriva"
                    onClicked: root.peFlat()
                }
                NeoButton {
                    objectName: "pitchToScale"
                    text: "A la escala"; fontSize: 13; padX: 8; padY: 4
                    tip: "Pone el centro de las notas elegidas (o de todas, si no hay ninguna elegida) en la nota más cercana de " + root.peScaleName()
                    onClicked: root.peToScale()
                }
                NeoButton {
                    text: arming ? "¿Quitar?" : "Quitar cambios"; confirm: "¿Quitar?"; fontSize: 13; padX: 8; padY: 4
                    tip: root.sel.length ? "Deja las notas elegidas como en la toma (segundo clic para confirmar)"
                                         : "Deja todas las notas como en la toma (segundo clic para confirmar)"
                    onClicked: root.peReset()
                }
            }
        }
    }
}
