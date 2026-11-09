import QtQuick
import "../theme"
import "../controls"
import "../state/layout.js" as L
import "../state/mixdata.js" as MD

// Módulo Pistas: audio importado y tomas de voz como clips editables (mover, recortar los bordes,
// dividir, duplicar, borrar, volumen, fundidos, normalizar, deshacer), Instrumento y Batería (clips
// con sus notas, suenan con el sintetizador del motor) e IA (DEMO). Regla con compases y cursor del motor.
Column {
    id: root
    property var tracks: []              // [{id, name, len, peaks, note, mute, solo, vol, pan, aclips}]
    property var mixer                      // fichas del mezclador: tipo y rol de voz de cada pista
    property var seq                        // secuenciador: subtítulo y estado de cada pista
    property var studio                     // ventana principal (motor y avisos)
    property var host                       // el módulo Pistas (para situar los conectores de cada fila)
    property int selected: -1
    property real headPos: 0             // 0..1 dentro de los 16 compases (sin motor)
    property real bar16: 40              // segundos de 16 compases
    property real posSec: 0              // posición del motor
    property int bpm: 96
    signal addAudio()
    signal addTone()
    signal notYet(string what)
    signal addType(string type)
    signal toggleMute(int i)
    signal toggleSolo(int i)
    signal removeTrack(int i)
    signal selectTrack(int i)
    width: parent ? parent.width : 600
    spacing: 0

    // ---------------- edición ----------------
    property string tool: "move"            // move | cut
    property bool snap: true                // ajustar a los tiempos del compás
    property real clipSel: 0                // id del clip elegido (0 = ninguno)
    property string clipUid: ""             // pista del clip elegido
    property var undoStack: []
    property var redoStack: []
    property real zoomPps: 0                // píxeles por segundo (0 = que quepa todo)
    readonly property real beat: 60 / Math.max(40, bpm)
    readonly property real span: {          // segundos que muestra el carril
        var e = bar16
        for (var i = 0; i < tracks.length; i++) {
            var cs = tracks[i].aclips || []
            for (var j = 0; j < cs.length; j++) e = Math.max(e, cs[j].start + cs[j].length + 2 * beat)
        }
        return e
    }
    readonly property real fitPps: Math.max(4, (scroll.width - 6 - 170) / span)
    readonly property real pps: zoomPps > 0 ? zoomPps : fitPps
    readonly property real laneW: Math.max(scroll.width - 6 - 170, span * pps)
    readonly property var selTrack: clipUid ? seq.trackOf(clipUid) : null
    readonly property var selInfo: {
        var cs = selTrack ? selTrack.aclips || [] : []
        for (var i = 0; i < cs.length; i++) if (cs[i].id === clipSel) return cs[i]
        return null
    }

    function colorOf(t) { return Theme.pc[seq.src[t.type]] || Theme.pc.pistas }
    function isAudio(t) { return (t.type === "audio" || t.type === "voz") && (t.aclips || []).length > 0 }
    function snapT(t) { return snap ? Math.round(t / beat) * beat : t }
    function fmtS(s) {
        s = Math.max(0, s)
        var m = Math.floor(s / 60), r = s - 60 * m
        return m + ":" + (r < 10 ? "0" : "") + r.toFixed(2)
    }
    function db(v) { return (v > 0 ? "+" : "") + v.toFixed(1) + " dB" }
    // Centro vertical de la fila i en coordenadas del módulo: ahí llega el cable de su módulo
    function rowCenter(i) {
        var r = rows.itemAt(i)
        return r && host ? r.mapToItem(host, 0, r.height / 2).y : 40
    }
    function pick(uid, id) { clipUid = uid; clipSel = id; var i = seq.indexOf(uid); if (i >= 0) selectTrack(i) }
    // Una edición en el motor; antes guarda los clips de la pista para deshacer
    function edit(uid, op, noUndo) {
        var t = seq.trackOf(uid)
        if (!t || !studio || !studio.engineOk) return null
        if (!noUndo) { undoStack = undoStack.concat([{ uid: uid, clips: t.aclips || [] }]).slice(-60); redoStack = [] }
        var r = studio.call("clipEdit", t.id, JSON.stringify(op))
        if (!r.ok) { studio.toast(r.error); if (!noUndo) undoStack = undoStack.slice(0, -1); return null }
        seq.replace(uid, { aclips: r.clips })
        if (clipUid === uid && !r.clips.some(function (c) { return c.id === clipSel })) clipSel = 0
        return r
    }
    function restore(fromStack, toStack) {
        if (!fromStack.length) return null
        var e = fromStack[fromStack.length - 1], t = seq.trackOf(e.uid)
        if (!t) return null
        var back = { uid: e.uid, clips: t.aclips || [] }
        var r = studio.call("clipEdit", t.id, JSON.stringify({ op: "set", clips: e.clips }))
        if (!r.ok) { studio.toast(r.error); return null }
        seq.replace(e.uid, { aclips: r.clips })
        clipSel = 0
        return back
    }
    function undo() {
        var b = restore(undoStack); if (!b) return
        undoStack = undoStack.slice(0, -1); redoStack = redoStack.concat([b])
    }
    function redo() {
        var b = restore(redoStack); if (!b) return
        redoStack = redoStack.slice(0, -1); undoStack = undoStack.concat([b])
    }
    // Dividir: el clip elegido en el cursor; si el cursor no lo cruza, el clip de esa pista bajo el cursor
    function splitAt(uid, id, at) {
        if (!uid) { studio.toast("Elige un clip de audio para dividir"); return }
        var t = seq.trackOf(uid), cs = t ? t.aclips || [] : []
        var c = cs.filter(function (k) { return k.id === id && at > k.start && at < k.start + k.length })[0]
             || cs.filter(function (k) { return at > k.start + 0.01 && at < k.start + k.length - 0.01 })[0]
        if (!c) { studio.toast("El cursor no está sobre un clip de " + (t ? t.name : "la pista")); return }
        edit(uid, { op: "split", clip: c.id, at: at })
    }
    function removeSel() { if (selInfo) edit(clipUid, { op: "remove", clip: clipSel }) }
    function dupSel() { if (selInfo) { var r = edit(clipUid, { op: "dup", clip: clipSel }); if (r) clipSel = r.clips[r.clips.length - 1].id } }
    function gainSel(d) { if (selInfo) edit(clipUid, { op: "gain", clip: clipSel, db: Math.round((selInfo.gain_db + d) * 10) / 10 }) }
    function fadeSel(which, d) {
        if (!selInfo) return
        var fi = selInfo.fade_in, fo = selInfo.fade_out
        if (which === "in") fi = Math.max(0, fi + d); else fo = Math.max(0, fo + d)
        edit(clipUid, { op: "fades", clip: clipSel, "in": fi, out: fo })
    }
    function seekTo(s) { if (studio && studio.engineOk) studio.call("seek", Math.max(0, s)) }

    Shortcut { sequence: "S"; enabled: root.visible && !!root.clipUid; onActivated: root.splitAt(root.clipUid, root.clipSel, root.posSec) }
    Shortcut { sequences: [StandardKey.Delete, "Backspace"]; enabled: root.visible && !!root.selInfo; onActivated: root.removeSel() }
    Shortcut { sequence: "Ctrl+D"; enabled: root.visible && !!root.selInfo; onActivated: root.dupSel() }
    Shortcut { sequences: [StandardKey.Undo]; enabled: root.visible && root.undoStack.length > 0; onActivated: root.undo() }
    Shortcut { sequences: [StandardKey.Redo, "Ctrl+Y"]; enabled: root.visible && root.redoStack.length > 0; onActivated: root.redo() }

    Flow {                                // .tb
        width: root.width
        spacing: 6
        bottomPadding: 8 + 3
        NeoButton { text: "+ Audio"; tip: "Importar WAV/AIFF/FLAC al motor nativo"; onClicked: root.addAudio() }
        NeoButton { text: "+ Tono de prueba"; tip: "Señal sintética de 440 Hz para comprobar el motor"; onClicked: root.addTone() }
        Repeater {
            model: [["inst", "Instrumento"], ["drum", "Batería"], ["ia", "IA"]]
            NeoButton { text: "+ " + modelData[1]; onClicked: root.addType(modelData[0]) }
        }
        NeoButton { text: "+ Voz"; tip: "Pista que graba la entrada del dispositivo (Grabador de cintas)"; onClicked: root.addType("voz") }
    }

    // ---------------- barra de edición ----------------
    Rectangle {
        width: root.width
        height: editFlow.height + 12
        color: "#000"
        Flow {
            id: editFlow
            x: 6; y: 6; width: parent.width - 12
            spacing: 5
            Tb { text: "↖ Mover"; on: root.tool === "move"; tip: "Arrastra un clip para moverlo y sus bordes para recortarlo"; onClicked: root.tool = "move" }
            Tb { text: "✂ Cortar"; on: root.tool === "cut"; tip: "Clic sobre un clip: lo divide en ese punto"; onClicked: root.tool = "cut" }
            Sep {}
            Tb { text: "Dividir (S)"; active: !!root.clipUid; tip: "Divide el clip en el cursor de reproducción"
                 onClicked: root.splitAt(root.clipUid, root.clipSel, root.posSec) }
            Tb { text: "Duplicar"; active: !!root.selInfo; tip: "Copia el clip detrás del último de la pista (Ctrl+D)"; onClicked: root.dupSel() }
            Tb { text: "Borrar"; active: !!root.selInfo; tip: "Quita el clip (Supr)"; onClicked: root.removeSel() }
            Tb { text: "Normalizar"; active: !!root.selInfo; tip: "Sube o baja el clip para que su pico quede en −1 dBFS"
                 onClicked: root.edit(root.clipUid, { op: "normalize", clip: root.clipSel, target: -1 }) }
            Sep {}
            Tb { text: "Vol −"; active: !!root.selInfo; onClicked: root.gainSel(-1) }
            Lcd { fontSize: 12; padX: 6; text: root.selInfo ? root.db(root.selInfo.gain_db) : "— dB" }
            Tb { text: "Vol +"; active: !!root.selInfo; onClicked: root.gainSel(1) }
            Sep {}
            Tb { text: "Fade in"; active: !!root.selInfo; tip: "Clic: +0,25 s · también se arrastra el cuadrito de la esquina del clip"
                 onClicked: root.fadeSel("in", 0.25) }
            Tb { text: "Fade out"; active: !!root.selInfo; tip: "Clic: +0,25 s · también se arrastra el cuadrito de la esquina del clip"
                 onClicked: root.fadeSel("out", 0.25) }
            Tb { text: "Sin fades"; active: !!root.selInfo && (root.selInfo.fade_in > 0 || root.selInfo.fade_out > 0)
                 onClicked: root.edit(root.clipUid, { op: "fades", clip: root.clipSel, "in": 0, out: 0 }) }
            Sep {}
            Tb { text: "⌗ Rejilla"; on: root.snap; tip: "Ajustar mover y recortar a los tiempos del compás"; onClicked: root.snap = !root.snap }
            Tb { text: "Deshacer"; active: root.undoStack.length > 0; tip: "Deshacer (Ctrl+Z)"; onClicked: root.undo() }
            Tb { text: "Rehacer"; active: root.redoStack.length > 0; tip: "Rehacer (Ctrl+Y)"; onClicked: root.redo() }
            Sep {}
            Tb { text: "−"; tip: "Alejar la línea de tiempo"; onClicked: root.zoomPps = Math.max(2, root.pps / 1.5) }
            Tb { text: "+"; tip: "Acercar la línea de tiempo"; onClicked: root.zoomPps = Math.min(800, root.pps * 1.5) }
            Tb { text: "Ajustar"; on: root.zoomPps === 0; tip: "Que quepa toda la canción"; onClicked: root.zoomPps = 0 }
        }
    }
    Rectangle {                           // datos del clip elegido
        width: root.width; height: 22
        color: "#1d1912"
        Text {
            x: 8; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 16; elide: Text.ElideRight
            text: root.selInfo
                  ? (root.selTrack ? root.selTrack.name : "") + " · inicio " + root.fmtS(root.selInfo.start) + " · dura " + root.fmtS(root.selInfo.length)
                    + " · desde " + root.fmtS(root.selInfo.offset) + " del archivo · " + root.db(root.selInfo.gain_db)
                    + " · fades " + root.selInfo.fade_in.toFixed(2) + " / " + root.selInfo.fade_out.toFixed(2) + " s"
                  : "Clic en un clip de audio para editarlo · clic en la regla o en un carril: mover el cursor · cursor " + root.fmtS(root.posSec)
            color: "#ffb000"; font.family: Theme.font; font.pixelSize: 11; font.weight: 600
        }
    }

    Rectangle {                           // .scroll
        id: scroll
        width: root.width
        height: content.height + 6
        color: "#16130e"
        border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030" }
        Flickable {
            id: hflick
            x: 3; y: 3
            width: parent.width - 6
            height: content.height
            contentWidth: 170 + root.laneW
            contentHeight: height
            flickableDirection: Flickable.HorizontalFlick
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentWidth > width
            clip: true
            Column {
                id: content
                width: hflick.contentWidth
                Item {                       // regla: compases (y segundos); clic = mover el cursor
                    width: content.width; height: 22
                    Rectangle { width: 170; height: parent.height; color: "#2b2720"
                                Text { x: 10; anchors.verticalCenter: parent.verticalCenter; text: "COMPÁS"; color: "#bdb398"
                                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700 } }
                    Item {
                        x: 170; width: root.laneW; height: parent.height
                        Repeater {
                            model: Math.ceil(root.span / (4 * root.beat)) + 1
                            Item {
                                required property int index
                                readonly property real bx: index * 4 * root.beat * root.pps
                                x: bx; height: parent.height
                                visible: bx < root.laneW && (root.pps * 4 * root.beat > 26 || index % 4 === 0)
                                Rectangle { width: 1; height: parent.height; color: Qt.rgba(1, 1, 1, 0.35) }
                                Text { x: 3; y: 3; text: String(parent.index + 1); color: "#f3e7c4"
                                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
                            }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: function (m) { root.seekTo(m.x / root.pps) } }
                    }
                    Rectangle { y: parent.height - 2; width: parent.width; height: 2; color: "#000" }
                }
                Repeater {
                    id: rows
                    model: root.tracks
                    delegate: Item {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool audio: root.isAudio(modelData)
                        width: content.width
                        height: Math.max(row.audio ? 84 : 64, th.implicitHeight) + 2
                        // .th
                        Rectangle {
                            id: th
                            width: 170; height: row.height - 2
                            implicitHeight: thCol.implicitHeight + 12
                            color: row.index === root.selected ? "#51452e" : "#2b2720"
                            Rectangle { width: 8; height: parent.height; color: root.colorOf(row.modelData) }
                            Rectangle { x: parent.width - 2; width: 2; height: parent.height; color: "#000" }
                            MouseArea { anchors.fill: parent; onClicked: root.selectTrack(row.index) }
                            Column {
                                id: thCol
                                x: 16; y: 6; width: 170 - 16 - 10
                                spacing: 3
                                Text { width: parent.width; text: row.modelData.name; elide: Text.ElideRight
                                       color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                                Text { width: parent.width; wrapMode: Text.Wrap
                                       text: row.modelData.type === "audio"
                                             ? "Audio: " + L.fmt(row.modelData.len) + " · " + (row.modelData.aclips || []).length + " clip"
                                               + ((row.modelData.aclips || []).length === 1 ? "" : "s") + (row.modelData.note ? " · " + row.modelData.note : "")
                                             : root.seq.tn[row.modelData.type] + ": " + root.seq.sub(row.modelData)
                                       color: "#bdb398"; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
                                Row {
                                    spacing: 4
                                    NeoButton { text: "M"; fontSize: 12; padX: 6; padY: 0; shadow: 2; pressedState: row.modelData.mute
                                                color: row.modelData.mute ? Theme.accent : Theme.button
                                                textColor: row.modelData.mute ? "#000" : Theme.ink
                                                tip: "Silenciar"; onClicked: root.toggleMute(row.index) }
                                    NeoButton { text: "S"; fontSize: 12; padX: 6; padY: 0; shadow: 2; pressedState: row.modelData.solo
                                                color: row.modelData.solo ? Theme.accent : Theme.button
                                                textColor: row.modelData.solo ? "#000" : Theme.ink
                                                tip: "Solo"; onClicked: root.toggleSolo(row.index) }
                                    NeoButton { text: "✕"; fontSize: 12; padX: 6; padY: 0; shadow: 2
                                                tip: "Quitar pista"; onClicked: root.removeTrack(row.index) }
                                }
                                Row {                       // .afo-trole: tipo y rol de voz
                                    id: trole
                                    readonly property var item: { root.mixer.items; return root.mixer.itemOfTrack(row.modelData.id) }
                                    visible: !!item
                                    width: parent.width; spacing: 4; topPadding: 2
                                    Rectangle {
                                        width: parent.width - 58 - 4; height: 14; anchors.verticalCenter: parent.verticalCenter
                                        color: MD.kindColor(trole.item ? trole.item.kind : ""); border.width: 2; border.color: "#000"
                                        Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                               text: MD.kindShort(trole.item ? trole.item.kind : ""); color: "#000"
                                               font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                    }
                                    Select {
                                        width: 58; options: MD.ROLES; current: trole.item ? trole.item.role : "—"
                                        fontSize: 11; fontWeight: 700; padX: 2; padY: 1; centered: true
                                        fill: "#fff"; ink: "#000"; tip: MD.roleTip()
                                        onPicked: function (v) { root.mixer.setTrackRole(row.modelData.id, v) }
                                    }
                                }
                            }
                        }
                        // .lane
                        Item {
                            id: lane
                            x: 170; width: root.laneW; height: row.height - 2
                            opacity: root.seq.disconnected(row.modelData) ? 0.3 : 1           // .off .lane
                            readonly property real w16: root.bar16 * root.pps                   // ancho de los 16 compases
                            MouseArea {              // fondo: elegir la pista y mover el cursor
                                anchors.fill: parent
                                onClicked: function (m) { root.selectTrack(row.index); root.clipSel = 0; root.seekTo(m.x / root.pps) }
                            }
                            Repeater {               // rejilla de compases
                                model: Math.ceil(root.span / (4 * root.beat))
                                Rectangle { required property int index
                                            x: (index + 1) * 4 * root.beat * root.pps - 1; width: 1; height: lane.height
                                            color: Qt.rgba(1, 1, 1, 0.14); visible: x < lane.width }
                            }
                            Repeater {               // clips de Instrumento, Batería e IA (en % de los 16 compases)
                                model: row.audio || row.modelData.type === "audio" || row.modelData.type === "voz" ? [] : row.modelData.clips
                                Rectangle {
                                    required property var modelData
                                    x: lane.w16 * modelData[0] / 100; y: 5
                                    width: lane.w16 * modelData[1] / 100; height: lane.height - 10
                                    color: root.colorOf(row.modelData); border.width: 2; border.color: "#000"
                                    opacity: row.modelData.mute ? 0.3 : 1                      // .muted .clip
                                    Rectangle { x: 2; y: 2; z: -1; width: parent.width; height: parent.height; color: "#000" }
                                }
                            }
                            Canvas {                 // .mn: notas del piano roll / golpes del patrón en cada compás del clip
                                width: lane.w16; height: parent.height
                                visible: row.modelData.type === "inst" || row.modelData.type === "drum"
                                property var t: row.modelData
                                onTChanged: requestPaint()
                                onWidthChanged: requestPaint()
                                onPaint: {
                                    var ctx = getContext("2d"); ctx.reset()
                                    if (!visible) return
                                    var drum = t.type === "drum", keys = Object.keys(drum ? t.pat : t.roll)
                                    var w = Math.max(1, width * 0.0034)
                                    for (var c = 0; c < t.clips.length; c++) {
                                        var b0 = Math.round(t.clips[c][0] / 6.25), b1 = Math.round((t.clips[c][0] + t.clips[c][1]) / 6.25)
                                        for (var b = b0; b < b1; b++)
                                            for (var k = 0; k < keys.length; k++) {
                                                var rs = keys[k].split("-"), r = +rs[0], s = +rs[1]
                                                ctx.fillStyle = drum ? (r === 0 ? "#ff4d3d" : r === 1 ? "#ff9b3d" : r === 5 ? "#ffe14d" : "#000") : "#000"
                                                ctx.fillRect(width * (b * 6.25 + s * 6.25 / 16) / 100, drum ? 6 + r * 6 : 6 + r * 4, w, 3)
                                            }
                                    }
                                }
                            }
                            Text {                   // pista de voz sin toma todavía
                                visible: row.modelData.type === "voz" && !row.audio
                                x: 10; anchors.verticalCenter: parent.verticalCenter
                                text: "Sin toma: graba desde el Grabador de cintas"
                                color: "#bdb398"; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
                            }

                            // clips de audio editables
                            Repeater {
                                model: row.audio ? row.modelData.aclips : []
                                Item {
                                    id: ac
                                    required property var modelData
                                    property bool busy: false
                                    property var live: ({})
                                    readonly property var v: busy ? live : modelData
                                    readonly property bool picked: root.clipSel === modelData.id && root.clipUid === row.modelData.uid
                                    x: v.start * root.pps; y: 4
                                    width: Math.max(4, v.length * root.pps); height: lane.height - 8
                                    z: picked ? 2 : 1
                                    function begin() { live = Object.assign({}, modelData); busy = true; root.pick(row.modelData.uid, modelData.id) }
                                    function set(k) { live = Object.assign({}, live, k) }
                                    function commitRange() {
                                        busy = false
                                        if (live.start === modelData.start && live.length === modelData.length && live.offset === modelData.offset) return
                                        root.edit(row.modelData.uid, { op: "range", clip: modelData.id, start: live.start, length: live.length, offset: live.offset })
                                    }
                                    Rectangle { x: 2; y: 2; width: parent.width; height: parent.height; color: "#000" }
                                    Rectangle {
                                        id: body
                                        anchors.fill: parent
                                        color: Qt.darker(root.colorOf(row.modelData), row.modelData.mute ? 2.2 : 1.0)
                                        border.width: ac.picked ? 3 : 2; border.color: ac.picked ? "#fff" : "#000"
                                        clip: true
                                        Rectangle {          // franja del nombre
                                            width: parent.width; height: 14; color: Qt.rgba(0, 0, 0, 0.35)
                                            Text { x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                                                   text: row.modelData.name + (Math.abs(ac.v.gain_db) > 0.05 ? "  " + root.db(ac.v.gain_db) : "")
                                                   color: "#fff"; font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                        }
                                        Canvas {             // forma de onda del trozo que suena, con su volumen y fundidos
                                            id: wave
                                            y: 14; width: parent.width; height: parent.height - 14
                                            property var peaks: row.modelData.peaks || []
                                            property var vv: ac.v
                                            onPeaksChanged: requestPaint()
                                            onVvChanged: requestPaint()
                                            onWidthChanged: requestPaint()
                                            onPaint: {
                                                var ctx = getContext("2d"); ctx.reset()
                                                var p = peaks, c = vv, src = Math.max(0.01, c.source_length || row.modelData.len || 1)
                                                var g = Math.pow(10, (c.gain_db || 0) / 20), n = Math.max(1, Math.floor(width / 2))
                                                ctx.fillStyle = "rgba(0,0,0,0.85)"
                                                for (var j = 0; j < n && p.length; j++) {
                                                    var tt = c.length * j / n
                                                    var env = 1
                                                    if (c.fade_in > 0 && tt < c.fade_in) env = tt / c.fade_in
                                                    if (c.fade_out > 0 && tt > c.length - c.fade_out) env = Math.min(env, (c.length - tt) / c.fade_out)
                                                    var v = (p[Math.min(p.length - 1, Math.floor((c.offset + tt) / src * p.length))] || 0) * g * env
                                                    var h = Math.min(height - 2, 2 + v * (height - 4))
                                                    ctx.fillRect(width * j / n, (height - h) / 2, 1.4, h)
                                                }
                                                // fundidos: zona sombreada y línea de la curva
                                                ctx.fillStyle = "rgba(0,0,0,0.28)"; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5
                                                var fi = c.fade_in * root.pps, fo = c.fade_out * root.pps
                                                if (fi > 1) { ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(fi, 0); ctx.lineTo(0, height); ctx.closePath(); ctx.fill()
                                                              ctx.beginPath(); ctx.moveTo(0, height); ctx.lineTo(fi, 0); ctx.stroke() }
                                                if (fo > 1) { ctx.beginPath(); ctx.moveTo(width, 0); ctx.lineTo(width - fo, 0); ctx.lineTo(width, height); ctx.closePath(); ctx.fill()
                                                              ctx.beginPath(); ctx.moveTo(width - fo, 0); ctx.lineTo(width, height); ctx.stroke() }
                                            }
                                        }
                                    }
                                    MouseArea {              // cuerpo: elegir, mover o cortar
                                        anchors.fill: parent
                                        preventStealing: true
                                        cursorShape: root.tool === "cut" ? Qt.IBeamCursor : pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                        property real px0
                                        onPressed: function (m) {
                                            if (root.tool === "cut") {
                                                root.pick(row.modelData.uid, ac.modelData.id)
                                                root.splitAt(row.modelData.uid, ac.modelData.id, root.snapT(ac.modelData.start + m.x / root.pps))
                                                return
                                            }
                                            px0 = mapToItem(lane, m.x, 0).x; ac.begin()
                                        }
                                        onPositionChanged: function (m) {
                                            if (!ac.busy) return
                                            var d = (mapToItem(lane, m.x, 0).x - px0) / root.pps
                                            ac.set({ start: Math.max(0, root.snapT(ac.modelData.start + d)) })
                                        }
                                        onReleased: if (ac.busy) ac.commitRange()
                                    }
                                    Rectangle {              // asa del volumen: arrastrar arriba/abajo
                                        visible: ac.picked && ac.width > 60
                                        x: (parent.width - width) / 2; y: 16
                                        width: gainTxt.implicitWidth + 12; height: 16; radius: 8
                                        color: gm.pressed ? Theme.accent : "#fff"; border.width: 2; border.color: "#000"
                                        Text { id: gainTxt; anchors.centerIn: parent; text: root.db(ac.v.gain_db); color: "#000"
                                               font.family: Theme.font; font.pixelSize: 9; font.weight: 700 }
                                        MouseArea {
                                            id: gm; anchors.fill: parent; preventStealing: true; cursorShape: Qt.SizeVerCursor
                                            property real y0
                                            onPressed: function (m) { y0 = mapToItem(lane, 0, m.y).y; ac.begin() }
                                            onPositionChanged: function (m) {
                                                var d = (y0 - mapToItem(lane, 0, m.y).y) * 0.25
                                                ac.set({ gain_db: Math.max(-60, Math.min(24, Math.round((ac.modelData.gain_db + d) * 10) / 10)) })
                                            }
                                            onReleased: { ac.busy = false; root.edit(row.modelData.uid, { op: "gain", clip: ac.modelData.id, db: ac.live.gain_db }) }
                                        }
                                    }
                                    Repeater {               // cuadritos de fundido (entrada y salida)
                                        model: ac.picked ? ["in", "out"] : []
                                        Rectangle {
                                            required property string modelData
                                            readonly property bool isIn: modelData === "in"
                                            width: 10; height: 10
                                            x: isIn ? Math.min(ac.width - 10, ac.v.fade_in * root.pps) : Math.max(0, ac.width - 10 - ac.v.fade_out * root.pps)
                                            y: 14
                                            color: fm.pressed ? Theme.accent : "#fff"; border.width: 2; border.color: "#000"
                                            MouseArea {
                                                id: fm; anchors.fill: parent; anchors.margins: -4; preventStealing: true; cursorShape: Qt.SizeHorCursor
                                                property real px0
                                                onPressed: function (m) { px0 = mapToItem(lane, m.x, 0).x; ac.begin() }
                                                onPositionChanged: function (m) {
                                                    var d = (mapToItem(lane, m.x, 0).x - px0) / root.pps, L0 = ac.modelData.length
                                                    if (parent.isIn) ac.set({ fade_in: Math.max(0, Math.min(L0 - ac.modelData.fade_out, ac.modelData.fade_in + d)) })
                                                    else ac.set({ fade_out: Math.max(0, Math.min(L0 - ac.modelData.fade_in, ac.modelData.fade_out - d)) })
                                                }
                                                onReleased: { ac.busy = false
                                                              root.edit(row.modelData.uid, { op: "fades", clip: ac.modelData.id, "in": ac.live.fade_in, out: ac.live.fade_out }) }
                                            }
                                        }
                                    }
                                    Repeater {               // bordes: recortar el principio o el final
                                        model: ["l", "r"]
                                        MouseArea {
                                            required property string modelData
                                            readonly property bool isLeft: modelData === "l"
                                            x: isLeft ? -3 : ac.width - 5; y: 14; width: 8; height: ac.height - 14
                                            preventStealing: true
                                            cursorShape: Qt.SizeHorCursor
                                            hoverEnabled: true
                                            property real px0
                                            Rectangle { anchors.fill: parent; color: "#fff"; opacity: parent.containsMouse || parent.pressed ? 0.6 : 0 }
                                            onPressed: function (m) { px0 = mapToItem(lane, m.x, 0).x; ac.begin() }
                                            onPositionChanged: function (m) {
                                                if (!ac.busy) return
                                                var c = ac.modelData, d = (mapToItem(lane, m.x, 0).x - px0) / root.pps
                                                if (isLeft) {
                                                    var s = root.snapT(c.start + d)
                                                    s = Math.max(c.start - c.offset, Math.min(c.start + c.length - 0.05, s))   // no antes del principio del archivo
                                                    ac.set({ start: Math.max(0, s), offset: c.offset + (Math.max(0, s) - c.start), length: c.length - (Math.max(0, s) - c.start) })
                                                } else {
                                                    var e = root.snapT(c.start + c.length + d)
                                                    e = Math.max(c.start + 0.05, Math.min(c.start + (c.source_length - c.offset), e))
                                                    ac.set({ length: e - c.start })
                                                }
                                            }
                                            onReleased: if (ac.busy) ac.commitRange()
                                        }
                                    }
                                }
                            }
                        }
                        Rectangle { y: row.height - 2; width: row.width; height: 2; color: "#000" }
                    }
                }
                DashedBox {
                    visible: root.tracks.length === 0
                    x: 8; width: content.width - 16
                    height: visible ? implicitHeight : 0
                    strokeColor: "#f3e7c4"; textColor: "#f3e7c4"; fill: "transparent"
                    text: "Sin pistas. Agrega una arriba o arrastra archivos de audio a la ventana."
                }
                Item { width: 1; height: root.tracks.length === 0 ? 8 : 0 }
            }
            Rectangle {                     // .ph-line: cursor de reproducción (posición del motor)
                visible: root.tracks.length > 0
                x: 170 + (root.posSec > 0 ? root.posSec : root.headPos * root.bar16) * root.pps
                width: 3; height: content.height
                color: "#ffd34d"
                Rectangle { anchors.centerIn: parent; width: 9; height: parent.height; color: "#ffd34d"; opacity: 0.25 }
            }
        }
    }

    Text {                                 // .hint
        width: root.width; topPadding: 8
        wrapMode: Text.Wrap
        text: "Audio: arrastra un clip para moverlo, sus bordes para recortarlo, el cuadrito de cada esquina para el fundido y la etiqueta de dB para el volumen. S divide en el cursor, Supr borra, Ctrl+D duplica, Ctrl+Z deshace. Cada pista se conecta con su módulo."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    component Tb: NeoButton {
        property bool on: false
        property bool active: true
        fontSize: 12; padX: 7; padY: 2; shadow: 0
        color: on ? Theme.accent : "#2b2720"; textColor: on ? "#000" : "#f3e7c4"
        opacity: active ? 1 : 0.4
        enabled: active
    }
    component Sep: Rectangle { width: 2; height: 24; color: "#4a4030" }
}
