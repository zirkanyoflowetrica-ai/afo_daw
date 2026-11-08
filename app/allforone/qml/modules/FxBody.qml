import QtQuick
import "../theme"
import "../controls"
import "../state/fxlibrary.js" as FL

// Módulo Efectos (Rack FX-96): la Biblioteca nativa AFO dentro del motor. Cada efecto es un plugin
// de Tracktion escrito en C++ (native/src/fx): procesa en el hilo de audio, se guarda en la sesión,
// es automatizable e informa su latencia. Aquí solo se elige dónde va, se ordena la cadena y se
// mueven los parámetros; los medidores y las curvas son los que mide el motor.
Column {
    id: root
    property var studio
    property bool shown: true                   // el módulo está en el lienzo (si no, no se consulta el motor)
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
    readonly property var targets: {
        var out = [["0", "Master"]]
        var t = studio.tracks
        for (var i = 0; i < t.length; i++) if (t[i].id >= 0) out.push([String(t[i].id), t[i].name])
        return out
    }
    onTargetsChanged: if (targets.map(function (o) { return o[0] }).indexOf(String(target)) < 0) pickTarget(0)
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
        studio.fxCountChanged()
    }
    function reload() {
        if (!studio.engineOk) return
        var r = studio.call("fxList", target)
        if (r.ok) setChain(r.chain)
    }
    function pickTarget(id) { target = id; sel = -1; reload() }
    function add(key) {
        var r = studio.call("fxAdd", target, key, -1)
        if (!r.ok) { studio.toast(r.error); return }
        sel = r.effect.id
        setChain(r.chain)
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
        studio.toast("Preset «" + presetName + "» guardado")
    }
    function deletePreset() {
        var r = studio.call("fxDeletePreset", curKey, presetName)
        if (!r.ok) { studio.toast(r.error); return }
        presets = r.presets; presetName = ""
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
    function setParam(i, v) {
        var p = type.params[i]
        studio.call("fxParam", cur.id, p.id, v)
        var vals = cur.values.slice(); vals[i] = v
        var id = cur.id
        chain = chain.map(function (e) { return e.id === id ? Object.assign({}, e, { values: vals }) : e })
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
            if (root.studio.playing && (root.cur.automated || []).length) {   // las perillas siguen la curva
                var f = root.studio.call("fxInfo", root.cur.id)
                if (f.ok) root.patch({ id: f.effect.id, values: f.effect.values })
            }
        }
    }

    // ---------------- destino y cadena ----------------
    Row {
        width: root.width; spacing: 8; bottomPadding: 10
        Text { text: "Insertar en"; height: 30; verticalAlignment: Text.AlignVCenter; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
        Select { width: Math.min(260, root.width - 220); options: root.targets; current: String(root.target)
                 onPicked: function (v) { root.pickTarget(Number(v)) } }
        Text { height: 30; verticalAlignment: Text.AlignVCenter; color: Theme.ink
               text: root.chain.length + (root.chain.length === 1 ? " efecto" : " efectos") + " · antes del fader"
               font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
    }
    Flow {                                      // la cadena en el orden de la señal
        width: root.width; spacing: 6; bottomPadding: 10
        Repeater {
            model: root.chain
            Rectangle {
                id: slot
                required property var modelData
                required property int index
                readonly property bool on: modelData.enabled
                readonly property bool picked: modelData.id === root.sel
                width: slotRow.width + 12; height: 34
                color: picked ? Theme.pressedBg : Theme.button
                border.width: 2; border.color: "#000"
                opacity: on ? 1 : 0.55
                Rectangle { x: 3; y: 3; z: -1; width: parent.width; height: parent.height; color: "#000" }
                MouseArea { anchors.fill: parent; onClicked: root.sel = slot.modelData.id }
                Row {
                    id: slotRow
                    x: 6; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                    NeoButton { text: slot.on ? "●" : "○"; fontSize: 11; padX: 5; padY: 0; shadow: 0
                                color: slot.on ? "#5ee0b0" : Theme.button; textColor: "#000"
                                tip: slot.on ? "Activo: pulsa para puentearlo (bypass)" : "Puenteado: pulsa para activarlo"
                                onClicked: root.enable(slot.modelData.id, !slot.on) }
                    Text { anchors.verticalCenter: parent.verticalCenter
                           text: (slot.index + 1) + ". " + (root.typeOf(slot.modelData.key) || { name: slot.modelData.key }).name.replace("AFO ", "")
                                 + ((slot.modelData.automated || []).length ? " ∿" : "")
                           color: slot.picked ? Theme.pressedInk : Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                    NeoButton { text: "◀"; fontSize: 10; padX: 4; padY: 0; shadow: 0; visible: slot.index > 0; tip: "Antes en la cadena"
                                onClicked: root.move(slot.modelData.id, slot.index - 1) }
                    NeoButton { text: "▶"; fontSize: 10; padX: 4; padY: 0; shadow: 0; visible: slot.index < root.chain.length - 1
                                tip: "Después en la cadena"; onClicked: root.move(slot.modelData.id, slot.index + 1) }
                    NeoButton { text: "✕"; fontSize: 10; padX: 4; padY: 0; shadow: 0; tip: "Quitar de la cadena"
                                onClicked: root.remove(slot.modelData.id) }
                }
            }
        }
    }
    DashedBox {
        visible: !root.chain.length; width: root.width; height: visible ? implicitHeight + 10 : 0
        text: "Sin efectos en " + (root.targets.filter(function (o) { return o[0] === String(root.target) })[0] || ["", "Master"])[1]
              + ". Elige uno en la biblioteca de abajo."
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
            Flow {                              // parámetros
                width: ed.width; spacing: 14
                Repeater {
                    model: root.type ? root.type.params : []
                    Column {
                        id: pc
                        required property var modelData
                        required property int index
                        readonly property real v: root.cur && root.cur.values[index] !== undefined ? root.cur.values[index] : modelData.def
                        spacing: 3
                        width: modelData.choices.length ? 130 : 64
                        Knob {
                            visible: !pc.modelData.choices.length
                            anchors.horizontalCenter: parent.horizontalCenter
                            value: root.toPos(pc.modelData, pc.v)
                            label: pc.modelData.name + (root.isAuto(pc.modelData.id) ? " ∿" : "")
                            labelColor: root.isAuto(pc.modelData.id) ? "#ffcf9e" : "#f3e7c4"
                            tip: pc.modelData.help
                            onMoved: function (pos) { root.setParam(pc.index, root.fromPos(pc.modelData, pos)) }
                        }
                        Text { visible: pc.modelData.choices.length > 0; text: pc.modelData.name; color: "#f3e7c4"
                               font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                        Select {
                            visible: pc.modelData.choices.length > 0
                            width: 130; fontSize: 11; padY: 4
                            options: pc.modelData.choices.map(function (c, i) { return [String(i), c] })
                            current: String(Math.round(pc.v))
                            tip: pc.modelData.help
                            onPicked: function (val) { root.setParam(pc.index, Number(val)) }
                        }
                        Text { visible: !pc.modelData.choices.length; anchors.horizontalCenter: parent.horizontalCenter
                               text: root.fmtVal(pc.modelData, pc.v); color: "#ffb000"
                               font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
                    }
                }
            }
        }
    }
    Item { width: 1; height: 10 }

    // ---------------- biblioteca (6 secciones, 20 carpetas, 96 módulos) ----------------
    Flow {
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
        width: root.width; topPadding: 8; wrapMode: Text.Wrap
        text: "Disponibles: " + root.catalog.length + " de 96 (Hito 1). Los efectos suenan en el motor C++, tienen presets y automatización, se guardan en el proyecto (Guardar / Abrir) y su latencia se compensa. Los marcados «por construir» aún no existen."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    Component.onCompleted: {
        var r = studio.call("fxCatalog")
        catalog = r.ok ? r.catalog : []
        reload()
        studio.fxBody = root
    }
}
