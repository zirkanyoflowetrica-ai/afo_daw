import QtQuick
import "../theme"
import "layout.js" as L

// Pistas de Instrumento, Batería, Voz e IA de la plantilla (mk, addT, pick, basic, piano roll, patrón…).
// Instrumento y Batería suenan con el sintetizador del motor C++ (plugin de Tracktion que toca un
// clip MIDI): editar una nota solo rehace el clip, sin renderizar. Las de Voz graban con el motor
// (Tracktion escribe el WAV desde la entrada del dispositivo). Pistas con IA genera instrumentales
// reales con ACE-Step en el equipo (ai_music.py, en otro proceso): el WAV entra como pista de audio.
QtObject {
    id: sq
    property var studio
    property int uidN: 0
    property var act: ({ inst: "", drum: "", ia: "", voz: "" })   // pista activa de cada módulo (uid)
    property int oct: 4
    property bool sus: false
    property var draftIa: ({ prompt: "", style: "Trap", cre: 50, dur: 60, key: "Auto", inst: true, lyrics: "", bpmSync: true, part: "Guitarra", partPrompt: "" })
    // IA en dos modos: «song» = canción completa en audio (ACE-Step) · «midi» = solo las notas (MIDI-LLM)
    property string iaMode: "song"
    property var draftMidi: ({ prompt: "", len: 2046, cre: 60 })
    property var midiAi: ({ ok: false, engineOk: false, model: { done: false, have: 0, size: 0 }, compositions: [] })
    property bool composing: false
    property bool midiDownloading: false
    property real midiProgress: 0
    property string midiMsg: ""
    property real midiDlProgress: 0
    property string midiDlMsg: ""
    // IA local (ACE-Step): estado del motor y los modelos, avance de la generación y de la descarga
    property var ai: ({ ok: false, engineOk: false, installed: "", packs: [], generations: [], styles: [], keys: [] })
    property bool generating: false
    property bool downloading: false
    property real aiProgress: 0
    property string aiMsg: ""
    property real dlProgress: 0
    property string dlMsg: ""
    // Grabador de cintas: entrada del dispositivo, escucha por los altavoces y toma en curso
    property var inputs: []
    property string input: ""
    property bool monitor: false
    property bool recording: false
    property string armedUid: ""

    readonly property var src: ({ inst: "inst", drum: "drums", ia: "ia", voz: "cinta", audio: "pistas" })
    readonly property var tn: ({ inst: "Instrumento", drum: "Batería", ia: "IA", voz: "Voz", audio: "Audio", aux: "Aux" })
    readonly property var insts: [["Piano de cola", "Teclas"], ["Bajo sintético", "Graves"], ["Batería acústica", "Percusión"],
        ["Guitarra eléctrica", "Cuerdas"], ["Pad ambiental", "Sintetizador"], ["Cuerdas de orquesta", "Cuerdas"],
        ["Voz coral", "Voces"], ["Campanas", "Percusión"], ["Bajo 808", "Graves"], ["Sinte analógico", "Sintetizador"],
        ["Sinte de tablas", "Sintetizador"], ["Sampler", "Tu sonido"]]
    // Filas del Piano roll: C5..C4 en la octava 4; «Octava» las transpone (y lo que suena, X2)
    readonly property var notes: ["C5", "B4", "A#4", "A4", "G#4", "G4", "F#4", "F4", "E4", "D#4", "D4", "C#4", "C4"]
        .map(function (n) { return n.slice(0, -1) + (Number(n.slice(-1)) + oct - 4) })
    readonly property var base: [523.25, 493.88, 466.16, 440, 415.3, 392, 369.99, 349.23, 329.63, 311.13, 293.66, 277.18, 261.63]
        .map(function (f) { return f * Math.pow(2, oct - 4) })
    readonly property var dn: ["Bombo", "Caja", "Hi-hat", "Hi-hat abierto", "Palmas", "Tom", "Platillo", "Cencerro"]
    readonly property var styles: ["Lo-fi", "Funk", "Ambient", "Rock", "Electrónica"]


    // ---------------- acceso ----------------
    function indexOf(uid) { for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].uid === uid) return i; return -1 }
    function trackOf(uid) { var i = indexOf(uid); return i >= 0 ? studio.tracks[i] : null }
    function active(type) { return trackOf(act[type]) }
    function isSynth(t) { return t.type === "inst" || t.type === "drum" }
    function disconnected(t) { return t.type !== "audio" && !!studio.hidden[src[t.type]] }
    function cfgOf(type) { var t = active(type); return t ? t.cfg : (type === "ia" ? draftIa : {}) }
    function sub(t) {
        if (disconnected(t)) return "módulo desconectado"
        if (t.midi && t.midi.length) return "MIDI · " + t.midi.length + (t.midi.length === 1 ? " nota" : " notas") + (t.type === "inst" ? " · " + insts[t.cfg.v][0] : "")
        if (t.type === "inst") return "síntesis · " + insts[t.cfg.v][0]
        if (t.type === "drum") return "síntesis · 16 pasos"
        if (t.type === "voz") return t.len > 0 ? "toma " + L.fmt(t.len) + " · motor nativo" : "sin toma · graba en Grabador de cintas"
        if (t.type === "aux") return "bus Aux · recibe los envíos de la consola"
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
        if (t.type === "aux") t.id = auxTrack(t)
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
    function auxTrack(t) {
        if (!studio.engineOk) return -1
        var r = studio.call("auxCreate", t.name)
        if (!r.ok) { studio.toast(r.error); return -1 }
        return r.track.id
    }
    function addTrack(type) {
        if (type === "ia") {           // la IA no crea pistas vacías: «Pista nueva › Generar con IA» (F5)
            if (studio.hidden.ia) studio.setHidden("ia", false)
            studio.newTrack("gen"); aiRefresh()
            return null
        }
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
        studio.followSelection(t)
        if (act[t.type] !== undefined) { var c = Object.assign({}, act); c[t.type] = t.uid; act = c }
        if (t.type === "voz") arm()
    }
    function forget(t) {
        if (t.type === "voz" && t.uid === armedUid) { if (recording) stopTake(true); armedUid = "" }
        if ((isSynth(t) || t.type === "voz" || t.type === "aux") && t.id >= 0) studio.call("removeTrack", t.id)
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
            type: t.type, cfg: t.cfg, clips: t.clips, roll: t.roll, pat: t.pat, midi: t.midi || null,
            sus: t.type === "inst" && sus, settingsOnly: !!settingsOnly }))
        if (!r.ok) studio.toast(r.error)
        else {
            if (r.warning) studio.toast(r.warning)
            if (r.length >= 0 && r.length !== t.len) replace(uid, { len: r.length })
        }
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
        previewMidi(cfg, note, d)
    }
    function previewMidi(cfg, note, d) { var t = active("inst"); audition({ type: "inst", cfg: cfg, note: note, seconds: noteDur(d), id: t ? t.id : -1 }) }
    function previewDrum(cfg, i) { var t = active("drum"); audition({ type: "drum", cfg: cfg, lane: i, id: t ? t.id : -1 }) }
    // Sampler de los pads: una ruta por carril ("" = sonido sintetizado); `paths` sin un carril lo deja como está
    function setDrumSamples(paths, replaceAll) {
        var t = active("drum")
        if (!t) { studio.toast("Crea una pista de batería primero"); return false }
        var cur = (t.cfg.smp || []).slice()
        for (var i = 0; i < 8; i++) if (replaceAll || paths[i]) cur[i] = paths[i] || ""
        setCfg("drum", "smp", cur)
        return true
    }

    // ---------------- Instrumentos y Piano roll ----------------
    function setCfg(type, key, value) {
        var t = active(type)
        if (!t) { if (type === "ia") { var d = Object.assign({}, draftIa); d[key] = value; draftIa = d } return }
        var c = Object.assign({}, t.cfg); c[key] = value
        replace(t.uid, { cfg: c })
        // swing, octava, largo de los pads y variación mueven las notas; el resto son parámetros
        if (isSynth(t)) update(t.uid, ["sw", "oct", "len", "seed"].indexOf(key) < 0)
    }
    function setVoice(v) {
        var t = active("inst"); if (!t) return
        setCfg("inst", "v", ((v % insts.length) + insts.length) % insts.length)
    }
    // Una pista con MIDI (de la IA o importado) no se edita en la rejilla de 16 pasos
    function midiLocked(t) {
        if (!t || !t.midi || !t.midi.length) return false
        studio.toast("«" + t.name + "» toca un MIDI de " + t.midi.length + " notas: la rejilla no lo edita. «Pasar a rejilla» lo vacía.")
        return true
    }
    function dropMidi(type) {
        var t = active(type); if (!t || !t.midi) return
        replace(t.uid, { midi: null, midiSrc: "" }); update(t.uid); studio.markDirty()
    }
    function toggleRoll(r, c) {
        var t = active("inst"); if (!t || midiLocked(t)) return
        var roll = Object.assign({}, t.roll), k = r + "-" + c
        if (base[r] === undefined) return                  // fila fuera del teclado
        if (roll[k]) delete roll[k]; else { roll[k] = 1; previewNote(t.cfg, base[r]) }
        replace(t.uid, { roll: roll }); update(t.uid)
    }
    function clearRoll() { var t = active("inst"); if (t) { replace(t.uid, { roll: {} }); update(t.uid) } }
    function setOct(d) {
        oct = Math.max(1, Math.min(7, oct + d))
        var t = active("inst")
        if (t && !midiLocked(t) && (t.cfg.oct || 4) !== oct) setCfg("inst", "oct", oct)   // transpone lo que suena
    }
    function toggleSus() { sus = !sus; rerenderAll("inst") }

    // ---------------- Batería ----------------
    function toggleStep(lane, s) {
        var t = active("drum"); if (!t || midiLocked(t)) return
        var p = Object.assign({}, t.pat), k = lane + "-" + s
        if (p[k]) delete p[k]; else { p[k] = 1; previewDrum(t.cfg, lane) }
        replace(t.uid, { pat: p }); update(t.uid)
    }
    // Step Sequencer: un paso encendido es 1 (fuerza 100, siempre, una vez) o [fuerza, probabilidad, repeticiones]
    readonly property var stepCycles: [[100, 127, 60], [100, 75, 50, 25], [1, 2, 3, 4]]
    function stepVal(t, lane, s) {
        var v = t && t.pat ? t.pat[lane + "-" + s] : 0
        if (!v) return null
        return v.length === 3 ? [v[0], v[1], v[2]] : [100, 100, 1]
    }
    function cycleStep(lane, s, field) {
        var t = active("drum"); if (!t || midiLocked(t)) return
        var v = stepVal(t, lane, s)
        if (!v) { toggleStep(lane, s); return }
        var cyc = stepCycles[field], i = cyc.indexOf(v[field])
        v[field] = cyc[(i + 1) % cyc.length]
        var p = Object.assign({}, t.pat)
        p[lane + "-" + s] = v[0] === 100 && v[1] === 100 && v[2] === 1 ? 1 : v
        replace(t.uid, { pat: p }); update(t.uid)
    }
    function clearPat() { var t = active("drum"); if (t) { replace(t.uid, { pat: {} }); update(t.uid) } }
    function basicPat() { var t = active("drum"); if (t) { replace(t.uid, { pat: basic() }); update(t.uid) } }

    // ---------------- Pistas con IA: ACE-Step local (ai_music.py) ----------------
    function aiRefresh() {
        if (!studio) return
        var r = studio.call("aiStatus")
        if (r.ok) { ai = r; generating = r.generating; downloading = r.downloading }
        else ai = { ok: false, error: r.error, engineOk: false, installed: "", packs: [], generations: [], styles: [], keys: [] }
    }
    function setHardwareProfile(name) {
        var r = studio.call("hardwareSetProfile", name)
        if (!r.ok) { studio.toast(r.error); return }
        aiRefresh()
        studio.toast("Perfil del equipo: " + r.profile.name)
    }
    // ---------------- Tomas y carpetas (F4, FLUJO_PROFESIONAL §3) ----------------
    // Lo que hace la IA sobre un clip entra en el flujo: «Rehacer» y «Alinear» dejan una toma nueva en la
    // misma pista (la anterior sigue ahí y se elige en la cabecera de la pista); «Versión» y «Separar»
    // dejan pistas en la carpeta de la original. Cada toma es un archivo con sus clips.
    // extra = { now: archivo nuevo, takes, take } para que Ctrl+Z y Ctrl+Y devuelvan también las tomas
    signal sourceReplaced(string uid, string previous, var clips, var extra)
    function takeState(t) { return { takes: t && t.takes ? t.takes : [], take: t && t.take ? t.take : 0 } }
    // Añade la toma que acaba de entrar (la pista ya suena con ella); devuelve el estado de antes
    function addTake(uid, prevSource, prevClips, name, path, clips) {
        var t = trackOf(uid)
        if (!t) return null
        var before = takeState(t), tk = (t.takes || []).slice()
        if (!tk.length) tk.push({ name: "Toma 1", source: prevSource, clips: prevClips, ai: false })
        else tk[t.take || 0] = Object.assign({}, tk[t.take || 0], { clips: prevClips })
        tk.push({ name: name, source: path, clips: clips, ai: true })
        replace(uid, { takes: tk, take: tk.length - 1 })
        return before
    }
    function takeName(t, what) {
        var n = 1
        ;(t && t.takes || []).forEach(function (k) { if (k.name.indexOf(what) === 0) n++ })
        return what + " " + n
    }
    // Elegir otra toma: la pista suena con su archivo y sus clips (los de la toma que deja se guardan)
    function useTake(uid, i) {
        var t = trackOf(uid)
        if (!t || !t.takes || i < 0 || i >= t.takes.length || i === (t.take || 0)) return false
        if (t.lab && t.takes[i].vid && studio.lab) { studio.lab.choose(t.lab, t.takes[i].vid); return true }   // F5: variante del laboratorio
        var tk = t.takes.slice()
        tk[t.take || 0] = Object.assign({}, tk[t.take || 0], { clips: t.aclips || [] })
        var r = studio.call("clipEdit", t.id, JSON.stringify({ op: "set", source: tk[i].source, clips: tk[i].clips }))
        if (!r.ok) { studio.toast(r.error); return false }
        replace(uid, { takes: tk, take: i, aclips: r.clips, peaks: r.peaks || t.peaks })
        studio.markDirty()
        studio.toast(t.name + ": suena «" + tk[i].name + "»")
        return true
    }
    // Mete una pista en la carpeta de otra: justo debajo de ella y de las que ya tiene
    function intoFolder(parentUid, childUid) {
        var a = studio.tracks.slice(), ci = -1
        for (var i = 0; i < a.length; i++) if (a[i].uid === childUid) ci = i
        if (ci < 0 || parentUid === childUid) return
        var c = Object.assign({}, a[ci], { folder: parentUid })
        a.splice(ci, 1)
        var pi = -1
        for (var j = 0; j < a.length; j++) if (a[j].uid === parentUid) pi = j
        if (pi < 0) return
        var at = pi + 1
        while (at < a.length && a[at].folder === parentUid) at++
        a.splice(at, 0, c)
        studio.tracks = a
        studio.selected = at
    }
    function folderKids(uid) { return studio.tracks.filter(function (t) { return t.folder === uid }) }
    function toggleFold(uid) { var t = trackOf(uid); if (t) replace(uid, { fold: !t.fold }) }

    // ---------------- Rehacer con IA una zona de una pista de audio (ACE-Step «repaint») ----------------
    // La zona es el clip elegido (se acota con «Dividir»). El resultado es el archivo entero, igual fuera
    // de la zona: entra como toma nueva de la pista con los mismos clips; Ctrl+Z la quita.
    property string repaintUid: ""
    function repaintClip(uid, clip, prompt) {
        var t = trackOf(uid)
        if (!t || !clip) { studio.toast("Elige un clip de una pista de audio"); return false }
        if (generating) { studio.toast("Ya hay un trabajo de IA en marcha"); return false }
        var r = studio.call("aiRepaint", t.id, JSON.stringify({ start: clip.offset, end: clip.offset + clip.length,
                                                                prompt: prompt || "", bpm: studio.bpm, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); return false }
        repaintUid = uid
        generating = true; aiProgress = 0.01; aiMsg = "Rehaciendo " + clip.length.toFixed(1) + " s de " + t.name
        studio.toast(aiMsg + " con la IA (en tu equipo)")
        return true
    }
    function applyRepaint(ev) {
        var uid = repaintUid; repaintUid = ""
        var t = trackOf(uid)
        if (!t || t.id !== ev.repaint.trackId) { studio.toast("La pista ya no está; el audio rehecho queda en " + ev.path); return }
        var before = t.aclips || []
        var r = studio.call("trackSetSource", t.id, ev.path)
        if (!r.ok) { studio.toast(r.error); return }
        replace(uid, { aclips: r.clips, peaks: r.track.peaks || [], len: r.track.length_seconds || t.len })
        var name = takeName(t, "Rehecha (IA)")
        var st = addTake(uid, r.previous, before, name, ev.path, r.clips)
        sourceReplaced(uid, r.previous, before, { now: ev.path, takes: st.takes, take: st.take })
        studio.markDirty()
        aiMsg = ev.message
        studio.toast("Zona " + ev.repaint.start.toFixed(1) + "–" + ev.repaint.end.toFixed(1) + " s rehecha: toma «" + name + "» en " + t.name
                     + " · la anterior sigue en sus tomas · Ctrl+Z la quita")
    }
    // ---------------- Vocal Align (AF-67): una toma se ajusta en el tiempo a una voz guía ----------------
    // El motor C++ escribe en otro hilo un archivo con la toma movida (sin cambiar el tono); al volver,
    // la pista lo usa con los mismos clips y «Deshacer» vuelve a la toma original.
    property string alignUid: ""
    property var alignOpts: ({ guide: "", strength: 100, maxShiftMs: 150 })
    property string alignMsg: ""
    function alignTrack(uid, guideUid) {
        var t = trackOf(uid), g = trackOf(guideUid)
        if (!t) { studio.toast("Elige un clip de la toma que quieres alinear"); return false }
        if (!g || g.uid === uid) { studio.toast("Elige en «Alinear con» la pista guía (otra pista de audio)"); return false }
        if (alignUid) { studio.toast("Ya se está alineando una pista"); return false }
        var r = studio.call("vocalAlign", t.id, g.id, JSON.stringify({ strength: alignOpts.strength, maxShiftMs: alignOpts.maxShiftMs }))
        if (!r.ok) { studio.toast(r.error); return false }
        alignUid = uid
        alignMsg = "Alineando " + t.name + " con " + g.name + "…"
        studio.toast(alignMsg)
        return true
    }
    function applyAlign(ev) {
        var uid = alignUid; alignUid = ""
        if (!ev.ok) { alignMsg = ev.error; studio.toast(ev.error); return }
        var t = trackOf(uid)
        if (!t || t.id !== ev.trackId) { studio.toast("La pista ya no está; el audio alineado queda en " + ev.path); return }
        var before = t.aclips || []
        replace(uid, { aclips: ev.clips, peaks: ev.track.peaks || [], len: ev.track.length_seconds || t.len })
        var st = addTake(uid, ev.previous, before, takeName(t, "Alineada"), ev.path, ev.clips)
        sourceReplaced(uid, ev.previous, before, { now: ev.path, takes: st.takes, take: st.take })
        studio.markDirty()
        alignMsg = t.name + " alineada: se movió " + ev.meanShiftMs + " ms de media (máx. " + ev.maxShiftMs + " ms)"
        studio.toast(alignMsg + " · toma nueva; la original sigue en sus tomas · Ctrl+Z la quita")
    }
    // ---------------- Pitch Editor (AF-64): las notas de una voz, movidas una a una ----------------
    // «Analizar» da las notas y el tono (motor C++, otro hilo); los cambios (semitonos, cents,
    // enderezar) se guardan aquí y «Aplicar» escribe una copia desde la toma analizada que la pista
    // usa con los mismos clips. Ctrl+Z vuelve al audio anterior.
    property var pitch: ({ trackId: -1, source: "", fileStart: 0, seconds: 0, hop: 0.01, curve: [], notes: [] })
    property string pitchBusy: ""             // "analyze" | "apply" | ""
    property string pitchMsg: ""
    function uidOfId(id) { for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === id) return studio.tracks[i].uid; return "" }
    function nameOfId(id) { var t = trackOf(uidOfId(id)); return t ? t.name : "" }
    function pitchAnalyze(trackId) {
        if (pitchBusy) { studio.toast("El editor de tono ya está trabajando"); return false }
        var r = studio.call("pitchAnalyze", trackId)
        if (!r.ok) { studio.toast(r.error); return false }
        pitchBusy = "analyze"
        pitchMsg = "Analizando las notas de " + nameOfId(trackId) + "…"
        return true
    }
    function pitchSetNotes(notes) { pitch = Object.assign({}, pitch, { notes: notes }) }
    function pitchApply() {
        if (pitchBusy) { studio.toast("El editor de tono ya está trabajando"); return false }
        if (!pitch.source) { studio.toast("Primero «Analizar notas»"); return false }
        var r = studio.call("pitchApply", pitch.trackId, JSON.stringify({ source: pitch.source, notes: pitch.notes }))
        if (!r.ok) { studio.toast(r.error); return false }
        pitchBusy = "apply"
        pitchMsg = r.edited ? "Aplicando " + r.edited + (r.edited === 1 ? " nota editada" : " notas editadas") + " en " + nameOfId(pitch.trackId) + "…"
                            : "Volviendo a la toma analizada…"
        return true
    }
    function applyPitch(ev) {
        pitchBusy = ""
        if (!ev.ok) { pitchMsg = ev.error; studio.toast(ev.error); return }
        if (ev.type === "pitchNotes") {
            pitch = { trackId: ev.trackId, source: ev.source, fileStart: ev.fileStart, seconds: ev.seconds,
                      hop: ev.hop, curve: ev.curve, notes: ev.notes }
            pitchMsg = ev.notes.length + " notas en " + nameOfId(ev.trackId)
            studio.toast(pitchMsg + ": elige una y muévela")
            return
        }
        var uid = uidOfId(ev.trackId), t = trackOf(uid)
        if (!t) { studio.toast("La pista ya no está; el audio editado queda en " + ev.path); return }
        var before = t.aclips || []
        replace(uid, { aclips: ev.clips, peaks: ev.track.peaks || [], len: ev.track.length_seconds || t.len })
        if (ev.previous !== ev.path) sourceReplaced(uid, ev.previous, before, { now: ev.path })
        studio.markDirty()
        pitchMsg = ev.edited ? t.name + ": " + ev.edited + (ev.edited === 1 ? " nota editada" : " notas editadas")
                             : t.name + ": de vuelta a la toma analizada"
        studio.toast(pitchMsg + " · Ctrl+Z vuelve al audio anterior")
    }
    // ---------------- Otra versión con IA de un clip (C13, ACE-Step «cover») ----------------
    // El trozo del clip elegido se vuelve a tocar: «Parecida» guarda melodía y timbre, «Libre» solo la
    // forma. El resultado va a una pista en la carpeta de la original, en el mismo sitio del clip; el
    // original no se toca.
    property string coverUid: ""
    property var coverOpts: ({ mode: "Parecida", likeness: 0.5, style: "Libre" })
    function coverClip(uid, clip) {
        var t = trackOf(uid)
        if (!t || !clip) { studio.toast("Elige un clip de una pista de audio"); return false }
        if (generating) { studio.toast("Ya hay un trabajo de IA en marcha"); return false }
        var o = coverOpts
        var r = studio.call("aiCover", t.id, JSON.stringify({ start: clip.offset, end: clip.offset + clip.length, at: clip.start,
                                                              mode: o.mode, likeness: o.likeness, style: o.style,
                                                              bpm: studio.bpm, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); return false }
        coverUid = uid
        generating = true; aiProgress = 0.01; aiMsg = "Haciendo una versión " + o.mode.toLowerCase() + " de " + clip.length.toFixed(1) + " s de " + t.name
        studio.toast(aiMsg + " con la IA (en tu equipo)")
        return true
    }
    function applyCover(ev) {
        var parent = coverUid
        coverUid = ""
        if (!addGenerated(ev.path, ev.title)) return
        var nt = studio.tracks[studio.tracks.length - 1]
        if (trackOf(parent)) intoFolder(parent, nt.uid)
        nt = trackOf(nt.uid)
        var cl = studio.clipsOf(nt.id)
        if (cl.length && ev.cover.at > 0) {
            var ce = studio.call("clipEdit", nt.id, JSON.stringify({ op: "range", clip: cl[0].id, start: ev.cover.at,
                                                                     length: cl[0].length, offset: cl[0].offset }))
            if (ce.ok) replace(nt.uid, { aclips: ce.clips }); else studio.toast(ce.error)
        }
        aiMsg = ev.message
        studio.toast(ev.message + ": en la pista «" + nt.name + "», en la carpeta de la original")
    }
    // F5: lo generado recuerda cómo se hizo (gen) y «Regenerar» pone otra versión como toma de su pista
    property string genUid: ""          // pista que recibe la próxima generación como toma ("" = pista nueva)
    property string genKind: "song"     // song | part
    function regenerate(uid) {
        var t = trackOf(uid)
        if (!t || !t.gen) { studio.toast("Esa pista no salió de «Generar con IA»"); return false }
        if (generating) { studio.toast("Ya hay un trabajo de IA en marcha"); return false }
        draftIa = Object.assign({}, draftIa, t.gen.cfg || {})
        genUid = uid
        if (t.gen.kind === "part") generatePart(); else generate()
        if (!generating) { genUid = ""; return false }
        studio.toast("Regenerando " + t.name + ": entrará como toma nueva")
        return true
    }
    function applyGenerated(ev) {
        var cfg = Object.assign({}, draftIa), kind = genKind, t = trackOf(genUid)
        genUid = ""
        aiMsg = ev.message
        if (!t) {
            if (!addGenerated(ev.path, ev.title)) return
            var nt = studio.tracks[studio.tracks.length - 1]
            replace(nt.uid, { gen: { kind: kind, cfg: cfg } })
            studio.toast(ev.message + ": pista «" + nt.name + "» · «Regenerar» en el Inspector pone otra versión como toma")
            return
        }
        var before = t.aclips || []
        var r = studio.call("trackSetSource", t.id, ev.path)
        if (!r.ok) { studio.toast(r.error); return }
        var at = before.length ? before[0].start : 0, len = r.track.length_seconds || t.len
        var ce = studio.call("clipEdit", t.id, JSON.stringify({ op: "set", clips: [{ start: at, length: len, offset: 0 }] }))
        var clips = ce.ok ? ce.clips : r.clips
        replace(t.uid, { aclips: clips, peaks: ce.peaks || r.track.peaks || [], len: len, gen: { kind: kind, cfg: cfg } })
        var name = takeName(t, "Generada")
        var st = addTake(t.uid, r.previous, before, name, ev.path, clips)
        sourceReplaced(t.uid, r.previous, before, { now: ev.path, takes: st.takes, take: st.take })
        studio.markDirty()
        studio.toast(ev.message + ": toma «" + name + "» en " + t.name + " · la anterior sigue en sus tomas · Ctrl+Z la quita")
    }
    function generate() {
        if (generating) return
        genKind = "song"
        var c = draftIa
        var r = studio.call("aiGenerate", JSON.stringify({
            prompt: c.prompt, style: c.style, duration: c.dur, key: c.key, instrumental: c.inst, lyrics: c.lyrics,
            creativity: c.cre, bpm: c.bpmSync ? studio.bpm : 0, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); aiMsg = r.error; return }
        generating = true; aiProgress = 0.01; aiMsg = "Preparando…"
    }
    // Parte nueva (guitarra, piano…) acorde al proyecto: tempo del proyecto y la tonalidad confirmada
    // en el Afinador / Mezcla IA si la hay; ACE-Step escucha lo que ya suena (aiPart en bridge.py)
    function generatePart() {
        if (generating) return
        genKind = "part"
        var c = draftIa, conf = studio.mixer ? studio.mixer.tune.confirmed : null
        var key = conf ? conf.key + (conf.scale.indexOf("Menor") === 0 ? " minor" : " major") : c.key
        var r = studio.call("aiPart", JSON.stringify({ part: c.part || "Guitarra", style: c.style, prompt: c.partPrompt || "",
                                                         bpm: studio.bpm, key: key, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); aiMsg = r.error; return }
        generating = true; aiProgress = 0.01
        aiMsg = "Escuchando " + Math.round(r.seconds) + " s del proyecto…"
    }
    // ---------------- Dividir en pistas: separador Demucs local (stems.py) ----------------
    property bool splitting: false
    property real splitProgress: 0
    property string splitMsg: ""
    function splitStems(trackId) {
        if (splitting) return
        var st = studio.call("stemsStatus")
        if (!st.ok) { studio.toast(st.error); return }
        if (!st.engineOk) { studio.toast("Falta el separador (motores\\demucs junto a AllForOne.exe)"); return }
        if (!st.modelOk) {
            if (!st.downloading) studio.call("stemsDownload")
            studio.toast("Descargando el modelo del separador (55 MB); al terminar vuelve a pulsar «Dividir»")
            return
        }
        var r = studio.call("stemsSplit", trackId, true)
        if (!r.ok) { studio.toast(r.error); return }
        splitting = true; splitProgress = 0.01; splitMsg = "Preparando el audio"
        studio.toast("Dividiendo en pistas con Demucs (≈ 5 s por cada segundo de audio)…")
    }
    function cancelGenerate() { studio.call("aiCancel"); aiMsg = "Cancelando…" }
    function download(pack) {
        var r = studio.call("aiDownload", pack)
        if (!r.ok) { studio.toast(r.error); return }
        downloading = true; dlMsg = "Conectando con Hugging Face…"
    }
    function cancelDownload() { studio.call("aiCancelDownload"); dlMsg = "Pausando…" }
    // Carga una generación guardada como pista de audio del motor (Pistas, mezclador y efectos)
    function addGenerated(path, title) {
        if (!studio.engineOk) { studio.toast("Motor nativo no disponible"); return false }
        var r = studio.call("addAudioPath", path, "IA · " + title)
        if (!r.ok) { studio.toast(r.error); return false }
        studio.addTrack(r.track, true)
        studio.markDirty()
        return true
    }
    // ---------------- Pistas con IA: composición MIDI local (midi_ai.py) ----------------
    function midiRefresh() {
        if (!studio) return
        var r = studio.call("midiStatus")
        if (r.ok) { midiAi = r; composing = r.generating; midiDownloading = r.downloading }
        else midiAi = { ok: false, error: r.error, engineOk: false, model: { done: false, have: 0, size: 0 }, compositions: [] }
    }
    function compose() {
        if (composing) return
        var c = draftMidi
        var r = studio.call("midiGenerate", JSON.stringify({ prompt: c.prompt, length: c.len, creativity: c.cre, bpm: studio.bpm, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); midiMsg = r.error; return }
        composing = true; midiProgress = 0.01; midiMsg = "Preparando…"
    }
    function cancelCompose() { studio.call("midiCancel"); midiMsg = "Cancelando…" }
    function midiDownload() {
        var r = studio.call("midiDownload")
        if (!r.ok) { studio.toast(r.error); return }
        midiDownloading = true; midiDlMsg = "Conectando con Hugging Face…"
    }
    function cancelMidiDownload() { studio.call("midiCancelDownload"); midiDlMsg = "Pausando…" }
    function setMidiCfg(k, v) { var d = Object.assign({}, draftMidi); d[k] = v; draftMidi = d }
    // Cada instrumento de la composición entra como su propia pista de Instrumento o Batería
    function addMidiTracks(tracks, title, src) {
        if (!studio.engineOk) { studio.toast("Motor nativo no disponible"); return 0 }
        var n = 0
        tracks.forEach(function (tr) {
            var t = mk(tr.type, tr.name)
            t.midi = tr.midi; t.midiSrc = src || ""
            t.clips = [[0, 100]]
            if (tr.type === "inst") t.cfg.v = tr.voice
            if (studio.hidden[src_(tr.type)]) studio.setHidden(src_(tr.type), false)
            push(t); n++
        })
        if (n) studio.markDirty()
        return n
    }
    function src_(type) { return src[type] }
    // Patrón MIDI de una familia del Instrumental Lab (C14): estilo, tonalidad, tempo y compases de la
    // sesión; llega por aiMidi con `family` y entra como pista MIDI editable.
    property string patternFamily: ""
    function labPattern(family, ctx) {
        if (!ctx) return false
        if (composing) { studio.toast("Ya se está componiendo"); return false }
        if (!midiAi.engineOk || !midiAi.model || !midiAi.model.done) { studio.toast("Falta el modelo MIDI: descárgalo en Navegador › IA"); return false }
        var r = studio.call("midiGenerate", JSON.stringify({ family: family, prompt: ctx.prompt || "", style: ctx.style, key: ctx.key,
                                                             bpm: ctx.bpm, bars: ctx.bars, beats: ctx.beats, length: 900,
                                                             creativity: 60, seed: -1 }))
        if (!r.ok) { studio.toast(r.error); return false }
        patternFamily = family
        composing = true; midiProgress = 0.01; midiMsg = "Componiendo un patrón de " + family.toLowerCase()
        studio.toast(midiMsg + " con la IA (en tu equipo)")
        return true
    }
    function openMidi(path, title) {
        var r = studio.call("midiOpen", path || "", studio.bpm)
        if (!r.ok) { if (!r.cancelled) studio.toast(r.error); return }
        var n = addMidiTracks(r.tracks, title || r.title, r.path)
        studio.toast("«" + (title || r.title) + "»: " + r.notes + " notas en " + n + " pistas")
    }
    function onAiEvent(ev) {
        if (ev.type === "align") { applyAlign(ev); return }
        if (ev.type === "pitchNotes" || ev.type === "pitchEdit") { applyPitch(ev); return }
        if (ev.type === "stemsDownload") {
            if (ev.phase === "progress") splitMsg = ev.message
            else studio.toast(ev.ok || ev.cancelled ? ev.message : ev.error)
            return
        }
        if (ev.type === "stems") {
            if (ev.phase === "progress") { splitting = true; splitProgress = ev.progress; splitMsg = ev.message + " · " + Math.round(ev.progress * 100) + " %"; return }
            splitting = false; splitProgress = 0
            if (!ev.ok) { splitMsg = ev.cancelled ? ev.message : ev.error; if (!ev.cancelled) studio.toast(ev.error); return }
            var n = 0, parent = uidOfId(ev.trackId)
            ;(ev.stems || []).forEach(function (s) {       // en la carpeta de la original (Studio One)
                var r = studio.call("addAudioPath", s.path, ev.name + " · " + s.label)
                if (!r.ok) { studio.toast(r.error); return }
                studio.addTrack(r.track, true); n++
                if (parent) intoFolder(parent, "a" + r.track.id)
            })
            var t = studio.tracks.slice()                  // la original queda silenciada (no se borra)
            for (var i = 0; i < t.length; i++) if (t[i].id === ev.trackId && !t[i].mute) {
                t[i] = Object.assign({}, t[i], { mute: true }); studio.tracks = t; studio.syncTrackStates(); break
            }
            studio.markDirty()
            splitMsg = ev.message
            studio.toast(ev.message + " · en la carpeta de la original, que queda silenciada")
            return
        }
        if (ev.type === "aiMidiDownload") {
            if (ev.phase === "progress") { midiDownloading = true; midiDlProgress = ev.progress; midiDlMsg = ev.message + " · " + (ev.got / 1073741824).toFixed(2) + " de " + (ev.size / 1073741824).toFixed(2) + " GB" }
            else { midiDownloading = false; midiDlMsg = ev.ok || ev.cancelled ? ev.message : ev.error; if (!ev.ok && !ev.cancelled) studio.toast(ev.error); midiRefresh() }
            return
        }
        if (ev.type === "aiMidi") {
            if (ev.phase === "progress") { composing = true; midiProgress = ev.progress; midiMsg = ev.message }
            else {
                composing = false; midiProgress = 0; patternFamily = ""
                if (ev.ok) {
                    midiMsg = ev.message
                    var n = addMidiTracks(ev.tracks, ev.title, ev.path)
                    if (ev.family) studio.toast("Patrón de " + ev.family.toLowerCase() + ": " + ev.notes + " notas en " + n + " pista(s) MIDI nuevas, editables en Pistas")
                    else studio.toast("Composición MIDI: " + ev.message + " · " + n + " pistas nuevas en Pistas")
                } else { midiMsg = ev.cancelled ? ev.message : ev.error; if (!ev.cancelled) studio.toast(ev.error) }
                midiRefresh()
            }
            return
        }
        if (ev.type === "aiDownload") {
            if (ev.phase === "progress") { downloading = true; dlProgress = ev.progress; dlMsg = ev.message + " · " + (ev.got / 1073741824).toFixed(2) + " de " + (ev.size / 1073741824).toFixed(2) + " GB" }
            else { downloading = false; dlMsg = ev.ok || ev.cancelled ? ev.message : ev.error; if (!ev.ok && !ev.cancelled) studio.toast(ev.error); aiRefresh() }
        } else if (ev.type === "aiGenerate") {
            if (ev.phase === "progress") { generating = true; aiProgress = ev.progress; aiMsg = ev.message }
            else {
                generating = false; aiProgress = 0
                if (ev.ok && ev.repaint) applyRepaint(ev)
                else if (ev.ok && ev.cover) applyCover(ev)
                else if (ev.ok) applyGenerated(ev)
                else { repaintUid = ""; coverUid = ""; genUid = ""; aiMsg = ev.cancelled ? ev.message : ev.error; if (!ev.cancelled) studio.toast(ev.error) }
                aiRefresh()
            }
        }
    }
}
