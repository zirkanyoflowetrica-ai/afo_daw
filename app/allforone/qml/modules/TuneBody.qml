import QtQuick
import "../theme"
import "../controls"

// Afinador Pitch AT-60: interfaz del efecto nativo «tune» (AF-60, afinación en tiempo real en el motor).
// Pantalla con la nota que se canta, la aguja de desafinación y la corrección aplicada; gráfica de tono
// de los últimos segundos (detectado frente a destino); teclado con las notas de la escala.
// Debajo, el Editor de tono (AF-64): las notas de la toma, movidas una a una y aplicadas como copia.
// Abajo, cómo afina la Mezcla IA al mezclar: Precisa (PSOLA, copia afinada) o En vivo (este AF-60).
Column {
    id: root
    property var mixer
    readonly property var studio: mixer ? mixer.studio : null
    readonly property var tn: mixer.tune
    width: parent ? parent.width : 620
    spacing: 8

    // --- pista y efecto ---
    property int trackId: -1
    property var fx: null                     // efecto «tune» de la pista (o null)
    property var desc: null                   // descripción del catálogo
    property var meters: []                   // [entrada, salida, nota, destino, corrección cents]
    property var hist: []                     // [[nota detectada, destino], …] de los últimos segundos
    readonly property int histLen: 240        // 8 s a 30 Hz
    readonly property var noteNames: ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]
    readonly property var masks: [0xFFF, 0xAB5, 0x5AD, 0x9AD, 0x295, 0x4A9]
    readonly property var tracks: studio ? studio.tracks.filter(function (t) { return t.id >= 0 && t.type !== "aux" }) : []

    function pv(id) {
        if (!fx || !desc) return 0
        for (var i = 0; i < desc.params.length; i++) if (desc.params[i].id === id) return fx.values[i] !== undefined ? fx.values[i] : desc.params[i].def
        return 0
    }
    function pdesc(id) { if (desc) for (var i = 0; i < desc.params.length; i++) if (desc.params[i].id === id) return desc.params[i]; return null }
    function noteName(m) { if (m <= 0) return "—"; var n = Math.round(m); return noteNames[(n % 12 + 12) % 12] + (Math.floor(n / 12) - 1) }
    function inScale(pc) { var k = Math.round(pv("key")), s = Math.round(pv("scale")); return (masks[s] >> (((pc - k) % 12 + 12) % 12)) & 1 }
    function guessTrack() {
        var best = -1
        for (var i = 0; i < tracks.length && best < 0; i++) { var it = mixer.itemOfTrack(tracks[i].id); if (it && it.role === "P") best = tracks[i].id }
        for (var j = 0; j < tracks.length && best < 0; j++) if (/voz|vocal|voice/i.test(tracks[j].name)) best = tracks[j].id
        if (best < 0 && tracks.length) best = tracks[0].id
        return best
    }
    function load() {
        if (!studio || !studio.engineOk) { fx = null; return }
        if (!desc) { var c = studio.call("fxCatalog"); if (c.ok) desc = c.catalog.filter(function (d) { return d.key === "tune" })[0] || null }
        if (trackId < 0 || !tracks.some(function (t) { return t.id === trackId })) trackId = guessTrack()
        if (trackId < 0) { fx = null; return }
        var r = studio.call("fxList", trackId)
        fx = r.ok ? (r.chain.filter(function (e) { return e.key === "tune" })[0] || null) : null
    }
    function insert() {
        var r = studio.call("fxAdd", trackId, "tune", 0)           // primero de la cadena, como en un estudio
        if (!r.ok) { studio.toast(r.error); return }
        studio.fxCountChanged(); studio.dirty = true
        load()
        if (mixer.tune.confirmed) useAnalysis()
        studio.toast("Afinador insertado al principio de la cadena de «" + trackName() + "»")
    }
    function remove() {
        if (!fx) return
        var r = studio.call("fxRemove", fx.id, trackId)
        if (!r.ok) { studio.toast(r.error); return }
        studio.fxCountChanged(); studio.dirty = true; fx = null; hist = []
    }
    function setP(id, v) {
        if (!fx) return
        if (!studio.autoWrite("fx", fx.id, id, v)) studio.call("fxParam", fx.id, id, v)
        var vals = fx.values.slice()
        for (var i = 0; i < desc.params.length; i++) if (desc.params[i].id === id) vals[i] = v
        fx = Object.assign({}, fx, { values: vals }); studio.dirty = true
    }
    function releaseP(id) { if (fx) studio.autoRelease("fx", fx.id, id, pv(id)) }
    function trackName() { for (var i = 0; i < tracks.length; i++) if (tracks[i].id === trackId) return tracks[i].name; return "" }
    // Tonalidad del análisis de la Mezcla IA (C… B, «Mayor»…) → parámetros del efecto
    function useAnalysis() {
        var src = mixer.tune.confirmed || mixer.tune
        var k = mixer.keys.indexOf(src.key)
        var sc = ({ "Cromatica": 0, "Mayor": 1, "Menor natural": 2, "Menor armonica": 3, "Pentatonica mayor": 4, "Pentatonica menor": 5 })[src.scale]
        if (k >= 0) setP("key", k)
        if (sc !== undefined) setP("scale", sc)
        studio.toast("Tonalidad aplicada al afinador: " + noteNames[Math.max(0, k)] + " " + (pdesc("scale") ? pdesc("scale").choices[sc || 0] : ""))
    }
    // Rango de 0..100 de la perilla ↔ valor con centro (como las perillas de Efectos)
    function toPos(p, v) {
        var x = (v - p.min) / Math.max(1e-9, p.max - p.min)
        if (p.centre > p.min && p.centre < p.max) x = Math.pow(Math.max(0, x), Math.log(0.5) / Math.log((p.centre - p.min) / (p.max - p.min)))
        return 100 * Math.max(0, Math.min(1, x))
    }
    function fromPos(p, pos) {
        var x = Math.max(0, Math.min(1, pos / 100))
        if (p.centre > p.min && p.centre < p.max) x = Math.pow(x, 1 / (Math.log(0.5) / Math.log((p.centre - p.min) / (p.max - p.min))))
        return p.min + x * (p.max - p.min)
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

    onTrackIdChanged: { hist = []; load() }
    Component.onCompleted: load()
    Connections {
        target: root.studio
        function onFxRevChanged() { root.load() }
        function onTracksChanged() { Qt.callLater(root.load) }
        function onEngineOkChanged() { root.load() }
    }
    Timer {                                   // medidores del efecto: ~30 por segundo mientras suena
        interval: 33; repeat: true
        running: !!root.fx && !!root.studio && root.studio.playing && root.visible
        onTriggered: {
            var r = root.studio.call("fxMeters", root.fx.id)
            if (!r.ok) return
            root.meters = r.m
            var h = root.hist.slice(); h.push([r.m[2] || 0, r.m[3] || 0])
            if (h.length > root.histLen) h.splice(0, h.length - root.histLen)
            root.hist = h
        }
    }

    // ---------------- cabecera: pista ----------------
    Row {
        width: root.width; spacing: 8
        Text { anchors.verticalCenter: parent.verticalCenter; text: "Pista"; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
        Select {
            width: 230
            options: root.tracks.map(function (t) { return t.name })
            current: root.trackName()
            onPicked: function (v) { for (var i = 0; i < root.tracks.length; i++) if (root.tracks[i].name === v) { root.trackId = root.tracks[i].id; break } }
        }
        NeoButton {
            visible: !root.fx && root.trackId >= 0
            text: "Insertar afinador"; color: Theme.accent; textColor: "#000"
            tip: "Pone el afinador en tiempo real al principio de la cadena de esta pista"
            onClicked: root.insert()
        }
        NeoButton {
            visible: !!root.fx
            readonly property bool on: !!root.fx && root.fx.enabled
            text: on ? "Activo" : "Puenteado"; pressedState: on
            color: on ? Theme.accent : Theme.button; textColor: on ? "#000" : Theme.ink
            tip: on ? "Clic: puentear (comparar con la voz sin afinar)" : "Clic: volver a afinar"
            onClicked: { root.studio.call("fxEnable", root.fx.id, !on); root.fx = Object.assign({}, root.fx, { enabled: !on }) }
        }
        NeoButton {
            visible: !!root.fx
            text: arming ? "¿Quitar?" : "Quitar"; confirm: "¿Quitar?"
            tip: "Quita el afinador de esta pista (segundo clic para confirmar)"
            onClicked: root.remove()
        }
    }

    Text {
        visible: !root.studio || !root.studio.engineOk || root.trackId < 0 || !root.fx
        width: root.width; wrapMode: Text.Wrap
        text: !root.studio || !root.studio.engineOk ? "Motor nativo no disponible: el afinador corre en el motor."
              : root.trackId < 0 ? "Sin pistas: carga o graba una voz y elígela aquí."
              : "«" + root.trackName() + "» no tiene afinador. «Insertar afinador» lo pone al principio de su cadena; corrige mientras suena y al exportar."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 13
    }

    // ---------------- pantalla ----------------
    Rectangle {
        id: screen
        width: root.width; height: 168
        color: "#0f1014"; border.width: Theme.border; border.color: Theme.line; radius: Theme.radius
        readonly property real det: root.meters.length > 2 ? root.meters[2] : 0
        readonly property real tgt: root.meters.length > 3 ? root.meters[3] : 0
        readonly property real corr: root.meters.length > 4 ? root.meters[4] : 0
        readonly property bool live: !!root.fx && root.studio && root.studio.playing && det > 0
        // nota cantada
        Column {
            x: 16; y: 12; width: 150
            Text { text: "NOTA"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
            Text { text: screen.live ? root.noteName(screen.det) : "—"; color: Theme.lcd
                   font.family: Theme.font; font.pixelSize: 44; font.weight: 800 }
            Text { text: screen.live ? (((screen.det - Math.round(screen.det)) * 100 >= 0 ? "+" : "") + Math.round((screen.det - Math.round(screen.det)) * 100) + " cents") : (root.studio && root.studio.playing ? "sin voz" : "en pausa")
                   color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        }
        // aguja de desafinación: −50 … +50 cents respecto a la nota destino
        Item {
            id: needle
            x: 180; y: 16; width: parent.width - 180 - 160; height: 70
            readonly property real off: screen.live ? Math.max(-50, Math.min(50, (screen.det - screen.tgt) * 100)) : 0
            Repeater {
                model: 11
                Rectangle { required property int index
                            x: needle.width * index / 10 - 1; y: index === 5 ? 6 : 18; width: 2; height: index === 5 ? 40 : 18
                            color: index === 5 ? Theme.lcd : Qt.rgba(1, 1, 1, 0.35) }
            }
            Text { x: 0; y: 46; text: "−50"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; y: 46; text: "0"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11 }
            Text { anchors.right: parent.right; y: 46; text: "+50"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11 }
            Rectangle {
                width: 4; height: 44; y: 2; radius: 2; color: "#ffffff"
                x: needle.width / 2 + needle.off / 50 * needle.width / 2 - 2
                visible: screen.live
                Behavior on x { NumberAnimation { duration: 60 } }
            }
        }
        // corrección aplicada
        Item {
            x: 180; y: 100; width: needle.width; height: 26
            Rectangle { y: 10; width: parent.width; height: 6; color: Qt.rgba(1, 1, 1, 0.12) }
            Rectangle {
                readonly property real c: Math.max(-100, Math.min(100, screen.corr)) / 100
                y: 10; height: 6; color: Theme.lcd
                x: parent.width / 2 + Math.min(0, c) * parent.width / 2; width: Math.abs(c) * parent.width / 2
            }
            Text { y: -8; text: "CORRECCIÓN"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
        }
        Text { x: 180; y: 134; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
               text: (screen.corr >= 0 ? "+" : "") + Math.round(screen.corr) + " cents aplicados" }
        // nota destino
        Column {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 12; width: 130
            Text { anchors.right: parent.right; text: "DESTINO"; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
            Text { anchors.right: parent.right; text: screen.live ? root.noteName(screen.tgt) : "—"; color: Theme.lcd
                   font.family: Theme.font; font.pixelSize: 44; font.weight: 800 }
            Text { anchors.right: parent.right; color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
                   text: root.fx ? root.noteNames[Math.round(root.pv("key"))] + " " + (root.pdesc("scale") ? root.pdesc("scale").choices[Math.round(root.pv("scale"))] : "") : "" }
        }
    }

    // ---------------- gráfica de tono ----------------
    Rectangle {
        width: root.width; height: 150
        color: "#0f1014"; border.width: Theme.border; border.color: Theme.line; radius: Theme.radius
        Canvas {
            id: graph
            anchors.fill: parent; anchors.margins: 4
            property var h: root.hist
            property color k: Theme.lcd
            onHChanged: requestPaint(); onKChanged: requestPaint(); onWidthChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                var pts = h.filter(function (q) { return q[0] > 0 })
                var lo = 1e9, hi = -1e9
                pts.forEach(function (q) { lo = Math.min(lo, q[0], q[1]); hi = Math.max(hi, q[0], q[1]) })
                if (!pts.length) { lo = 57; hi = 69 }
                var mid = Math.round((lo + hi) / 2), span = Math.max(12, Math.ceil(hi - lo) + 4)
                var top = mid + span / 2, bot = mid - span / 2
                var Y = function (m) { return height * (top - m) / (top - bot) }
                ctx.font = "11px sans-serif"
                for (var n = Math.ceil(bot); n <= Math.floor(top); n++) {      // filas de notas (las de la escala más claras)
                    var ins = root.fx ? root.inScale(n) : 1
                    ctx.fillStyle = ins ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.0)"
                    ctx.fillRect(0, Y(n + 0.5), width, Y(n - 0.5) - Y(n + 0.5))
                    ctx.fillStyle = ins ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.25)"
                    if ((n % 12 + 12) % 12 === 0 || (ins && Y(n - 1) - Y(n) >= 10)) ctx.fillText(root.noteName(n), 4, Y(n) + 4)
                }
                var dx = width / root.histLen, x0 = width - h.length * dx
                function line(idx, color, w) {
                    ctx.beginPath(); var pen = false
                    for (var i = 0; i < h.length; i++) {
                        var v = h[i][idx]
                        if (v <= 0) { pen = false; continue }
                        var x = x0 + i * dx, y = Y(v)
                        if (!pen) { ctx.moveTo(x, y); pen = true } else ctx.lineTo(x, y)
                    }
                    ctx.strokeStyle = color; ctx.lineWidth = w; ctx.stroke()
                }
                ctx.globalAlpha = 0.55; line(1, String(k), 5)     // destino (nota de la escala), banda ancha
                ctx.globalAlpha = 1.0; line(0, "#ffffff", 2)       // lo que se canta
            }
        }
        Text { anchors.right: parent.right; anchors.rightMargin: 8; y: 6
               text: "blanco: lo que se canta · color: la nota de la escala"
               color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 11 }
        Text { anchors.centerIn: parent; visible: !root.hist.some(function (q) { return q[0] > 0 })
               text: !root.fx ? "Sin afinador en la pista"
                     : root.hist.length && root.studio.playing ? "Sin voz en este tramo"
                     : "Pulsa Reproducir: aquí se dibuja el tono de la voz y su corrección"
               color: Theme.lcdSoft; font.family: Theme.font; font.pixelSize: 13 }
    }

    // ---------------- teclado de la escala ----------------
    Row {
        id: keysRow
        width: root.width; height: 44; spacing: 3
        Repeater {
            model: 12
            Rectangle {
                required property int index
                readonly property bool black: [1, 3, 6, 8, 10].indexOf(index) >= 0
                readonly property bool on: root.fx && root.inScale(index)
                readonly property bool now: root.meters.length > 3 && root.meters[3] > 0 && root.studio.playing && (Math.round(root.meters[3]) % 12) === index
                width: (keysRow.width - 33) / 12; height: 44; radius: 3
                color: now ? Theme.lcd : on ? (black ? "#55597a" : "#d9dcef") : (black ? "#202124" : "#5a5c63")
                border.width: 1; border.color: Theme.line
                Text { anchors.centerIn: parent; text: root.noteNames[index]
                       color: parent.now ? "#000" : parent.on && !parent.black ? "#000" : "#e8e8e8"
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                MouseArea { anchors.fill: parent; enabled: !!root.fx; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: root.setP("key", parent.index)
                            ToolTipLite { text: "Clic: tónica = " + root.noteNames[parent.parent.index]; show: parent.containsMouse } }
            }
        }
    }

    // ---------------- controles ----------------
    Row {
        width: root.width; spacing: 10
        enabled: !!root.fx; opacity: root.fx ? 1 : 0.55
        Column {
            spacing: 4; width: 150
            Text { text: "Tónica"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.noteNames; current: root.noteNames[Math.round(root.pv("key"))]
                     onPicked: function (v) { root.setP("key", root.noteNames.indexOf(v)) } }
            Text { text: "Escala"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.pdesc("scale") ? root.pdesc("scale").choices : []
                     current: root.pdesc("scale") ? root.pdesc("scale").choices[Math.round(root.pv("scale"))] : ""
                     onPicked: function (v) { root.setP("scale", root.pdesc("scale").choices.indexOf(v)) } }
            Text { text: "Voz"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.pdesc("range") ? root.pdesc("range").choices : []
                     current: root.pdesc("range") ? root.pdesc("range").choices[Math.round(root.pv("range"))] : ""
                     onPicked: function (v) { root.setP("range", root.pdesc("range").choices.indexOf(v)) } }
        }
        Repeater {
            model: [["speed", "Velocidad"], ["humanize", "Naturalidad"], ["amount", "Intensidad"], ["mix", "Mezcla"]]
            Column {
                required property var modelData
                readonly property var pd: root.pdesc(modelData[0])
                readonly property real v: root.pv(modelData[0])
                spacing: 4; width: (root.width - 150 - 50) / 4
                Knob {
                    anchors.horizontalCenter: parent.horizontalCenter
                    label: parent.modelData[1]
                    value: parent.pd ? root.toPos(parent.pd, parent.v) : 0
                    tip: parent.pd ? parent.pd.help : ""
                    onMoved: function (pos) { if (parent.pd) root.setP(parent.modelData[0], root.fromPos(parent.pd, pos)) }
                    onReleased: root.releaseP(parent.modelData[0])
                }
                Text { anchors.horizontalCenter: parent.horizontalCenter
                       text: parent.modelData[0] === "speed" ? (parent.v < 1 ? "robot" : Math.round(parent.v) + " ms") : Math.round(parent.v) + " %"
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; font.weight: 800 }
            }
        }
    }
    Row {
        spacing: 6
        enabled: !!root.fx; opacity: root.fx ? 1 : 0.55
        NeoButton { text: "Detectar tonalidad"; tip: "Analiza la música (instrumental) y propone tónica y escala"; onClicked: root.mixer.analyze() }
        NeoButton { readonly property var src: root.tn.confirmed || root.tn
                    text: "Usar " + (root.noteNames[root.mixer.keys.indexOf(src.key)] || src.key) + " " + src.scale
                    tip: "Pone en el afinador la tonalidad que dio el análisis"; onClicked: root.useAnalysis() }
        NeoButton { text: "Natural"; tip: "Velocidad 80 ms, naturalidad 40 %"; onClicked: { root.setP("speed", 80); root.setP("humanize", 40) } }
        NeoButton { text: "Robot"; tip: "Velocidad 0 ms: salta de nota en nota (efecto T-Pain)"; onClicked: { root.setP("speed", 0); root.setP("humanize", 0) } }
    }
    Note { width: root.width; visible: !!root.tn.status; text: root.tn.status }

    // ---------------- Editor de tono (AF-64) ----------------
    Rectangle {
        width: root.width; height: peCol.height + 16
        color: Theme.device; border.width: 1; border.color: Theme.deviceBorder; radius: Theme.radius
        Column {
            id: peCol
            x: 10; y: 8; width: parent.width - 20; spacing: 6
            Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.StyledText
                   text: "<b>Editor de tono (AF-64)</b>: las notas de la toma, una a una. Muévelas en semitonos o cents, enderézalas (quita vibrato y deriva) o llévalas a la escala; «Aplicar» escribe una copia que la pista usa con los mismos clips (Ctrl+Z vuelve). El tiempo no cambia."
                   color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13 }
            Row {
                id: peTop
                spacing: 6
                NeoButton {
                    objectName: "pitchAnalyze"
                    text: root.seq && root.seq.pitchBusy === "analyze" ? "Analizando…" : root.peHere ? "Volver a analizar" : "Analizar notas"
                    color: root.peHere ? Theme.button : Theme.accent; textColor: root.peHere ? Theme.ink : "#000"
                    enabled: root.trackId >= 0 && !!root.seq && !root.seq.pitchBusy
                    tip: "Busca las notas de «" + root.trackName() + "» en su audio (el motor lo hace en otro hilo)"
                         + (root.peHere && root.peEdited ? ". Se pierden los cambios sin aplicar" : "")
                    onClicked: { root.sel = []; root.viewStart = 0; root.seq.pitchAnalyze(root.trackId) }
                }
                NeoButton {
                    objectName: "pitchApply"
                    text: root.seq && root.seq.pitchBusy === "apply" ? "Aplicando…" : "Aplicar a la pista"
                    enabled: root.peHere && !root.seq.pitchBusy
                    color: root.peEdited ? Theme.pc.afina : Theme.button; textColor: root.peEdited ? "#000" : Theme.ink
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
                    color: on ? Theme.pc.afina : Theme.button; textColor: on ? "#000" : Theme.ink
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

    // ---------------- afinación sin conexión de la Mezcla IA ----------------
    Rectangle {
        width: root.width; height: offCol.height + 16
        color: Theme.device; border.width: 1; border.color: Theme.deviceBorder; radius: Theme.radius
        Column {
            id: offCol
            x: 10; y: 8; width: parent.width - 20; spacing: 6
            Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.StyledText
                   text: root.tn.method !== "psola"
                         ? "<b>Al mezclar con IA · en vivo</b>: pone este afinador (AF-60) en las voces marcadas con la tonalidad confirmada, la intensidad elegida, velocidad según el tempo y rango según la voz. No toca el audio y se ajusta aquí después."
                         : "<b>Al mezclar con IA · precisa</b>: afina las voces marcadas sin conexión (PSOLA, la más exacta en las pruebas) y pone en su pista una copia <i>_afinada</i>; el original queda intacto."
                   color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13 }
            Row {                              // la Mezcla IA solo afina con una tonalidad confirmada
                spacing: 8
                NeoButton {
                    readonly property bool ok: !!root.tn.confirmed
                    text: ok ? "✓ " + (root.noteNames[root.mixer.keys.indexOf(root.tn.confirmed.key)] || root.tn.confirmed.key) + " "
                               + root.tn.confirmed.scale + " · " + Math.round(root.tn.confirmed.bpm) + " BPM"
                             : "Confirmar " + (root.noteNames[root.mixer.keys.indexOf(root.tn.key)] || root.tn.key) + " " + root.tn.scale
                               + " · " + Math.round(root.tn.bpm) + " BPM"
                    pressedState: ok; color: ok ? Theme.pc.afina : Theme.button; textColor: ok ? "#000" : Theme.ink
                    tip: ok ? "Tonalidad confirmada: la Mezcla IA puede afinar. Clic: volver a confirmar"
                            : "Autoriza a la Mezcla IA a afinar en esta tonalidad (la del análisis; «Detectar tonalidad» la propone)"
                    onClicked: root.mixer.confirmTune()
                }
                NeoButton {
                    readonly property bool on: root.tn.method !== "psola"
                    text: "Efecto nativo (AF-60)"; fontSize: 12; padX: 8; padY: 3; pressedState: on
                    color: on ? Theme.pc.afina : Theme.button; textColor: on ? "#000" : Theme.ink
                    tip: "Por defecto: pone el afinador AF-60 en la cadena de la voz; no escribe audio y se retoca aquí"
                    onClicked: root.mixer.setTune({ method: "live" })
                }
                NeoButton {
                    readonly property bool on: root.tn.method === "psola"
                    text: "Copia precisa (PSOLA)"; fontSize: 12; padX: 8; padY: 3; pressedState: on
                    color: on ? Theme.pc.afina : Theme.button; textColor: on ? "#000" : Theme.ink
                    tip: "Afinación sin conexión (PSOLA de V4.2): algo más exacta, escribe una copia afinada de la voz"
                    onClicked: root.mixer.setTune({ method: "psola" })
                }
            }
            Row {
                spacing: 6
                Repeater {
                    model: [["lead", "Principal"], ["l", "L"], ["r", "R"], ["b", "Dobles / coros"]]
                    NeoButton {
                        required property var modelData
                        readonly property bool on: !!root.tn.voices[modelData[0]]
                        text: modelData[1]; fontSize: 12; padX: 8; padY: 3
                        color: on ? Theme.pc.afina : Theme.button; textColor: on ? "#000" : Theme.ink; pressedState: on
                        onClicked: root.mixer.toggleVoice(modelData[0])
                    }
                }
                Text { anchors.verticalCenter: parent.verticalCenter; leftPadding: 10; text: "Intensidad"; color: Theme.deviceInk
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 120; height: 24; color: Theme.input; border.width: 1; border.color: Theme.line
                    Rectangle { x: 1; y: 1; height: 22; width: (parent.width - 2) * root.mixer.tuneStrength / 100; color: Theme.pc.afina }
                    Text { anchors.centerIn: parent; text: Math.round(root.mixer.tuneStrength) + " %"; color: Theme.ink
                           font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                    MouseArea { anchors.fill: parent; preventStealing: true
                                function at(x) { root.mixer.tuneStrength = Math.round(Math.max(0, Math.min(100, x / width * 100))) }
                                onPressed: function (m) { at(m.x) }
                                onPositionChanged: function (m) { if (pressed) at(m.x) } }
                }
            }
        }
    }
}
