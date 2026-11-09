import QtQuick
import "../theme"
import "../controls"
import "../state/fxlibrary.js" as FL
import "../state/fxgraph.js" as FG

// Rack de efectos (Rack FX-96 del canal y Rack FX-M del master): la Biblioteca nativa AFO dentro del
// motor. Cada efecto es un plugin de Tracktion escrito en C++ (native/src/fx): procesa en el hilo de
// audio, se guarda en la sesión, es automatizable e informa su latencia. Como en un DAW, la cadena es
// una fila de dispositivos en orden de señal (activar, mover, quitar, «+» para agregar sin límite),
// cada uno con su pantalla (calculada con las fórmulas del motor) y sus perillas. Debajo, el detalle
// del efecto elegido: medidores del motor, presets propios y automatización.
// El rack del canal sigue a la tira elegida en Mezcla; el del master siempre muestra el master.
Column {
    id: root
    property var studio
    property bool shown: true                   // el módulo está en el lienzo (si no, no se consulta el motor)
    property bool master: false                 // Rack FX-M: siempre la pista 0
    property string extraId: ""                 // rack extra («+» del menú): elige su canal por su cuenta
    property bool libOpen: false                // biblioteca abierta con «+ Agregar efecto»
    property int menuFor: -1                    // efecto con el menú ⋮ abierto
    property var presetCache: ({})              // key → [{name, factory}]
    property var cardLive: ({})                 // id → medidores (delay: tiempo real; analizador: espectro)
    property var catalog: []
    property int target: 0                      // pista del motor (0 = master)
    property var chain: []
    property int sel: -1                        // id del efecto abierto en el editor
    property int family: 1                      // «Efectos de audio»
    property var meters: []
    property var spectrum: []
    property var presets: []                    // [{name, factory}] del efecto abierto
    property string presetName: ""
    property string autoParam: ""               // parámetro de la línea de automatización
    property var autoPts: []                    // [[segundos, valor], …] de ese parámetro
    width: parent ? parent.width : 700
    spacing: 0

    readonly property var built: {
        var m = {}
        for (var i = 0; i < catalog.length; i++) m[catalog[i].af] = catalog[i]
        return m
    }
    // sin tira elegida, el rack del canal muestra la primera pista (el master tiene su propio rack)
    readonly property int follow: master ? 0 : extraId ? -1 : studio.rackTrack > 0 ? studio.rackTrack : targets.length > 1 ? Number(targets[1][0]) : -1
    onFollowChanged: if (follow >= 0 && follow !== target) pickTarget(follow)
    readonly property string targetName: (targets.filter(function (o) { return o[0] === String(target) })[0] || ["", "Master"])[1]
    readonly property var targets: {
        var out = [["0", "Master"]]
        var t = studio.tracks
        for (var i = 0; i < t.length; i++) if (t[i].id >= 0) out.push([String(t[i].id), t[i].name])
        return out
    }
    onTargetsChanged: if (!master && targets.map(function (o) { return o[0] }).indexOf(String(target)) < 0) pickTarget(0)
    readonly property var cur: { for (var i = 0; i < chain.length; i++) if (chain[i].id === sel) return chain[i]; return null }
    readonly property var type: cur ? typeOf(cur.key) : null
    readonly property string curKey: cur ? cur.key : ""
    readonly property int curId: cur ? cur.id : -1
    onCurKeyChanged: loadPresets()
    onCurIdChanged: { presetName = ""; autoParam = type && type.params.length ? pickAutoParam() : ""; loadAuto() }
    onAutoParamChanged: loadAuto()
    readonly property var autoDesc: { if (!type) return null; for (var i = 0; i < type.params.length; i++) if (type.params[i].id === autoParam) return type.params[i]; return null }
    readonly property real span: studio.bar16                   // la línea abarca los 16 compases del lienzo

    function typeOf(key) { for (var i = 0; i < catalog.length; i++) if (catalog[i].key === key) return catalog[i]; return null }
    function setChain(c) {
        chain = c || []
        if (!cur) sel = chain.length ? chain[chain.length - 1].id : -1
        var c = Object.assign({}, presetCache), fresh = false
        for (var i = 0; i < chain.length; i++) if (c[chain[i].key] === undefined && chain[i].key !== "vst3") {
            var r = studio.call("fxPresets", chain[i].key); c[chain[i].key] = r.ok ? r.presets : []; fresh = true
        }
        if (fresh) presetCache = c
        studio.fxCountChanged()
    }
    function nameOf(e) { return e.label || (typeOf(e.key) || { name: e.key }).name.replace("AFO ", "") }
    function reload() {
        if (!studio.engineOk) return
        var r = studio.call("fxList", target)
        if (r.ok) setChain(r.chain)
    }
    function pickTarget(id, byUser) {
        target = id; sel = -1; menuFor = -1; reload()
        if (extraId) { if (byUser) studio.setExtraTarget(extraId, id); return }
        if (byUser && !master && id > 0 && studio.rackTrack !== id) studio.rackTrack = id   // la consola marca esa tira
    }
    function add(key) {
        var r = studio.call("fxAdd", target, key, -1)
        if (!r.ok) { studio.toast(r.error); return }
        sel = r.effect.id
        setChain(r.chain)
        libOpen = false
    }
    // Plugin VST3 externo al final de la cadena
    function addPlugin(pluginId) {
        var r = studio.call("fxAddPlugin", target, pluginId, -1)
        if (!r.ok) { studio.toast(r.error); return }
        sel = r.effect.id
        setChain(r.chain)
        studio.toast(r.effect.name + " (VST3) en " + targetName + " · ábrelo con «Abrir plugin»")
    }
    function remove(id) { var r = studio.call("fxRemove", id, target); if (r.ok) setChain(r.chain) }
    function move(id, idx) { var r = studio.call("fxMove", id, idx, target); if (r.ok) setChain(r.chain) }
    function enable(id, b) {
        var r = studio.call("fxEnable", id, b)
        if (r.ok) setChain(chain.map(function (e) { return e.id === id ? Object.assign({}, e, { enabled: b }) : e }))
    }
    function patch(e) { chain = chain.map(function (x) { return x.id === e.id ? Object.assign({}, x, e) : x }) }
    function isAuto(pid) { return !!cur && (cur.automated || []).indexOf(pid) >= 0 }
    function pickAutoParam() {                  // el primero ya automatizado, o la salida/mezcla, o el primero
        var a = cur.automated || []
        if (a.length) return a[0]
        for (var i = 0; i < type.params.length; i++) if (type.params[i].id === "output" || type.params[i].id === "mix") return type.params[i].id
        return type.params[0].id
    }

    // ---------------- presets ----------------
    function loadPresets() {
        if (!curKey) { presets = []; return }
        var r = studio.call("fxPresets", curKey)
        presets = r.ok ? r.presets : []
    }
    function applyPreset(name) {
        var r = studio.call("fxApplyPreset", cur.id, name)
        if (!r.ok) { studio.toast(r.error); return }
        patch(r.effect); presetName = name
    }
    function savePreset(name) {
        var r = studio.call("fxSavePreset", cur.id, name)
        if (!r.ok) { studio.toast(r.error); return }
        presets = r.presets; presetName = name.trim()
        var c = Object.assign({}, presetCache); c[curKey] = r.presets; presetCache = c
        studio.toast("Preset «" + presetName + "» guardado")
    }
    function deletePreset() {
        var r = studio.call("fxDeletePreset", curKey, presetName)
        if (!r.ok) { studio.toast(r.error); return }
        presets = r.presets; presetName = ""
        var c = Object.assign({}, presetCache); c[curKey] = r.presets; presetCache = c
    }

    // ---------------- automatización ----------------
    function loadAuto() {
        if (!cur || !autoParam || !studio.engineOk) { autoPts = []; return }
        var r = studio.call("fxAutomation", cur.id, autoParam)
        autoPts = r.ok ? r.points : []
    }
    function setAuto(pts) {
        pts = pts.slice().sort(function (a, b) { return a[0] - b[0] })
        var r = studio.call("fxSetAutomation", cur.id, autoParam, JSON.stringify(pts))
        if (!r.ok) { studio.toast(r.error); return }
        autoPts = pts
        patch(r.effect)
    }
    function setParam(i, v) { setParamOf(cur, i, v) }
    function setParamOf(e, i, v) {
        var p = typeOf(e.key).params[i]
        studio.call("fxParam", e.id, p.id, v)
        var vals = e.values.slice(); vals[i] = v
        var id = e.id
        chain = chain.map(function (x) { return x.id === id ? Object.assign({}, x, { values: vals }) : x })
    }
    function applyPresetTo(e, name) {
        var r = studio.call("fxApplyPreset", e.id, name)
        if (!r.ok) { studio.toast(r.error); return }
        patch(r.effect)
        if (e.id === sel) presetName = name
    }

    // Rango con centro (como juce::NormalisableRange::setSkewForCentre): 0..100 ↔ valor del parámetro
    function skew(p) { return p.centre > p.min && p.centre < p.max ? Math.log(0.5) / Math.log((p.centre - p.min) / (p.max - p.min)) : 1 }
    function toPos(p, v) { return 100 * Math.pow(Math.max(0, Math.min(1, (v - p.min) / (p.max - p.min))), skew(p)) }
    function fromPos(p, pos) { return p.min + (p.max - p.min) * Math.pow(pos / 100, 1 / skew(p)) }
    function fmtVal(p, v) {
        if (p.choices.length) return p.choices[Math.round(v)] || ""
        var a = Math.abs(v), s = a >= 1000 ? (v / 1000).toFixed(a >= 10000 ? 1 : 2) + " k" : a >= 100 ? v.toFixed(0) + " " : a >= 10 ? v.toFixed(1) + " " : v.toFixed(2) + " "
        return (s + p.unit).trim()
    }
    function db(v) { return v <= -99 ? "−∞" : v.toFixed(1) }

    Timer {                                     // medidores del efecto abierto (~12 por segundo)
        interval: 80; repeat: true
        running: root.shown && root.studio.engineOk && !!root.cur
        onTriggered: {
            var r = root.studio.call("fxMeters", root.cur.id)
            if (r.ok) root.meters = r.m
            if (root.cur.key === "analyzer") { var s = root.studio.call("fxSpectrum", root.cur.id, 96); if (s.ok) root.spectrum = s.bands }
            var live = {}
            for (var i = 0; i < root.chain.length; i++) {
                var e = root.chain[i]
                if (e.key === "analyzer" && root.studio.playing) { var sp = root.studio.call("fxSpectrum", e.id, 48); if (sp.ok) live[e.id] = sp.bands }
                else if (e.key === "delay") live[e.id] = e.id === root.cur.id ? root.meters : (root.studio.call("fxMeters", e.id).m || [])
            }
            root.cardLive = live
            if (root.studio.playing && (root.cur.automated || []).length) {   // las perillas siguen la curva
                var f = root.studio.call("fxInfo", root.cur.id)
                if (f.ok) root.patch({ id: f.effect.id, values: f.effect.values })
            }
        }
    }

    // ---------------- cabecera: «VOZ P / CADENA DE EFECTOS» · «RACK VOZ P» ----------------
    Row {
        width: root.width; spacing: 10; bottomPadding: 10
        Column {
            width: root.width - (pickBox.visible ? pickBox.width + 10 : 0)
            Text { width: parent.width; elide: Text.ElideRight
                   text: root.targetName.toUpperCase() + " / CADENA DE EFECTOS"
                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 17; font.weight: 700; font.letterSpacing: 0.6 }
            Text { width: parent.width; elide: Text.ElideRight
                   text: "RACK " + root.targetName.toUpperCase() + " · " + root.chain.length + (root.chain.length === 1 ? " efecto" : " efectos")
                         + " · " + (root.master ? "después de la mezcla, antes del limitador" : "antes del fader")
                   color: Theme.ink; opacity: 0.75; font.family: Theme.font; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 0.4 }
        }
        Column {
            id: pickBox
            visible: !root.master
            width: 190; spacing: 2
            Text { text: "Canal (o elige una tira en Mezcla)"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
            Select { width: parent.width; fontSize: 12; padY: 4; options: root.targets; current: String(root.target)
                     onPicked: function (v) { root.pickTarget(Number(v), true) } }
        }
    }

    // ---------------- cadena de dispositivos (como un DAW: en fila, en orden de señal) ----------------
    Rectangle {
        id: chainBox
        width: root.width; height: 300
        color: Theme.chain; radius: Theme.radius
        border.width: 1; border.color: Theme.line
        Flickable {
            id: chainFlick
            x: 6; y: 6; width: parent.width - 12; height: parent.height - 12
            contentWidth: devRow.width; contentHeight: height
            clip: true; boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.HorizontalFlick
            interactive: contentWidth > width
            Row {
                id: devRow
                height: chainFlick.height; spacing: 6
                Repeater {
                    model: root.chain
                    Rectangle {
                        id: card
                        required property var modelData
                        required property int index
                        readonly property var desc: root.typeOf(modelData.key)
                        readonly property bool picked: modelData.id === root.sel
                        readonly property var knobs: desc ? desc.params.filter(function (p) { return !p.choices.length }) : []
                        readonly property var picks: desc ? desc.params.filter(function (p) { return p.choices.length > 0 }) : []
                        readonly property int cols: Math.max(2, Math.ceil(knobs.length / 2))
                        width: modelData.key === "vst3" ? 200 : Math.max(200, cols * 64 + 16)
                        height: devRow.height
                        color: Theme.device; radius: Theme.radius
                        border.width: picked ? 2 : 1; border.color: picked ? Theme.knobArc : Theme.deviceBorder
                        MouseArea { anchors.fill: parent; onClicked: root.sel = card.modelData.id }
                        Rectangle {                      // cabecera: activar · nombre · ◀ ▶ ≡ ✕
                            id: devHead
                            x: 1; y: 1; width: parent.width - 2; height: 24
                            color: Theme.deviceHead; radius: Theme.radius
                            Rectangle {
                                x: 7; anchors.verticalCenter: parent.verticalCenter
                                width: 12; height: 12; radius: 6
                                color: card.modelData.enabled ? Theme.knobArc : Theme.knobTrack
                                border.width: 1; border.color: Theme.deviceBorder
                                MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor
                                            onClicked: root.enable(card.modelData.id, !card.modelData.enabled) }
                                ToolTipLite { text: card.modelData.enabled ? "Activo: clic para puentear" : "Puenteado: clic para activar"; show: false }
                            }
                            Text {
                                x: 26; width: parent.width - 26 - devBtns.width - 8; anchors.verticalCenter: parent.verticalCenter
                                elide: Text.ElideRight
                                text: root.nameOf(card.modelData) + ((card.modelData.automated || []).length ? " ∿" : "")
                                color: Theme.deviceInk; opacity: card.modelData.enabled ? 1 : 0.55
                                font.family: Theme.font; font.pixelSize: 12; font.weight: 700
                            }
                            Row {
                                id: devBtns
                                anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                                spacing: 1
                                DevBtn { glyph: "◀"; tip: "Mover antes"; visible: card.index > 0; onClicked: root.move(card.modelData.id, card.index - 1) }
                                DevBtn { glyph: "▶"; tip: "Mover después"; visible: card.index < root.chain.length - 1; onClicked: root.move(card.modelData.id, card.index + 1) }
                                DevBtn { glyph: "≡"; tip: "Detalle: medidores, presets propios y automatización"; onClicked: root.sel = card.modelData.id }
                                DevBtn { glyph: "✕"; tip: "Quitar de la cadena"; onClicked: root.remove(card.modelData.id) }
                            }
                        }
                        Column {
                            x: 8; y: devHead.height + 6; width: parent.width - 16; spacing: 6
                            opacity: card.modelData.enabled ? 1 : 0.55
                            Column {                     // plugin VST3: su propia ventana
                                visible: card.modelData.key === "vst3"
                                width: parent.width; spacing: 8
                                NeoButton { text: "Abrir plugin"; width: parent.width; fontSize: 12; padY: 6
                                            tip: "Abre la ventana del plugin (sus controles y presets)"
                                            onClicked: { var r = root.studio.call("fxPluginEditor", card.modelData.id); if (!r.ok) root.studio.toast(r.error) } }
                                Text { width: parent.width; wrapMode: Text.Wrap; text: "VST3 externo. Su estado se guarda con el proyecto."
                                       color: Theme.deviceInk; opacity: 0.75; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                            }
                            Select {
                                visible: card.modelData.key !== "vst3"
                                width: parent.width; fontSize: 10; padX: 4; padY: 2
                                fill: Theme.deviceHead; ink: Theme.deviceInk
                                options: [["", (card.desc || { af: "" }).af + " · preset…"]].concat((root.presetCache[card.modelData.key] || []).map(function (p) { return [p.name, p.name + (p.factory ? "" : " ★")] }))
                                current: ""
                                tip: "Presets de fábrica y los tuyos (★)"
                                onPicked: function (v) { if (v) root.applyPresetTo(card.modelData, v) }
                            }
                            Canvas {                     // pantalla del dispositivo: lo que hará con estos valores
                                visible: !!card.desc
                                width: parent.width; height: visible ? 64 : 0
                                property var fx: card.modelData
                                property var live: root.cardLive[card.modelData.id]
                                onFxChanged: requestPaint()
                                onLiveChanged: requestPaint()
                                onWidthChanged: requestPaint()
                                onPaint: { if (card.desc) FG.draw(getContext("2d"), width, height, fx, card.desc, live) }
                            }
                            Grid {                       // perillas en dos filas
                                columns: card.cols; columnSpacing: 4; rowSpacing: 2
                                Repeater {
                                    model: card.knobs
                                    Column {
                                        id: kc
                                        required property var modelData
                                        readonly property int pi: card.desc.params.indexOf(modelData)
                                        readonly property real v: card.modelData.values[pi] !== undefined ? card.modelData.values[pi] : modelData.def
                                        readonly property bool auto: (card.modelData.automated || []).indexOf(modelData.id) >= 0
                                        width: 60; spacing: 0
                                        Knob {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            value: root.toPos(kc.modelData, kc.v)
                                            label: kc.modelData.name + (kc.auto ? " ∿" : "")
                                            labelColor: kc.auto ? Theme.knobArc : Theme.deviceInk
                                            tip: kc.modelData.help
                                            onMoved: function (pos) { root.setParamOf(card.modelData, kc.pi, root.fromPos(kc.modelData, pos)) }
                                        }
                                        Text { anchors.horizontalCenter: parent.horizontalCenter
                                               text: root.fmtVal(kc.modelData, kc.v); color: Theme.deviceInk; opacity: 0.8
                                               font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                    }
                                }
                            }
                            Flow {                       // parámetros de elegir (modo, tipo…)
                                width: parent.width; spacing: 6
                                Repeater {
                                    model: card.picks
                                    Column {
                                        id: pcol
                                        required property var modelData
                                        readonly property int pi: card.desc.params.indexOf(modelData)
                                        readonly property real v: card.modelData.values[pi] !== undefined ? card.modelData.values[pi] : modelData.def
                                        spacing: 1
                                        Text { text: pcol.modelData.name; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                                        Select {
                                            width: 96; fontSize: 10; padY: 2; padX: 4
                                            fill: Theme.deviceHead; ink: Theme.deviceInk
                                            options: pcol.modelData.choices.map(function (c, i) { return [String(i), c] })
                                            current: String(Math.round(pcol.v))
                                            tip: pcol.modelData.help
                                            onPicked: function (val) { root.setParamOf(card.modelData, pcol.pi, Number(val)) }
                                        }
                                    }
                                }
                            }
                        }
                        Text {
                            visible: !!card.modelData.auto
                            anchors.bottom: parent.bottom; anchors.bottomMargin: 4; x: 8
                            text: "puesto por la mezcla automática"; color: Theme.deviceInk; opacity: 0.6
                            font.family: Theme.font; font.pixelSize: 9; font.weight: 600
                        }
                    }
                }
                Rectangle {                              // hueco final: agregar efecto
                    width: 150; height: devRow.height
                    color: "transparent"; radius: Theme.radius
                    border.width: 1; border.color: Theme.deviceBorder
                    Column {
                        anchors.centerIn: parent; spacing: 6; width: parent.width - 20
                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.libOpen ? "×" : "+"
                               color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 30; font.weight: 300 }
                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                               text: root.libOpen ? "Cerrar biblioteca" : (root.chain.length ? "Agregar efecto" : "Sin efectos en " + root.targetName + ". Agrega uno" + (root.master ? " o pulsa MASTERIZAR abajo" : "") + ".")
                               color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.libOpen = !root.libOpen }
                }
            }
        }
        Rectangle {                                      // barra de desplazamiento horizontal
            visible: chainFlick.contentWidth > chainFlick.width + 1
            y: parent.height - 5; height: 3; radius: 1.5
            x: chainFlick.x + chainFlick.visibleArea.xPosition * chainFlick.width
            width: Math.max(24, chainFlick.visibleArea.widthRatio * chainFlick.width)
            color: Theme.ink; opacity: 0.35
        }
    }
    Item { width: 1; height: 10 }

    // ---------------- editor del efecto abierto ----------------
    Rectangle {
        visible: !!root.type
        width: root.width; height: visible ? ed.height + 20 : 0
        color: Theme.device; radius: Theme.radius; border.width: 1; border.color: Theme.deviceBorder
        Column {
            id: ed
            x: 10; y: 10; width: parent.width - 20
            spacing: 8
            Row {
                width: ed.width; spacing: 10
                Lcd { text: root.type ? root.type.af : ""; fontSize: 14 }
                Column {
                    width: ed.width - 260; anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; elide: Text.ElideRight; text: root.type ? root.type.name : ""
                           color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: root.type ? root.type.summary : ""
                           color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                }
                Column {                        // entrada / salida medidas en el motor
                    width: 160; spacing: 3; anchors.verticalCenter: parent.verticalCenter
                    Repeater {
                        model: [["Entrada", 0], ["Salida", 1]]
                        Row {
                            required property var modelData
                            spacing: 6
                            Text { width: 48; text: modelData[0]; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                            Rectangle {
                                width: 70; height: 9; color: "#120f0a"; border.width: 1; border.color: "#000"
                                anchors.verticalCenter: parent.verticalCenter
                                Rectangle { x: 1; y: 1; height: 7; color: (root.meters[modelData[1]] || -100) > -1 ? "#ff4d3d" : "#5ee0b0"
                                            width: 68 * Math.max(0, Math.min(1, ((root.meters[modelData[1]] === undefined ? -100 : root.meters[modelData[1]]) + 60) / 60)) }
                            }
                            Text { text: root.db(root.meters[modelData[1]] === undefined ? -100 : root.meters[modelData[1]]) + " dB"
                                   color: "#ffb000"; font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
                        }
                    }
                    Text {
                        readonly property var extra: root.type && root.type.meters.length && root.type.key !== "eq" ? root.type.meters : []
                        visible: extra.length > 0
                        text: extra.map(function (n, i) { var v = root.meters[2 + i]; return n + ": " + (v === undefined ? "—" : v.toFixed(1)) }).join(" · ")
                        color: "#ffb000"; font.family: Theme.font; font.pixelSize: 10; font.weight: 700
                    }
                    Text { text: "Latencia: " + (root.cur ? (root.cur.latency_seconds * 1000).toFixed(2) : "0") + " ms (compensada)"
                           color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                }
            }
            Row {                               // presets
                width: ed.width; spacing: 8
                Text { text: "Preset"; height: 28; verticalAlignment: Text.AlignVCenter; color: Theme.deviceInk
                       font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                Select {
                    width: Math.min(230, ed.width * 0.35); fontSize: 12; padY: 4
                    options: [["", "— elegir —"]].concat(root.presets.map(function (p) { return [p.name, p.name + (p.factory ? "" : " ★")] }))
                    current: root.presetName
                    tip: "Presets de fábrica y los tuyos (★). Los parámetros que no nombra vuelven a su valor por defecto."
                    onPicked: function (v) { if (v) root.applyPreset(v) }
                }
                Rectangle {
                    width: 150; height: 28; color: "#fff"; border.width: 2; border.color: "#000"
                    TextInput {
                        id: presetIn
                        x: 6; width: parent.width - 12; anchors.verticalCenter: parent.verticalCenter
                        color: "#000"; font.family: Theme.font; font.pixelSize: 12; selectByMouse: true; clip: true
                        onAccepted: if (text.trim()) { root.savePreset(text); text = "" }
                        Text { visible: !presetIn.text && !presetIn.activeFocus; text: "nombre del preset"; color: "#888"
                               font: presetIn.font; anchors.verticalCenter: parent.verticalCenter }
                    }
                }
                NeoButton { text: "Guardar"; fontSize: 12; padX: 8; padY: 2; shadow: 2; tip: "Guardar los valores actuales como preset tuyo"
                            onClicked: { if (presetIn.text.trim()) { root.savePreset(presetIn.text); presetIn.text = "" } else root.studio.toast("Escribe un nombre para el preset") } }
                NeoButton { text: "Borrar"; fontSize: 12; padX: 8; padY: 2; shadow: 2
                            visible: root.presets.some(function (p) { return p.name === root.presetName && !p.factory })
                            tip: "Borrar este preset tuyo"; onClicked: root.deletePreset() }
            }
            Column {                            // línea de automatización del parámetro elegido
                width: ed.width; spacing: 4
                Row {
                    spacing: 8
                    Text { text: "Automatización"; height: 26; verticalAlignment: Text.AlignVCenter; color: Theme.deviceInk
                           font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                    Select {
                        width: 170; fontSize: 11; padY: 3
                        options: root.type ? root.type.params.map(function (p) { return [p.id, p.name + (root.isAuto(p.id) ? " ∿" : "")] }) : []
                        current: root.autoParam
                        onPicked: function (v) { root.autoParam = v }
                    }
                    Text { height: 26; verticalAlignment: Text.AlignVCenter; color: Theme.deviceInk
                           text: root.autoPts.length ? root.autoPts.length + " puntos · sigue la curva al reproducir y al exportar"
                                                     : "Sin curva: clic en la línea para añadir un punto"
                           font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                    NeoButton { text: "Quitar curva"; fontSize: 11; padX: 6; padY: 1; shadow: 2; visible: root.autoPts.length > 0
                                tip: "El parámetro vuelve a su valor fijo"; onClicked: root.setAuto([]) }
                }
                Canvas {
                    id: lane
                    width: ed.width; height: 84
                    property int drag: -1
                    property var pts: root.autoPts
                    readonly property real playX: root.studio.step < 0 ? -1 : width * (root.studio.step % 256) / 256
                    onPtsChanged: requestPaint()
                    onPlayXChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    function xOf(t) { return width * t / root.span }
                    function yOf(v) { var d = root.autoDesc; return d ? height - 6 - (height - 12) * root.toPos(d, v) / 100 : height / 2 }
                    function tOf(x) { return Math.max(0, Math.min(root.span, x / width * root.span)) }
                    function vOf(y) { return root.fromPos(root.autoDesc, Math.max(0, Math.min(100, 100 * (height - 6 - y) / (height - 12)))) }
                    function hit(x, y) { for (var i = 0; i < pts.length; i++) if (Math.abs(xOf(pts[i][0]) - x) < 7 && Math.abs(yOf(pts[i][1]) - y) < 7) return i; return -1 }
                    onPaint: {
                        var ctx = getContext("2d"); ctx.reset()
                        ctx.fillStyle = "#0c0a07"; ctx.fillRect(0, 0, width, height)
                        ctx.strokeStyle = "rgba(255,255,255,0.10)"; ctx.lineWidth = 1
                        for (var b = 0; b <= 16; b++) { var gx = width * b / 16; ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, height); ctx.stroke() }
                        var p = pts || []
                        if (p.length) {
                            ctx.beginPath(); ctx.moveTo(0, yOf(p[0][1]))
                            for (var i = 0; i < p.length; i++) ctx.lineTo(xOf(p[i][0]), yOf(p[i][1]))
                            ctx.lineTo(width, yOf(p[p.length - 1][1]))
                            ctx.strokeStyle = "#ffcf9e"; ctx.lineWidth = 2; ctx.stroke()
                            ctx.fillStyle = "#ffb000"
                            for (var j = 0; j < p.length; j++) ctx.fillRect(xOf(p[j][0]) - 4, yOf(p[j][1]) - 4, 8, 8)
                        }
                        if (playX >= 0) { ctx.strokeStyle = "#ff4d3d"; ctx.beginPath(); ctx.moveTo(playX, 0); ctx.lineTo(playX, height); ctx.stroke() }
                        ctx.fillStyle = "#bdb398"; ctx.font = "10px sans-serif"
                        ctx.fillText("16 compases · clic: añadir · arrastrar: mover · clic derecho: borrar", 6, 12)
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: !!root.autoDesc
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        onPressed: function (m) {
                            var i = lane.hit(m.x, m.y), p = lane.pts.slice()
                            if (m.button === Qt.RightButton) { if (i >= 0) { p.splice(i, 1); root.setAuto(p) } return }
                            if (i < 0) {
                                p.push([lane.tOf(m.x), lane.vOf(m.y)]); p.sort(function (a, b) { return a[0] - b[0] })
                                root.autoPts = p; i = lane.hit(m.x, m.y)
                            }
                            lane.drag = i
                        }
                        onPositionChanged: function (m) {
                            if (lane.drag < 0) return
                            var p = root.autoPts.slice(); p[lane.drag] = [lane.tOf(m.x), lane.vOf(m.y)]; root.autoPts = p
                        }
                        onReleased: { if (lane.drag >= 0) { lane.drag = -1; root.setAuto(root.autoPts) } }
                    }
                }
            }
            Canvas {                            // curva real del EQ o espectro del Analizador
                id: plot
                readonly property bool eq: !!root.cur && (root.cur.key === "eq")
                readonly property bool an: !!root.cur && root.cur.key === "analyzer"
                visible: eq || an
                width: ed.width; height: visible ? 120 : 0
                property var data: eq ? root.meters.slice(2) : root.spectrum
                onDataChanged: requestPaint()
                onPaint: {
                    var ctx = getContext("2d"); ctx.reset()
                    ctx.fillStyle = "#0c0a07"; ctx.fillRect(0, 0, width, height)
                    ctx.strokeStyle = "rgba(255,255,255,0.10)"; ctx.lineWidth = 1
                    var lo = eq ? -24 : -90, hi = eq ? 24 : 0
                    ;[20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000].forEach(function (f) {
                        var x = width * Math.log(f / 20) / Math.log(1000); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
                    })
                    for (var g = lo; g <= hi; g += eq ? 6 : 15) {
                        var gy = height * (hi - g) / (hi - lo); ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(width, gy); ctx.stroke()
                    }
                    var d = data || []; if (d.length < 2) return
                    ctx.beginPath()
                    for (var i = 0; i < d.length; i++) {
                        var x2 = width * i / (d.length - 1), y2 = height * (hi - Math.max(lo, Math.min(hi, d[i]))) / (hi - lo)
                        if (i) ctx.lineTo(x2, y2); else ctx.moveTo(x2, y2)
                    }
                    ctx.strokeStyle = eq ? "#ffcf9e" : "#5ee0b0"; ctx.lineWidth = 2; ctx.stroke()
                    ctx.fillStyle = "#bdb398"; ctx.font = "10px sans-serif"
                    ctx.fillText(eq ? "respuesta real del EQ (±24 dB)" : "espectro (dBFS, 20 Hz – 20 kHz)", 6, 12)
                }
            }
        }
    }
    Item { width: 1; height: 10 }

    // ---------------- biblioteca (6 secciones, 20 carpetas, 96 módulos) ----------------
    Flow {
        visible: root.libOpen; height: visible ? implicitHeight : 0
        width: root.width; spacing: 6; bottomPadding: 8
        Repeater {
            model: FL.FAMILIES
            NeoButton {
                required property var modelData
                required property int index
                readonly property bool on: root.family === index
                text: modelData.name; fontSize: 12; padX: 8; padY: 2
                color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                onClicked: root.family = index
            }
        }
    }
    Column {
        visible: root.libOpen; height: visible ? implicitHeight : 0
        width: root.width; spacing: 6
        Repeater {
            model: FL.FAMILIES[root.family].folders
            Column {
                id: folder
                required property var modelData
                width: root.width; spacing: 4
                Text { text: folder.modelData.name; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                Flow {
                    width: root.width; spacing: 5
                    Repeater {
                        model: folder.modelData.items
                        Item {
                            id: it
                            required property var modelData
                            readonly property var fx: root.built[modelData[0]] || null
                            width: fx ? addBtn.width : todo.width + 12; height: 26
                            NeoButton {
                                id: addBtn
                                visible: !!it.fx
                                text: "+ " + it.modelData[0] + " " + it.modelData[1]; fontSize: 11; padX: 6; padY: 1; shadow: 2
                                color: "#ffcf9e"; textColor: "#000"
                                tip: it.fx ? it.fx.summary : ""
                                onClicked: root.add(it.fx.key)
                            }
                            Rectangle {
                                visible: !it.fx
                                width: parent.width; height: 24; color: "transparent"
                                border.width: 1; border.color: Theme.ink; opacity: 0.45
                                Text { id: todo; x: 6; anchors.verticalCenter: parent.verticalCenter
                                       text: it.modelData[0] + " " + it.modelData[1] + " · por construir"
                                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 10; font.weight: 500 }
                            }
                        }
                    }
                }
            }
        }
    }
    Text {
        visible: root.libOpen; height: visible ? implicitHeight : 0
        width: root.width; topPadding: 8; wrapMode: Text.Wrap
        text: "Disponibles: " + root.catalog.length + " de 96 (Hito 1). Los efectos suenan en el motor C++, tienen presets y automatización, se guardan en el proyecto (Guardar / Abrir) y su latencia se compensa. Los marcados «por construir» aún no existen."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    Component.onCompleted: {
        var r = studio.call("fxCatalog")
        catalog = r.ok ? r.catalog : []
        if (master) studio.fxMasterBody = root
        else if (extraId) { var et = studio.extraTargets[extraId]; target = et !== undefined ? et : (targets.length > 1 ? Number(targets[1][0]) : 0) }
        else { studio.fxBody = root; if (follow > 0) target = follow }
        reload()
    }

    // Botón de la cabecera de un dispositivo (solo el símbolo)
    component DevBtn: Rectangle {
        id: db
        property string glyph
        property string tip
        signal clicked()
        width: 18; height: 18; radius: 2
        color: dbm.containsMouse ? Theme.knobArc : "transparent"
        Text { anchors.centerIn: parent; text: db.glyph; color: dbm.containsMouse ? "#000" : Theme.deviceInk
               font.family: "Segoe UI Symbol"; font.pixelSize: 10 }
        MouseArea { id: dbm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: db.clicked() }
        ToolTipLite { text: db.tip; show: dbm.containsMouse }
    }
}
