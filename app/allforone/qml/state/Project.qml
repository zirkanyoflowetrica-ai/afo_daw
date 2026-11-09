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

    function snapshot() {
        var s = studio, sq = s.seq, mx = s.mixer
        return {
            bpm: s.bpm, sus: sq.sus, oct: sq.oct, hidden: s.hidden,
            master: { pos: s.masterPos, drive: s.masterDrive, tone: s.masterTone, limiter: s.limiter },
            masterVersions: mx.versions, versionSel: mx.versionSel,
            tracks: s.tracks.map(function (t) {
                var it = t.id >= 0 ? mx.itemOfTrack(t.id) : null
                return { uid: t.uid, id: t.id, type: t.type, name: t.name, vol: t.vol, pan: t.pan, mute: t.mute, solo: t.solo,
                         cfg: t.cfg || {}, roll: t.roll || {}, pat: t.pat || {}, clips: t.clips || [], start: t.start || 0,
                         stem: !!it, mix: it ? { kind: it.kind, role: it.role } : null }
            })
        }
    }

    // saveAs: elegir archivo aunque ya tenga uno
    function save(saveAs) {
        if (!studio.engineOk) { studio.toast("Motor no disponible: no se puede guardar el proyecto"); return false }
        var r = studio.call("projectSave", JSON.stringify(snapshot()), saveAs ? "" : file)
        if (!r.ok) { if (!r.cancelled) studio.toast(r.error); return false }
        file = r.path; name = r.name
        studio.toast("Proyecto guardado: " + r.path)
        return true
    }

    function open(path) {
        if (!studio.engineOk) { studio.toast("Motor no disponible: no se puede abrir un proyecto"); return false }
        var r = studio.call("projectOpen", path || "")
        if (!r.ok) { if (!r.cancelled) studio.toast(r.error); return false }
        load(r.doc)
        file = r.path; name = r.name
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
        var m = doc.master || {}
        s.setMaster(m.pos === undefined ? 70 : m.pos)
        s.setMasterProcessing(m.drive === undefined ? 30 : m.drive, m.tone === undefined ? 50 : m.tone, m.limiter !== false)
        sq.sus = !!doc.sus
        if (doc.oct) sq.oct = doc.oct
        var h = doc.hidden || {}
        for (var k in h) if (s.panelItems[k]) s.setHidden(k, !!h[k])
        ;(doc.tracks || []).forEach(function (d) {
            var id = -1, uid = ""
            if (d.type === "audio") {
                if (!d.path) return                        // audio que ya no está: se avisa al final
                var r = s.call("addAudioPath", d.path, d.name)
                if (!r.ok) { s.toast(r.error); return }
                s.addTrack(r.track, d.stem !== false)
                id = r.track.id; uid = "a" + id
            } else {
                var t = sq.mk(d.type, d.name)
                ;["cfg", "roll", "pat", "clips"].forEach(function (f) { if (d[f] !== undefined) t[f] = d[f] })
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
        })
        var mf = s.call("fxRestore", 0, JSON.stringify(doc.master_fx || []))
        if (!mf.ok) s.toast(mf.error)
        s.call("setMasterCeiling", doc.master_ceiling === undefined ? -1 : doc.master_ceiling)
        mx.masterStats = null
        mx.versions = doc.masterVersions || []
        mx.versionSel = doc.versionSel === undefined ? -1 : doc.versionSel
        s.syncTrackStates()
        s.refreshRacks()
        s.fxCountChanged()
        loading = false
    }
}
