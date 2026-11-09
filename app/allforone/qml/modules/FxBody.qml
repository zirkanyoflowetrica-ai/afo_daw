import QtQuick
import "../theme"
import "../controls"
import "../state/fxlibrary.js" as FL
import "../state/fxgraph.js" as FG

// Rack de efectos (Rack FX-96 del canal y Rack FX-M del master): la Biblioteca nativa AFO dentro del
// motor. Cada efecto es un plugin de Tracktion escrito en C++ (native/src/fx): procesa en el hilo de
// audio, se guarda en la sesión, es automatizable e informa su latencia. A la izquierda la cadena en
// orden de señal (activar, ordenar, quitar, «+ Agregar efecto», sin límite); a la derecha una tarjeta
// por efecto con su gráfica (calculada con las fórmulas del motor) y sus perillas. Debajo, el detalle
// del efecto elegido: medidores del motor, presets propios y automatización.
// El rack del canal sigue a la tira elegida en Mezcla; el del master siempre muestra el master.
Column {
    id: root
    property var studio
    property bool shown: true                   // el módulo está en el lienzo (si no, no se consulta el motor)
    property bool master: false                 // Rack FX-M: siempre la pista 0
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
    readonly property int follow: master ? 0 : studio.rackTrack
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
        for (var i = 0; i < chain.length; i++) if (c[chain[i].key] === undefined) {
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
    function pickTarget(id) {
        target = id; sel = -1; menuFor = -1; reload()
        if (!master && id > 0 && studio.rackTrack !== id) studio.rackTrack = id
    }
    function add(key) {
        var r = studio.call("fxAdd", target, key, -1)
        if (!r.ok) { studio.toast(r.error); return }
        sel = r.effect.id
        setChain(r.chain)
        libOpen = false
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
                     onPicked: function (v) { root.pickTarget(Number(v)) } }
        }
    }

    // ---------------- rack: lista a la izquierda, tarjetas a la derecha ----------------
    Row {
        width: root.width; spacing: 12; bottomPadding: 10
        Column {                                   // lista de la cadena (orden de señal)
            id: listCol
            width: Math.min(210, root.width * 0.3); spacing: 4
            Repeater {
                model: root.chain
                Rectangle {
                    id: li
                    required property var modelData
                    required property int index
                    readonly property bool picked: modelData.id === root.sel
                    width: listCol.width; height: liCol.height + 8
                    color: picked ? Theme.pressedBg : Theme.button
                    border.width: 2; border.color: "#000"
                    Rectangle { x: 3; y: 3; z: -1; width: parent.width; height: parent.height; color: "#000" }
                    MouseArea { anchors.fill: parent; onClicked: { root.sel = li.modelData.id; root.menuFor = -1 } }
                    Column {
                        id: liCol
                        x: 6; y: 4; width: parent.width - 12; spacing: 4
                        Row {
                            width: parent.width; spacing: 6
                            Rectangle {                 // casilla: activo / puenteado
                                width: 16; height: 16; anchors.verticalCenter: parent.verticalCenter
                                color: li.modelData.enabled ? "#5ee0b0" : "#fff"; border.width: 2; border.color: "#000"
                                Text { anchors.centerIn: parent; text: li.modelData.enabled ? "✓" : ""; color: "#000"
                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: root.enable(li.modelData.id, !li.modelData.enabled) }
                            }
                            Text { width: parent.width - 16 - 26 - 12; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: (li.index + 1) + ". " + root.nameOf(li.modelData) + ((li.modelData.automated || []).length ? " ∿" : "")
                                   color: li.picked ? Theme.pressedInk : Theme.ink; opacity: li.modelData.enabled ? 1 : 0.55
                                   font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                            NeoButton { text: "⋮"; width: 26; fontSize: 12; padX: 4; padY: 0; shadow: 0; tip: "Ordenar o quitar"
                                        onClicked: root.menuFor = root.menuFor === li.modelData.id ? -1 : li.modelData.id }
                        }
                        Flow {                          // menú ⋮
                            visible: root.menuFor === li.modelData.id
                            width: parent.width; spacing: 4; height: visible ? implicitHeight : 0
                            NeoButton { text: "▲ Subir"; fontSize: 10; padX: 5; padY: 1; shadow: 0; visible: li.index > 0
                                        onClicked: root.move(li.modelData.id, li.index - 1) }
                            NeoButton { text: "▼ Bajar"; fontSize: 10; padX: 5; padY: 1; shadow: 0; visible: li.index < root.chain.length - 1
                                        onClicked: root.move(li.modelData.id, li.index + 1) }
                            NeoButton { text: "✕ Quitar"; fontSize: 10; padX: 5; padY: 1; shadow: 0
                                        onClicked: { root.menuFor = -1; root.remove(li.modelData.id) } }
                        }
                        Text { visible: !!li.modelData.auto; text: "mezcla automática"; color: li.picked ? Theme.pressedInk : Theme.ink
                               opacity: 0.7; font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                    }
                }
            }
            NeoButton {
                width: listCol.width; text: root.libOpen ? "× CERRAR BIBLIOTECA" : "+ AGREGAR EFECTO"
                fontSize: 12; fontWeight: 700; padY: 6; color: "#ffcf9e"; textColor: "#000"
                tip: "Inserta cualquier efecto de la Biblioteca nativa al final de la cadena (sin límite)"
                onClicked: root.libOpen = !root.libOpen
            }
        }
        Flow {                                      // tarjetas
            id: cards
            width: root.width - listCol.width - 12; spacing: 10
            readonly property real cw: width >= 520 ? (width - 10) / 2 : width
            DashedBox {
                visible: !root.chain.length; width: cards.width; height: visible ? implicitHeight + 10 : 0
                text: "Sin efectos en " + root.targetName + ". Pulsa «+ Agregar efecto»" + (root.master ? " o usa Master IA." : " o mezcla automáticamente.")
            }
            Repeater {
                model: root.chain
                Rectangle {
                    id: card
                    required property var modelData
                    required property int index
                    readonly property var desc: root.typeOf(modelData.key)
                    readonly property bool picked: modelData.id === root.sel
                    width: cards.cw; height: cardCol.height + 16
                    color: "#16130e"; border.width: 3; border.color: picked ? "#ffb000" : "#000"
                    opacity: modelData.enabled ? 1 : 0.6
                    Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
                    Column {
                        id: cardCol
                        x: 8; y: 8; width: parent.width - 16; spacing: 6
                        Row {                            // power · nombre · ≡ ⋮
                            width: parent.width; spacing: 5
                            NeoButton { text: "⏻"; width: 26; fontSize: 12; padX: 3; padY: 1; shadow: 2
                                        color: card.modelData.enabled ? "#5ee0b0" : "#3a352a"; textColor: "#000"
                                        tip: card.modelData.enabled ? "Puentear (bypass)" : "Activar"
                                        onClicked: root.enable(card.modelData.id, !card.modelData.enabled) }
                            Text { width: parent.width - 26 - 26 - 26 - 15; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                   text: root.nameOf(card.modelData); color: "#f3e7c4"
                                   font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                            NeoButton { text: "≡"; width: 26; fontSize: 12; padX: 3; padY: 1; shadow: 2; tip: "Detalle: medidores, presets propios y automatización"
                                        onClicked: root.sel = card.modelData.id }
                            NeoButton { text: "⋮"; width: 26; fontSize: 12; padX: 3; padY: 1; shadow: 2; tip: "Ordenar o quitar (en la lista)"
                                        onClicked: root.menuFor = root.menuFor === card.modelData.id ? -1 : card.modelData.id }
                        }
                        Select {
                            width: parent.width; fontSize: 10; padX: 4; padY: 2
                            options: [["", (root.typeOf(card.modelData.key) || { af: "" }).af + " · preset…"]].concat((root.presetCache[card.modelData.key] || []).map(function (p) { return [p.name, p.name + (p.factory ? "" : " ★")] }))
                            current: ""
                            tip: "Presets de fábrica y los tuyos (★)"
                            onPicked: function (v) { if (v) root.applyPresetTo(card.modelData, v) }
                        }
                        Canvas {
                            id: mini
                            width: parent.width; height: 62
                            property var fx: card.modelData
                            property var live: root.cardLive[card.modelData.id]
                            onFxChanged: requestPaint()
                            onLiveChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onPaint: { if (card.desc) FG.draw(getContext("2d"), width, height, fx, card.desc, live) }
                        }
                        Flow {
                            width: parent.width; spacing: 6
                            Repeater {
                                model: card.desc ? card.desc.params : []
                                Column {
                                    id: kc
                                    required property var modelData
                                    required property int index
                                    readonly property real v: card.modelData.values[index] !== undefined ? card.modelData.values[index] : modelData.def
                                    readonly property bool auto: (card.modelData.automated || []).indexOf(modelData.id) >= 0
                                    spacing: 2
                                    width: modelData.choices.length ? 96 : 56
                                    Knob {
                                        visible: !kc.modelData.choices.length
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        value: root.toPos(kc.modelData, kc.v)
                                        label: kc.modelData.name + (kc.auto ? " ∿" : "")
                                        labelColor: kc.auto ? "#ffcf9e" : "#f3e7c4"
                                        tip: kc.modelData.help
                                        onMoved: function (pos) { root.setParamOf(card.modelData, kc.index, root.fromPos(kc.modelData, pos)) }
                                    }
                                    Text { visible: kc.modelData.choices.length > 0; text: kc.modelData.name; color: "#f3e7c4"
                                           font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                                    Select {
                                        visible: kc.modelData.choices.length > 0
                                        width: 96; fontSize: 10; padY: 3; padX: 4
                                        options: kc.modelData.choices.map(function (c, i) { return [String(i), c] })
                                        current: String(Math.round(kc.v))
                                        tip: kc.modelData.help
                                        onPicked: function (val) { root.setParamOf(card.modelData, kc.index, Number(val)) }
                                    }
                                    Text { visible: !kc.modelData.choices.length; anchors.horizontalCenter: parent.horizontalCenter
                                           text: root.fmtVal(kc.modelData, kc.v); color: "#ffb000"
                                           font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ---------------- editor del efecto abierto ----------------
    Rectangle {
        visible: !!root.type
        width: root.width; height: visible ? ed.height + 20 : 0
        color: "#16130e"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
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
                           color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: root.type ? root.type.summary : ""
                           color: "#bdb398"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                }
                Column {                        // entrada / salida medidas en el motor
                    width: 160; spacing: 3; anchors.verticalCenter: parent.verticalCenter
                    Repeater {
                        model: [["Entrada", 0], ["Salida", 1]]
                        Row {
                            required property var modelData
                            spacing: 6
                            Text { width: 48; text: modelData[0]; color: "#bdb398"; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
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
                           color: "#bdb398"; font.family: Theme.font; font.pixelSize: 10; font.weight: 600 }
                }
            }
            Row {                               // presets
                width: ed.width; spacing: 8
                Text { text: "Preset"; height: 28; verticalAlignment: Text.AlignVCenter; color: "#f3e7c4"
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
                    Text { text: "Automatización"; height: 26; verticalAlignment: Text.AlignVCenter; color: "#f3e7c4"
                           font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                    Select {
                        width: 170; fontSize: 11; padY: 3
                        options: root.type ? root.type.params.map(function (p) { return [p.id, p.name + (root.isAuto(p.id) ? " ∿" : "")] }) : []
                        current: root.autoParam
                        onPicked: function (v) { root.autoParam = v }
                    }
                    Text { height: 26; verticalAlignment: Text.AlignVCenter; color: "#bdb398"
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
        else { studio.fxBody = root; if (studio.rackTrack > 0) target = studio.rackTrack }
        reload()
    }
}
