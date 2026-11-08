import QtQuick
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
    }
    function setTrackRole(id, role) {
        for (var i = 0; i < items.length; i++) if (items[i].trackId === id) { setItemRole(i, role); return }
    }
    function removeItem(i) { var out = items.slice(); out.splice(i, 1); items = out }
    function clear() { items = []; live = {}; status = "Lista vacía."; progress = 0 }

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
            // El Afinador llega en la fase 2: sin afinación (intensidad 0 %)
            tune: { mode: "Automático", key: "F", scale: "Menor natural", bpm: 91, prefer: true, strength: 0,
                    voices: { lead: true, l: false, r: false, b: false } }
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
            if (ev.panel !== "afina") { status = ev.desc || "Trabajando…"; if (ev.p !== undefined) progress = ev.p }
        } else if (ev.type === "done") {
            var rs = runs.slice(); rs.push(ev.run); runs = rs; run = rs.length - 1
            busy = false; workingTrack = -1; progress = 100
            status = "Mezcla #" + rs.length + " lista en " + ev.run.seconds + " s · " + Object.keys(ev.run.masters).length +
                     " masters · " + ev.run.review.length + " pistas A/B" + (ev.run.tuned ? " · afinada" : "")
            studio.toast("Mezcla automática terminada · la consola refleja los niveles y el paneo")
        } else if (ev.type === "error") {
            busy = false; workingTrack = -1; status = "Error: " + ev.error
            studio.toast(ev.error)
        } else if (ev.type === "idle") {
            if (busy) { busy = false; workingTrack = -1 }
        }
    }
}
