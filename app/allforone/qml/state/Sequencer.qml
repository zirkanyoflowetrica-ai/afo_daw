import QtQuick
import "../theme"
import "layout.js" as L

// Pistas de Instrumento, Batería, Voz e IA de la plantilla (mk, addT, pick, basic, piano roll, patrón…).
// Instrumento y Batería suenan con el sintetizador del motor C++ (plugin de Tracktion que toca un
// clip MIDI): editar una nota solo rehace el clip, sin renderizar. Las de Voz graban con el motor
// (Tracktion escribe el WAV desde la entrada del dispositivo). Las de IA son la DEMO de la
// plantilla: clips de ejemplo, sin audio.
QtObject {
    id: sq
    property var studio
    property int uidN: 0
    property var act: ({ inst: "", drum: "", ia: "", voz: "" })   // pista activa de cada módulo (uid)
    property int oct: 4
    property bool sus: false
    property var draftIa: ({ prompt: "", style: "Lo-fi", cre: 60, den: 40 })
    property bool generating: false
    // Grabador de cintas: entrada del dispositivo, escucha por los altavoces y toma en curso
    property var inputs: []
    property string input: ""
    property bool monitor: false
    property bool recording: false
    property string armedUid: ""

    readonly property var src: ({ inst: "inst", drum: "drums", ia: "ia", voz: "cinta", audio: "pistas" })
    readonly property var tn: ({ inst: "Instrumento", drum: "Batería", ia: "IA", voz: "Voz", audio: "Audio" })
    readonly property var insts: [["Piano de cola", "Teclas"], ["Bajo sintético", "Graves"], ["Batería acústica", "Percusión"],
        ["Guitarra eléctrica", "Cuerdas"], ["Pad ambiental", "Sintetizador"], ["Cuerdas de orquesta", "Cuerdas"],
        ["Voz coral", "Voces"], ["Campanas", "Percusión"]]
    readonly property var notes: ["C5", "B4", "A#4", "A4", "G#4", "G4", "F#4", "F4", "E4", "D#4", "D4", "C#4", "C4"]
    readonly property var base: [523.25, 493.88, 466.16, 440, 415.3, 392, 369.99, 349.23, 329.63, 311.13, 293.66, 277.18, 261.63]
    readonly property var dn: ["Bombo", "Caja", "Hi-hat", "Hi-hat abierto", "Palmas", "Tom", "Platillo", "Cencerro"]
    readonly property var styles: ["Lo-fi", "Funk", "Ambient", "Rock", "Electrónica"]

    property Timer genTimer: Timer { interval: 1100; onTriggered: sq.finishGenerate() }

    // ---------------- acceso ----------------
    function indexOf(uid) { for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].uid === uid) return i; return -1 }
    function trackOf(uid) { var i = indexOf(uid); return i >= 0 ? studio.tracks[i] : null }
    function active(type) { return trackOf(act[type]) }
    function isSynth(t) { return t.type === "inst" || t.type === "drum" }
    function disconnected(t) { return t.type !== "audio" && !!studio.hidden[src[t.type]] }
    function cfgOf(type) { var t = active(type); return t ? t.cfg : (type === "ia" ? draftIa : {}) }
    function sub(t) {
        if (disconnected(t)) return "módulo desconectado"
        if (t.type === "inst") return "síntesis · " + insts[t.cfg.v][0]
        if (t.type === "drum") return "síntesis · 16 pasos"
        if (t.type === "ia") return "DEMO · " + t.cfg.style + " · sin audio"
        if (t.type === "voz") return t.len > 0 ? "toma " + L.fmt(t.len) + " · motor nativo" : "sin toma · graba en Grabador de cintas"
        return ""
    }
    function replace(uid, changes) {
        var i = indexOf(uid); if (i < 0) return null
        var t = studio.tracks.slice()
        t[i] = Object.assign({}, t[i], changes)
        studio.tracks = t
        return t[i]
    }

    // ---------------- crear, elegir, quitar ----------------
    function mk(type, name) {
        var t = { uid: "s" + (++uidN), id: -1, type: type, name: name, len: 0, peaks: [], note: "",
                  mute: false, solo: false, vol: 70, pan: 50, clips: [], cfg: {}, roll: {}, pat: {} }
        if (type === "inst") { t.cfg = { v: 0, vel: 70, bri: 50, rev: 30 }; t.clips = [[0, 50], [62.5, 37.5]] }
        if (type === "drum") { t.cfg = { vol: 80, tun: 50, sw: 20 }; t.clips = [[0, 100]] }
        if (type === "ia") t.cfg = Object.assign({}, draftIa)
        if (type === "voz") t.start = 0
        return t
    }
    function basic() {
        var p = {}
        ;[0, 4, 8, 12].forEach(function (s) { p["0-" + s] = 1 })
        ;[4, 12].forEach(function (s) { p["1-" + s] = 1 })
        ;[0, 2, 4, 6, 8, 10, 12, 14].forEach(function (s) { p["2-" + s] = 1 })
        p["3-14"] = 1
        return p
    }
    function push(t) {
        if (isSynth(t)) t.id = engineTrack(t)
        if (t.type === "voz") t.id = recTrack(t)
        var a = studio.tracks.slice(); a.push(t); studio.tracks = a
        var c = Object.assign({}, act); c[t.type] = t.uid; act = c
        studio.selected = a.length - 1
        if (isSynth(t)) update(t.uid)
        if (t.type === "voz") arm()
    }
    // Pista del motor con el sintetizador (−1 si el motor no está disponible)
    function engineTrack(t) {
        if (!studio.engineOk) return -1
        var r = studio.call("synthCreate", t.name, t.type === "drum" ? 1 : 0)
        if (!r.ok) { studio.toast(r.error); return -1 }
        return r.track.id
    }
    function recTrack(t) {
        if (!studio.engineOk) return -1
        var r = studio.call("recCreate", t.name)
        if (!r.ok) { studio.toast(r.error); return -1 }
        return r.track.id
    }
    function addTrack(type) {
        var n = studio.tracks.filter(function (x) { return x.type === type }).length + 1
        var t = mk(type, tn[type] + " " + n)
        if (type === "drum") t.pat = basic()
        if (studio.hidden[src[type]]) studio.setHidden(src[type], false)
        push(t)
        return t
    }
    // Las 3 pistas con las que arranca la plantilla
    function createDefaults() {
        var a = mk("inst", "Acordes"), b = mk("inst", "Bajo"), d = mk("drum", "Batería 1")
        b.cfg.v = 1
        ;[[0, 0], [4, 4], [7, 5], [10, 6], [3, 8], [6, 10], [9, 12]].forEach(function (rc) { a.roll[rc[0] + "-" + rc[1]] = 1 })
        ;[[12, 0], [12, 6], [12, 8], [10, 12], [12, 14]].forEach(function (rc) { b.roll[rc[0] + "-" + rc[1]] = 1 })
        d.pat = basic()
        a.id = engineTrack(a); b.id = engineTrack(b); d.id = engineTrack(d)
        var t = studio.tracks.slice(); t.unshift(a, b, d); studio.tracks = t
        act = { inst: a.uid, drum: d.uid, ia: "", voz: "" }
        studio.selected = 0
        update(a.uid); update(b.uid); update(d.uid)
    }
    function pick(i) {
        var t = studio.tracks[i]; if (!t) return
        studio.selected = i
        if (act[t.type] !== undefined) { var c = Object.assign({}, act); c[t.type] = t.uid; act = c }
        if (t.type === "voz") arm()
    }
    function forget(t) {
        if (t.type === "voz" && t.uid === armedUid) { if (recording) stopTake(true); armedUid = "" }
        if ((isSynth(t) || t.type === "voz") && t.id >= 0) studio.call("removeTrack", t.id)
        var c = Object.assign({}, act)
        for (var k in c) if (c[k] === t.uid) {
            var other = studio.tracks.filter(function (x) { return x.type === k && x.uid !== t.uid })[0]
            c[k] = other ? other.uid : ""
        }
        act = c
        if (t.type === "voz") Qt.callLater(arm)
    }

    // ---------------- Grabador de cintas (graba el motor) ----------------
    function refreshInputs() {
        var r = studio.engineOk ? studio.call("recInputs") : { ok: false }
        inputs = r.ok ? r.inputs : []
        if (inputs.indexOf(input) < 0) input = inputs.length ? inputs[0] : ""
    }
    // Arma la pista de voz activa en la entrada elegida; sin pista o con el módulo quitado, desarma
    function arm() {
        if (!studio.engineOk || recording) return
        var t = active("voz")
        if (!t || t.id < 0 || studio.hidden.cinta) {
            if (armedUid) studio.call("recArm", -1, "", false)
            armedUid = ""; return
        }
        refreshInputs()
        if (!inputs.length) { armedUid = ""; return }
        var r = studio.call("recArm", t.id, input, monitor)
        armedUid = r.ok ? t.uid : ""
        if (!r.ok) studio.toast(r.error)
    }
    function setInput(v) { input = v; arm() }
    function setMonitor(b) { monitor = b; arm() }
    function startTake() {
        var t = active("voz")
        if (!t) { studio.toast("Crea una pista de voz primero"); return }
        if (recording) return
        if (armedUid !== t.uid) arm()
        if (armedUid !== t.uid) {
            if (!inputs.length) studio.toast("El dispositivo de audio no tiene entradas: elige otro en «Audio» (p. ej. ASIO4ALL)")
            return
        }
        var r = studio.call("recStart")
        if (!r.ok) { studio.toast(r.error); return }
        recording = true
    }
    function stopTake(discard) {
        if (!recording) return
        recording = false
        var r = studio.call("recStop", !!discard)
        if (!r.ok) { studio.toast(r.error); return }
        var info = r.track, t = null
        for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === info.id) t = studio.tracks[i]
        if (!t || discard) return
        if (!info.source_path) { studio.toast("La toma quedó vacía"); return }
        replace(t.uid, { len: info.length_seconds, peaks: info.peaks, start: info.start_seconds || 0, aclips: studio.clipsOf(t.id) })
        studio.mixer.unlinkTrack(info.id)
        studio.mixer.linkTrack(info)
        studio.toast("Toma guardada en " + t.name + " (" + L.fmt(info.length_seconds) + ")")
    }
    function listenTake() {
        var t = active("voz")
        if (!t || t.id < 0) { studio.toast("Crea una pista de voz primero"); return }
        var r = studio.call("recListen", t.id)
        if (!r.ok) studio.toast(r.error)
    }

    // ---------------- sintetizador del motor ----------------
    // Manda parámetros y patrón a la pista del motor (settingsOnly: solo parámetros, p. ej. al girar una perilla)
    function update(uid, settingsOnly) {
        var t = trackOf(uid)
        if (!t || !isSynth(t) || t.id < 0) return
        var r = studio.call("synthUpdate", t.id, JSON.stringify({
            type: t.type, cfg: t.cfg, clips: t.clips, roll: t.roll, pat: t.pat,
            sus: t.type === "inst" && sus, settingsOnly: !!settingsOnly }))
        if (!r.ok) studio.toast(r.error)
        else if (r.length >= 0 && r.length !== t.len) replace(uid, { len: r.length })
    }
    function rerenderAll(type) {
        studio.tracks.forEach(function (t) { if (isSynth(t) && (!type || t.type === type)) update(t.uid) })
    }
    function audition(data) {
        if (!studio.engineOk) return
        var r = studio.call("synthAudition", JSON.stringify(data))
        if (!r.ok && r.error) studio.toast(r.error)
    }
    function noteDur(d) { return sus ? 1.4 : (d || 0.4) }
    function previewNote(cfg, freq, d) {
        var note = Math.round(69 + 12 * Math.log(freq / 440) / Math.LN2)
        audition({ type: "inst", cfg: cfg, note: note, seconds: noteDur(d) })
    }
    function previewMidi(cfg, note, d) { audition({ type: "inst", cfg: cfg, note: note, seconds: noteDur(d) }) }
    function previewDrum(cfg, i) { audition({ type: "drum", cfg: cfg, lane: i }) }

    // ---------------- Instrumentos y Piano roll ----------------
    function setCfg(type, key, value) {
        var t = active(type)
        if (!t) { if (type === "ia") { var d = Object.assign({}, draftIa); d[key] = value; draftIa = d } return }
        var c = Object.assign({}, t.cfg); c[key] = value
        replace(t.uid, { cfg: c })
        if (isSynth(t)) update(t.uid, key !== "sw")   // el swing mueve las notas; el resto solo son parámetros
    }
    function setVoice(v) {
        var t = active("inst"); if (!t) return
        setCfg("inst", "v", ((v % insts.length) + insts.length) % insts.length)
    }
    function toggleRoll(r, c) {
        var t = active("inst"); if (!t) return
        var roll = Object.assign({}, t.roll), k = r + "-" + c
        if (roll[k]) delete roll[k]; else { roll[k] = 1; previewNote(t.cfg, base[r]) }
        replace(t.uid, { roll: roll }); update(t.uid)
    }
    function clearRoll() { var t = active("inst"); if (t) { replace(t.uid, { roll: {} }); update(t.uid) } }
    function setOct(d) { oct = Math.max(1, Math.min(7, oct + d)) }
    function toggleSus() { sus = !sus; rerenderAll("inst") }

    // ---------------- Batería ----------------
    function toggleStep(lane, s) {
        var t = active("drum"); if (!t) return
        var p = Object.assign({}, t.pat), k = lane + "-" + s
        if (p[k]) delete p[k]; else { p[k] = 1; previewDrum(t.cfg, lane) }
        replace(t.uid, { pat: p }); update(t.uid)
    }
    function clearPat() { var t = active("drum"); if (t) { replace(t.uid, { pat: {} }); update(t.uid) } }
    function basicPat() { var t = active("drum"); if (t) { replace(t.uid, { pat: basic() }); update(t.uid) } }

    // ---------------- Pistas con IA (DEMO de la plantilla) ----------------
    function genClips(den) {
        var cl = [], x = 0
        while (x < 90) {
            var l = 12.5 * (1 + Math.floor(Math.random() * 2))
            cl.push([x, Math.min(l, 100 - x)])
            x += l + 12.5 * Math.floor(Math.random() * (1 + (100 - den) / 50))
        }
        return cl
    }
    function generate() { if (!generating) { generating = true; genTimer.start() } }
    function finishGenerate() {
        var c = Object.assign({}, cfgOf("ia")), t = mk("ia", "")
        t.cfg = c
        t.name = "IA " + c.style + " " + (studio.tracks.filter(function (x) { return x.type === "ia" }).length + 1)
        t.clips = genClips(c.den)
        if (studio.hidden.ia) studio.setHidden("ia", false)
        push(t)
        generating = false
        studio.toast("Pista de IA de demostración creada y conectada (sin audio)")
    }
    function regenerate() {
        var t = active("ia"); if (!t) return
        replace(t.uid, { clips: genClips(t.cfg.den) })
        studio.toast("Clips de demostración regenerados")
    }
}
