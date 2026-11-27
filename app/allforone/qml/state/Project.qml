import QtQuick

// Proyecto (.afo): guardar la sesión y recuperarla. La interfaz aporta pistas, notas, patrones,
// tempo y master; Python añade del motor las cadenas de efectos (valores, puenteo, automatización)
// y las rutas de los audios (ver allforone/project.py). Abrir borra la sesión y la reconstruye.
QtObject {
    id: pj
    property var studio
    property string file: ""                    // ruta del proyecto abierto o guardado
    property string name: ""
    property bool loading: false
    // Biblioteca (X11): dónde vive el proyecto ({artist, release, song}; vacío = proyecto suelto) y, para
    // una canción que aún no tiene .afo, el archivo donde se guardará la primera vez
    property var where: ({})
    property string songTarget: ""
    readonly property string title: where.artist ? where.artist + " · " + where.release + " · " + where.song
                                                 : (name ? name : "Proyecto suelto")

    // Abrir una canción de la biblioteca: su .afo, o un proyecto vacío que se guardará en su carpeta
    function openSong(s) {
        if (s.hasAfo) return open(s.afo)
        if (!studio.engineOk) { studio.toast("Motor no disponible: no se puede abrir un proyecto"); return false }
        clear()
        file = ""; songTarget = s.afo; name = s.name
        var parts = String(s.path).replace(/\\/g, "/").split("/")
        where = { artist: parts[parts.length - 3], release: parts[parts.length - 2], song: parts[parts.length - 1] }
        studio.dirty = false
        studio.toast("Canción nueva «" + s.name + "»: se guardará en su carpeta de la biblioteca")
        return true
    }
    // Proyecto suelto: sesión vacía, sin artista ni canción
    function newLoose() {
        if (studio.engineOk) clear()
        file = ""; songTarget = ""; name = ""; where = ({})
        studio.dirty = false
    }

    function snapshot() {
        var s = studio, sq = s.seq, mx = s.mixer
        return {
            bpm: s.bpm, songKey: s.songKey, chords: s.chords, markers: s.markers, sus: sq.sus, oct: sq.oct, hidden: s.hidden,
            master: { pos: s.masterPos, drive: s.masterDrive, tone: s.masterTone, limiter: s.limiter },
            masterVersions: mx.versions, versionSel: mx.versionSel,
            // Ajustes de la Mezcla IA y del Afinador (la tonalidad confirmada vuelve confirmada)
            ai: { profile: mx.profile, mode: mx.mode, stepKnob: mx.stepKnob, space: mx.spaceKnob, masterSel: mx.masterSel,
                  tuneStrength: mx.tuneStrength,
                  tune: { mode: mx.tune.mode, key: mx.tune.key, scale: mx.tune.scale, bpm: mx.tune.bpm, method: mx.tune.method,
                          voices: mx.tune.voices, confirmed: mx.tune.confirmed, status: mx.tune.status } },
            tracks: s.tracks.map(function (t) {
                var it = t.id >= 0 ? mx.itemOfTrack(t.id) : null
                return { uid: t.uid, id: t.id, type: t.type, name: t.name, vol: t.vol, pan: t.pan, mute: t.mute, solo: t.solo,
                         cfg: t.cfg || {}, roll: t.roll || {}, pat: t.pat || {}, clips: t.clips || [], start: t.start || 0,
                         midi: t.midi || undefined, midiSrc: t.midiSrc || undefined,
                         takes: t.takes && t.takes.length ? t.takes : undefined, take: t.takes ? t.take || 0 : undefined,
                         folder: t.folder || undefined, fold: t.fold || undefined, gen: t.gen || undefined, color: t.color || undefined,
                         stem: !!it, mix: it ? { kind: it.kind, role: it.role } : null }
            })
        }
    }

    // saveAs: elegir archivo aunque ya tenga uno
    function save(saveAs) {
        if (!studio.engineOk) { studio.toast("Motor no disponible: no se puede guardar el proyecto"); return false }
        var r = studio.call("projectSave", JSON.stringify(snapshot()), saveAs ? "" : (file || songTarget))
        if (!r.ok) { if (!r.cancelled) studio.toast(r.error); return false }
        file = r.path; name = r.name; where = r.where || ({}); songTarget = ""
        studio.dirty = false
        studio.toast("Proyecto guardado: " + r.path)
        return true
    }

    function open(path) {
        if (!studio.engineOk) { studio.toast("Motor no disponible: no se puede abrir un proyecto"); return false }
        var r = studio.call("projectOpen", path || "")
        if (!r.ok) { if (!r.cancelled) studio.toast(r.error); return false }
        load(r.doc)
        file = r.path; name = r.name; where = r.where || ({}); songTarget = ""
        studio.dirty = false
        studio.arrangeView.fitAll()            // el proyecto abierto se ve entero
        Qt.callLater(function () { studio.arrangeView.refresh(); studio.arrangeView.fitAll() })
        var miss = r.doc.missing || []
        studio.toast("Proyecto abierto: " + r.name + (miss.length ? " · falta el audio de: " + miss.join(", ") : ""))
        return true
    }

    // Vacía la sesión: pistas (y sus efectos) y la cadena del master
    function clear() {
        var s = studio
        if (s.seq.recording) s.seq.stopTake(true)
        s.call("stop")
        for (var i = s.tracks.length - 1; i >= 0; i--) s.removeTrackAt(i)
        s.call("fxRestore", 0, "[]")
    }

    function load(doc) {
        var s = studio, sq = s.seq, mx = s.mixer
        loading = true
        clear()
        s.applyTempo(doc.bpm || 96)
        s.setSongKey((doc.songKey || {}).key || "", (doc.songKey || {}).scale || "", true)
        s.chords = doc.chords || []; s.markers = doc.markers || []     // F7: pista de acordes y secciones
        var m = doc.master || {}
        s.setMaster(m.pos === undefined ? 70 : m.pos)
        s.setMasterProcessing(m.drive === undefined ? 30 : m.drive, m.tone === undefined ? 50 : m.tone, m.limiter !== false)
        sq.sus = !!doc.sus
        if (doc.oct) sq.oct = doc.oct
        var h = doc.hidden || {}
        for (var k in h) if (["inst", "drums", "ia", "cinta"].indexOf(k) >= 0) s.setHidden(k, !!h[k])
        var idOf = {}                                      // uid guardado → id nuevo del motor (envíos a buses Aux)
        var uidOf = {}                                     // uid guardado → uid nuevo (carpetas, F4)
        ;(doc.tracks || []).forEach(function (d) {
            var id = -1, uid = ""
            if (d.type === "audio") {
                if (!d.path) return                        // audio que ya no está: se avisa al final
                var r = s.call("addAudioPath", d.path, d.name)
                if (!r.ok) { s.toast(r.error); return }
                s.addTrack(r.track, d.stem !== false)
                id = r.track.id; uid = "a" + id
            } else if (d.type === "ia") {
                return                                     // pistas de la antigua demostración: no tenían audio
            } else {
                var t = sq.mk(d.type, d.name)
                ;["cfg", "roll", "pat", "clips", "midi", "midiSrc"].forEach(function (f) { if (d[f] !== undefined) t[f] = d[f] })
                t.mute = !!d.mute; t.solo = !!d.solo
                sq.push(t)
                id = t.id; uid = t.uid
                if (d.type === "voz" && d.path && id >= 0) {
                    var v = s.call("setTrackAudio", id, d.path, d.start || 0)
                    if (v.ok) {
                        sq.replace(uid, { len: v.track.length_seconds, peaks: v.track.peaks, start: v.track.start_seconds || 0,
                                          aclips: s.clipsOf(id) })
                        mx.unlinkTrack(id); mx.linkTrack(v.track)
                    } else s.toast(v.error)
                }
            }
            if (d.type === "audio") sq.replace(uid, { mute: !!d.mute, solo: !!d.solo })
            if (d.aclips && d.aclips.length && id >= 0) {    // cortes, volumen y fundidos guardados
                var ce = s.call("clipEdit", id, JSON.stringify({ op: "set", clips: d.aclips }))
                if (ce.ok) sq.replace(uid, { aclips: ce.clips }); else s.toast(ce.error)
            }
            s.setTrackMixUid(uid, d.vol === undefined ? 70 : d.vol, d.pan === undefined ? 50 : d.pan)
            var it = id >= 0 ? mx.itemOfTrack(id) : null
            if (it && d.mix) { it.kind = d.mix.kind; it.role = d.mix.role; mx.touch() }
            if (id >= 0 && d.fx && d.fx.length) {
                var f = s.call("fxRestore", id, JSON.stringify(d.fx))
                if (!f.ok) s.toast(f.error)
            }
            if (uid && d.color) sq.replace(uid, { color: d.color })       // F8: color de pista
            if (id >= 0 && d.uid) idOf[d.uid] = id
            if (uid && d.uid) uidOf[d.uid] = uid
            if (uid && (d.takes || d.folder || d.fold || d.gen))   // F4: tomas y carpeta; F5: cómo se generó
                sq.replace(uid, { takes: d.takes || [], take: d.take || 0, folder: d.folder || "", fold: !!d.fold, gen: d.gen || null })
            if (id >= 0) {                                   // automatización del fader / paneo y modo
                for (var p in (d.trackAuto || {})) s.call("trackAutoSet", id, p, JSON.stringify(d.trackAuto[p]))
                if (d.autoMode) s.call("autoMode", id, d.autoMode)
            }
        })
        s.tracks = s.tracks.map(function (t) {              // la carpeta apunta al uid nuevo de su pista
            return t.folder ? Object.assign({}, t, { folder: uidOf[t.folder] || "" }) : t })
        ;(doc.tracks || []).forEach(function (d) {          // envíos: cuando ya existen todos los buses
            ;(d.sends || []).forEach(function (e) {
                if (idOf[d.uid] === undefined || idOf[e.to] === undefined) return
                var r = s.call("sendSet", idOf[d.uid], idOf[e.to], e.db, !!e.pre)
                if (!r.ok) s.toast(r.error)
            })
        })
        var mf = s.call("fxRestore", 0, JSON.stringify(doc.master_fx || []))
        if (!mf.ok) s.toast(mf.error)
        s.call("setMasterCeiling", doc.master_ceiling === undefined ? -1 : doc.master_ceiling)
        mx.masterStats = null
        var ai = doc.ai
        if (ai) {
            if (ai.profile) mx.profile = ai.profile
            if (ai.mode) mx.mode = ai.mode
            if (ai.stepKnob !== undefined) mx.stepKnob = ai.stepKnob
            if (ai.space !== undefined) mx.spaceKnob = ai.space
            if (ai.masterSel !== undefined) mx.masterSel = ai.masterSel
            mx.tuneStrength = ai.tuneStrength || 0
            if (ai.tune) {
                var c = ai.tune.confirmed
                mx.setTune(ai.tune)
                // La confirmación también vive en Python (mixsvc.approval): se repite con esa tonalidad
                if (c) {
                    mx.setTune({ mode: "Manual", key: c.key, scale: c.scale, bpm: c.bpm, confirmed: null })
                    Qt.callLater(mx.confirmTune)
                }
            }
        }
        mx.versions = doc.masterVersions || []
        mx.versionSel = doc.versionSel === undefined ? -1 : doc.versionSel
        s.syncTrackStates()
        s.refreshRacks()
        s.fxCountChanged()
        loading = false
    }
}
