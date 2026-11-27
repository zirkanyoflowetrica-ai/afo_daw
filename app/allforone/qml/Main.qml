import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import "theme"
import "controls"
import "modules"
import "state"
import "state/mixdata.js" as MD

// AllForOne con interfaz nativa (Qt Quick). Distribución fija de un DAW de uso diario
// (docs/DISENO_DAW.md §2): cabecera, navegador, Arreglo ⇄ Mezclador, inspector, panel de detalle de lo
// seleccionado y barra de estado. Nada flota ni se solapa; cada zona se pliega con su botón y su atajo.
// El audio y los datos vienen de Python (`afo`).
Window {
    id: win
    width: 1600; height: 900
    minimumWidth: 900; minimumHeight: 560
    visible: true
    title: (dirty ? "● " : "") + (pj.name || "Sin título") + " — AllForOne " + appVersion
    color: Theme.bg

    // ---------------- estado ----------------
    property bool engineOk: false
    // Barra de estado (guía de diseño §1): dispositivo de audio y cambios sin guardar
    property var deviceInfo: ({})
    property real latencyMs: 0
    property bool dirty: false
    // Vista principal: «home» (Inicio: la biblioteca; sale al arrancar, sin proyecto abierto, F4),
    // «arrange» (Arreglo: pistas, clips y automatización) o «mixer» (Mezclador: la consola). Tab o F5 / F6.
    property string view: "home"
    onViewChanged: if (!loading) saveLayout()
    QtObject { id: lu; function clamp(v, a, b) { return Math.max(a, Math.min(b, v)) } }
    // Doble flujo: el Arreglo (línea de tiempo) en una ventana aparte, para un segundo monitor, y el
    // Mezclador en la principal. Es otra vista del MISMO proyecto (pistas, clips y automatización del
    // motor). Se crea dentro de su ventana: Qt no deja mover lo ya dibujado de una ventana a otra.
    property bool dualWindow: false
    readonly property var flowWindow: flowWin                       // para la autoprueba (captura)
    onDualWindowChanged: {
        if (dualWindow) { view = "mixer"; flowWin.show(); flowWin.raise() }
        else flowWin.hide()
    }
    // Llamadas al motor que cambian el proyecto (las de leer y medir no cuentan)
    readonly property var editCalls: ["fxAdd", "fxAddPlugin", "fxApplyPreset", "fxEnable", "fxMove", "fxParam", "fxRemove",
        "fxRestore", "fxSetAutomation", "clipEdit", "masterLoad", "setMasterCeiling", "setMasterProcessing", "setMasterVolume",
        "setTrackAudio", "setTrackPan", "setTrackVolume", "synthUpdate", "unmaster"]
    function markDirty() { if (!loading && !pj.loading) dirty = true }
    function refreshDevice() {
        if (!engineOk) return
        var r = call("deviceStatus")
        if (r.ok) { deviceInfo = r.device; latencyMs = r.latency_ms }
    }
    Timer { interval: 2500; repeat: true; running: win.engineOk; onTriggered: win.refreshDevice() }
    property bool playing: false
    property real posSec: 0                   // posición del motor en segundos
    property real bpm: 96
    property int step: -1                     // semicorchea dentro de los 16 compases (como la plantilla)
    property var tracks: []
    property int selected: -1
    // Fuentes desconectadas (Instrumentos, Batería, IA, Grabador): sus pistas no suenan ni graban.
    // Se cambia con «Conectada» en la cabecera de su página; se guarda en el proyecto.
    property var hidden: ({})
    property string abSource: "rack"          // a qué rack escucha Antes / Después (ReviewBody.src)
    property string currentId: ""              // última página a la que se fue (goTo)
    property alias navZone: navZ
    property alias inspZone: inspZ
    property alias detailZone: detZ
    property real detailH: lu.clamp(savedLayout.detailH || 360, 200, 700)
    // F12: la ventana se reparte sin huecos a cualquier tamaño. Los laterales y el panel de abajo
    // toman su tamaño (el de fábrica o el que eligió el usuario) si caben; en pantallas pequeñas se
    // estrechan para que la vista principal conserve al menos la mitad del ancho y del alto.
    readonly property real bodyH: height - menuBar.height - header.height - statusBar.height
    readonly property real navW: Math.round(lu.clamp(width * 0.21, 270, 390))
    readonly property real inspW: Math.round(lu.clamp(width * 0.25, 330, 460))
    readonly property real detailFitH: Math.round(Math.min(detailH, Math.max(180, bodyH * 0.36)))
    property var plugins: []                   // plugins VST3 encontrados: [{id, name, vendor, instrument, path}]
    property string pluginStatus: "Aún no se han buscado plugins."
    property bool pluginScanning: false
    property real masterPos: 70                // fader master (70 = 0 dB)
    property var masterDb: [-100, -100]
    property var trackDb: ({})
    property var trackLoud: ({})               // id → [pico, RMS, LUFS M, LUFS S, LUFS I] tras el fader (motor)
    property var masterLoud: [-100, -100, -100, -100, -100]   // lo mismo tras la sección master
    property string meterMode: "dB"            // qué miden las tiras de Mezcla: dB (pico), LUFS (corto plazo) o RMS
    property int rackTrack: -1                 // canal cuyo rack muestra Efectos (la tira elegida en Mezcla)
    property real vu: 0
    property bool limiter: true                // sección master del motor (Mezcla final)
    property real masterDrive: 30
    property real masterTone: 50
    property var rec: null                     // pista armada del motor: {track, recording, seconds, input, db, monitor}
    property bool previewing: false            // el motor reproduce una toma o una escucha A/B
    property int fxRev: 0                      // sube cada vez que cambia una cadena de efectos
    function fxCountChanged() { fxRev++ }
    property var fxBody: null
    function refreshRacks() { if (fxBody) fxBody.reload() }
    // Valor que muestra una tira según el modo elegido (dB de pico, LUFS a corto plazo o RMS)
    function stripValue(id) {
        var l = trackLoud[String(id)]
        if (meterMode === "dB" || !l) return trackLevel(id)
        return meterMode === "RMS" ? l[1] : l[3] > -100 ? l[3] : l[2]
    }
    // Para la autoprueba: acciones del módulo Efectos y lo que muestra
    function fxCommand(what, a, b) {
        if (!fxBody) return null
        goTo("fx")                                 // lo que se hace en Efectos se ve en Efectos
        if (what === "target") fxBody.pickTarget(a)
        else if (what === "add") fxBody.add(a)
        else if (what === "param") fxBody.setParam(a, b)
        else if (what === "bypass") fxBody.enable(fxBody.sel, !!a)
        else if (what === "remove") fxBody.remove(fxBody.sel)
        else if (what === "preset") fxBody.applyPreset(a)
        else if (what === "auto") { fxBody.autoParam = a; fxBody.setAuto(b) }
        else if (what === "pick") { var pk = fxBody.chain.filter(function (e) { return e.key === a })[0]; if (pk) fxBody.sel = pk.id }
        else if (what === "ab") fxBody.abToggle(fxBody.cur)
        else if (what === "drop") fxBody.dropAt(fxBody.sel, a)
        else if (what === "macro") fxBody.setMacro(a, b.fx, b.param, b.amount)
        return { lab: fxBody.labInfo ? fxBody.labInfo.linked : null, macros: fxBody.labMacros.length, tuneEditor: fxBody.tuneShown, ab: fxBody.cur && fxBody.ab[fxBody.cur.id] ? fxBody.ab[fxBody.cur.id].side : "",
                 target: fxBody.target, chain: fxBody.chain.map(function (e) { return { id: e.id, key: e.key, enabled: e.enabled, values: e.values, automated: e.automated || [] } }),
                 sel: fxBody.sel, meters: fxBody.meters, spectrum: fxBody.spectrum, catalog: fxBody.catalog.length,
                 presets: fxBody.presets.length, autoPts: fxBody.autoPts }
    }
    property alias mixer: mx
    property alias seq: sq
    property alias project: pj
    Mixer { id: mx; studio: win }
    Sequencer { id: sq; studio: win }
    Lab { id: lb; studio: win; seq: sq }        // Instrumental Lab (lab.py): estado para su vista
    property var lab: lb
    Project { id: pj; studio: win }

    // ---------------- órdenes (F1): un registro (actions.py) → menús, clic derecho y Ctrl+K ----------------
    property var actionsReg: []
    property var actionMenus: []
    function loadActions() { var r = call("actionList"); if (r.ok) { actionsReg = r.actions; actionMenus = r.menus } }
    function actionsOf(menu) { return actionsReg.filter(function (a) { return a.menu === menu }) }
    function actionsCtx(ctx) { return actionsReg.filter(function (a) { return a.ctx.indexOf(ctx) >= 0 }) }
    readonly property var selTrackObj: selected >= 0 && selected < tracks.length ? tracks[selected] : null
    readonly property bool clipPicked: !!arrange.selInfo
    function actionEnabled(id) {
        var t = selTrackObj, a = arrange
        switch (id) {
        case "file.import": case "file.export": case "track.newAudio": return engineOk
        case "edit.analyze": return engineOk && !songBusy
        case "script.folder": case "script.reload": return true
        case "edit.undo": return (view === "mixer" && !!mx.undoSnap && !mx.busy) || a.undoStack.length > 0
        case "edit.redo": return a.redoStack.length > 0
        case "edit.split": case "clip.split": return !!a.clipUid
        case "edit.duplicate": case "edit.delete": case "clip.duplicate": case "clip.delete": case "clip.gainUp": case "clip.gainDown":
        case "clip.normalize": case "clip.fadeIn": case "clip.fadeOut": case "clip.noFades": return clipPicked
        case "clip.repaint": case "clip.cover": return clipPicked && !sq.generating
        case "clip.align": return clipPicked && !sq.alignUid
        case "clip.pitch": return clipPicked && !!a.selTrack && a.selTrack.id > 0 && !sq.pitchBusy
        case "clip.stems": return clipPicked && !!a.selTrack && a.selTrack.type === "audio" && !sq.splitting
        case "clip.tempoKey": case "clip.toProjectTempo": case "clip.projectToTempo": case "clip.toProjectKey":
        case "clip.projectToKey": return clipPicked && !(tkInfo && tkInfo.busy)
        case "clip.original": return clipPicked && ((a.selInfo.speed || 1) !== 1 || (a.selInfo.semitones || 0) !== 0)
        case "track.solo": case "track.mute": case "track.remove": return !!t
        case "track.effects": return !!t && t.id > 0
        case "track.stems": return !!t && t.type === "audio" && t.id >= 0 && !sq.splitting
        case "track.regenerate": return !!t && !!t.gen && !sq.generating
        case "track.newAux": return engineOk
        case "mix.auto": return engineOk && !mx.busy
        case "mix.remix": return mx.items.length > 0 && !mx.busy && mx.runs > 0
        case "mix.abA": case "mix.abB": return engineOk
        case "mix.master": return engineOk && !mx.mastering && !mx.busy
        case "view.arrange": case "view.mixer": case "view.toggle": return !dualWindow || id === "view.mixer"
        }
        return handlerOf(id) !== undefined
    }
    function handlerOf(id) {
        if (actionHandlers[id] !== undefined) return actionHandlers[id]
        if (id.indexOf("script.") === 0 && actionsReg.some(function (x) { return x.id === id }))
            return function () { runScript(id.slice(7) + ".py") }
        return undefined
    }
    function actionChecked(id) {
        var t = selTrackObj
        switch (id) {
        case "edit.snap": return arrange.snap
        case "edit.toolMove": return arrange.tool === "move"
        case "edit.toolCut": return arrange.tool === "cut"
        case "track.solo": return !!t && !!t.solo
        case "track.mute": return !!t && !!t.mute
        case "mix.abA": return mx.abState === "A"
        case "mix.abB": return mx.abState === "B"
        case "view.arrange": return view === "arrange"
        case "view.mixer": return view === "mixer"
        case "view.lab": return newBox.opened && newBox.page === "lab"
        case "view.dual": return dualWindow
        case "view.backdrop": return backdrop.mode !== "none"
        case "view.nav": return !navZ.folded
        case "view.insp": return !inspZ.folded
        case "view.detail": return !detZ.folded
        }
        if (id.indexOf("view.theme") === 0) return Theme.name === id.slice(10)
        return false
    }
    // Qué hace cada orden: lo mismo que el botón o atajo que ya existía (nada nuevo ni decorativo)
    readonly property var actionHandlers: ({
        "file.home": function () { view = "home" },
        "file.open": function () { pj.open("") },
        "file.save": function () { pj.save(false) },
        "file.saveAs": function () { pj.save(true) },
        "file.import": function () { importAudio() },
        "file.export": function () { exportMix() },
        "file.audio": function () { openAudioSettings() },
        "edit.analyze": function () { view = "arrange"; analyzeSong() },
        "edit.undo": function () { if (view === "mixer" && mx.undoSnap) mx.undoMix(); else arrange.undo() },   // F6: en el Mezclador deshace la mezcla automática
        "edit.redo": function () { arrange.redo() },
        "edit.split": function () { arrange.splitAt(arrange.clipUid, arrange.clipSel, posSec) },
        "edit.duplicate": function () { arrange.dupSel() },
        "edit.delete": function () { arrange.removeSel() },
        "edit.snap": function () { arrange.snap = !arrange.snap },
        "edit.toolMove": function () { arrange.tool = "move" },
        "edit.toolCut": function () { arrange.tool = "cut" },
        "track.newAudio": function () { importAudio(); view = dualWindow ? "mixer" : "arrange" },
        "track.newInst": function () { addMore("piano") },
        "track.newDrum": function () { addMore("drums") },
        "track.newVoice": function () { addMore("cinta") },
        "track.newAux": function () { arrange.addAux() },
        "track.new": function () { newTrack("") },
        "track.generate": function () { newTrack("gen") },
        "track.interp": function () { newTrack("interp") },
        "track.regenerate": function () { sq.regenerate(selTrackObj.uid) },
        "track.solo": function () { toggleTrackFlag(selTrackObj.uid, "solo") },
        "track.mute": function () { toggleTrackFlag(selTrackObj.uid, "mute") },
        "track.stems": function () { sq.splitStems(selTrackObj.id) },
        "track.effects": function () { rackTrack = selTrackObj.id; goTo("fx") },
        "track.remove": function () { var i = sq.indexOf(selTrackObj.uid); if (i >= 0) removeTrackAt(i) },
        "clip.split": function () { arrange.splitAt(arrange.clipUid, arrange.clipSel, posSec) },
        "clip.duplicate": function () { arrange.dupSel() },
        "clip.delete": function () { arrange.removeSel() },
        "clip.gainUp": function () { arrange.gainSel(1) },
        "clip.gainDown": function () { arrange.gainSel(-1) },
        "clip.normalize": function () { arrange.edit(arrange.clipUid, { op: "normalize", clip: arrange.clipSel, target: -1 }) },
        "clip.fadeIn": function () { arrange.fadeSel("in", 0.25) },
        "clip.fadeOut": function () { arrange.fadeSel("out", 0.25) },
        "clip.noFades": function () { arrange.edit(arrange.clipUid, { op: "fades", clip: arrange.clipSel, "in": 0, out: 0 }) },
        // F4: la IA sobre el clip se abre en un cuadro junto al clip (dice dónde quedará el resultado)
        "clip.repaint": function () { aiBox.openFor("repaint", arrange.clipUid) },
        "clip.cover": function () { aiBox.openFor("cover", arrange.clipUid) },
        "clip.align": function () { aiBox.openFor("align", arrange.clipUid) },
        "clip.pitch": function () { var id = arrange.selTrack.id; rackTrack = id; pitchEd.trackId = id; goTo("tono"); sq.pitchAnalyze(id) },
        "clip.stems": function () { sq.splitStems(arrange.selTrack.id) },
        "clip.tempoKey": function () { tempoKey("clip.tempoKey") },
        "clip.toProjectTempo": function () { tempoKey("clip.toProjectTempo") },
        "clip.projectToTempo": function () { tempoKey("clip.projectToTempo") },
        "clip.toProjectKey": function () { tempoKey("clip.toProjectKey") },
        "clip.projectToKey": function () { tempoKey("clip.projectToKey") },
        "clip.original": function () { tempoKey("clip.original") },
        "mix.auto": function () { view = "mixer"; mixBox.open() },          // F6: orden del Mezclador con sus ajustes
        "mix.remix": function () { mx.mix(true) },
        "mix.abA": function () { mx.bypass("A") },
        "mix.abB": function () { mx.bypass("B") },
        "mix.master": function () { mx.masterAuto(mx.masterSel) },
        "mix.masterFx": function () { goTo("fxm") },
        "view.arrange": function () { if (dualWindow) flowWin.raise(); else view = "arrange" },
        "view.mixer": function () { view = "mixer" },
        "view.toggle": function () { view = view === "mixer" ? "arrange" : "mixer" },
        "view.lab": function () { newTrack("lab") },
        "view.dual": function () { dualWindow = !dualWindow },
        "view.nav": function () { navZ.folded = !navZ.folded },
        "view.insp": function () { inspZ.folded = !inspZ.folded },
        "view.detail": function () { detZ.folded = !detZ.folded },
        "view.reset": function () { resetLayout() },
        "view.backdrop": function () { backdropBox.open() },
        "view.themeOscuro": function () { setTheme("Oscuro") },
        "view.themeGrafito": function () { setTheme("Grafito") },
        "view.themeClaro": function () { setTheme("Claro") },
        "view.palette": function () { palette.open() },
        "script.folder": function () { call("scriptsFolder") },
        "script.reload": function () { loadActions(); toast(actionsOf("Scripts").length - 2 + " script(s) en el menú Scripts") }
    })
    function runAction(id) {
        var h = handlerOf(id)
        if (!h) { toast("Orden desconocida: " + id); return false }
        if (id.indexOf("script.") === 0 && !actionHandlers[id] && (!engineOk || scriptBusy)) {
            toast(scriptBusy ? "Ya corre el script «" + scriptBusy + "»" : "Los scripts necesitan el motor de audio"); return false }
        if (!actionEnabled(id)) return false
        h()
        return true
    }
    Shortcut { sequence: "Ctrl+K"; onActivated: palette.open() }

    // ---------------- tempo y tonalidad (F11): audio ⇄ proyecto, como en un DAW profesional ----------------
    // Tonalidad del proyecto: la que se ve en la cabecera; el Afinador y la IA la usan
    property var songKey: ({ key: "", scale: "" })
    readonly property var keyNames: ["Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si"]
    readonly property var keyCodes: ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    readonly property var keyOptions: {
        var o = [["", "—"]]
        for (var i = 0; i < 12; i++) o.push([keyCodes[i] + "|Mayor", keyNames[i] + " mayor"])
        for (var j = 0; j < 12; j++) o.push([keyCodes[j] + "|Menor natural", keyNames[j] + " menor"])
        return o
    }
    function keyLabel(k, s) { var i = keyCodes.indexOf(k); return i < 0 ? "—" : keyNames[i] + (String(s).indexOf("Menor") === 0 ? " menor" : " mayor") }
    function setSongKey(k, s, quiet) {
        songKey = { key: k || "", scale: k ? s : "" }
        if (k) mx.setTune({ key: k, scale: s })
        if (!quiet) markDirty()
    }
    // F7: análisis del proyecto (Python, en otro hilo): pista de acordes y marcadores de sección.
    // Se guardan con el proyecto y Ctrl+Z (Arreglo) vuelve a lo de antes.
    property var chords: []                 // [{start, end, root, quality, name, name_es}]
    property var markers: []                // [{start, end, label}]
    property bool songBusy: false
    property var songInfo: null             // lo último que midió: {bpm, key, scale, chords, sections}
    function analyzeSong() {
        if (songBusy) return false
        var ids = tracks.filter(function (t) { return t.id >= 0 && !t.mute && (t.aclips || []).length > 0 })
                        .map(function (t) { return t.id })
        var r = call("projectAnalyze", JSON.stringify(ids), bpm)
        if (!r.ok) { toast(r.error); return false }
        songBusy = true
        toast("Analizando el proyecto: tempo, tonalidad, acordes y secciones…")
        return true
    }
    // F8: scripts del usuario (scripts/*.py, API afo). Corren en otro proceso sobre una copia del proyecto;
    // sus órdenes se aplican aquí, en el hilo de la interfaz, y quedan como UN paso de Ctrl+Z en el Arreglo.
    property string scriptBusy: ""
    property var scriptLast: null           // autoprueba: {name, ok, applied, error, log}
    function scriptSnapshot() {
        return { bpm: bpm, key: songKey, chords: chords, markers: markers,
                 tracks: tracks.filter(function (t) { return t.type !== "master" }).map(function (t) {
                     return { uid: t.uid, id: t.id, type: t.type, name: t.name, vol_db: MD.faderToDb(t.vol === undefined ? 70 : t.vol),
                              pan: ((t.pan === undefined ? 50 : t.pan) - 50) / 50, mute: !!t.mute, solo: !!t.solo,
                              color: t.color || "", clips: t.aclips || [] } }) }
    }
    function runScript(file) {
        if (scriptBusy) { toast("Ya corre el script «" + scriptBusy + "»"); return false }
        var r = call("scriptRun", file, JSON.stringify(scriptSnapshot()))
        if (!r.ok) { toast(r.error); return false }
        scriptBusy = r.name
        toast("Script «" + r.name + "» en marcha (proceso aparte)…")
        return true
    }
    function onScriptDone(ev) {
        scriptBusy = ""
        if (!ev.ok) {
            scriptLast = { name: ev.name, ok: false, applied: 0, error: ev.error, log: ev.log || [] }
            toast("Script «" + ev.name + "»: " + ev.error + ". No se cambió nada"); return
        }
        var n = applyScript(ev.name, ev.commands || [])
        scriptLast = { name: ev.name, ok: true, applied: n.applied, error: "", log: ev.log || [], exported: n.exported }
        var msg = (ev.log || []).slice(-1)[0] || (n.applied + " cambio(s)")
        toast("Script «" + ev.name + "» · " + msg + (n.undo ? " · Ctrl+Z lo deshace" : "") + (n.exported ? " · stems en " + n.exported : ""))
    }
    function applyScript(name, cmds) {
        var entries = [], trkBefore = {}, clipDone = {}, songSaved = false, applied = 0, exportCmd = null, racks = false
        if (cmds.some(function (c) { return c.op === "fx" })) {          // efectos: la instantánea del Mezclador (F6) los devuelve
            var snap = mx.call("snapshot")
            if (snap.ok) entries.push({ mix: snap.tracks })
        }
        cmds.forEach(function (c) {
            var t = c.uid ? sq.trackOf(c.uid) : null
            if (c.uid && !t) return
            if (c.op === "track") {
                if (!trkBefore[c.uid]) trkBefore[c.uid] = { uid: c.uid, vol: t.vol === undefined ? 70 : t.vol, pan: t.pan === undefined ? 50 : t.pan,
                                                            mute: !!t.mute, solo: !!t.solo, name: t.name, color: t.color || "" }
                if (c.vol_db !== undefined || c.pan !== undefined)
                    setTrackMixUid(c.uid, c.vol_db !== undefined ? MD.dbToFader(c.vol_db) : t.vol, c.pan !== undefined ? 50 + 50 * c.pan : t.pan)
                var ch = {}
                ;["mute", "solo", "name", "color"].forEach(function (k) { if (c[k] !== undefined) ch[k] = c[k] })
                sq.replace(c.uid, ch)
            } else if (c.op === "clip_gain") {
                if (!clipDone[c.uid]) { clipDone[c.uid] = true; entries.push({ uid: c.uid, clips: t.aclips || [] }) }
                if (!arrange.edit(c.uid, { op: "gain", clip: c.clip, db: c.db }, true)) return
            } else if (c.op === "markers" || c.op === "chords" || c.op === "key") {
                if (!songSaved) { songSaved = true; entries.push(arrange.songState()) }
                if (c.op === "markers") setSongInfo(chords, c.markers, null)
                else if (c.op === "chords") setSongInfo(c.chords, markers, null)
                else setSongKey(c.key, c.scale, false)
            } else if (c.op === "fx") {
                var f = call("fxAdd", t.id, c.key, -1)
                if (!f.ok) { toast(f.error); return }
                racks = true
            } else if (c.op === "seek") { call("seek", c.t)
            } else if (c.op === "play") { if (!playing) call("togglePlay")
            } else if (c.op === "stop") { call("stop"); step = -1
            } else if (c.op === "export_stems") { exportCmd = c; return }
            applied++
        })
        var tb = Object.keys(trkBefore).map(function (k) { return trkBefore[k] })
        if (tb.length) { entries.push({ trk: tb }); syncTrackStates() }
        if (racks) refreshRacks()
        var exported = ""
        if (exportCmd) {
            var list = exportCmd.uids.map(function (u) { return sq.trackOf(u) }).filter(function (x) { return x && x.id >= 0 })
                                     .map(function (x) { return [x.id, x.name] })
            var folder = exportCmd.folder || (pj.file ? pj.file.replace(/[\\/][^\\/]*$/, "") + "/stems" : "")
            var r = call("exportStems", folder, JSON.stringify(list))
            syncTrackStates()                                 // vuelven el Mute y el Solo de cada pista
            if (r.ok) { exported = r.folder; applied += r.files.length } else toast(r.error)
        }
        if (entries.length) {
            arrange.undoStack = arrange.undoStack.concat([{ multi: entries, label: name }]).slice(-60)
            arrange.redoStack = []
            markDirty()
        }
        return { applied: applied, undo: entries.length > 0, exported: exported }
    }
    function setSongInfo(c, m, k) {
        chords = c || []; markers = m || []
        if (k) setSongKey(k.key, k.scale, true)
        markDirty()
    }
    function onSongAnalysis(ev) {
        songBusy = false
        if (!ev.ok) { toast(ev.error); return }
        arrange.pushSong()
        var sure = ev.key.confidence >= 0.2
        setSongInfo(ev.chords, ev.sections, ev.key.key && sure ? { key: ev.key.key, scale: ev.key.scale } : null)
        songInfo = { bpm: ev.tempo.bpm, key: ev.key.key, scale: ev.key.scale, sure: sure, chords: ev.chords.length, sections: ev.sections.length }
        var tb = ev.tempo.bpm ? (Math.abs(ev.tempo.bpm - bpm) < 0.5 ? "tempo " + bpm + " BPM, como el proyecto"
                                 : "el audio va a " + ev.tempo.bpm + " BPM y el proyecto a " + bpm) : "sin pulso claro"
        toast("Proyecto: " + (ev.key.key ? keyLabel(ev.key.key, ev.key.scale) + (sure ? "" : " (dudosa: no se cambia)") : "sin tonalidad clara")
              + " · " + ev.chords.length + " acordes · " + ev.sections.length + " secciones · " + tb + ". Ctrl+Z lo deshace")
    }
    property var audioInfo: ({})            // uid de la pista → {bpm, key, scale, busy, error}
    property string tkPending: ""           // orden que espera al análisis
    readonly property var tkInfo: arrange.clipUid ? (audioInfo[arrange.clipUid] || null) : null
    function setAudioInfo(uid, v) { var a = Object.assign({}, audioInfo); a[uid] = v; audioInfo = a }
    function analyzeClip(then) {
        var t = arrange.selTrack, c = arrange.selInfo
        if (!t || !c) return false
        tkPending = then || ""
        var r = call("clipAnalyze", t.id, c.id, bpm)
        if (!r.ok) { toast(r.error); tkPending = ""; return false }
        setAudioInfo(t.uid, Object.assign({}, audioInfo[t.uid] || {}, { busy: true, error: "" }))
        toast("Analizando el tempo y la tonalidad de «" + t.name + "»…")
        return true
    }
    function onTempoKey(ev) {
        var uid = ""
        for (var i = 0; i < tracks.length; i++) if (tracks[i].id === ev.trackId) uid = tracks[i].uid
        if (!uid) return
        if (!ev.ok) { setAudioInfo(uid, { busy: false, error: ev.error }); toast(ev.error); tkPending = ""; return }
        var info = { busy: false, error: "", bpm: ev.tempo.bpm, raw: ev.tempo.raw, key: ev.key.key, scale: ev.key.scale,
                     sure: ev.tempo.confidence >= 0.3 && ev.key.confidence >= 0.2 }
        setAudioInfo(uid, info)
        toast("«" + sq.trackOf(uid).name + "»: " + (info.bpm ? info.bpm + " BPM" : "sin pulso claro") + " · "
              + (info.key ? keyLabel(info.key, info.scale) : "sin tonalidad clara") + (info.sure ? "" : " (dudoso: puedes corregirlo)"))
        var next = tkPending; tkPending = ""
        if (next && next !== "clip.tempoKey") runAction(next)
    }
    // Corregir a mano lo detectado (el panel de tempo y tonalidad)
    function setAudioTempo(uid, v) { setAudioInfo(uid, Object.assign({}, audioInfo[uid] || {}, { bpm: v })) }
    function setAudioKey(uid, k, s) { setAudioInfo(uid, Object.assign({}, audioInfo[uid] || {}, { key: k, scale: s })) }
    function clipStretch(speed, semis) {
        var c = arrange.selInfo; if (!c) return null
        return arrange.edit(arrange.clipUid, { op: "stretch", clip: c.id, speed: speed, semitones: semis })
    }
    function keyShift(fk, fs, tk, ts) { return afo.keyShift(fk, fs, tk, ts) }
    // Las cuatro órdenes (y volver al original). Si falta el análisis, lo hace y sigue sola.
    function tempoKey(id) {
        var t = arrange.selTrack, c = arrange.selInfo
        if (!t || !c) return
        var info = audioInfo[t.uid]
        if (id === "clip.original") { clipStretch(1, 0); toast("«" + t.name + "» vuelve a su tempo y su tono"); return }
        if (id === "clip.tempoKey") { tkBox.openFor(t.uid); if (!info || !info.bpm) analyzeClip(id); return }
        if (!info || info.busy || (!info.bpm && !info.key)) { if (!info || !info.busy) analyzeClip(id); return }
        var sp = c.speed || 1, se = c.semitones || 0
        if (id === "clip.toProjectTempo") {
            if (!info.bpm) { toast("No se encontró un pulso claro en el audio: escribe su tempo en «Tempo y tonalidad…»"); return }
            clipStretch(bpm / info.bpm, se)
            toast("«" + t.name + "» a " + bpm + " BPM (estaba a " + info.bpm + "). Ctrl+Z lo deshace")
        } else if (id === "clip.projectToTempo") {
            if (!info.bpm) { toast("No se encontró un pulso claro en el audio: escribe su tempo en «Tempo y tonalidad…»"); return }
            if (sp !== 1) clipStretch(1, se)
            applyTempo(info.bpm)
            toast("El proyecto pasa a " + info.bpm + " BPM, el tempo de «" + t.name + "»")
        } else if (id === "clip.toProjectKey") {
            if (!songKey.key) { toast("El proyecto aún no tiene tonalidad: elígela en la cabecera (Tono) o usa «Proyecto a la tonalidad del audio»"); return }
            if (!info.key) { toast("No se encontró una tonalidad clara: elígela en «Tempo y tonalidad…»"); return }
            var n = keyShift(info.key, info.scale, songKey.key, songKey.scale)
            clipStretch(sp, n)
            toast("«" + t.name + "» de " + keyLabel(info.key, info.scale) + " a " + keyLabel(songKey.key, songKey.scale)
                  + " (" + (n > 0 ? "+" : "") + n + " semitonos). Ctrl+Z lo deshace")
        } else if (id === "clip.projectToKey") {
            if (!info.key) { toast("No se encontró una tonalidad clara: elígela en «Tempo y tonalidad…»"); return }
            if (se !== 0) clipStretch(sp, 0)
            if (!songKey.key) { setSongKey(info.key, info.scale); toast("Tonalidad del proyecto: " + keyLabel(info.key, info.scale)); return }
            var m = keyShift(songKey.key, songKey.scale, info.key, info.scale)
            var moved = transposeProject(m, t.uid)
            setSongKey(info.key, info.scale)
            toast("Proyecto a " + keyLabel(info.key, info.scale) + " (" + (m > 0 ? "+" : "") + m + " semitonos): " + moved + " pista(s) transpuestas")
        }
    }
    // Transpone el proyecto: los clips de audio (en el motor) y las notas de los instrumentos; la batería no
    function transposeProject(n, exceptUid) {
        if (!n) return 0
        var moved = 0
        for (var i = 0; i < tracks.length; i++) {
            var t = tracks[i]
            if (t.uid === exceptUid || t.id < 0) continue
            if ((t.type === "audio" || t.type === "voz") && (t.aclips || []).length) {
                var cs = t.aclips.map(function (c) { return Object.assign({}, c, { semitones: Math.max(-24, Math.min(24, (c.semitones || 0) + n)) }) })
                var r = call("clipEdit", t.id, JSON.stringify({ op: "set", clips: cs }))
                if (r.ok) { sq.replace(t.uid, { aclips: r.clips }); moved++ }
            } else if (t.type === "inst") {
                var cfg = Object.assign({}, t.cfg); cfg.tr = Math.max(-24, Math.min(24, (cfg.tr || 0) + n))
                sq.replace(t.uid, { cfg: cfg }); sq.update(t.uid); moved++
            }
        }
        markDirty()
        return moved
    }
    Shortcut { sequences: [StandardKey.Open]; onActivated: pj.open("") }
    Shortcut { sequences: [StandardKey.Save]; onActivated: pj.save(false) }
    Shortcut { sequence: "Ctrl+Shift+S"; onActivated: pj.save(true) }
    Shortcut { sequence: "F4"; onActivated: win.view = "home" }
    Shortcut { sequence: "Shift+Space"; enabled: !win.typing; onActivated: { if (win.engineOk) win.call("stop"); win.step = -1 } }
    Shortcut { sequence: "Ctrl+Shift+R"; onActivated: win.resetLayout() }
    Shortcut { sequence: "Ctrl+,"; onActivated: win.openAudioSettings() }
    Shortcut { sequence: "F5"; onActivated: win.view = "arrange" }
    Shortcut { sequence: "F6"; onActivated: win.view = "mixer" }
    Shortcut { sequence: "F7"; onActivated: win.dualWindow = !win.dualWindow }
    Shortcut { sequence: "F8"; onActivated: win.newTrack("lab") }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: !win.typing; onActivated: win.newTrack("") }
    property alias arrangeView: arrange
    // Para la autoprueba: guardar y abrir proyectos sin diálogo
    // Para la autoprueba: Inicio (biblioteca). a/b según la acción
    function homeCommand(what, a, b) {
        if (what === "show") view = "home"
        else if (what === "create") { var it = homeView.create(a, b, a === "release" ? { type: "album" } : {}); return it ? it.path : "" }
        else if (what === "open") { var s = homeView.song; if (s) homeView.openSong(s) }
        homeView.reload()
        return { view: view, visible: homeView.visible, title: pj.title, file: pj.file, songTarget: pj.songTarget,
                 artists: homeView.tree.map(function (x) { return x.name }), song: homeView.song,
                 recent: homeView.recent.map(function (x) { return x.path }) }
    }
    function projectCommand(what, path) {
        if (what === "save") { pj.file = path; return pj.save(false) }
        if (what === "open") return pj.open(path)
        if (what === "loose") { pj.newLoose(); return true }
        return pj.snapshot()
    }
    onBpmChanged: { sq.rerenderAll(); markDirty() }   // el patrón depende del tempo: se vuelve a sintetizar
    onHiddenChanged: { syncTrackStates(); sq.arm() }   // módulo quitado = sus pistas desconectadas (no suenan ni graban)
    onTracksChanged: markDirty()
    // La selección manda (DISENO_DAW §1.3): al elegir una pista, Efectos muestra su cadena y el panel de
    // detalle abre su editor (patrón, notas, clips)
    function followSelection(t) {
        if (!t || loading) return
        selPicked = { id: t.id, type: t.type }                          // el tipo lo dice la pista elegida
        if (t.id > 0) rackTrack = t.id
        if (t.type === "inst") sq.oct = (t.cfg && t.cfg.oct) || 4      // la Octava es de cada pista
        fitDetail()
    }
    // F3 (FLUJO_PROFESIONAL §2): el editor de abajo no tiene pestañas fijas; muestra los modos de lo
    // elegido (la tira o pista de rackTrack): instrumento → notas, sonido y efectos; batería → patrón
    // y efectos; audio y voz → efectos, tono (AF-64) y afinador (AF-60); master → efectos.
    readonly property var detTrack: { for (var i = 0; i < tracks.length; i++) if (tracks[i].id === rackTrack) return tracks[i]; return null }
    property var selPicked: ({ id: -2, type: "" })
    // se calcula al momento: onRackTrackChanged llega antes de que se actualicen las propiedades enlazadas
    function kindOf(rt, picked, tr) {
        if (rt === 0) return "master"
        if (picked.id === rt && picked.type) return picked.type
        for (var i = 0; i < tr.length; i++) if (tr[i].id === rt) return tr[i].type
        return fxMain && fxMain.target === 0 ? "master" : ""     // sin tira elegida (o ya no existe), Efectos enseña el master
    }
    readonly property string detKind: kindOf(rackTrack, selPicked, tracks)
    readonly property var detAll: ({ piano: ["Notas", "Piano roll: las notas de la pista de instrumento"],
                                     inst: ["Sonido", "El instrumento de la pista: sintetizador del motor o VST3"],
                                     drums: ["Patrón", "Pads y patrón de 16 pasos de la batería"],
                                     fx: ["Efectos", "La cadena de efectos de lo elegido y el editor del efecto elegido"],
                                     tono: ["Tono", "Editor de tono (AF-64): las notas de la toma, una a una"],
                                     afina: ["Afinador", "Afinador en tiempo real AF-60 de la pista"] })
    function detModesFor(kind) {
        return ({ inst: ["piano", "inst", "fx"], drum: ["drums", "fx"], audio: ["fx", "tono", "afina"],
                  voz: ["fx", "tono", "afina"], ia: ["fx", "tono", "afina"] })[kind] || ["fx"]
    }
    readonly property var detModes: {
        var ids = detModesFor(detKind).slice()
        if (ids.indexOf(detZ.current) < 0) ids.push(detZ.current)       // una orden abrió otro editor
        return ids.map(function (id) { return [id, detAll[id][0], detAll[id][1]] })
    }
    function fitDetail() {
        if (loading) return
        var k = kindOf(rackTrack, selPicked, tracks), ids = detModesFor(k)
        if (ids.indexOf(detZ.current) < 0) detZ.current = ids[0]
        if (["audio", "voz", "ia"].indexOf(k) >= 0) { tuneBody.trackId = rackTrack; pitchEd.trackId = rackTrack }
    }
    onRackTrackChanged: fitDetail()
    readonly property real bar16: 16 * 4 * 60 / Math.max(40, bpm)
    property real stripScroll: 0               // desplazamiento horizontal de las tiras de la consola
    function setDark(b) { setTheme(b ? "Oscuro" : "Claro") }
    // ---------------- temas (carpeta templates/) ----------------
    property var themes: []
    function loadThemes() { var r = call("themeList"); if (r.ok) themes = r.themes; return themes }
    function setTheme(name, quiet) {
        var r = call("themeLoad", name)
        if (!r.ok) { if (!quiet) toast(r.error); Theme.apply({}); return false }
        Theme.apply(r.theme)
        if (!loading) saveLayout()
        return true
    }
    // Para la autoprueba y las comparaciones: estado del mezclador, mezclar y encuadrar un módulo a zoom 1
    function mixerSnapshot() {
        return { items: mx.items, runs: mx.runs, busy: mx.busy, status: mx.status, live: mx.live,
                 tune: mx.tune, tuned: (mx.tuneStrength > 0 ? mx.tunedStrips() : []).map(function (k) { return k.name }),
                 lastTuned: mx.lastTuned, master: mx.masterStats, mastering: mx.mastering, rackTrack: rackTrack,
                 versions: mx.versions.map(function (v) { return { name: v.name, kind: v.kind, fx: v.chain.length, lufs: v.lufs } }),
                 versionSel: mx.versionSel,
                 masterChain: engineOk ? (call("fxList", 0).chain || []).map(function (e) { return e.label || e.key }) : [],
                 masterLoud: masterLoud,
                 tracks: tracks.map(function (t) { return { uid: t.uid, id: t.id, type: t.type, name: t.name, vol: t.vol, pan: t.pan,
                                                             len: t.len || 0, peaks: (t.peaks || []).length,
                                                             notes: Object.keys(t.roll || {}).length + Object.keys(t.pat || {}).length,
                                                             midi: (t.midi || []).length, sub: sq.sub(t),
                                                             takes: (t.takes || []).map(function (k) { return { name: k.name } }), take: t.take || 0 } }),
                 act: sq.act, voice: sq.active("inst") ? sq.active("inst").cfg.v : -1 }
    }
    // Para la autoprueba: la pista de batería activa (patrón del Step Sequencer y ajustes)
    function drumSnapshot() {
        var t = sq.active("drum")
        return t ? { type: t.type, clips: t.clips, pat: t.pat, cfg: t.cfg } : null
    }
    // Para la autoprueba: acciones del secuenciador
    function seqCommand(what, a, b) {
        if (what === "add") sq.addTrack(a)
        else if (what === "roll") sq.toggleRoll(a, b)
        else if (what === "step") sq.toggleStep(a, b)
        else if (what === "stepcycle") sq.cycleStep(a, b[0], b[1])
        else if (what === "drumcfg") sq.setCfg("drum", a, b)
        else if (what === "voice") sq.setVoice(a)
        else if (what === "aigen") { sq.setCfg("ia", "prompt", a); sq.setCfg("ia", "dur", b || 30); sq.generate() }
        else if (what === "hide") setHidden(a, b)
        else if (what === "record") sq.startTake()
        else if (what === "recstop") sq.stopTake(false)
        else if (what === "midi") { sq.iaMode = "midi"; sq.openMidi(a, b) }
        else if (what === "song") sq.iaMode = "song"
        else if (what === "drop") removeTrackAt(tracks.length - 1)
        else if (what === "cfg") sq.setCfg("inst", a, b)
    }
    function mixNow(remix) { mx.mix(!!remix) }
    function openProject(path) { return pj.open(path) }
    function setTuneStrength(v) { mx.tuneStrength = v }
    function tuneCommand(what, v) { if (what === "confirm") mx.confirmTune(); else mx.setTuneParam(what, v) }
    function mixerCommand(what, a) {
        if (what === "master") mx.masterAuto(a === undefined ? mx.masterSel : a)
        else if (what === "unmaster") mx.unmaster()
        else if (what === "saveVersion") mx.saveVersion("", "manual", null)
        else if (what === "loadVersion") mx.loadVersion(a)
        else if (what === "ab") mx.bypass(a)
        else if (what === "rack") rackTrack = a
        else if (what === "meter") meterMode = a
        return mixerSnapshot()
    }
    // Para la autoprueba: zonas fijas, ir a una página, plegar, contraste, vistas y temas
    // F12: huecos y desbordes de la distribución a este tamaño de ventana
    function fitReport() {
        var r = zoneRects(), area = 0
        for (var k in r) if (r[k].visible) area += r[k].w * r[k].h
        var right = 0
        for (var i = 0; i < leftGroup.children.length; i++) {
            var c = leftGroup.children[i]
            if (c.visible) right = Math.max(right, c.mapToItem(null, c.width, 0).x)
        }
        var mixFill = view === "mixer" ? Math.round(mixBody.height - mixFlick.height) : 0
        return { w: Math.round(width), h: Math.round(height), zones: r, covered: Math.round(area),
                 headerRight: Math.round(right), mainW: r.principal.w, mainH: r.principal.h, mixGap: mixFill,
                 navW: r.navegador.w, inspW: r.inspector.w, detailH: r.detalle.h }
    }
    function zoneRects() {
        var out = {}, z = { menus: menuBar, cabecera: header, navegador: navZ, principal: mainArea, inspector: inspZ, detalle: detZ, estado: statusBar }
        for (var k in z) { var it = z[k], p = it.mapToItem(null, 0, 0); out[k] = { x: Math.round(p.x), y: Math.round(p.y), w: Math.round(it.width), h: Math.round(it.height), visible: it.visible } }
        return out
    }
    function layoutCommand(what, a, b) {
        if (what === "zones") return zoneRects()
        if (what === "fit") return fitReport()
        if (what === "fxhelp") return fxMain.helpTexts()
        if (what === "sections") return { nav: navZ.sectionInfo(a), insp: inspZ.sectionInfo(a), detTabs: !detZ.sections }
        if (what === "actions") { loadActions()
                                  return { ids: actionsReg.map(function (x) { return x.id }),
                                           missing: actionsReg.filter(function (x) { return handlerOf(x.id) === undefined }).map(function (x) { return x.id }),
                                           extra: Object.keys(actionHandlers).filter(function (k) { return !actionsReg.some(function (x) { return x.id === k }) }),
                                           menus: actionMenus, clip: actionsCtx("clip").map(function (x) { return x.id }),
                                           track: actionsCtx("track").map(function (x) { return x.id }) } }
        if (what === "run") return { ok: runAction(a), enabled: actionEnabled(a), checked: actionChecked(a) }
        if (what === "arrangeScroll") {          // F10: lleva el scroll del Arreglo a una fracción (0..1)
            arrange.scrollTo(a); return arrange.scrollProgress > 0 || a === 0 }
        if (what === "backdrop") {               // F10: poner (a = modo, b = ruta), ajustar y medir
            if (a === "set") setBackdrop(b)
            else if (a) chooseBackdrop(a, b)
            var zs = [["zona", Theme.panelColor("", Theme.sidebar)], ["Inicio", Theme.canvas], ["Arreglo", Theme.device],
                      ["Mezclador", Theme.panelColor("mezcla", Theme.pc.mezcla)]]
            return { state: backdrop, on: backdropView.on, visible: backdropView.visible, alpha: Theme.surfaceAlpha, zoneAlpha: backdropZoneAlpha,
                     bg: String(Theme.bg), ink: String(Theme.ink), inkDim: String(Theme.inkDim),
                     surfaces: zs.map(function (z) { return [z[0], String(z[1]), Theme.veil(z[1]).a] }),
                     zoneColorA: navZ.color.a, emptyBelow: arrange.emptyBelow(), surfaceVisible: arrange.backdropOn,
                     layerX: backdropView.children.filter(function (c) { return c.source !== undefined }).map(function (c) { return c.x }),
                     progress: arrange.scrollProgress }
        }
        if (what === "script") {                 // F8: lanzar, estado y deshacer
            if (a === "undo") arrange.undo()
            else if (a) return runScript(a)
            return { busy: scriptBusy, last: scriptLast, undo: arrange.undoStack.length,
                     tracks: tracks.map(function (t) { return { uid: t.uid, name: t.name, vol: t.vol, color: t.color || "", mute: !!t.mute,
                                                                gains: (t.aclips || []).map(function (c) { return c.gain_db }) } }),
                     markers: markers.map(function (m) { return m.label }) }
        }
        if (what === "menu") { if (a === "palette") { palette.open(); palette.query = b || ""; return { open: palette.visible, hits: palette.hits.map(function (x) { return x.id }) } }
                               if (a === "close") { palette.close(); barMenu.close(); ctxMenu.close(); return true }
                               if (a === "ctx") { openContext(b, menuBar, 40, 10); return { open: ctxMenu.visible, count: ctxMenu.count } }
                               barMenu.menu = a; barMenu.items = actionsOf(a); barMenu.openAt(menuBar, 6, menuBar.height)
                               return { open: barMenu.visible, count: barMenu.count } }
        if (what === "browser") { if (a) fxBrowser.add(a)
                                  return { sections: fxBrowser.sections.map(function (s) { return [s[0], s[1].map(function (d) { return d.key })] }),
                                           target: fxBrowser.targetName } }
        if (what === "pages") return navZ.tabs.concat(inspZ.tabs).map(function (t) { return t[0] }).concat(Object.keys(detAll))
        if (what === "modes") { if (a !== undefined && a !== null) rackTrack = a; fitDetail()
                                return { kind: detKind, modes: detModes.map(function (m) { return m[0] }), current: detZ.current,
                                         caption: detZ.caption, pitchTrack: pitchEd.trackId } }
        if (what === "overlaps") {
            var r = zoneRects(), ks = Object.keys(r).filter(function (k) { return r[k].visible && r[k].w > 0 && r[k].h > 0 }), out = []
            for (var i = 0; i < ks.length; i++)
                for (var j = i + 1; j < ks.length; j++) {
                    var p = r[ks[i]], q = r[ks[j]]
                    if (p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h) out.push(ks[i] + "/" + ks[j])
                }
            return out
        }
        if (what === "goto") { goTo(a); var zn = zoneOf(currentId); return { currentId: currentId, zone: zn ? zn.title : "", page: zn ? zn.current : "",
                                                                     folded: zn ? zn.folded : true, view: view } }
        if (what === "fold") { var zf = ({ nav: navZ, insp: inspZ, detail: detZ })[a]; zf.folded = !!b; return zoneRects() }
        if (what === "select") { sq.pick(a); fitDetail(); return { detail: detZ.current, rack: rackTrack, kind: detKind, picked: tracks[a] ? tracks[a].type + ":" + tracks[a].id : "" } }
        if (what === "contrast") {                // pares texto/fondo del tema actual (guía de diseño §8)
            var c = function (x) { return String(x) }, out2 = [
                ["texto/fondo", c(Theme.ink), c(Theme.bg)], ["texto/cabecera", c(Theme.ink), c(Theme.header)],
                ["texto/campo", c(Theme.ink), c(Theme.input)], ["texto/botón", c(Theme.ink), c(Theme.button)],
                ["texto/menú", c(Theme.ink), c(Theme.sidebar)], ["botón pulsado", c(Theme.pressedInk), c(Theme.pressedBg)],
                ["botón principal", c(Theme.inkOnAccent), c(Theme.accent)], ["chip del modelo", c(Theme.chipInk), c(Theme.chip)],
                ["dispositivo", c(Theme.deviceInk), c(Theme.device)], ["cabecera de dispositivo", c(Theme.deviceInk), c(Theme.deviceHead)],
                ["pantalla", c(Theme.screenInk), c(Theme.screen)], ["tarjeta de pantalla", c(Theme.screenInk), c(Theme.screenCard)],
                ["texto secundario de pantalla", c(Theme.screenDim), c(Theme.screenCard)],
                ["pantalla con el ratón", c(Theme.screenInk), c(Theme.screenHover)],
                ["texto secundario/zona", c(Theme.inkDim), c(Theme.s1)], ["texto secundario/control", c(Theme.inkDim), c(Theme.s3)],
                ["texto/ratón encima", c(Theme.ink), c(Theme.pn2)], ["ayuda emergente", c(Theme.tipInk), c(Theme.tipBg)],
                ["lectura LCD", c(Theme.lcd), c(Theme.lcdBg)], ["lectura LCD secundaria", c(Theme.lcdSoft), c(Theme.lcdBg)],
                ["texto sobre grabar", c(Theme.inkOnColor), c(Theme.rec)], ["aviso en rojo", c(Theme.recInk), c(Theme.s1)],
                ["texto sobre IA", c(Theme.inkOnColor), c(Theme.ai)], ["texto sobre medidor", c(Theme.inkOnColor), c(Theme.meterOk)]]
            for (var ti = 0; ti < Theme.tracks.length; ti++)
                out2.push(["texto sobre pista " + (ti + 1), c(Theme.inkOnColor), c(Theme.tracks[ti])])
            for (var mk2 in Theme.pc) out2.push(["texto sobre color " + mk2, c(Theme.inkOnColor), c(Theme.pc[mk2])])
            for (var mid in Theme.pc) {
                out2.push(["título " + mid, c(Theme.headInk(Theme.pc[mid])), c(Theme.panelHead)])
                if (mid !== "piano") out2.push(["cuerpo " + mid, c(Theme.ink), c(Theme.panelColor(mid, Theme.pc[mid]))])
            }
            return out2
        }
        if (what === "view") { if (a === "lab") newTrack("lab"); else { if (a) view = a; newBox.close() }
                               return { view: view, lanes: arrange.laneCount, inserts: arrange.insertCount, rows: arrange.rows.length,
                                        visible: arrange.visible, modules: mixPage.visible,
                                        auxes: mixBody.auxes.length, sends: mixBody.sendCount, sendsH: mixBody.sendsH,
                                        mixInserts: mixBody.insertCount } }
        // Bus Aux desde el Mezclador (autoprueba): a = [nombre del bus, id de la pista que envía, dB]
        if (what === "aux") { var at = mixBody.addAux()
                              if (!at || at.id < 0) return { ok: false }
                              mixBody.setSend(a[1], at.id, a[2], false)
                              return { ok: true, id: at.id, sends: mixBody.sendCount, uid: at.uid } }
        // Edición de un clip desde el Arreglo (autoprueba): a = pista (uid), b = operación con «clip»
        if (what === "arrClip") { arrange.pick(a, b.clip || 0)
                                  var rc = b.op === "split" ? (arrange.splitAt(a, b.clip, b.at), { clips: sq.trackOf(a).aclips }) : arrange.edit(a, b)
                                  return { ok: !!rc, clips: rc ? rc.clips : [], undo: arrange.undoStack.length } }
        // F4 (autoprueba): órdenes del secuenciador, estado de tomas y carpetas, y el cuadro de IA del clip
        if (what === "seq") return sq[a].apply(sq, b || [])
        if (what === "seqSet") { sq[a] = b; return true }
        if (what === "song") {                       // autoprueba F7: análisis del proyecto
            if (a === "run") return analyzeSong()
            if (a === "undo") arrange.undo()
            return { busy: songBusy, chords: chords.map(function (c) { return [c.start, c.end, c.name] }),
                     markers: markers.map(function (m) { return [m.start, m.end, m.label] }), key: songKey, info: songInfo,
                     lane: arrange.songLaneInfo() }
        }
        if (what === "f6") {                         // autoprueba F6: un solo mezclador
            if (a === "close") mixBox.close(); else if (a === "masterA" || a === "masterB") mx.bypassMaster(a.slice(-1)); else if (a) runAction(a)
            var autoOn = 0, autoAll = 0
            tracks.forEach(function (t) {
                if (t.id < 0) return
                ;(call("fxList", t.id).chain || []).forEach(function (e) { if (e.auto) { autoAll++; if (e.enabled) autoOn++ } })
            })
            var ma = (call("fxList", 0).chain || []).filter(function (e) { return e.auto })
            return { insp: inspZ.tabs.map(function (t) { return t[0] }), bar: mixBody.barTexts(), box: mixBox.opened, view: view,
                     ab: mx.abState, masterAb: mx.masterAb, autoOn: autoOn, autoAll: autoAll,
                     masterAuto: ma.length, masterOn: ma.filter(function (e) { return e.enabled }).length,
                     undo: mx.undoSnap ? mx.undoSnap.vols : null, runs: mx.runs, busy: mx.busy }
        }
        if (what === "newTrack") { if (a === "close") { newBox.close(); return true }
                                   newTrack(a); return { opened: newBox.opened, page: newBox.page,
                                                         kinds: newBox.kinds.map(function (k) { return k[0] }),
                                                         nav: navZ.tabs.map(function (t) { return t[0] }), view: view } }
        if (what === "dropTrack") { var dt = sq.trackOf(a); if (!dt) return false        // pista y su fila de la Mezcla IA
                                    for (var di = 0; di < mx.items.length; di++) if (mx.items[di].trackId === dt.id) { mx.removeItem(di); break }
                                    removeTrackAt(sq.indexOf(a)); return true }
        if (what === "f4") return { tracks: tracks.map(function (t) {
                                        return { uid: t.uid, id: t.id, name: t.name, takes: (t.takes || []).map(function (k) { return k.name }),
                                                 take: t.take || 0, folder: t.folder || "", fold: !!t.fold, mute: !!t.mute, gen: !!t.gen } }),
                                    rows: arrange.rows.map(function (t) { return t.uid }), tools: arrange.toolTexts(),
                                    snap: pj.snapshot().tracks.map(function (x) { return { uid: x.uid, takes: x.takes ? x.takes.length : 0,
                                                                                            take: x.take, folder: x.folder || "", gen: !!x.gen } }) }
        if (what === "aiBox") { arrange.pick(b, a === "x" ? 0 : (sq.trackOf(b).aclips[0] || {}).id || 0)
                                aiBox.openFor(a, b)
                                var ob = { opened: aiBox.opened, where: aiBox.where[a] || "", can: aiBox.can }
                                aiBox.close(); return ob }
        if (what === "arrUndo") { arrange.undo(); return { clips: sq.trackOf(a).aclips, redo: arrange.redoStack.length } }
        if (what === "auxRemove") { var ai = sq.indexOf(a); if (ai >= 0) removeTrackAt(ai); return ai >= 0 }
        if (what === "theme") { var ok = setTheme(a, true)
                                var cols = { accent: String(Theme.accent) }
                                for (var mk in Theme.pc) cols[mk] = String(Theme.pc[mk])
                                return { ok: ok, name: Theme.name, frame: Theme.frame, knob: Theme.knobStyle, colors: cols,
                                                                   themes: loadThemes().map(function (t) { return t.name }) } }
        return null
    }
    // Conectar / desconectar una fuente (sus pistas dejan de sonar y de grabar; nada se borra)
    function setHidden(id, b) { var h = Object.assign({}, hidden); h[id] = !!b; hidden = h }

    // ---------------- F10: fondo opcional (FLUJO_PROFESIONAL §7), apagado de fábrica ----------------
    readonly property var backdropFactory: ({ mode: "none", layers: [], dir: "", name: "", dark: "", light: "",
                                              intensity: 50, atten: 50, zoneAlpha: 8, reduce: false })
    property var backdrop: backdropFactory
    Binding { target: Theme; property: "surfaceAlpha"; value: win.backdrop.mode === "none" ? 1 : 1 - win.backdropZoneAlpha / 100 }
    // La transparencia de las zonas se queda en lo que permite el contraste (≥ 4,5:1 del texto y del texto
    // secundario) con el píxel más oscuro y el más claro de la imagen, ya atenuada: nunca se pasa de ahí.
    function lumOf(c) {
        c = Qt.color(c)
        var f = function (x) { return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4) }
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b)
    }
    function mixC(a, b, t) { a = Qt.color(a); b = Qt.color(b); return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1) }
    function ratioOf(f, b) { var x = lumOf(f), y = lumOf(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }
    function backdropSurfaces() { return [Theme.panelColor("", Theme.sidebar), Theme.canvas, Theme.device, Theme.panelColor("mezcla", Theme.pc.mezcla)] }
    function backdropContrastOk(pct) {
        var px = [backdrop.dark, backdrop.light].filter(function (p) { return !!p }), ss = backdropSurfaces()
        for (var i = 0; i < px.length; i++) {
            var under = mixC(px[i], Theme.bg, backdrop.atten / 100)
            for (var j = 0; j < ss.length; j++) {
                var eff = mixC(ss[j], under, pct / 100)
                if (ratioOf(Theme.ink, eff) < 4.5 || ratioOf(Theme.inkDim, eff) < 4.5) return false
            }
        }
        return true
    }
    readonly property real backdropZoneAlpha: {
        if (backdrop.mode === "none") return 0
        for (var a = backdrop.zoneAlpha; a > 0; a -= 0.5) if (backdropContrastOk(a)) return a
        return 0
    }
    function setBackdrop(ch) {
        var b = Object.assign({}, backdrop, ch)
        b.intensity = Math.max(0, Math.min(100, b.intensity)); b.atten = Math.max(0, Math.min(80, b.atten))
        b.zoneAlpha = Math.max(0, Math.min(15, b.zoneAlpha))
        backdrop = b
        if (!loading) saveLayout()
    }
    // Ninguno / Imagen / Parallax: elegir el archivo o la carpeta (o, sin diálogo, `src` en la autoprueba)
    function chooseBackdrop(mode, src) {
        if (mode === "none") { setBackdrop({ mode: "none", layers: [], dir: "", name: "", dark: "", light: "" }); toast("Sin fondo"); return true }
        var r = src ? call("backdropUse", mode, src) : call("backdropPick", mode)
        if (!r.ok) { if (!r.cancelled) toast(r.error); return false }
        setBackdrop({ mode: r.mode, layers: r.layers, dir: r.dir, name: r.name, dark: r.dark, light: r.light })
        toast("Fondo: «" + r.name + "» (" + r.layers.length + (r.layers.length === 1 ? " capa" : " capas") + "), copiado a datos/fondos")
        return true
    }

    // ---------------- diseño guardado ----------------
    function saveLayout() {
        layoutStore.save(JSON.stringify({ v: layoutVersion, theme: Theme.name, view: view === "home" ? "arrange" : view, look2: 3, detailH: detailH,
                                          fold: { nav: navZ.folded, insp: inspZ.folded, detail: detZ.folded },
                                          tab: { nav: navZ.current, insp: inspZ.current, detail: detZ.current }, backdrop: backdrop }))
    }
    // Versión de la distribución: un diseño guardado de otra versión no se aplica; solo
    // se conserva el tema
    readonly property int layoutVersion: 7
    property var savedLayout: {
        var d
        try { d = JSON.parse(layoutStore.load()) } catch (e) { return {} }
        return d.v === layoutVersion ? d : { theme: d.theme, look2: d.look2, backdrop: d.backdrop }
    }
    function resetLayout() {
        navZ.folded = false; inspZ.folded = false; detZ.folded = false; detailH = 360
        navZ.current = "add"; inspZ.current = "pista"; detZ.current = "fx"
        saveLayout()
        toast("Distribución de fábrica restaurada")
    }

    // ---------------- ir a una página ----------------
    // Cada cuerpo de módulo vive en una página de una zona fija (DISENO_DAW §2). goTo abre su zona y su
    // pestaña; la consola es la vista Mezclador.
    readonly property var pageZone: ({ audios: "nav", add: "nav", fxlist: "nav", recent: "nav",
                                       pista: "insp", master: "insp", cinta: "insp",
                                       inst: "detail", piano: "detail", drums: "detail",
                                       fx: "detail", tono: "detail", afina: "detail" })
    function zoneOf(id) { return ({ nav: navZ, insp: inspZ, detail: detZ })[pageZone[id]] || null }
    function titleOf(id) {
        return ({ audios: "Archivos", add: "Añadir", fxlist: "Efectos", recent: "Inicio", pista: "Pista",
                  master: "Master", cinta: "Grabar", pistas: "Arreglo", inst: "Instrumento", piano: "Piano roll",
                  drums: "Batería", fx: "Efectos", tono: "Tono", afina: "Afinador", mezcla: "Mezclador" })[id] || id
    }
    function goTo(id) {
        if (id === "mastia") id = "fxm"                         // F6: Master IA es un dispositivo del master (Efectos)
        if (id === "antes") id = "fx"                           // F6: Antes / Después va bajo el rack en Efectos
        if (id === "fxm") { rackTrack = 0; id = "fx" }          // el master es un canal más de Efectos
        if (id === "ia" || id === "lab") { newTrack(id === "ia" ? "gen" : "lab"); return }   // F5: en «Pista nueva»
        currentId = id
        if (id === "mezcla") { if (!dualWindow) view = "mixer"; return }
        if (id === "pistas") { view = dualWindow ? "mixer" : "arrange"; return }   // los clips se editan en el Arreglo
        var z = zoneOf(id)
        if (!z) return
        z.current = id; z.folded = false
    }
    function addMore(base) {
        var type = ({ piano: "inst", inst: "inst", drums: "drum", ia: "ia", cinta: "voz" })[base]
        if (type) { sq.addTrack(type); goTo(sq.src[type] === "inst" ? "piano" : sq.src[type]); return }
        if (base === "audios" || base === "pistas") {
            if (engineOk) importAudio(); else toast("Motor nativo no disponible")
            goTo("pistas")
        }
    }
    function addInstrument(voice) {
        sq.addTrack("inst"); sq.setCfg("inst", "v", voice); goTo("inst")
        toast("Pista nueva: " + sq.insts[voice][0])
    }
    function addEffect(key) {
        if (!fxBody || !key) return
        fxBody.add(key); goTo("fx")
    }
    property bool loading: true

    // ---------------- plugins VST3 externos ----------------
    function scanPlugins() {
        if (!engineOk) { toast("Motor nativo no disponible"); return }
        if (pluginScanning) return
        var r = call("pluginScan")
        if (!r.ok) { pluginStatus = r.error; return }
        pluginScanning = true
        pluginStatus = "Buscando plugins VST3 en otro proceso (puedes seguir trabajando; la primera vez tarda unos minutos)…"
    }
    // Avance de la búsqueda (otro proceso): si un plugin la tumba, se salta y sigue
    function onScanEvent(ev) {
        if (ev.phase === "progress") {
            pluginStatus = (ev.skipped ? "«" + ev.name + "» cerró el buscador: se salta. " : "") + "Abriendo " + ev.name + "…"
            return
        }
        pluginScanning = false
        if (ev.plugins) plugins = ev.plugins
        if (ev.error) { pluginStatus = ev.error; return }
        pluginStatus = plugins.length + " plugins VST3" + (ev.folders.length ? " en " + ev.folders.join(", ") : "")
                     + (ev.crashed.length ? " · saltados por cerrar el buscador: " + ev.crashed.join(", ") : "")
                     + (ev.failed.length ? " · " + ev.failed.length + " no se pudieron abrir" : "")
        toast("Búsqueda de plugins terminada: " + plugins.length + " VST3")
    }
    function loadPluginList() {
        var r = call("pluginList")
        if (r.ok) { plugins = r.plugins; if (r.plugins.length) pluginStatus = r.plugins.length + " plugins VST3 (lista guardada)" }
    }
    function addPluginEffect(p) {
        if (!fxBody) return
        fxBody.addPlugin(p.id); goTo("fx")
    }
    function addPluginInstrument(p) {
        sq.addTrack("inst")
        sq.setCfg("inst", "plugin", p.id)
        goTo("inst")
        toast("Pista nueva con " + p.name + " (VST3)")
    }

    // ---------------- motor ----------------
    function call(name) {
        var args = Array.prototype.slice.call(arguments, 1)
        var r
        try { r = JSON.parse(afo[name].apply(afo, args)) } catch (e) { return { ok: false, error: String(e) } }
        if (r.ok && editCalls.indexOf(name) >= 0) markDirty()
        return r
    }
    // stem = false: la pista no es un audio para el mezclador (tono de prueba, master enviado a Pistas)
    function addTrack(info, stem) {
        var t = tracks.slice()
        t.push({ uid: "a" + info.id, id: info.id, type: "audio", name: info.name, len: info.length_seconds || 0, peaks: info.peaks || [],
                 note: info.note || "", mute: false, solo: false, vol: 70, pan: 50, aclips: clipsOf(info.id) })
        tracks = t; selected = t.length - 1
        if (stem !== false) mx.linkTrack(info)
    }
    // Clips de audio de una pista del motor (Pistas los edita como en un DAW)
    function clipsOf(id) { var r = engineOk && id >= 0 ? call("clipList", id) : null; return r && r.ok ? r.clips : [] }
    function refreshClips(uid) {
        var i = sq.indexOf(uid); if (i < 0) return
        var t = tracks.slice(); t[i] = Object.assign({}, t[i], { aclips: clipsOf(t[i].id) }); tracks = t
    }
    function removeTrackAt(i) {
        var t = tracks.slice(), gone = t.splice(i, 1)[0]
        if (gone.type === "audio") call("removeTrack", gone.id)
        tracks = t
        sq.forget(gone)
        if (selected >= t.length) selected = t.length - 1
        if (gone.id >= 0) mx.unlinkTrack(gone.id)
    }
    // Fader (0..100, 70 = 0 dB) y paneo (0..100, 50 = centro) de una pista, en la interfaz y en el motor
    function setTrackMix(id, vol, pan) {
        for (var i = 0; i < tracks.length; i++) if (tracks[i].id === id) setTrackMixUid(tracks[i].uid, vol, pan)
    }
    function setTrackMixUid(uid, vol, pan) {
        var i = sq.indexOf(uid), old = i >= 0 ? tracks[i] : null
        var ov = old && old.vol !== undefined ? old.vol : -1, op = old && old.pan !== undefined ? old.pan : -1
        var t = sq.replace(uid, { vol: Math.round(vol), pan: pan })
        if (!t || t.id < 0 || !engineOk) return
        if (Math.round(vol) !== ov && !autoWrite("track", t.id, "volume", MD.faderToDb(Math.round(vol))))
            call("setTrackVolume", t.id, Math.round(vol))
        if (pan !== op && !autoWrite("track", t.id, "pan", (pan - 50) / 50))
            call("setTrackPan", t.id, (pan - 50) / 50)
    }
    // Automatización en vivo (Touch / Latch / Write): mientras suena, un control de una pista que no
    // está en Read graba su valor en la curva; devuelve false si no escribe (se aplica el valor fijo).
    function autoWrite(kind, id, param, value) {
        if (!playing || !engineOk) return false
        var r = call("autoTouch", kind, id, param, value, "move")
        if (r.ok && r.writing) { autoRev++; return true }
        return false
    }
    function autoRelease(kind, id, param, value) {
        if (!playing || !engineOk) return
        var r = call("autoTouch", kind, id, param, value, "end")
        if (r.ok && r.writing) autoRev++
    }
    function trackRelease(uid) {
        var i = sq.indexOf(uid); if (i < 0) return
        var t = tracks[i]; if (t.id < 0) return
        autoRelease("track", t.id, "volume", MD.faderToDb(t.vol === undefined ? 70 : t.vol))
        autoRelease("track", t.id, "pan", ((t.pan === undefined ? 50 : t.pan) - 50) / 50)
    }
    property int autoRev: 0                    // sube con cada punto escrito: el Arreglo redibuja sus curvas
    function seqSrc(type) { return sq.src[type] }
    // Pico [L, R] de una pista (el motor da un valor o un par)
    function trackLR(id) { var v = trackDb[String(id)]; return v === undefined ? [-100, -100] : v.length === 2 ? v : [v, v] }
    function toggleTrackFlag(uid, k) {
        var i = sq.indexOf(uid); if (i < 0) return
        var t = tracks.slice(), c = {}; c[k] = !t[i][k]; t[i] = Object.assign({}, t[i], c); tracks = t; syncTrackStates()
    }
    function trackLevel(id) { var v = trackDb[String(id)]; return v === undefined ? -100 : v }
    function setMaster(v) { masterPos = v; if (engineOk) call("setMasterVolume", v) }
    function applyTempo(v) { v = Math.round(v * 100) / 100; bpm = v; bpmInput.text = String(v); if (engineOk) call("setTempo", v) }
    function setMasterProcessing(drive, tone, lim) {
        masterDrive = drive; masterTone = tone; limiter = lim
        if (engineOk) call("setMasterProcessing", drive, tone, lim)
    }
    function exportMix() {
        toast("Renderizando mezcla…")
        var r = call("exportMix")
        toast(r.ok ? "Exportado: " + r.path : (r.cancelled ? "Exportación cancelada" : r.error))
    }
    function syncTrackStates() {
        if (!engineOk) return
        var list = tracks.filter(function (t) { return t.id >= 0 }).map(function (t) { return [t.id, t.mute || sq.disconnected(t), t.solo] })
        if (list.length) call("setTrackStates", JSON.stringify(list))
    }
    function importAudio() {
        var r = call("importAudio")
        if (r.ok) {
            r.tracks.forEach(addTrack)
            var conv = (r.converting || []).length
            toast(r.tracks.length + " archivo(s) en el motor" + (conv ? " · convirtiendo " + conv + " a 32 bits" : ""))
        } else if (!r.cancelled) toast(r.error)
    }
    function importPaths(paths) { mx.importToTracks(paths) }   // audio → ficha + pista + tira
    function timeText() {
        var beats = Math.max(0, posSec) * bpm / 60
        return (Math.floor(beats / 4) + 1) + "." + (Math.floor(beats % 4) + 1)
    }
    Connections {
        target: afo
        function onAiEvent(s) {
            try { var ev = JSON.parse(s); if (ev.type === "aiTempoKey") win.onTempoKey(ev); else if (ev.type === "aiSongAnalysis") win.onSongAnalysis(ev); else if (ev.type === "scriptDone") win.onScriptDone(ev); else if (!lb.onAiEvent(ev)) sq.onAiEvent(ev) } catch (e) { console.warn(e) }
        }
        function onPluginScanEvent(s) { try { win.onScanEvent(JSON.parse(s)) } catch (e) { console.warn(e) } }
        function onStateChanged(s) {
            var st; try { st = JSON.parse(s) } catch (e) { return }
            win.playing = st.playing
            win.posSec = st.position
            if (st.playing || st.position > 0) win.step = Math.floor(st.position * win.bpm / 15) % 256
            win.masterDb = st.master
            win.trackDb = st.tracks
            if (st.loud) win.trackLoud = st.loud
            if (st.mloud) win.masterLoud = st.mloud
            win.vu = MD.dbToPct(st.vu)            // RMS con balística VU calculado en el motor
            win.rec = st.rec
            win.previewing = !!st.preview
            if (sq.recording && !(st.rec && st.rec.recording)) {    // el motor dejó de grabar (dispositivo perdido)
                sq.stopTake(false)
                toast("La grabación se detuvo: el dispositivo de audio dejó de grabar")
            }
        }
        function onMixerEvent(s) {
            var ev; try { ev = JSON.parse(s) } catch (e) { return }
            if (ev.type !== "import") { mx.onEvent(ev); return }
            if (ev.phase === "convert") { mx.status = ev.desc + (ev.left ? " (quedan " + ev.left + ")" : ""); mx.progress = Math.min(95, mx.progress + 5) }
            else if (ev.phase === "track") { addTrack(ev.track); mx.status = ev.track.name + ": " + (ev.track.note || "importado"); mx.progress = 0 }
            else if (ev.phase === "error") { toast(ev.error); mx.status = ev.error; mx.progress = 0 }
        }
    }

    // ---------------- configuración de audio ----------------
    function openAudioSettings() {
        if (!engineOk) { toast("Motor nativo no disponible"); return }
        audioSettings.show()
    }
    // Tras cambiar de driver se vuelve a armar la pista de voz; algunos (ASIO4ALL) se reinician al
    // arrancar, así que se reintenta unas veces antes de darse por vencido
    function audioDeviceChanged() { rearm.tries = 0; rearm.restart(); refreshDevice() }
    Timer {
        id: rearm
        interval: 300
        property int tries: 0
        onTriggered: {
            sq.refreshInputs(); sq.arm()
            if (!sq.armedUid && sq.active("voz") && sq.inputs.length && ++tries < 5) restart()
        }
    }
    AudioSettings { id: audioSettings; studio: win }

    // ---------------- aviso (#toast) ----------------
    function toast(t) { toastText.text = t; toastBox.opacity = 1; toastTimer.restart() }
    Timer { id: toastTimer; interval: 2400; onTriggered: toastBox.opacity = 0 }

    // ---------------- barra de menús (F1): Archivo · Editar · Pista · Clip · Mezcla · Ver ----------------
    Rectangle {
        id: menuBar
        objectName: "menuBar"
        z: 6
        width: parent.width; height: 28
        color: Theme.s0
        Component.onCompleted: win.loadActions()
        Rectangle { y: parent.height - 1; width: parent.width; height: 1; color: Theme.line }
        Row {
            x: 6; height: parent.height
            Repeater {
                model: win.actionMenus
                Rectangle {
                    id: mb
                    required property string modelData
                    readonly property bool open: barMenu.visible && barMenu.menu === modelData
                    width: mt.implicitWidth + 20; height: menuBar.height - 1
                    color: open || mma.containsMouse ? Theme.s3 : "transparent"
                    Text { id: mt; anchors.centerIn: parent; text: mb.modelData; color: Theme.ink
                           font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                    MouseArea {
                        id: mma; anchors.fill: parent; hoverEnabled: true
                        onClicked: { barMenu.menu = mb.modelData; barMenu.items = win.actionsOf(mb.modelData); barMenu.openAt(mb, 0, mb.height) }
                        onContainsMouseChanged: if (containsMouse && barMenu.visible && barMenu.menu !== mb.modelData) {
                            barMenu.menu = mb.modelData; barMenu.items = win.actionsOf(mb.modelData); barMenu.openAt(mb, 0, mb.height) }
                    }
                }
            }
        }
        // F12: proyecto y tema en la barra de menús, así la cabecera cabe en una fila desde 1280 px
        Row {
            anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Text {                                  // dónde vive el proyecto: Artista · Lanzamiento · Canción
                objectName: "projectTitle"
                width: Math.min(implicitWidth, Math.max(80, win.width - 900)); elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
                text: pj.title + (win.dirty ? " •" : "")
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                HoverHandler { id: ptH }
                ToolTipLite { text: (pj.file || pj.songTarget || "Sin guardar") + (win.dirty ? " · cambios sin guardar" : ""); show: ptH.hovered }
            }
            Row {                                   // selector de tema (carpetas de templates/)
                spacing: 3
                anchors.verticalCenter: parent.verticalCenter
                Select {
                    width: 140; fontSize: 12; padY: 2
                    anchors.verticalCenter: parent.verticalCenter
                    options: win.themes.map(function (t) { return [t.name, t.name] })
                    current: Theme.name
                    tip: "Tema · " + (win.themes.filter(function (t) { return t.name === Theme.name })[0] || { description: "" }).description
                    onPicked: function (v) { win.setTheme(v) }
                }
                NeoButton { text: "↻"; tip: "Volver a leer la carpeta de temas (templates)"; padX: 6; padY: 1; fontSize: 12; shadow: 0
                            anchors.verticalCenter: parent.verticalCenter
                            onClicked: { win.loadThemes(); win.toast(win.themes.length + " temas en templates") } }
                NeoButton { text: "📁"; tip: "Abrir la carpeta de temas: copia aquí la carpeta de un tema para usarlo"; padX: 6; padY: 1; fontSize: 12; shadow: 0
                            anchors.verticalCenter: parent.verticalCenter
                            onClicked: win.call("themeFolder") }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Ctrl+K: buscar"; color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: palette.open() }
                HoverHandler { id: ckH }
                ToolTipLite { text: "Buscar una orden: escribe lo que quieres hacer y pulsa Intro (Ctrl+K)"; show: ckH.hovered }
            }
        }
    }
    ActionMenu { id: barMenu; objectName: "barMenu"; studio: win; property string menu: "" }
    ActionMenu { id: ctxMenu; objectName: "ctxMenu"; studio: win }
    CommandPalette { id: palette; objectName: "palette"; studio: win }
    TempoKeyBox { id: tkBox; objectName: "tempoKeyBox"; studio: win }
    AiClipBox { id: aiBox; objectName: "aiClipBox"; studio: win }
    // F5: Pista nueva (Audio, Instrumento, Batería, Voz, Intérprete IA, Generar con IA, Por piezas)
    NewTrackBox { id: newBox; objectName: "newTrackBox"; studio: win }
    // F6: Mezcla automática, orden del Mezclador (barra del Mezclador y menú Mezcla)
    MixAutoBox { id: mixBox; objectName: "mixAutoBox"; studio: win; mixer: mx }
    function newTrack(page) { newBox.openFor(page || "") }
    // Clic derecho en el Arreglo: el clip (o la pista) ya está elegido; sale su menú donde está el ratón
    function openContext(ctx, item, x, y) { ctxMenu.ctx = ctx; ctxMenu.items = actionsCtx(ctx); ctxMenu.openAt(item, x, y) }

    // ---------------- cabecera ----------------
    Rectangle {
        id: header
        y: menuBar.height
        z: 5
        width: parent.width
        height: Math.round(leftGroup.y + leftGroup.height + 10 + 3)
        color: Theme.header
        Rectangle { y: parent.height - Math.max(1, Theme.border); width: parent.width; height: Math.max(1, Theme.border); color: Theme.line }

        Flow {
            id: leftGroup
            x: 14; y: 10
            width: parent.width - 28
            spacing: 16
            Row {                                   // .transport
                spacing: 6
                NeoButton {
                    text: "Arreglo"; tip: "Vista Arreglo: pistas con sus clips y curvas de automatización (F5; Tab cambia de vista)"
                    pressedState: win.view === "arrange"
                    color: win.view === "arrange" ? Theme.pressedBg : Theme.button; textColor: win.view === "arrange" ? Theme.pressedInk : Theme.ink
                    onClicked: { if (win.dualWindow) flowWin.raise(); else win.view = "arrange" }
                }
                NeoButton {
                    text: "Mezclador"; tip: "Vista Mezclador: la consola con una tira por pista y el master (F6; Tab cambia de vista)"
                    pressedState: win.view === "mixer"
                    color: win.view === "mixer" ? Theme.pressedBg : Theme.button; textColor: win.view === "mixer" ? Theme.pressedInk : Theme.ink
                    onClicked: win.view = "mixer"
                }
                NeoButton {
                    text: "⧉"; tip: win.dualWindow ? "Cerrar la ventana del Arreglo (F7)"
                                                   : "Doble flujo: el Arreglo en una ventana aparte (otro monitor) y el Mezclador aquí (F7)"
                    pressedState: win.dualWindow
                    color: win.dualWindow ? Theme.pressedBg : Theme.button; textColor: win.dualWindow ? Theme.pressedInk : Theme.ink
                    onClicked: win.dualWindow = !win.dualWindow
                }
                NeoButton {
                    text: "■"; tip: "Detener y volver al principio (Mayús+Espacio)"
                    onClicked: { if (win.engineOk) win.call("stop"); win.step = -1 }
                }
                NeoButton {
                    text: win.playing ? "❚❚ Pausa" : "▶ Reproducir"
                    tip: "Reproducir o pausar (Espacio)"
                    color: Theme.accent; textColor: Theme.inkOnAccent
                    width: Math.max(100, implicitWidth)
                    onClicked: {
                        if (!win.engineOk) { win.toast("Motor nativo no disponible"); return }
                        var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error)
                    }
                }
                Rectangle {                         // .time
                    width: timeLbl.implicitWidth + 26; height: 35
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.lcdBg; border.width: Theme.border; border.color: Theme.line
                    Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line }
                    Text { id: timeGlow; anchors.centerIn: parent; text: timeLbl.text; color: Theme.lcd; opacity: 0.45
                           font: timeLbl.font; scale: 1.06 }
                    Text { id: timeLbl; anchors.centerIn: parent; text: win.timeText(); color: Theme.lcd
                           font.family: Theme.font; font.pixelSize: 18; font.weight: 700; font.letterSpacing: 1.44 }
                }
                Row {
                    spacing: 6
                    anchors.verticalCenter: parent.verticalCenter
                    Text { text: "Tempo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
                           anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        width: 64; height: 32
                        color: Theme.input; border.width: Theme.buttonBorder; border.color: Theme.line
                        TextInput {
                            id: bpmInput
                            x: 6; width: parent.width - 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: "96"
                            color: Theme.ink; selectByMouse: true
                            font.family: Theme.font; font.pixelSize: 14; font.weight: 500
                            validator: DoubleValidator { bottom: 1; top: 220; decimals: 2; notation: DoubleValidator.StandardNotation }
                            onTextEdited: {
                                var v = parseFloat(text)
                                if (v >= 40 && v <= 220) { win.bpm = v; if (win.engineOk) win.call("setTempo", v) }
                            }
                        }
                    }
                    Text { text: "Tono"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
                           anchors.verticalCenter: parent.verticalCenter }
                    Select {
                        objectName: "songKey"
                        width: 118; anchors.verticalCenter: parent.verticalCenter
                        options: win.keyOptions
                        current: win.songKey.key ? win.songKey.key + "|" + win.songKey.scale : ""
                        tip: "Tonalidad del proyecto: la usan el Afinador, la IA y «Audio a la tonalidad del proyecto» (clic derecho en un clip)"
                        onPicked: function (v) { var p = v.split("|"); win.setSongKey(p[0], p[1] || "") }
                    }
                }
            }
            Row {                                   // .zoom
                spacing: 6
                NeoButton {
                    text: "⚙ Audio"
                    tip: "Driver (Windows Audio, DirectSound, ASIO4ALL…), dispositivo, frecuencia y búfer (Ctrl+,)"
                    onClicked: win.openAudioSettings()
                }
            }
        }

    }

    // ---------------- zonas fijas (DISENO_DAW §2) ----------------
    // Fuente que conecta / desconecta cada página (ocultar ≠ silenciar ≠ desconectar)
    function sourceOf(page) { return ({ inst: "inst", piano: "inst", drums: "drums", ia: "ia", cinta: "cinta" })[page] || "" }
    Component {
        id: srcToggle
        NeoButton {
            readonly property var zone: parent && parent.parent ? parent.parent.parent : null
            readonly property string key: zone ? win.sourceOf(zone.current) : ""
            readonly property bool off: !!key && !!win.hidden[key]
            visible: key.length > 0
            text: off ? "○ Apagada" : "● Activa"; fontSize: 12; padY: 2; padX: 8
            pressedState: off
            color: off ? Theme.pressedBg : Theme.button; textColor: off ? Theme.pressedInk : Theme.ink
            tip: off ? "Sus pistas no suenan ni graban. Pulsa para volver a conectarlas"
                     : "Desconecta esta fuente: sus pistas dejan de sonar y de grabar (no se borra nada)"
            onClicked: win.setHidden(key, !off)
        }
    }

    // Navegador (izquierda): lo que se añade al proyecto
    Zone {
        id: navZ
        z: 4
        title: "Navegador"; vertical: true; sections: true
        anchors { top: header.bottom; bottom: detZ.top; right: parent.right }
        width: folded ? 34 : win.navW
        foldTip: folded ? "Mostrar el navegador (Ctrl+B)" : "Plegar el navegador (Ctrl+B)"
        tabs: [["add", "Añadir", "Instrumentos, batería, voz, audio y plugins VST3: cada uno crea su pista"],
               ["fxlist", "Efectos", "Efectos nativos por categoría y VST3: doble clic añade a la pista elegida"],
               ["audios", "Archivos", "Audios del proyecto: tipo y rol para la Mezcla IA"],
               ["recent", "Inicio", "Proyectos recientes y la biblioteca (F4)"]]
        current: "add"
        extra: srcToggle
        help: ({
            add: ["Añadir", "Cada fila crea su pista: instrumento (sintetizador del motor o VST3), batería, voz, audio o un plugin. Con «+» añades otra pista de ese tipo."],
            fxlist: ["Efectos", "Efectos nativos por categoría y tus VST3. Clic: ves qué hace. Doble clic o «Añadir a…»: lo pone al final de la cadena de la pista elegida (o del master)."],
            audios: ["Archivos", "Cada audio crea su <b>pista</b> y su <b>tira en la consola</b>. Tipo y rol se deducen del nombre (_L, _R, _B…) y se corrigen aquí, en el Arreglo o en el Mezclador.<br><br>Quitar un audio de esta lista no borra nada de tu disco; si borras su pista, el audio sigue aquí y puedes volver a crearla."],
            recent: ["Inicio", "Proyectos recientes y la biblioteca: artista → álbum o single → canción. Doble clic para abrir; F4 abre Inicio en grande."]
        })
        onFoldedChanged: if (!win.loading) win.saveLayout()
        onPicked: if (!win.loading) win.saveLayout()
        SideMenu {
            id: sideMenu
            studio: win
            x: 0; y: navZ.pageY; width: parent.width; height: navZ.pageH
            showTabs: false
            tab: 1
            visible: navZ.current === "add" && !navZ.folded
        }
        ZonePage { zid: "fxlist"; tint: "fx"; minWidth: 246; Browser { id: fxBrowser; studio: win } }
        ZonePage { zid: "recent"; tint: "pistas"; minWidth: 246; Browser { studio: win; mode: "home" } }
        ZonePage { zid: "audios"; tint: "audios"; minWidth: 246; AudiosBody { mixer: mx; studio: win } }
    }

    // Inspector: pista elegida, master (medidores, proceso y versiones) y grabación. Sin Asistente IA (F6):
    // la mezcla automática es una orden del Mezclador y Master IA un dispositivo del master.
    Zone {
        id: inspZ
        z: 4
        title: "Inspector"; vertical: true; sections: true
        anchors { top: header.bottom; bottom: detZ.top; left: parent.left }
        width: folded ? 34 : win.inspW
        foldTip: folded ? "Mostrar el inspector (Ctrl+I)" : "Plegar el inspector (Ctrl+I)"
        tabs: [["pista", "Pista", "Volumen, paneo, envíos y efectos de la pista elegida"],
               ["master", "Master", "Sonoridad, saturación, tono, limitador y versiones del master"],
               ["cinta", "Grabar", "Grabador de voz: entrada, monitor y tomas de la pista de voz"]]
        current: "pista"
        extra: srcToggle
        help: ({
            pista: ["Pista", "Volumen, paneo, Solo y Mute, rol de voz para la Mezcla IA, envíos a los buses Aux y efectos de la pista elegida en el Arreglo o en el Mezclador."],
            master: ["Master", "VU y sonoridad del master, saturación, tono y limitador. <b>Master IA</b> es un dispositivo del master (Efectos › Master) y su A/B está en la tira MASTER.<br>Versiones del master (Rebobinado). Clic en una versión: se carga en el master y suena al reproducir, para compararlas. Doble clic en el nombre: renombrarla. Se guardan con el proyecto."],
            cinta: ["Grabar", "Grabador de voz: elige la entrada, escucha el monitor y graba tomas en la pista de voz."]
        })
        onFoldedChanged: if (!win.loading) win.saveLayout()
        onPicked: if (!win.loading) win.saveLayout()
        ZonePage { id: pistaPage; zid: "pista"; tint: "mezcla"; minWidth: 306; Inspector { objectName: "inspector"; studio: win; mixer: mx; shown: pistaPage.shown } }
        ZonePage {
            zid: "master"; tint: "master"; minWidth: 306
            Column {
                width: parent ? parent.width : 400; spacing: 12
                MasteringBody { mixer: mx; studio: win }
                Rectangle { width: parent.width; height: 1; color: Theme.line }
                MasterBody { studio: win; mixer: mx }
            }
        }
        ZonePage { zid: "cinta"; tint: "cinta"; minWidth: 306; CintaBody { seq: sq; studio: win } }
    }

    // Vista principal: Arreglo ⇄ Mezclador (Tab)
    Item {
        id: mainArea
        z: 3
        anchors { top: header.bottom; left: inspZ.right; right: navZ.left; bottom: detZ.top }
        clip: true
        ArrangeView {
            id: arrange
            studio: win
            anchors.fill: parent
            visible: win.view === "arrange"
        }
        Item {
            id: mixPage
            anchors.fill: parent
            visible: win.view === "mixer"
            Rectangle { anchors.fill: parent; color: Theme.veil(Theme.panelColor("mezcla", Theme.pc.mezcla)) }
            Flickable {
                id: mixFlick
                x: 12; y: 10; width: parent.width - 24; height: parent.height - 20
                contentWidth: mixBody.width; contentHeight: mixBody.height
                clip: true; boundsBehavior: Flickable.StopAtBounds
                MixBody { id: mixBody; width: Math.max(mixFlick.width, 700); fitHeight: mixFlick.height; mixer: mx; studio: win }
            }
        }
        DropArea {                                  // arrastrar audios desde el Explorador
            anchors.fill: parent
            z: 11
            onEntered: function (d) { d.accepted = d.hasUrls }
            onDropped: function (d) {
                var paths = []
                for (var i = 0; i < d.urls.length; i++) {
                    var u = d.urls[i].toString()
                    if (u.indexOf("file:///") === 0) paths.push(decodeURIComponent(u.slice(8)))
                }
                if (paths.length) {
                    if (win.engineOk) win.importPaths(paths); else win.toast("Motor nativo no disponible")
                }
            }
        }
    }

    // Panel de detalle (abajo): el editor de lo seleccionado
    Zone {
        id: detZ
        z: 4
        title: "Detalle"
        anchors { left: parent.left; right: parent.right; bottom: statusBar.top }
        height: folded ? headH : win.detailFitH
        foldTip: folded ? "Mostrar el panel de detalle (Ctrl+E)" : "Plegar el panel de detalle (Ctrl+E)"
        tabs: win.detModes
        caption: "EDITOR · " + (win.detKind === "master" ? "Master" : win.detTrack ? win.detTrack.name : "sin selección")
        current: "fx"
        extra: srcToggle
        help: ({
            piano: ["Piano roll", "Las notas MIDI de la pista de instrumento elegida; suenan con su instrumento (sintetizador del motor o VST3)."],
            inst: ["Instrumento", "El instrumento se carga una sola vez y cada pista guarda solo su preset. Velocidad, Brillo y Reverb son del sintetizador interno; un VST3 se ajusta en su propio editor."],
            drums: ["Batería", "Pads y patrón de 16 pasos de la pista de batería: cada paso encendido suena en ese tiempo del compás."],
            fx: ["Efectos", "La cadena de efectos de la pista elegida o del master, en el orden de la señal. Arrastra una tarjeta para cambiar el orden; A/B compara dos ajustes; el «?» de cada efecto explica qué hace. Los efectos se añaden desde Navegador › Efectos."],
            tono: ["Tono", "<b>Editor de tono (AF-64)</b>: las notas de la toma, una a una. Muévelas en semitonos o cents, enderézalas (quita vibrato y deriva) o llévalas a la escala; «Aplicar» escribe una copia que la pista usa con los mismos clips (Ctrl+Z vuelve). El tiempo no cambia. Clic derecho en un clip › Editar tono lo abre aquí."],
            afina: ["Afinador", "Afinador AF-60: corrige la afinación de la voz mientras suena y al exportar. Es un efecto de la cadena (también se ajusta en Efectos). Debajo, cómo afina la Mezcla IA."]
        })
        onFoldedChanged: if (!win.loading) win.saveLayout()
        onPicked: if (!win.loading) win.saveLayout()
        Rectangle {                                 // asa para cambiar el alto (solo lo cambia el usuario)
            parent: detZ
            z: 6
            visible: !detZ.folded
            width: parent.width; height: 6; color: dh.hovered || dm.pressed ? Theme.accent : "transparent"
            HoverHandler { id: dh; cursorShape: Qt.SizeVerCursor }
            MouseArea {
                id: dm
                anchors.fill: parent
                cursorShape: Qt.SizeVerCursor
                property real y0
                property real h0
                onPressed: function (m) { y0 = mapToItem(null, m.x, m.y).y; h0 = win.detailFitH }
                onPositionChanged: function (m) {
                    if (!pressed) return
                    win.detailH = lu.clamp(h0 - (mapToItem(null, m.x, m.y).y - y0), 200, Math.max(200, win.height - 320))
                }
                onReleased: win.saveLayout()
            }
            ToolTipLite { text: "Arrastra para cambiar el alto del panel de detalle"; show: dh.hovered && !dm.pressed }
        }
        ZonePage { zid: "piano"; tint: "piano"; minWidth: 760; PianoBody { seq: sq } }
        ZonePage { zid: "inst"; tint: "inst"; minWidth: 420; InstBody { seq: sq } }
        ZonePage { zid: "drums"; tint: "drums"; minWidth: 760; DrumsBody { seq: sq; curStep: win.playing && win.step >= 0 ? win.step % 16 : -1 } }
        ZonePage {                                  // un solo editor de efectos: cada pista y el master
            id: fxPage; zid: "fx"; tint: "fx"; minWidth: 860
            Column {
                width: parent ? parent.width : 860
                spacing: 10
                FxBody { id: fxMain; studio: win; shown: fxPage.visible }
                AutoMasterBox { objectName: "masterIa"; mixer: mx; visible: fxMain.target === 0 }   // F6: Master IA
                Text { text: "Antes / Después"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                ReviewBody { mixer: mx; studio: win; shown: fxPage.visible }
            }
        }
        ZonePage { zid: "tono"; tint: "afina"; minWidth: 620; PitchEditor { id: pitchEd; mixer: mx } }
        ZonePage { zid: "afina"; tint: "afina"; minWidth: 620; TuneBody { id: tuneBody; mixer: mx } }
    }

    // ---------------- ventana aparte: Arreglo (doble flujo) ----------------
    Window {
        id: flowWin
        title: "AllForOne · Arreglo (línea de tiempo)"
        width: 1400; height: 820
        minimumWidth: 640; minimumHeight: 420
        color: Theme.canvas
        onClosing: win.dualWindow = false
        Rectangle {
            id: flowBar
            width: parent.width; height: 46; color: Theme.header; z: 2
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.border; color: Theme.line }
            Row {
                x: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Text { anchors.verticalCenter: parent.verticalCenter; rightPadding: 8
                       text: "Arreglo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                NeoButton {
                    text: win.playing ? "❚❚ Pausa" : "▶ Reproducir"; tip: "Reproducir o pausar (Espacio)"
                    color: Theme.accent; textColor: Theme.inkOnAccent
                    onClicked: { var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error) }
                }
                NeoButton { text: "■"; tip: "Detener y volver al principio (Mayús+Espacio)"; onClicked: { if (win.engineOk) win.call("stop"); win.step = -1 } }
                NeoButton { text: "Volver a una ventana"; tip: "Cierra esta ventana; el Arreglo sigue en la principal (F7)"
                            onClicked: { win.dualWindow = false; win.view = "arrange" } }
                Text { anchors.verticalCenter: parent.verticalCenter; leftPadding: 10
                       text: "Mismo proyecto que la ventana principal · ahí queda el Mezclador"
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
            }
        }
        Loader {                                    // solo existe con la ventana abierta
            id: flowArrange
            anchors { top: flowBar.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
            active: win.dualWindow
            sourceComponent: ArrangeView { studio: win }
        }
        Shortcut { sequence: "F7"; onActivated: win.dualWindow = false }
        Shortcut { sequence: "Space"; enabled: win.engineOk; onActivated: { var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error) } }
    }

    // Inicio (F4): la biblioteca encima de las zonas; sale al arrancar sin proyecto abierto
    // F10: el fondo va detrás de las zonas (z 3–8), encima del color de la ventana. En el Inicio (que tapa
    // las zonas) se recorta a su hueco y sube justo debajo de él; la imagen no se mueve de sitio.
    Item {
        id: backdropFrame
        readonly property bool home: win.view === "home"
        z: home ? 7.5 : 1
        x: home ? homeView.x : 0; y: home ? homeView.y : 0
        width: home ? homeView.width : win.width; height: home ? homeView.height : win.height
        clip: true
    Backdrop {
        id: backdropView
        objectName: "backdrop"
        x: -backdropFrame.x; y: -backdropFrame.y
        width: win.width; height: win.height
        mode: win.backdrop.mode; layers: win.backdrop.layers
        intensity: win.backdrop.intensity; atten: win.backdrop.atten; reduce: win.backdrop.reduce
        active: win.active
        progress: arrange.scrollProgress
    }
    }
    BackdropBox { id: backdropBox; objectName: "backdropBox"; studio: win }
    HomeView {
        id: homeView
        studio: win
        z: 8
        anchors { top: header.bottom; left: parent.left; right: parent.right; bottom: statusBar.top }
        visible: win.view === "home"
    }

    // ---------------- ayuda y aviso ----------------
    StatusBar {                                     // estado siempre visible: audio, proyecto, ayuda, zoom
        id: statusBar
        studio: win
        z: 5
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
    }
    Rectangle {                                     // #toast
        id: toastBox
        z: 6
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        x: (win.width - width) / 2; y: statusBar.y - 24 - height
        width: Math.min(toastText.implicitWidth + 28, win.width * 0.9)
        height: toastText.height + 16
        color: Theme.tipBg; border.width: 1; border.color: Theme.accent
        Text {
            id: toastText
            x: 14; y: 8; width: Math.min(implicitWidth, win.width * 0.9 - 28)
            wrapMode: Text.Wrap
            color: Theme.tipInk; font.family: Theme.font; font.pixelSize: 14; font.weight: 600
        }
    }

    Component.onCompleted: {
        var fo = savedLayout.fold || {}, tb = savedLayout.tab || {}
        navZ.folded = !!fo.nav; inspZ.folded = !!fo.insp; detZ.folded = !!fo.detail
        if (tb.nav && pageZone[tb.nav] === "nav") navZ.current = tb.nav
        if (tb.insp && pageZone[tb.insp] === "insp") inspZ.current = tb.insp
        if (tb.detail && pageZone[tb.detail] === "detail") detZ.current = tb.detail
        loadThemes()                              // tema guardado (los diseños antiguos guardaban "dark"/"light")
        // De fábrica: Oscuro (familia Oscuro / Grafito / Claro, docs/FLUJO_PROFESIONAL.md §6). Un diseño
        // guardado con un tema anterior a la familia (AllForOne, AllForOne Oscuro, Professional, Sobrio)
        // pasa una vez al de la familia con la misma luz; después se respeta lo que elija el usuario.
        var tn = savedLayout.theme
        var old = ({ "AllForOne": "Claro", "light": "Claro", "AllForOne Oscuro": "Oscuro", "dark": "Oscuro",
                     "Professional": "Grafito", "Sobrio": "Oscuro" })
        if (!tn || ((savedLayout.look2 || 0) < 3 && old[tn])) tn = old[tn] || "Oscuro"
        if (!setTheme(tn, true)) setTheme("Oscuro", true)
        var sb = savedLayout.backdrop                 // F10: el fondo guardado, si sus capas siguen ahí
        if (sb && sb.mode && sb.mode !== "none") {
            var ck = call("backdropCheck", JSON.stringify(sb.layers || []))
            if (ck.ok && !ck.missing.length) backdrop = Object.assign({}, backdropFactory, sb)
            else Qt.callLater(function () { toast("El fondo guardado ya no está en datos/fondos: sin fondo") })
        }

        var info = call("hello")
        engineOk = !!info.engine
        if (engineOk) {
            call("setMasterVolume", 70)                 // 70 = 0 dB
            call("setMasterProcessing", masterDrive, masterTone, limiter)
            call("setTempo", bpm)
            var dev = info.device || {}
            toast(dev.open ? "Motor nativo listo · " + dev.type + " · " + dev.output : "Motor nativo listo · sin dispositivo de salida abierto")
        } else toast("Motor nativo no disponible: " + (info.error || "desconocido"))
        if (engineOk) loadPluginList()            // plugins VST3 de la última búsqueda
        refreshDevice()
        mx.connect()
        sq.createDefaults()
        firstFit.start()
    }
    Timer { id: firstFit; interval: 60; onTriggered: win.loading = false }
    // Tab cambia Arreglo ⇄ Mezclador (no mientras se escribe en un campo de texto)
    readonly property bool typing: !!activeFocusItem && activeFocusItem.cursorPosition !== undefined
    Shortcut { sequence: "Tab"; enabled: !win.typing && !win.dualWindow && win.view !== "home"; onActivated: win.view = win.view === "mixer" ? "arrange" : "mixer" }
    Shortcut { sequence: "Ctrl+B"; onActivated: navZ.folded = !navZ.folded }
    Shortcut { sequence: "Ctrl+I"; onActivated: inspZ.folded = !inspZ.folded }
    Shortcut { sequence: "Ctrl+E"; onActivated: detZ.folded = !detZ.folded }
    Shortcut {                                      // Espacio: reproducir / pausa, como en cualquier DAW
        sequence: "Space"; enabled: win.engineOk
        onActivated: { var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error) }
    }
}
