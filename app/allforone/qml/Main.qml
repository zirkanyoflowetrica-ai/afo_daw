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
    property int bpm: 96
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
    property var fxMasterBody: null
    function refreshRacks() { if (fxBody) fxBody.reload(); if (fxMasterBody) fxMasterBody.reload() }
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
        return { tuneEditor: fxBody.tuneShown, ab: fxBody.cur && fxBody.ab[fxBody.cur.id] ? fxBody.ab[fxBody.cur.id].side : "",
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
    Shortcut { sequence: "F8"; onActivated: win.view = "lab" }
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
        if (t.id > 0) rackTrack = t.id
        if (t.type === "inst") sq.oct = (t.cfg && t.cfg.oct) || 4      // la Octava es de cada pista
        var ed = ({ inst: "piano", drum: "drums", audio: "pistas", ia: "pistas", voz: "pistas" })[t.type]
        if (ed && ["piano", "drums", "pistas", "inst"].indexOf(detZ.current) >= 0) detZ.current = ed
    }
    readonly property real bar16: 16 * 4 * 60 / Math.max(40, bpm)
    property real stripScroll: 0               // desplazamiento horizontal de las tiras de la consola
    function setDark(b) { setTheme(b ? "AllForOne Oscuro" : "AllForOne") }
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
                 masterChain: fxMasterBody ? fxMasterBody.chain.map(function (e) { return e.label || e.key }) : [],
                 masterLoud: masterLoud,
                 tracks: tracks.map(function (t) { return { uid: t.uid, id: t.id, type: t.type, name: t.name, vol: t.vol, pan: t.pan,
                                                             len: t.len || 0, peaks: (t.peaks || []).length,
                                                             notes: Object.keys(t.roll || {}).length + Object.keys(t.pat || {}).length,
                                                             midi: (t.midi || []).length, sub: sq.sub(t) } }),
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
    function zoneRects() {
        var out = {}, z = { cabecera: header, navegador: navZ, principal: mainArea, inspector: inspZ, detalle: detZ, estado: statusBar }
        for (var k in z) { var it = z[k], p = it.mapToItem(null, 0, 0); out[k] = { x: Math.round(p.x), y: Math.round(p.y), w: Math.round(it.width), h: Math.round(it.height), visible: it.visible } }
        return out
    }
    function layoutCommand(what, a, b) {
        if (what === "zones") return zoneRects()
        if (what === "browser") { if (a) fxBrowser.add(a)
                                  return { sections: fxBrowser.sections.map(function (s) { return [s[0], s[1].map(function (d) { return d.key })] }),
                                           target: fxBrowser.targetName } }
        if (what === "pages") return navZ.tabs.concat(inspZ.tabs, detZ.tabs).map(function (t) { return t[0] })
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
        if (what === "select") { sq.pick(a); return { detail: detZ.current, rack: rackTrack } }
        if (what === "contrast") {                // pares texto/fondo del tema actual (guía de diseño §8)
            var c = function (x) { return String(x) }, out2 = [
                ["texto/fondo", c(Theme.ink), c(Theme.bg)], ["texto/cabecera", c(Theme.ink), c(Theme.header)],
                ["texto/campo", c(Theme.ink), c(Theme.input)], ["texto/botón", c(Theme.ink), c(Theme.button)],
                ["texto/menú", c(Theme.ink), c(Theme.sidebar)], ["botón pulsado", c(Theme.pressedInk), c(Theme.pressedBg)],
                ["botón principal", "#000000", c(Theme.accent)], ["chip del modelo", c(Theme.chipInk), c(Theme.chip)],
                ["dispositivo", c(Theme.deviceInk), c(Theme.device)], ["cabecera de dispositivo", c(Theme.deviceInk), c(Theme.deviceHead)],
                ["pantalla", c(Theme.screenInk), c(Theme.screen)], ["tarjeta de pantalla", c(Theme.screenInk), c(Theme.screenCard)],
                ["texto secundario de pantalla", c(Theme.screenDim), c(Theme.screenCard)],
                ["pantalla con el ratón", c(Theme.screenInk), c(Theme.screenHover)]]
            for (var mid in Theme.pc) {
                out2.push(["título " + mid, c(Theme.headInk(Theme.pc[mid])), c(Theme.panelHead)])
                if (mid !== "piano") out2.push(["cuerpo " + mid, c(Theme.ink), c(Theme.panelColor(mid, Theme.pc[mid]))])
            }
            return out2
        }
        if (what === "view") { if (a) view = a
                               return { view: view, lanes: arrange.laneCount, inserts: arrange.insertCount, rows: arrange.rows.length,
                                        visible: arrange.visible, modules: mixPage.visible,
                                        auxes: arrange.auxes.length, sends: arrange.sendCount, sendsH: arrange.sendsH } }
        // Bus Aux desde la consola (autoprueba): a = [nombre del bus, id de la pista que envía, dB]
        if (what === "aux") { var at = arrange.addAux()
                              if (!at || at.id < 0) return { ok: false }
                              arrange.setSend(a[1], at.id, a[2], false)
                              return { ok: true, id: at.id, sends: arrange.sendCount, uid: at.uid } }
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

    // ---------------- diseño guardado ----------------
    function saveLayout() {
        layoutStore.save(JSON.stringify({ v: layoutVersion, theme: Theme.name, view: view === "home" ? "arrange" : view, look2: 2, detailH: detailH,
                                          fold: { nav: navZ.folded, insp: inspZ.folded, detail: detZ.folded },
                                          tab: { nav: navZ.current, insp: inspZ.current, detail: detZ.current } }))
    }
    // Versión de la distribución: un diseño guardado de otra versión no se aplica; solo
    // se conserva el tema
    readonly property int layoutVersion: 7
    property var savedLayout: {
        var d
        try { d = JSON.parse(layoutStore.load()) } catch (e) { return {} }
        return d.v === layoutVersion ? d : { theme: d.theme, look2: d.look2 }
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
    readonly property var pageZone: ({ ia: "nav", audios: "nav", add: "nav", fxlist: "nav", recent: "nav",
                                       pista: "insp", asist: "insp", master: "insp", cinta: "insp",
                                       pistas: "detail", inst: "detail", piano: "detail", drums: "detail",
                                       fx: "detail", fxm: "detail", afina: "detail" })
    function zoneOf(id) { return ({ nav: navZ, insp: inspZ, detail: detZ })[pageZone[id]] || null }
    function titleOf(id) {
        return ({ ia: "IA", audios: "Archivos", add: "Añadir", fxlist: "Efectos", recent: "Inicio", pista: "Pista", asist: "Asistente IA",
                  master: "Versiones", cinta: "Grabar", pistas: "Clips", inst: "Instrumento", piano: "Piano roll",
                  drums: "Batería", fx: "Efectos", fxm: "Efectos master", afina: "Afinador", mezcla: "Mezclador" })[id] || id
    }
    function goTo(id) {
        if (id === "mastia" || id === "antes") id = "asist"     // Master IA y A/B están en el Asistente IA (X17)
        currentId = id
        if (id === "mezcla") { if (!dualWindow) view = "mixer"; return }
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
    function applyTempo(v) { bpm = v; bpmInput.text = String(v); if (engineOk) call("setTempo", v) }
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
            try { var ev = JSON.parse(s); if (!lb.onAiEvent(ev)) sq.onAiEvent(ev) } catch (e) { console.warn(e) }
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

    // ---------------- cabecera ----------------
    Rectangle {
        id: header
        z: 5
        width: parent.width
        height: Math.round(leftGroup.y + leftGroup.height + 10 + 3)
        color: Theme.header
        Rectangle { y: parent.height - Math.max(1, Theme.border); width: parent.width; height: Math.max(1, Theme.border); color: Theme.line }

        Row {
            id: leftGroup
            x: 14; y: 10
            spacing: 16
            Row {                                   // .transport
                spacing: 6
                NeoButton {
                    text: "Inicio"; tip: "Inicio: tus artistas, álbumes y canciones, y los proyectos recientes (F4)"
                    pressedState: win.view === "home"
                    color: win.view === "home" ? Theme.pressedBg : Theme.button; textColor: win.view === "home" ? Theme.pressedInk : Theme.ink
                    onClicked: win.view = "home"
                }
                NeoButton {
                    text: "☰"; tip: "Mostrar u ocultar el navegador: añadir instrumentos y efectos, IA y archivos (Ctrl+B)"
                    readonly property bool on: !navZ.folded
                    pressedState: on
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink
                    onClicked: navZ.folded = !navZ.folded
                }
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
                    text: "Crear IA"; tip: "Vista Crear IA: el laboratorio de instrumentales por piezas, con variantes y preescucha (F8)"
                    pressedState: win.view === "lab"
                    color: win.view === "lab" ? Theme.pressedBg : Theme.button; textColor: win.view === "lab" ? Theme.pressedInk : Theme.ink
                    onClicked: win.view = "lab"
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
                    color: Theme.accent; textColor: "#000"
                    width: Math.max(100, implicitWidth)
                    onClicked: {
                        if (!win.engineOk) { win.toast("Motor nativo no disponible"); return }
                        var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error)
                    }
                }
                NeoButton {
                    text: "Abrir"; tip: "Abrir un proyecto .afo (Ctrl+O)"
                    onClicked: pj.open("")
                }
                NeoButton {
                    text: "Guardar"; tip: "Guardar el proyecto con pistas, efectos y automatización (Ctrl+S; Ctrl+Mayús+S: guardar como)"
                    onClicked: pj.save(false)
                }
                Rectangle {                         // .time
                    width: timeLbl.implicitWidth + 26; height: 35
                    anchors.verticalCenter: parent.verticalCenter
                    color: "#120f0a"; border.width: Theme.border; border.color: Theme.line
                    Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: "#3a3020" }
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
                            validator: IntValidator { bottom: 1; top: 220 }
                            onTextEdited: {
                                var v = parseInt(text)
                                if (v >= 40 && v <= 220) { win.bpm = v; if (win.engineOk) win.call("setTempo", v) }
                            }
                        }
                    }
                }
            }
            Row {                                   // .zoom
                spacing: 6
                Text {                              // dónde vive el proyecto: Artista · Lanzamiento · Canción
                    width: Math.min(implicitWidth, 300); elide: Text.ElideRight
                    anchors.verticalCenter: parent.verticalCenter
                    text: pj.title + (win.dirty ? " •" : "")
                    color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                    HoverHandler { id: ptH }
                    ToolTipLite { text: (pj.file || pj.songTarget || "Sin guardar") + (win.dirty ? " · cambios sin guardar" : ""); show: ptH.hovered }
                }
                NeoButton { text: "Restaurar zonas"; tip: "Abre todas las zonas con su tamaño y sus pestañas de fábrica (Ctrl+Mayús+R)"; onClicked: win.resetLayout() }
                Row {                               // selector de tema (carpetas de templates/)
                    spacing: 4
                    Text { text: "Tema"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
                           font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                    Select {
                        width: 170; fontSize: 13; padY: 4
                        anchors.verticalCenter: parent.verticalCenter
                        options: win.themes.map(function (t) { return [t.name, t.name] })
                        current: Theme.name
                        tip: (win.themes.filter(function (t) { return t.name === Theme.name })[0] || { description: "" }).description
                        onPicked: function (v) { win.setTheme(v) }
                    }
                    NeoButton { text: "↻"; tip: "Volver a leer la carpeta de temas (templates)"; padX: 6
                                onClicked: { win.loadThemes(); win.toast(win.themes.length + " temas en templates") } }
                    NeoButton { text: "📁"; tip: "Abrir la carpeta de temas: copia aquí la carpeta de un tema para usarlo"; padX: 6
                                onClicked: win.call("themeFolder") }
                }
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
        title: "Navegador"; vertical: true
        anchors { top: header.bottom; bottom: detZ.top; left: parent.left }
        width: folded ? 34 : 390
        foldTip: folded ? "Mostrar el navegador (Ctrl+B)" : "Plegar el navegador (Ctrl+B)"
        tabs: [["add", "Añadir", "Instrumentos, batería, voz, audio y plugins VST3: cada uno crea su pista"],
               ["fxlist", "Efectos", "Efectos nativos por categoría y VST3: doble clic añade a la pista elegida"],
               ["ia", "IA", "Canción, MIDI y partes con IA, en tu equipo"],
               ["audios", "Archivos", "Audios del proyecto: tipo y rol para la Mezcla IA"],
               ["recent", "Inicio", "Proyectos recientes y la biblioteca (F4)"]]
        current: "add"
        extra: srcToggle
        onFoldedChanged: if (!win.loading) win.saveLayout()
        onPicked: if (!win.loading) win.saveLayout()
        SideMenu {
            id: sideMenu
            studio: win
            anchors.fill: parent
            showTabs: false
            tab: 1
            visible: navZ.current === "add" && !navZ.folded
        }
        ZonePage { zid: "fxlist"; tint: "fx"; minWidth: 300; Browser { id: fxBrowser; studio: win } }
        ZonePage { zid: "recent"; tint: "pistas"; minWidth: 300; Browser { studio: win; mode: "home" } }
        ZonePage { zid: "ia"; tint: "ia"; minWidth: 300; IaBody { seq: sq } }
        ZonePage { zid: "audios"; tint: "audios"; minWidth: 300; AudiosBody { mixer: mx; studio: win } }
    }

    // Inspector (derecha): asistente de mezcla y master, versiones y grabación
    Zone {
        id: inspZ
        z: 4
        title: "Inspector"; vertical: true
        anchors { top: header.bottom; bottom: detZ.top; right: parent.right }
        width: folded ? 34 : 460
        foldTip: folded ? "Mostrar el inspector (Ctrl+I)" : "Plegar el inspector (Ctrl+I)"
        tabs: [["pista", "Pista", "Volumen, paneo, envíos y efectos de la pista elegida"],
               ["asist", "Asistente IA", "Mezcla IA, Master IA y Antes / Después en un sitio"],
               ["master", "Versiones", "Versiones del master guardadas (Rebobinado)"],
               ["cinta", "Grabar", "Grabador de voz: entrada, monitor y tomas de la pista de voz"]]
        current: "pista"
        extra: srcToggle
        onFoldedChanged: if (!win.loading) win.saveLayout()
        onPicked: if (!win.loading) win.saveLayout()
        ZonePage { id: pistaPage; zid: "pista"; tint: "mezcla"; minWidth: 360; Inspector { objectName: "inspector"; studio: win; mixer: mx; shown: pistaPage.shown } }
        ZonePage {
            id: abPage; zid: "asist"; tint: "mastia"; minWidth: 380
            Column {
                width: parent ? parent.width : 400; spacing: 14
                MixAiBody { mixer: mx; studio: win }
                Rectangle { width: parent.width; height: 3; color: Theme.ink }
                MasteringBody { mixer: mx; studio: win }
                Rectangle { width: parent.width; height: 3; color: Theme.ink }
                Text { text: "ANTES / DESPUÉS"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.52 }
                ReviewBody { mixer: mx; studio: win; shown: abPage.shown }
            }
        }
        ZonePage { zid: "master"; tint: "master"; minWidth: 380; MasterBody { studio: win; mixer: mx } }
        ZonePage { zid: "cinta"; tint: "cinta"; minWidth: 360; CintaBody { seq: sq; studio: win } }
    }

    // Vista principal: Arreglo ⇄ Mezclador (Tab)
    Item {
        id: mainArea
        z: 3
        anchors { top: header.bottom; left: navZ.right; right: inspZ.left; bottom: detZ.top }
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
            Rectangle { anchors.fill: parent; color: Theme.panelColor("mezcla", Theme.pc.mezcla) }
            Flickable {
                id: mixFlick
                x: 12; y: 10; width: parent.width - 24; height: parent.height - 20
                contentWidth: mixBody.width; contentHeight: mixBody.height
                clip: true; boundsBehavior: Flickable.StopAtBounds
                MixBody { id: mixBody; width: Math.max(mixFlick.width, 700); mixer: mx; studio: win }
            }
        }
        LabView { id: labView; objectName: "labView"; studio: win; anchors.fill: parent; visible: win.view === "lab" }
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
        height: folded ? headH : win.detailH
        foldTip: folded ? "Mostrar el panel de detalle (Ctrl+E)" : "Plegar el panel de detalle (Ctrl+E)"
        tabs: [["pistas", "Clips", "Clips de las pistas de audio: dividir (S), mover, fundidos, normalizar, rehacer con IA"],
               ["piano", "Piano roll", "Notas de la pista de instrumento elegida"],
               ["inst", "Instrumento", "Sonido de la pista de instrumento: sintetizador del motor o VST3"],
               ["drums", "Batería", "Pads y patrón de 16 pasos de la pista de batería"],
               ["fx", "Efectos", "Cadena de efectos de la pista elegida y su editor"],
               ["afina", "Afinador", "Afinador AF-60 y afinación de las voces"],
               ["fxm", "Efectos master", "Cadena del master y masterizado automático"]]
        current: "fx"
        extra: srcToggle
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
                onPressed: function (m) { y0 = mapToItem(null, m.x, m.y).y; h0 = win.detailH }
                onPositionChanged: function (m) {
                    if (!pressed) return
                    win.detailH = lu.clamp(h0 - (mapToItem(null, m.x, m.y).y - y0), 200, Math.max(200, win.height - 320))
                }
                onReleased: win.saveLayout()
            }
            ToolTipLite { text: "Arrastra para cambiar el alto del panel de detalle"; show: dh.hovered && !dm.pressed }
        }
        ZonePage {
            zid: "pistas"; tint: "pistas"; minWidth: 900
            TracksBody {
                tracks: win.tracks
                mixer: mx
                seq: sq
                host: null
                studio: win
                posSec: win.posSec
                bpm: win.bpm
                onAddType: function (type) { sq.addTrack(type) }
                selected: win.selected
                bar16: win.bar16
                headPos: win.step < 0 ? 0 : (win.step % 256) / 256
                onAddAudio: { if (win.engineOk) win.importAudio(); else win.toast("Motor nativo no disponible") }
                onAddTone: {
                    var r = win.call("addTestTone")
                    if (r.ok) { win.addTrack(r.track, false); win.toast("Tono de prueba 440 Hz (sintético) añadido") } else win.toast(r.error)
                }
                onNotYet: function (what) { win.toast("«" + what + "» todavía no está en la interfaz nativa") }
                onSelectTrack: function (i) { sq.pick(i) }
                onToggleMute: function (i) { var t = win.tracks.slice(); t[i] = Object.assign({}, t[i], { mute: !t[i].mute }); win.tracks = t; win.syncTrackStates() }
                onToggleSolo: function (i) { var t = win.tracks.slice(); t[i] = Object.assign({}, t[i], { solo: !t[i].solo }); win.tracks = t; win.syncTrackStates() }
                onRemoveTrack: function (i) { win.removeTrackAt(i) }
                onSplitTrack: function (i) { sq.splitStems(win.tracks[i].id) }
            }
        }
        ZonePage { zid: "piano"; tint: "piano"; minWidth: 760; PianoBody { seq: sq } }
        ZonePage { zid: "inst"; tint: "inst"; minWidth: 420; InstBody { seq: sq } }
        ZonePage { zid: "drums"; tint: "drums"; minWidth: 760; DrumsBody { seq: sq; curStep: win.playing && win.step >= 0 ? win.step % 16 : -1 } }
        ZonePage { id: fxPage; zid: "fx"; tint: "fx"; minWidth: 860; FxBody { studio: win; shown: fxPage.visible } }
        ZonePage { zid: "afina"; tint: "afina"; minWidth: 620; TuneBody { mixer: mx } }
        ZonePage {
            id: fxmPage; zid: "fxm"; tint: "fxm"; minWidth: 860
            Column {
                width: parent ? parent.width : 860
                FxBody { studio: win; shown: fxmPage.visible; master: true }
                AutoMasterBox { mixer: mx }
            }
        }
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
                    color: Theme.accent; textColor: "#000"
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
        color: "#000"
        Rectangle { x: 4; y: 4; z: -1; width: parent.width; height: parent.height; color: "#ffc233" }
        Text {
            id: toastText
            x: 14; y: 8; width: Math.min(implicitWidth, win.width * 0.9 - 28)
            wrapMode: Text.Wrap
            color: "#fff"; font.family: Theme.font; font.pixelSize: 14; font.weight: 600
        }
    }

    Component.onCompleted: {
        var fo = savedLayout.fold || {}, tb = savedLayout.tab || {}
        navZ.folded = !!fo.nav; inspZ.folded = !!fo.insp; detZ.folded = !!fo.detail
        if (tb.nav && pageZone[tb.nav] === "nav") navZ.current = tb.nav
        if (tb.insp && pageZone[tb.insp] === "insp") inspZ.current = tb.insp
        if (tb.detail && pageZone[tb.detail] === "detail") detZ.current = tb.detail
        loadThemes()                              // tema guardado (los diseños antiguos guardaban "dark"/"light")
        // De fábrica: Sobrio (carbón, un acento discreto, colores apagados; X12, 24-11-2026: «quita los
        // colores llamativos»). Un diseño guardado antes con un tema de fábrica pasa una vez a Sobrio;
        // después se respeta lo que elija el usuario en «Tema».
        var tn = savedLayout.theme === "dark" ? "AllForOne Oscuro" : savedLayout.theme === "light" ? "AllForOne" : savedLayout.theme
        if (!tn || ((savedLayout.look2 || 0) < 2 && ["AllForOne", "AllForOne Oscuro", "Professional"].indexOf(tn) >= 0)) tn = "Sobrio"
        if (!setTheme(tn, true)) setTheme("Sobrio", true)

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
