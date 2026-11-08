import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import "layout.js" as L

// AllForOne con interfaz nativa (Qt Quick). Referencia visual: PLANTILLA_DAW.html.
// Lógica del lienzo portada de la plantilla; el audio y los datos vienen de Python (`afo`).
Window {
    id: win
    width: 1600; height: 900
    minimumWidth: 900; minimumHeight: 560
    visible: true
    title: "AllForOne " + appVersion
    color: Theme.bg

    // ---------------- estado ----------------
    property bool engineOk: false
    property bool playing: false
    property int bpm: 96
    property int step: -1                     // semicorchea dentro de los 16 compases (como la plantilla)
    property var tracks: []
    property int selected: -1
    property var hidden: ({})
    property var portOverride: ({})
    property var bends: ({})
    property int portRev: 0
    property int geomRev: 0
    property int zTop: 20
    property real tx: 0
    property real ty: 0
    property real zoom: 1
    property var panelItems: ({})
    readonly property real bar16: 16 * 4 * 60 / Math.max(40, bpm)
    readonly property var cableLinks: L.links(hidden)
    readonly property var portList: {
        var out = []
        for (var i = 0; i < cableLinks.length; i++) {
            out.push({ key: cableLinks[i].key, end: "from", pid: cableLinks[i].f, link: cableLinks[i] })
            out.push({ key: cableLinks[i].key, end: "to", pid: cableLinks[i].t, link: cableLinks[i] })
        }
        return out
    }

    // ---------------- geometría ----------------
    function geom(id) {
        var p = panelItems[id]
        return p ? { x: p.x, y: p.y, w: p.width, h: p.height } : { x: 0, y: 0, w: 1, h: 1 }
    }
    function anchorOf(link, end) {
        var id = end === "from" ? link.f : link.t
        return L.anchor(geom(id), portOverride[link.key + ":" + end] || L.defaultPin(link, end))
    }
    function fitIds(ids) {
        var rs = []
        for (var i = 0; i < ids.length; i++) if (panelItems[ids[i]] && !hidden[ids[i]]) rs.push(geom(ids[i]))
        if (!rs.length) return
        var v = L.fit(rs, viewport.width, viewport.height)
        zoom = v.z; tx = v.tx; ty = v.ty
    }
    function visibleIds() { return L.PANELS.map(function (p) { return p[0] }).filter(function (i) { return !hidden[i] }) }
    function zoomAt(f, cx, cy) {
        var z = Math.max(.2, Math.min(1.6, zoom * f)); f = z / zoom
        tx = cx - (cx - tx) * f; ty = cy - (cy - ty) * f; zoom = z
    }
    function setDark(b) { Theme.dark = b }
    function setHidden(id, b) {
        var h = Object.assign({}, hidden); h[id] = b; hidden = h
        if (!b) Qt.callLater(fitIds, [id])
    }

    // ---------------- diseño guardado ----------------
    function saveLayout() {
        var pos = {}
        for (var id in panelItems) {
            var p = panelItems[id], o = [p.x, p.y, p.width]
            if (p.resized) o.push(p.fixedHeight)
            pos[id] = o
        }
        layoutStore.save(JSON.stringify({ pos: pos, ports: portOverride, bends: bends, theme: Theme.dark ? "dark" : "light" }))
    }
    property var savedLayout: {
        try { return JSON.parse(layoutStore.load()) } catch (e) { return {} }
    }
    function resetLayout() {
        for (var i = 0; i < L.PANELS.length; i++) {
            var d = L.PANELS[i], p = panelItems[d[0]]
            p.x = d[3][0]; p.y = d[3][1]; p.width = d[3][2]; p.resized = false; p.fixedHeight = d[4]
        }
        portOverride = {}; bends = {}; portRev++
        Qt.callLater(fitIds, ["inst", "drums", "pistas"])
        saveLayout()
        toast("Diseño original restaurado")
    }

    // ---------------- motor ----------------
    function call(name) {
        var args = Array.prototype.slice.call(arguments, 1)
        try { return JSON.parse(afo[name].apply(afo, args)) } catch (e) { return { ok: false, error: String(e) } }
    }
    function addTrack(info) {
        var t = tracks.slice()
        t.push({ id: info.id, name: info.name, len: info.length_seconds || 0, peaks: info.peaks || [],
                 note: info.note || "", mute: false, solo: false })
        tracks = t; selected = t.length - 1
    }
    function syncTrackStates() {
        call("setTrackStates", JSON.stringify(tracks.map(function (t) { return [t.id, t.mute, t.solo] })))
    }
    function importAudio() {
        var r = call("importAudio")
        if (r.ok) {
            r.tracks.forEach(addTrack)
            var conv = (r.converting || []).length
            toast(r.tracks.length + " archivo(s) en el motor" + (conv ? " · convirtiendo " + conv + " a 32 bits" : ""))
        } else if (!r.cancelled) toast(r.error)
    }
    function importPaths(paths) {
        var r = call("importPaths", JSON.stringify(paths))
        if (r.ok) {
            r.tracks.forEach(addTrack)
            var conv = (r.converting || []).length
            toast(r.tracks.length + " archivo(s) en el motor" + (conv ? " · convirtiendo " + conv + " a 32 bits" : ""))
        } else toast(r.error)
    }
    function timeText() {
        if (step < 0) return "1.1"
        var s = step % 16, b = step >> 4
        return (b + 1) + "." + ((s >> 2) + 1)
    }
    Connections {
        target: afo
        function onStateChanged(s) {
            var st; try { st = JSON.parse(s) } catch (e) { return }
            win.playing = st.playing
            if (st.playing || st.position > 0) win.step = Math.floor(st.position * win.bpm / 15) % 256
        }
        function onMixerEvent(s) {
            var ev; try { ev = JSON.parse(s) } catch (e) { return }
            if (ev.type !== "import") return
            if (ev.phase === "convert") toast(ev.desc)
            else if (ev.phase === "track") { addTrack(ev.track); toast("Convertido y en el motor: " + ev.track.name) }
            else if (ev.phase === "error") toast(ev.error)
        }
    }

    // ---------------- aviso (#toast) ----------------
    function toast(t) { toastText.text = t; toastBox.opacity = 1; toastTimer.restart() }
    Timer { id: toastTimer; interval: 2400; onTriggered: toastBox.opacity = 0 }

    // ---------------- cabecera ----------------
    Rectangle {
        id: header
        z: 5
        width: parent.width
        height: Math.round(chips.y + chips.height + 10 + 3)
        color: Theme.header
        Rectangle { y: parent.height - 3; width: parent.width; height: 3; color: Theme.line }

        Row {
            id: leftGroup
            x: 14; y: 10
            spacing: 16
            Row {                                   // .transport
                spacing: 6
                NeoButton {
                    text: "■"; tip: "Detener"
                    onClicked: { if (win.engineOk) win.call("stop"); win.step = -1 }
                }
                NeoButton {
                    text: win.playing ? "❚❚ Pausa" : "▶ Reproducir"
                    color: "#ffc233"; textColor: "#000"
                    width: Math.max(100, implicitWidth)
                    onClicked: {
                        if (!win.engineOk) { win.toast("Motor nativo no disponible"); return }
                        var r = win.call("togglePlay"); if (!r.ok) win.toast(r.error)
                    }
                }
                Rectangle {                         // .time
                    width: timeLbl.implicitWidth + 26; height: 35
                    anchors.verticalCenter: parent.verticalCenter
                    color: "#120f0a"; border.width: 3; border.color: "#000"
                    Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#3a3020" }
                    Text { id: timeGlow; anchors.centerIn: parent; text: timeLbl.text; color: "#ffb000"; opacity: 0.45
                           font: timeLbl.font; scale: 1.06 }
                    Text { id: timeLbl; anchors.centerIn: parent; text: win.timeText(); color: "#ffb000"
                           font.family: Theme.font; font.pixelSize: 18; font.weight: 700; font.letterSpacing: 1.44 }
                }
                Row {
                    spacing: 6
                    anchors.verticalCenter: parent.verticalCenter
                    Text { text: "Tempo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
                           anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        width: 64; height: 32
                        color: Theme.input; border.width: 2; border.color: "#000"
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
                NeoButton { text: "−"; tip: "Alejar"; onClicked: win.zoomAt(.8, viewport.width / 2, viewport.height / 2) }
                NeoButton { text: "+"; tip: "Acercar"; onClicked: win.zoomAt(1.25, viewport.width / 2, viewport.height / 2) }
                NeoButton { text: "Ver todo"; onClicked: win.fitIds(win.visibleIds()) }
                NeoButton { text: "Restaurar diseño"; tip: "Restaurar posiciones, tamaños y cables iniciales"; onClicked: win.resetLayout() }
                NeoButton {
                    text: Theme.dark ? "◑ Claro" : "◐ Oscuro"
                    tip: "Cambiar entre el tema claro original y el oscuro"
                    onClicked: { Theme.dark = !Theme.dark; win.saveLayout() }
                }
            }
        }

        Item {                                      // .chips
            id: chips
            readonly property real avail: header.width - 28
            readonly property bool sameRow: leftGroup.width + 16 + chipFlow.implicitW <= avail
            width: Math.min(avail, chipFlow.implicitW)
            height: chipFlow.height
            x: header.width - 14 - width
            y: sameRow ? 10 : 10 + leftGroup.height + 10
            Flow {
                id: chipFlow
                width: parent.width
                spacing: 6
                property real implicitW: {
                    var w = 0, n = 0
                    for (var i = 0; i < children.length; i++)
                        if (children[i].width > 0) { w += children[i].width + (n ? 6 : 0); n++ }
                    return w
                }
                Text {
                    text: "Módulos:"; color: Theme.ink; height: 34; verticalAlignment: Text.AlignVCenter
                    font.family: Theme.font; font.pixelSize: 14; font.weight: 700
                }
                Repeater {
                    model: L.PANELS
                    NeoButton {
                        id: chip
                        readonly property string pid: modelData[0]
                        readonly property bool on: !win.hidden[pid]
                        text: modelData[1] + (on ? "" : "  +")
                        color: on ? Theme.pc[pid] : Theme.button
                        textColor: on ? "#000" : Theme.ink
                        pressedState: on
                        onClicked: win.setHidden(pid, on)
                        Rectangle { width: 12; height: 12; border.width: 2; border.color: "#000"
                                    color: chip.on ? "#000" : (Theme.dark ? "#1b1822" : "#fff") }
                    }
                }
            }
        }
    }

    // ---------------- lienzo infinito ----------------
    Item {
        id: viewport
        anchors { top: header.bottom; left: parent.left; right: parent.right; bottom: parent.bottom }
        clip: true

        Canvas {                                    // rejilla de puntos
            id: dots
            anchors.fill: parent
            property real s: 34 * win.zoom
            property real ox: win.tx
            property real oy: win.ty
            property bool dark: Theme.dark
            onSChanged: requestPaint(); onOxChanged: requestPaint(); onOyChanged: requestPaint()
            onDarkChanged: requestPaint(); onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d"); ctx.reset()
                ctx.fillStyle = Theme.dot
                var x0 = ((ox % s) + s) % s + s / 2 - s, y0 = ((oy % s) + s) % s + s / 2 - s
                for (var y = y0; y < height + s; y += s)
                    for (var x = x0; x < width + s; x += s) { ctx.beginPath(); ctx.arc(x, y, 1.75, 0, 6.2832); ctx.fill() }
            }
        }
        MouseArea {                                 // arrastrar el fondo mueve el lienzo
            anchors.fill: parent
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            property point start
            property point orig
            onPressed: function (m) { start = Qt.point(m.x, m.y); orig = Qt.point(win.tx, win.ty) }
            onPositionChanged: function (m) { win.tx = orig.x + m.x - start.x; win.ty = orig.y + m.y - start.y }
        }

        Item {
            id: world
            x: win.tx; y: win.ty
            scale: win.zoom
            transformOrigin: Item.TopLeft

            // cables (debajo de los módulos, como el <svg id="cables">)
            Repeater {
                model: win.cableLinks
                Item {
                    id: cable
                    required property var modelData
                    readonly property color c: Theme.pc[modelData.f]
                    readonly property var geo: {
                        win.geomRev; win.portRev
                        var a = win.anchorOf(modelData, "from"), b = win.anchorOf(modelData, "to")
                        var m = win.bends[modelData.key] || { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
                        return { d: L.cableShape(a, b, m), m: m }
                    }
                    z: 0
                    Shape {                          // drop-shadow(4px 4px 0 #000)
                        x: 4; y: 4
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath { strokeColor: "#000"; strokeWidth: 12; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                                    PathSvg { path: cable.geo.d } }
                    }
                    Shape {
                        preferredRendererType: Shape.CurveRenderer
                        ShapePath { strokeColor: "#000"; strokeWidth: 12; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                                    PathSvg { path: cable.geo.d } }
                        ShapePath { strokeColor: cable.c; strokeWidth: 6; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                                    PathSvg { path: cable.geo.d } }
                        ShapePath {                  // flujo mientras suena
                            id: flow
                            strokeColor: win.playing ? Qt.rgba(1, 1, 1, 0.95) : "transparent"
                            strokeWidth: 2.5; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            strokeStyle: ShapePath.DashLine; dashPattern: [1.2, 6.4]
                            NumberAnimation on dashOffset { from: 7.6; to: 0; duration: 600; loops: Animation.Infinite; running: win.playing }
                            PathSvg { path: cable.geo.d }
                        }
                    }
                }
            }

            // módulos
            Repeater {
                model: L.PANELS
                ModulePanel {
                    id: panel
                    required property var modelData
                    required property int index
                    pid: modelData[0]; title: modelData[1]; modelName: modelData[2]
                    viewZ: win.zoom
                    visible: !win.hidden[pid]
                    autoHeight: pid === "pistas"
                    z: index + 1
                    Component.onCompleted: {
                        var o = (win.savedLayout.pos || {})[pid] || modelData[3]
                        x = L.clamp(o[0], -15000, 15000); y = L.clamp(o[1], -15000, 15000); width = L.clamp(o[2], 240, 5000)
                        fixedHeight = modelData[4]
                        if (o.length > 3) { fixedHeight = L.clamp(o[3], 190, 4000); resized = true }
                        var m = Object.assign({}, win.panelItems); m[pid] = panel; win.panelItems = m
                    }
                    onXChanged: win.geomRev++
                    onYChanged: win.geomRev++
                    onWidthChanged: win.geomRev++
                    onHeightChanged: win.geomRev++
                    onVisibleChanged: win.geomRev++
                    onRaiseRequested: z = ++win.zTop
                    onEditFinished: win.saveLayout()
                    onFocusRequested: win.fitIds([pid])
                    onCloseRequested: win.setHidden(pid, true)

                    Loader {
                        width: panel.bodyWidth
                        sourceComponent: panel.pid === "pistas" ? tracksComp : pendingComp
                    }
                    Component {
                        id: tracksComp
                        TracksBody {
                            tracks: win.tracks
                            selected: win.selected
                            bar16: win.bar16
                            headPos: win.step < 0 ? 0 : (win.step % 256) / 256
                            onAddAudio: { if (win.engineOk) win.importAudio(); else win.toast("Motor nativo no disponible") }
                            onAddTone: {
                                var r = win.call("addTestTone")
                                if (r.ok) { win.addTrack(r.track); win.toast("Tono de prueba 440 Hz (sintético) añadido") } else win.toast(r.error)
                            }
                            onNotYet: function (what) { win.toast("«" + what + "» todavía no está en la interfaz nativa") }
                            onSelectTrack: function (i) { win.selected = i }
                            onToggleMute: function (i) { var t = win.tracks.slice(); t[i] = Object.assign({}, t[i], { mute: !t[i].mute }); win.tracks = t; win.syncTrackStates() }
                            onToggleSolo: function (i) { var t = win.tracks.slice(); t[i] = Object.assign({}, t[i], { solo: !t[i].solo }); win.tracks = t; win.syncTrackStates() }
                            onRemoveTrack: function (i) {
                                var t = win.tracks.slice(), gone = t.splice(i, 1)[0]
                                win.call("removeTrack", gone.id); win.tracks = t
                                if (win.selected >= t.length) win.selected = t.length - 1
                            }
                        }
                    }
                    Component {
                        id: pendingComp
                        PendingBody {
                            phase: ({ audios: 1, mezcla: 1, master: 1, afina: 2, mastia: 2, antes: 2, cinta: 4 })[panel.pid] || 3
                            summary: ({
                                piano: "Piano roll con teclado y rejilla de notas.",
                                inst: "Banco de instrumentos con presets por pista.",
                                drums: "Caja de ritmos de 16 pasos.",
                                cinta: "Grabador de tomas de voz (pasará a grabar con el motor nativo).",
                                ia: "Generador de pistas (DEMO).",
                                mezcla: "Consola con tiras reales, rol de voz y MEZCLAR AUTOMÁTICAMENTE (Mezclador V4.2).",
                                master: "Medidor VU, fader master con medidores reales y exportación.",
                                audios: "Carga de stems: cada audio crea su pista y su tira. Ya puedes arrastrar audios a la ventana o usar «+ Audio» en Pistas.",
                                afina: "Tonalidad, BPM y afinación PSOLA por voz.",
                                mastia: "Los 4 masters del Mezclador V4.2 con LUFS y true peak reales.",
                                antes: "Comparación A/B por pista al mismo volumen."
                            })[panel.pid] || ""
                        }
                    }
                }
            }

            // conectores redondos (en el borde de su módulo, por encima de él)
            Repeater {
                model: win.portList
                Item {
                    id: port
                    required property var modelData
                    readonly property var pnl: win.panelItems[modelData.pid]
                    readonly property var a: { win.geomRev; win.portRev; return win.anchorOf(modelData.link, modelData.end) }
                    readonly property color c: Theme.pc[modelData.link.f]
                    visible: !!pnl && pnl.visible
                    x: a.x - 13; y: a.y - 13
                    z: pnl ? pnl.z + 0.5 : 0
                    width: 26; height: 26
                    scale: pm.containsMouse || pm.pressed ? 1.13 : 1
                    Rectangle { x: 2; y: 2; width: 26; height: 26; radius: 13; color: "#000" }
                    Rectangle {
                        anchors.fill: parent; radius: 13; color: "#d0d0d0"; border.width: 3; border.color: "#000"
                        Rectangle { anchors.centerIn: parent; width: 17; height: 17; radius: 8.5; color: "#111" }
                        Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: port.c }
                        Rectangle { anchors.fill: parent; anchors.margins: 3; radius: 10; color: "transparent"
                                    border.width: 1; border.color: "#fff"; visible: port.modelData.end === "from" }
                    }
                    Rectangle { anchors.fill: parent; anchors.margins: -5; radius: 18; color: "transparent"
                                border.width: 3; border.color: "#fff"; visible: pm.containsMouse || pm.pressed }
                    MouseArea {
                        id: pm
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                        onPositionChanged: function (m) {
                            if (!pressed) return
                            var p = mapToItem(world, m.x, m.y), o = Object.assign({}, win.portOverride)
                            o[port.modelData.key + ":" + port.modelData.end] = L.nearestPin(win.geom(port.modelData.pid), p.x, p.y)
                            win.portOverride = o; win.portRev++
                        }
                        onReleased: win.saveLayout()
                    }
                    ToolTipLite { text: "Arrastra para cambiar este conector a cualquier lado del módulo"; show: pm.containsMouse && !pm.pressed }
                }
            }

            // cuadrado del cable para curvarlo (por encima de todo, como #handles)
            Repeater {
                model: win.cableLinks
                Rectangle {
                    id: bend
                    required property var modelData
                    readonly property var m: {
                        win.geomRev; win.portRev
                        var a = win.anchorOf(modelData, "from"), b = win.anchorOf(modelData, "to")
                        return win.bends[modelData.key] || { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
                    }
                    z: 100000
                    x: m.x - 10.5; y: m.y - 10.5
                    width: 21; height: 21; radius: 4
                    color: bm.containsMouse ? "#ffc233" : Theme.grip
                    border.width: 3; border.color: "#000"
                    Rectangle { x: 2; y: 2; z: -1; width: 21; height: 21; radius: 4; color: "#000" }
                    Rectangle { anchors.centerIn: parent; width: 8; height: 8; color: Theme.pc[bend.modelData.f]; border.width: 1; border.color: "#000" }
                    MouseArea {
                        id: bm
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.SizeAllCursor
                        onPositionChanged: function (m) {
                            if (!pressed) return
                            var p = mapToItem(world, m.x, m.y), o = Object.assign({}, win.bends)
                            o[bend.modelData.key] = { x: p.x, y: p.y }
                            win.bends = o; win.portRev++
                        }
                        onReleased: win.saveLayout()
                    }
                    ToolTipLite { text: "Arrastra para curvar este cable en cualquier dirección"; show: bm.containsMouse && !bm.pressed }
                }
            }
        }

        MouseArea {                                 // la rueda siempre hace zoom (como en la plantilla)
            anchors.fill: parent
            z: 10
            acceptedButtons: Qt.NoButton
            onWheel: function (w) { win.zoomAt(w.angleDelta.y > 0 ? 1.12 : 1 / 1.12, w.x, w.y); w.accepted = true }
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

    // ---------------- ayuda y aviso ----------------
    Rectangle {                                     // #help
        z: 4
        x: 14; y: win.height - 14 - height
        width: Math.min(helpText.implicitWidth + 24, win.width - 28)
        height: helpText.height + 12
        color: Theme.help
        border.width: 2; border.color: "#000"
        Rectangle { x: 3; y: 3; z: -1; width: parent.width; height: parent.height; color: "#000" }
        Text {
            id: helpText
            x: 10; y: 6; width: Math.min(implicitWidth, win.width - 48)
            wrapMode: Text.Wrap
            text: "Franja negra: mover módulo · Cuadritos del borde: cambiar ancho y alto · Conectores redondos: arrastra a cualquier lado · Cuadrado del cable: cambiar su curva."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
            lineHeight: 1.5
        }
    }
    Rectangle {                                     // #toast
        id: toastBox
        z: 6
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        x: (win.width - width) / 2; y: win.height - 60 - height
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
        Theme.dark = savedLayout.theme === "dark"
        var po = savedLayout.ports || {}, ok = {}
        for (var k in po) if (po[k] && ["top", "bottom", "left", "right"].indexOf(po[k].side) >= 0 && isFinite(po[k].u)) ok[k] = { side: po[k].side, u: L.clamp(po[k].u, .03, .97) }
        portOverride = ok
        var be = savedLayout.bends || {}, bk = {}
        for (var b in be) if (be[b] && isFinite(be[b].x) && isFinite(be[b].y)) bk[b] = { x: L.clamp(be[b].x, -15000, 15000), y: L.clamp(be[b].y, -15000, 15000) }
        bends = bk

        var info = call("hello")
        engineOk = !!info.engine
        if (engineOk) {
            call("setMasterVolume", 70)                 // 70 = 0 dB
            call("setTempo", bpm)
            var dev = info.device || {}
            toast(dev.open ? "Motor nativo listo · " + dev.type + " · " + dev.output : "Motor nativo listo · sin dispositivo de salida abierto")
        } else toast("Motor nativo no disponible: " + (info.error || "desconocido"))
        firstFit.start()
    }
    Timer { id: firstFit; interval: 60; onTriggered: win.fitIds(["inst", "drums", "pistas"]) }
}
