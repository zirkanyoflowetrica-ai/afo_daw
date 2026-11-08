import QtQuick
import "../theme"
import "mixdata.js" as MD

// Estado del Mezclador Automático V4.2 en la interfaz nativa (equivale a AFO_MX de afo_panels.js).
// Un audio = una ficha (`items`) = una pista del motor = una tira de la consola.
QtObject {
    id: mx
    property var studio                        // la ventana (pistas, avisos, motor)
    property var data: MD.D
    property bool ready: false
    property var items: []                      // {uid, path, name, kind, role, auto_kind, auto_role, trackId, note}
    property int uid: 0
    property var reference: null
    property string profile: "trap_oscuro"
    property string mode: MD.D.modes[0]
    property real stepKnob: 40                  // 5..10 dB → 0..100 (7 dB = 40)
    property real spaceKnob: 45
    property bool busy: false
    property real progress: 0
    property string status: "Carga audios en el módulo «Audios»: cada uno crea su pista y su tira."
    property var runs: []
    property int run: -1
    property var live: ({})                     // por id de pista del motor: decisiones reales del mezclador
    property int workingTrack: -1
    // Afinador (PSOLA): tonalidad y BPM confirmados antes de afinar
    property var tune: ({ mode: "Automático", key: "F", scale: "Menor natural", bpm: 91, prefer: true,
                          voices: { lead: true, l: false, r: false, b: false }, analysis: null, confirmed: null,
                          status: "Pendiente: analiza y confirma antes de afinar." })
    property real tuneStrength: 0               // intensidad 0..100 (0 = sin afinación)
    property var keys: ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    property var scales: ["Cromatica", "Mayor", "Menor natural", "Menor armonica", "Pentatonica mayor", "Pentatonica menor"]
    // Master IA y Antes / Después
    property int masterSel: 3
    property string masterAb: "B"
    property int reviewSel: 0
    property string reviewAb: "A"
    readonly property var currentRun: run >= 0 && run < runs.length ? runs[run] : null

    function stepDb() { return 5 + stepKnob / 20 }
    function call(cmd, data) {
        try { return JSON.parse(afo.mixer(cmd, JSON.stringify(data || {}))) } catch (e) { return { ok: false, error: String(e) } }
    }
    function fail(r) { if (r && !r.ok && !r.cancelled) studio.toast(r.error); return r }
    function connect() {
        var info = call("info")
        if (info.ok) {
            data = { profiles: info.profiles.map(function (p) { return [p[0], p[1]] }), modes: info.modes, masters: info.masters, types: info.types }
            mode = data.modes[0]
            keys = info.keys; scales = info.scales
            ready = true
        } else { status = info.error; ready = false }
    }

    // ---------------- fichas ----------------
    function touch() { items = items.slice() }
    function addItems(list) {
        var known = items.map(function (i) { return i.path }), out = items.slice(), fresh = []
        for (var i = 0; i < (list || []).length; i++) {
            var s = list[i]
            if (!s || known.indexOf(s.path) >= 0 || out.length >= 30) continue
            known.push(s.path); fresh.push(s)
            out.push({ uid: ++uid, path: s.path, name: s.name, kind: s.kind, role: s.role,
                       auto_kind: s.auto_kind, auto_role: s.auto_role, trackId: -1, note: "" })
        }
        items = out
        unconfirm()
        return fresh
    }
    function itemOfTrack(id) {
        for (var i = 0; i < items.length; i++) if (items[i].trackId === id) return items[i]
        return null
    }
    function roleOfTrack(id) { var it = itemOfTrack(id); return it ? it.role : "—" }
    function kindOfTrack(id) { var it = itemOfTrack(id); return it ? it.kind : "" }
    // Un audio que acaba de entrar al motor se enlaza con su ficha (o se crea, clasificada por su nombre)
    function linkTrack(info) {
        var path = info.originalPath || info.source_path || ""
        var it = null
        for (var i = 0; i < items.length; i++) if (items[i].path === path && items[i].trackId < 0) { it = items[i]; break }
        if (!it && path) {
            var r = call("describe", { paths: [path] })
            var s = r.ok && r.stems && r.stems.length ? r.stems[0]
                  : { path: path, name: info.name, kind: "Otro", role: "—", auto_kind: "Otro", auto_role: "—" }
            addItems([s])
            it = items[items.length - 1]
        }
        if (!it) return
        it.trackId = info.id; it.note = info.note || ""
        touch()
    }
    // La pista se borró: su audio sigue en la lista, sin pista
    function unlinkTrack(id) {
        var it = itemOfTrack(id)
        if (it) { it.trackId = -1; touch() }
        var l = Object.assign({}, live); delete l[id]; live = l
    }
    function setItemKind(i, kind) { items[i].kind = kind; touch() }
    function setItemRole(i, role) {
        var it = items[i]
        it.role = role
        if (MD.KIND_FOR_ROLE[role] && MD.VOCAL_KINDS.indexOf(it.kind) >= 0) it.kind = MD.KIND_FOR_ROLE[role]
        touch()
        unconfirm()
    }
    function setTrackRole(id, role) {
        for (var i = 0; i < items.length; i++) if (items[i].trackId === id) { setItemRole(i, role); return }
    }
    function removeItem(i) { var out = items.slice(); out.splice(i, 1); items = out; unconfirm() }
    function clear() { items = []; live = {}; status = "Lista vacía."; progress = 0; unconfirm() }

    // ---------------- importar ----------------
    function importToTracks(paths) {
        if (!paths || !paths.length) return
        var info = call("describe", { paths: paths })
        if (info.ok) addItems(info.stems)
        if (!studio.engineOk) { studio.toast("Motor no disponible: los audios quedan en la lista, sin pista"); return }
        var r = studio.call("importPaths", JSON.stringify(paths))
        if (!r.ok) { studio.toast(r.error); return }
        r.tracks.forEach(studio.addTrack)
        ;(r.errors || []).forEach(studio.toast)
        var n = (r.converting || []).length
        if (n) { status = "Convirtiendo " + n + " archivo(s) que el motor no lee tal cual…"; progress = 5 }
        studio.toast(r.tracks.length + " pista(s) creadas" + (n ? " · " + n + " en conversión" : ""))
    }
    function addFromDialog() { var r = fail(call("add")); if (r.ok) importToTracks(r.stems.map(function (s) { return s.path })) }
    function makeMissing() { importToTracks(items.filter(function (i) { return i.trackId < 0 }).map(function (i) { return i.path })) }
    function pickReference() { var r = fail(call("ref")); if (r.ok) reference = r.reference }

    // ---------------- mezcla ----------------
    function request() {
        var p = data.profiles.filter(function (x) { return x[0] === profile })[0]
        return {
            stems: items.map(function (s) { return { path: s.path, name: s.name, kind: s.kind, role: s.role, auto_kind: s.auto_kind, auto_role: s.auto_role } }),
            reference: reference, profile: profile, mode: mode, profile_name: p ? p[1] : "",
            step_db: stepDb(), space: spaceKnob,
            tune: { mode: tune.mode, key: tune.key, scale: tune.scale, bpm: tune.bpm, prefer: tune.prefer,
                    strength: tuneStrength, voices: tune.voices }
        }
    }
    function mix(remix) {
        if (!items.length) { studio.toast("Carga audios en el módulo «Audios»"); return }
        live = {}
        var r = fail(call(remix ? "remix" : "mix", request()))
        if (r.ok) { busy = true; progress = 1; status = remix ? "Remezclando (la mezcla anterior se conserva)…" : "Mezclando…" }
    }

    function onEvent(ev) {
        if (ev.type === "strip") {
            var it = items[ev.i], id = it ? it.trackId : -1
            if (ev.phase === "work") { workingTrack = id; return }
            workingTrack = -1
            if (id < 0) return
            var l = Object.assign({}, live)
            l[id] = { gain_db: ev.gain_db, pan: ev.pan, peak_db: ev.peak_db, rms_db: ev.rms_db, position: ev.position, note: ev.note, kind: ev.kind }
            live = l
            if (ev.kind) { it.kind = ev.kind; touch() }
            // Las decisiones reales se llevan a la consola: fader (nivel) y perilla (paneo)
            studio.setTrackMix(id, MD.dbToFader(ev.gain_db), 50 + 50 * (+ev.pan || 0))
        } else if (ev.type === "progress") {
            if (ev.panel === "afina") setTune({ status: ev.desc })
            else { status = ev.desc || "Trabajando…"; if (ev.p !== undefined) progress = ev.p }
        } else if (ev.type === "analysis") {
            var t = { analysis: ev, status: ev.summary + "\n\nRevisa la propuesta y pulsa «Confirmar»." }
            if (ev.key && tune.mode !== "Manual") { t.key = ev.key; t.scale = ev.scale || tune.scale }
            if (ev.bpm && tune.mode !== "Manual") t.bpm = Math.round(ev.bpm * 10) / 10
            setTune(t)
        } else if (ev.type === "done") {
            var rs = runs.slice(); rs.push(ev.run); runs = rs; run = rs.length - 1
            busy = false; workingTrack = -1; progress = 100; reviewSel = 0
            status = "Mezcla #" + rs.length + " lista en " + ev.run.seconds + " s · " + Object.keys(ev.run.masters).length +
                     " masters · " + ev.run.review.length + " pistas A/B" + (ev.run.tuned ? " · afinada" : "")
            studio.toast("Mezcla automática terminada · la consola refleja los niveles y el paneo")
        } else if (ev.type === "error") {
            busy = false; workingTrack = -1; status = "Error: " + ev.error
            if (ev.panel === "analysis") setTune({ status: "Error: " + ev.error })
            studio.toast(ev.error)
        } else if (ev.type === "idle") {
            if (busy) { busy = false; workingTrack = -1 }
        }
    }

    // ---------------- Afinador ----------------
    function setTune(changes) { tune = Object.assign({}, tune, changes) }
    function unconfirm() { if (tune.confirmed) setTune({ confirmed: null }) }
    function setTuneParam(k, v) { var c = {}; c[k] = v; c.confirmed = null; setTune(c) }
    function toggleVoice(k) { var v = Object.assign({}, tune.voices); v[k] = !v[k]; setTune({ voices: v }) }
    function analyze() {
        var r = fail(call("analyze", request()))
        if (r.ok) setTune({ status: "Analizando instrumentos…" })
    }
    function confirmTune() {
        var r = call("confirm", request())
        if (r.ok) setTune({ confirmed: r.confirmed, status: r.status })
        else setTune({ confirmed: null, status: r.error || "Sin confirmar" })
    }
    // Tiras que el Afinador va a tocar: pistas con el rol de las voces marcadas
    function tunedStrips() {
        var V = tune.voices, want = []
        if (V.lead) want.push("P")
        if (V.l) want.push("L", "B_L")
        if (V.r) want.push("R", "B_R")
        if (V.b) want.push("B", "B_L", "B_R")
        var out = [], tr = studio.tracks
        for (var i = 0; i < tr.length; i++) {
            var it = itemOfTrack(tr[i].id)
            if (it && it.role !== "—" && want.indexOf(it.role) >= 0) out.push({ i: i, role: it.role, name: tr[i].name })
        }
        return out
    }

    // ---------------- Master IA y Antes / Después ----------------
    function listen(what, ab) {
        var d = { what: what, ab: ab, run: run, sel: what === "master" ? masterSel : reviewSel }
        if (ab !== "stop") { if (what === "master") masterAb = ab; else reviewAb = ab }
        var r = fail(call("listen", d))
        if (r.ok && r.file) studio.toast("Escuchando " + r.file)
    }
    function sendMasterToTracks() {
        var r = fail(call("tracks", { run: run, sel: masterSel }))
        if (r.ok) { r.tracks.forEach(function (t) { studio.addTrack(t, false) }); studio.toast("Master añadido a Pistas") }
    }
    function exportZip() {
        var r = fail(call("zip", { run: run, sel: masterSel }))
        if (r.ok) studio.toast("Comprimiendo la sesión en segundo plano → " + r.path)
    }
    function openFolder() { fail(call("folder", { run: run, sel: masterSel })) }
}
