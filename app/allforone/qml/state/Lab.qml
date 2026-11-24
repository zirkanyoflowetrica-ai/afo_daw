import QtQuick

// Instrumental Lab (lab.py, docs/INSTRUMENTAL_LAB.md): estado y acciones para la vista del
// laboratorio (X18). La generación corre en el equipo (ACE-Step y Demucs, procesos aparte); aquí solo
// se llama al puente y se reflejan sus eventos (aiEvent con type «labState» y «labJob»).
// Preescucha: una pista real por familia, «<familia> · Lab (borrador)», con la variante elegida desde
// el compás 1. Elegir otra variante cambia el audio de esa misma pista; «Enviar al proyecto» le quita
// la marca de borrador y «Descartar» la quita del proyecto.
QtObject {
    id: lb
    property var studio
    property var seq                       // Sequencer: replace / indexOf de las pistas
    property var status: ({ ok: false, families: [], styles: [], keys: [], defaults: ({}) })
    property var state: null               // sesión abierta (lab.json con rutas absolutas) o null
    property var sessions: []
    property var favorites: []
    property bool busy: false
    property real progress: 0
    property string msg: ""
    property string family: ""             // familia que se está generando ahora
    property var drafts: ({})              // familia → id de su pista borrador en el motor
    readonly property bool previewing: Object.keys(drafts).length > 0

    function refresh() {
        var r = studio.call("labStatus")
        if (r.ok) { status = r; state = r.state; busy = r.busy }
        return r
    }
    function listSessions() {
        var r = studio.call("labSessions")
        if (r.ok) { sessions = r.sessions; favorites = r.favorites }
        return r
    }
    function _apply(r, okMsg) {
        if (!r.ok) { studio.toast(r.error); return false }
        if (r.state !== undefined) state = r.state
        if (r.queued !== undefined) { busy = true; progress = 0.01; msg = "En cola" }
        if (okMsg) studio.toast(okMsg)
        return true
    }
    function _variant(fam, vid) {
        var f = (state && state.families || []).filter(function (x) { return x.name === fam })[0]
        return f ? f.variants.filter(function (v) { return v.id === vid })[0] : null
    }

    // --- sesiones ---
    function create(opts) { discard(); return _apply(studio.call("labNew", JSON.stringify(opts)), "Sesión del laboratorio creada") }
    function open(folder) { discard(); return _apply(studio.call("labOpen", folder)) }
    function addFamily(f) { return _apply(studio.call("labAddFamily", f)) }

    // --- generar (cola: un motor de IA a la vez) ---
    function guideText() { return _apply(studio.call("labGuideText"), "Componiendo la guía: luego Demucs da la V1 de cada familia") }
    function guideProject() { return _apply(studio.call("labGuideProject"), "Separando el proyecto: cada parte será la V1 de su familia") }
    function generate(f, n) { return _apply(studio.call("labGenerate", f, n || 0)) }
    function regenerate(f) { return _apply(studio.call("labRegenerate", f), f + ": las no bloqueadas pasan al historial") }
    function similar(f, vid) { return _apply(studio.call("labSimilar", f, vid, 0.5)) }
    function cancel() { studio.call("labCancel") }

    // --- elegir, bloquear, favorita, referencia, quitar ---
    function choose(f, vid) {
        if (_apply(studio.call("labSet", f, vid, "chosen", true)) && previewing) preview()
    }
    function lock(f, vid, on) { return _apply(studio.call("labSet", f, vid, "locked", on)) }
    function favorite(f, vid, on) { return _apply(studio.call("labSet", f, vid, "favorite", on)) }
    function reference(f, on) { return _apply(studio.call("labReference", f, on)) }
    function remove(f, vid) {
        if (_apply(studio.call("labRemove", f, vid), "Variante a la papelera de la sesión") && previewing) preview()
    }
    function oneShots() {
        var r = studio.call("labOneShots", "Batería")
        if (!_apply(r)) return []
        var hits = r.state.oneshots ? r.state.oneshots.hits : {}
        studio.toast("Golpes sueltos: " + Object.keys(hits).join(", ") + " (en la carpeta golpes de la sesión)")
        return hits
    }

    // Los golpes sueltos a los pads de la Batería activa (sampler del motor, C10)
    function hitsToPads() {
        var r = studio.call("labHitLanes")
        if (!r.ok) { studio.toast(r.error); return false }
        if (!seq.setDrumSamples(r.lanes, false)) return false
        studio.toast("Golpes del laboratorio en los pads: " + r.lanes.map(function (p, i) { return p ? seq.dn[i] : "" })
                     .filter(function (x) { return x }).join(", "))
        return true
    }

    // --- preescucha con pistas reales ---
    function _removeIds(ids) {
        for (var k = 0; k < ids.length; k++)
            for (var i = studio.tracks.length - 1; i >= 0; i--)
                if (studio.tracks[i].id === ids[k] && studio.tracks[i].type === "audio") { studio.removeTrackAt(i); break }
    }
    function preview() {
        var r = studio.call("labPreview")
        if (!r.ok) { studio.toast(r.error); return false }
        _removeIds(r.stale)
        var d = {}
        r.tracks.forEach(function (t) {
            d[t.family] = t.id
            if (t.change === "new") {
                studio.addTrack(t.track, true)
                seq.replace("a" + t.id, { lab: t.family })
            } else if (t.change === "audio") {
                seq.replace("a" + t.id, { len: t.track.length_seconds || 0, peaks: t.track.peaks || [], aclips: studio.clipsOf(t.id) })
            }
        })
        drafts = d
        studio.syncTrackStates()
        if (r.bpm && Math.abs(r.bpm - studio.bpm) > 0.01)
            studio.toast("El laboratorio va a " + r.bpm + " BPM y el proyecto a " + studio.bpm + ": cambia el tempo del proyecto para que encaje")
        return true
    }
    function send() {
        var r = studio.call("labSend")
        if (!r.ok) { studio.toast(r.error); return false }
        r.tracks.forEach(function (t) {
            seq.replace("a" + t.id, { name: t.name, lab: "", len: t.track.length_seconds || 0, peaks: t.track.peaks || [], aclips: studio.clipsOf(t.id) })
        })
        drafts = ({})
        studio.markDirty()
        studio.toast(r.tracks.length + " pistas del laboratorio enviadas al proyecto")
        return true
    }
    function discard() {
        var r = studio.call("labDiscard")
        if (r.ok && r.ids.length) _removeIds(r.ids)
        drafts = ({})
    }
    function _toggle(f, field) {
        var id = drafts[f]
        if (id === undefined) return
        var t = seq.trackOf("a" + id)
        if (!t) return
        var ch = {}; ch[field] = !t[field]
        seq.replace("a" + id, ch)
        studio.syncTrackStates()
    }
    function soloFamily(f) { _toggle(f, "solo") }
    function muteFamily(f) { _toggle(f, "mute") }

    // --- eventos del puente ---
    function onAiEvent(ev) {
        if (ev.type === "labState") {
            state = ev.state
            busy = ev.state ? ev.state.busy : false
            if (previewing && ev.state) preview()          // la elegida pudo cambiar (V1 de la guía, regenerar…)
            return true
        }
        if (ev.type === "labJob") {
            if (ev.phase === "progress") { busy = true; progress = ev.progress; msg = ev.message; family = ev.family || ""; return true }
            busy = false; progress = 0; family = ""
            msg = ev.ok ? ev.message : (ev.cancelled ? ev.message : ev.error)
            studio.toast(msg)
            return true
        }
        return false
    }
}
