import QtQuick
import "../theme"
import "../controls"

// Crear IA (X18, docs/INSTRUMENTAL_LAB.md §2 y §5): la vista del Instrumental Lab, junto a Arreglo y
// Mezclador. Izquierda: contexto y sesión. Centro: una fila por familia con sus variantes como discos
// dibujados de su propio audio (surcos = envolvente, anillo = energía por bandas), que giran cuando
// suenan. Derecha: las pistas del proyecto; un disco se arrastra a una de ellas (cambia su audio) o a
// «Pista nueva». Abajo: preescucha con pistas reales, enviar y descartar. Todo llama a state/Lab.qml.
Item {
    id: root
    property var studio
    readonly property var lb: studio ? studio.lab : null
    readonly property var seq: lb ? lb.seq : null
    readonly property var st: lb ? lb.state : null
    readonly property var ctx: st ? st.context : null
    readonly property var stat: lb ? lb.status : ({})
    readonly property var families: st ? st.families : []
    readonly property var audioTracks: (studio ? studio.tracks : []).filter(function (t) { return t.type === "audio" && t.id > 0 && !t.lab })
    property var pending: null                  // {track, family, variant}: cambiar el audio de una pista (se confirma)
    property int dragHover: -2                  // id de la pista bajo el disco que se arrastra (-1 = pista nueva)

    // Color apagado por familia (del tema)
    function famColor(f) {
        var k = ({ "Batería": "drums", "Bajo": "inst", "Piano / teclados": "piano", "Guitarra": "pistas", "Sintetizador": "ia",
                   "Cuerdas": "afina", "Metales": "mastia", "Maderas": "antes", "Percusión": "cinta" })[f] || "audios"
        return Theme.pc[k] || Theme.accent
    }
    function draftOf(f) { return lb && lb.drafts[f] !== undefined ? lb.drafts[f] : -1 }
    function trackByDraft(f) {
        var id = draftOf(f); if (id < 0) return null
        for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === id) return studio.tracks[i]
        return null
    }
    function sounding(f, v) {
        if (!studio || !studio.playing || !v.chosen) return false
        var t = trackByDraft(f)
        if (!t || t.mute) return false
        var anySolo = studio.tracks.some(function (x) { return x.solo })
        return !anySolo || !!t.solo
    }
    // Un disco a una pista nueva (lo mismo que soltarlo en «Pista nueva»)
    function dropNew(fam, v) {
        if (!studio.engineOk) { studio.toast("Motor no disponible"); return false }
        var r = studio.call("addAudioPath", v.path, fam + " " + v.label)
        if (!r.ok) { studio.toast(r.error); return false }
        studio.addTrack(r.track)
        studio.toast(fam + " " + v.label + " en una pista nueva")
        return true
    }
    // Un disco sobre una pista: pide confirmación en el sitio (su audio se cambia)
    function askReplace(t, fam, v) { pending = { track: t, family: fam, variant: v } }
    function doReplace() {
        var p = pending; pending = null
        if (!p) return false
        var r = studio.call("setTrackAudio", p.track.id, p.variant.path, 0)
        if (!r.ok) { studio.toast(r.error); return false }
        root.lb.seq.replace(p.track.uid, { len: r.track.length_seconds || 0, peaks: r.track.peaks || [], aclips: studio.clipsOf(p.track.id) })
        studio.markDirty()
        studio.toast("«" + p.track.name + "» suena ahora con " + p.family + " " + p.variant.label)
        return true
    }
    // Editar una variante (X19): con los controles de verdad de su pista borrador (cadena de efectos del
    // motor, Inspector y editor de clips); no hay controles propios del laboratorio
    function edit(f) {
        var id = draftOf(f); if (id < 0) return false
        for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === id) { studio.selected = i; break }
        studio.rackTrack = id
        studio.goTo("fx"); studio.goTo("pista")
        studio.toast(f + ": edita su pista borrador con los efectos de abajo y el Inspector")
        return true
    }
    function newSession() {
        lb.create({ prompt: prompt.text, style: style.current, bpm: Math.round(studio.bpm), key: key.current,
                    beats: parseInt(beats.current), bars: parseInt(bars.current), variants: parseInt(nvar.current) })
    }
    onVisibleChanged: if (visible && lb) { lb.refresh(); lb.listSessions(); if (seq) seq.midiRefresh() }

    Rectangle { anchors.fill: parent; color: Theme.panelColor("ia", Theme.pc.ia) }

    // ================= izquierda: contexto y sesión =================
    Rectangle {
        id: left
        x: 8; y: 8; width: 250; height: parent.height - bottom.height - 24
        color: Theme.panelBody; radius: Theme.radius; border.width: 1; border.color: Theme.line
        Flickable {
            anchors.fill: parent; anchors.margins: 10
            contentHeight: lcol.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: lcol
                width: parent.width; spacing: 6
                Text { text: "CREAR IA"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; font.weight: 700; font.letterSpacing: 0.6 }
                Text { width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
                       text: root.st && root.ctx ? "Sesión «" + root.st.name + "» · " + root.ctx.style + " · " + root.ctx.bpm + " BPM · "
                                       + root.ctx.key + " · " + root.ctx.bars + " compases de " + root.ctx.beats
                                     : "Crea una sesión: la instrumental se arma por piezas, una fila por instrumento." }
                Text { topPadding: 6; text: "Descripción"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600 }
                Rectangle {
                    width: parent.width; height: 54; color: Theme.input; border.width: Theme.buttonBorder
                    border.color: prompt.activeFocus ? Theme.focus : Theme.line
                    TextEdit { id: prompt; anchors.fill: parent; anchors.margins: 6; wrapMode: TextEdit.Wrap; selectByMouse: true
                               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
                    Text { visible: !prompt.text; x: 6; y: 6; text: "Piano oscuro con 808…"; color: Theme.ink; opacity: 0.7
                           font.family: Theme.font; font.pixelSize: 12 }
                }
                Grid {
                    columns: 2; columnSpacing: 6; rowSpacing: 4; width: parent.width
                    Text { text: "Estilo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; width: 70 }
                    Select { id: style; width: lcol.width - 76; options: root.stat.styles || []; current: "Hip hop"; fontSize: 12; padY: 3
                             onPicked: function (v) { current = v } }
                    Text { text: "Tonalidad"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
                    Select { id: key; width: lcol.width - 76; options: root.stat.keys || []; current: "Auto"; fontSize: 12; padY: 3
                             onPicked: function (v) { current = v } }
                    Text { text: "Compases"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
                    Select { id: bars; width: lcol.width - 76; options: ["4", "8", "16"]; current: "8"; fontSize: 12; padY: 3
                             onPicked: function (v) { current = v } }
                    Text { text: "Compás"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
                    Select { id: beats; width: lcol.width - 76; options: [["3", "3/4"], ["4", "4/4"], ["6", "6/8"]]; current: "4"; fontSize: 12; padY: 3
                             onPicked: function (v) { current = v } }
                    Text { text: "Variantes"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
                    Select { id: nvar; width: lcol.width - 76; options: ["2", "3", "4", "6", "8"]; current: "4"; fontSize: 12; padY: 3
                             onPicked: function (v) { current = v } }
                }
                Text { width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 11
                       text: "Tempo: el del proyecto (" + Math.round(root.studio ? root.studio.bpm : 0) + " BPM)." }
                NeoButton { text: root.st ? "Nueva sesión" : "Crear sesión"; fontSize: 12; padY: 3; color: Theme.accent; textColor: Theme.inkOnAccent
                            confirm: root.st ? "¿Nueva? (la actual queda guardada)" : ""
                            tip: "Familias propuestas para el estilo; la sesión se guarda en la carpeta de datos"
                            onClicked: root.newSession() }
                Text { topPadding: 8; visible: (root.lb ? root.lb.sessions : []).length > 0; text: "Sesiones guardadas"
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600 }
                Select { visible: (root.lb ? root.lb.sessions : []).length > 0; width: parent.width; fontSize: 12; padY: 3
                         options: (root.lb ? root.lb.sessions : []).map(function (s) { return [s.folder, s.name + " · " + (s.created || "")] })
                         current: root.st ? root.st.folder : ""
                         tip: "Abrir otra sesión del laboratorio"
                         onPicked: function (v) { if (!root.st || v !== root.st.folder) root.lb.open(v) } }
                Text { topPadding: 8; visible: !!root.st; text: "Añadir familia"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600 }
                Select { visible: !!root.st; width: parent.width; fontSize: 12; padY: 3; current: ""
                         options: [["", "Elige un instrumento…"]].concat((root.stat.families || []).filter(function (f) {
                             return !root.families.some(function (x) { return x.name === f }) }))
                         onPicked: function (v) { if (v) root.lb.addFamily(v) } }
            }
        }
    }

    // ================= derecha: pistas del proyecto (destino de los discos) =================
    Rectangle {
        id: right
        anchors.right: parent.right; anchors.rightMargin: 8
        y: 8; width: 190; height: left.height
        color: Theme.panelBody; radius: Theme.radius; border.width: 1; border.color: Theme.line
        Column {
            x: 10; y: 10; width: parent.width - 20; spacing: 6
            Text { text: "PISTAS"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.6 }
            Text { width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 11
                   text: "Arrastra un disco aquí: a una pista (cambia su audio) o a una nueva." }
            Repeater {
                model: [{ id: -1, name: "＋ Pista nueva" }].concat(root.audioTracks)
                Rectangle {
                    id: slot
                    required property var modelData
                    objectName: "labSlot" + modelData.id
                    width: parent.width; height: 32; radius: Theme.radius
                    color: root.dragHover === modelData.id ? Theme.pressedBg : Theme.input
                    border.width: Theme.buttonBorder; border.color: root.dragHover === modelData.id ? Theme.focus : Theme.line
                    Text { x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
                           text: slot.modelData.name; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
                           color: root.dragHover === slot.modelData.id ? Theme.pressedInk : Theme.ink }
                    DropArea {
                        anchors.fill: parent; keys: ["afo-lab-disc"]
                        onEntered: root.dragHover = slot.modelData.id
                        onExited: if (root.dragHover === slot.modelData.id) root.dragHover = -2
                        onDropped: function (d) {
                            root.dragHover = -2
                            var s = d.source
                            if (slot.modelData.id < 0) root.dropNew(s.family, s.variant)
                            else root.askReplace(slot.modelData, s.family, s.variant)
                        }
                    }
                }
            }
        }
    }

    // ================= centro: familias y variantes =================
    Item {
        id: mid
        anchors { left: left.right; leftMargin: 8; right: right.left; rightMargin: 8; top: parent.top; topMargin: 8; bottom: bottom.top; bottomMargin: 8 }
        Column {
            visible: !root.st
            anchors.centerIn: parent; width: Math.min(parent.width - 20, 420); spacing: 8
            Text { width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 14
                   text: "Sin sesión abierta. Crea una a la izquierda o abre una guardada." }
        }
        Column {
            id: gen
            visible: !!root.st
            width: parent.width; spacing: 6
            Flow {
                width: parent.width; spacing: 6
                NeoButton { text: "Componer guía"; fontSize: 12; padY: 3; color: Theme.accent; textColor: Theme.inkOnAccent
                            opacity: root.stat.textOk ? 1 : 0.5
                            tip: root.stat.textOk ? "ACE-Step compone una canción guía y Demucs la separa: cada parte es la V1 de su familia (1–2 min)"
                                                  : "Falta el modelo de canciones de ACE-Step: descárgalo en Navegador › IA"
                            onClicked: if (root.stat.textOk && !root.lb.busy) root.lb.guideText() }
                NeoButton { text: "Desde el proyecto"; fontSize: 12; padY: 3
                            opacity: root.stat.demucsOk ? 1 : 0.5
                            tip: root.stat.demucsOk ? "Demucs separa la mezcla actual del proyecto: cada parte es la V1 de su familia"
                                                    : "Falta Demucs (separador) en esta instalación"
                            onClicked: if (root.stat.demucsOk && !root.lb.busy) root.lb.guideProject() }
                NeoButton { visible: root.lb && root.lb.busy; text: "Cancelar"; fontSize: 12; padY: 3; tip: "Detiene la generación en curso"
                            onClicked: root.lb.cancel() }
            }
            Rectangle {
                visible: root.lb && root.lb.busy
                width: parent.width; height: 8; color: Theme.input; border.width: 1; border.color: Theme.line
                Rectangle { x: 1; y: 1; height: 6; color: Theme.accent; width: (parent.width - 2) * Math.max(0, Math.min(1, root.lb ? root.lb.progress : 0)) }
            }
            Text { visible: !!(root.lb && root.lb.msg); width: parent.width; wrapMode: Text.Wrap; color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 12; text: root.lb ? root.lb.msg + (root.lb.family ? " · " + root.lb.family : "") : "" }
            Text { width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 11
                   text: root.seq && root.seq.composing ? root.seq.midiMsg + " · " + Math.round(root.seq.midiProgress * 100) + " %"
                         : "Variantes de audio (ACE-Step) y patrones MIDI editables por familia (MIDI-LLM, en tu equipo)." }
            Text { visible: !root.stat.legoOk; width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 11
                   text: "Para generar variantes (V2…) falta el modelo «partes» de ACE-Step: descárgalo en Navegador › IA." }
        }
        Flickable {
            visible: !!root.st
            anchors { left: parent.left; right: parent.right; top: gen.bottom; topMargin: 8; bottom: parent.bottom }
            contentHeight: rows.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: rows
                width: parent.width; spacing: 8
                Repeater {
                    model: root.families
                    Rectangle {
                        id: fam
                        required property var modelData
                        objectName: "labFamily"
                        readonly property color fc: root.famColor(modelData.name)
                        readonly property var draft: root.trackByDraft(modelData.name)
                        width: rows.width; height: fcol.implicitHeight + 16; radius: Theme.radius
                        color: Theme.panelBody; border.width: 1; border.color: Theme.line
                        Rectangle { width: 5; height: parent.height; radius: Theme.radius; color: fam.fc }
                        Column {
                            id: fcol
                            x: 14; y: 8; width: parent.width - 22; spacing: 6
                            Flow {
                                width: parent.width; spacing: 6
                                Text { text: fam.modelData.name; color: Theme.ink; font.family: Theme.font; font.pixelSize: 14; font.weight: 700
                                       height: 24; verticalAlignment: Text.AlignVCenter }
                                Text { text: fam.modelData.variants.length + " variante(s)"; color: Theme.ink; opacity: 0.85
                                       font.family: Theme.font; font.pixelSize: 11; height: 24; verticalAlignment: Text.AlignVCenter }
                                NeoButton { text: "+ Variante"; fontSize: 11; padX: 6; padY: 2; shadow: 2; opacity: root.stat.legoOk ? 1 : 0.5
                                            tip: "Genera una variante más de " + fam.modelData.name + " sobre el resto (ACE-Step, unos 10 s)"
                                            onClicked: if (root.stat.legoOk && !root.lb.busy) root.lb.generate(fam.modelData.name, 1) }
                                NeoButton { text: "Regenerar (" + (root.ctx ? root.ctx.variants : 4) + ")"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                                            opacity: root.stat.legoOk ? 1 : 0.5; confirm: "¿Regenerar?"
                                            tip: "Las no bloqueadas pasan al historial y salen " + (root.ctx ? root.ctx.variants : 4) + " nuevas"
                                            onClicked: if (root.stat.legoOk && !root.lb.busy) root.lb.regenerate(fam.modelData.name) }
                                NeoButton { objectName: "labPattern"
                                            readonly property bool can: !!(root.seq && root.seq.midiAi.engineOk && root.seq.midiAi.model && root.seq.midiAi.model.done)
                                            text: root.seq && root.seq.patternFamily === fam.modelData.name ? "Componiendo…" : "Patrón MIDI"
                                            fontSize: 11; padX: 6; padY: 2; shadow: 2; opacity: can ? 1 : 0.5
                                            tip: can ? "Compone un patrón MIDI de " + fam.modelData.name.toLowerCase() + " con el estilo, tonalidad y tempo de la sesión; entra como pista MIDI editable"
                                                     : "Falta el modelo MIDI: descárgalo en Navegador › IA"
                                            onClicked: if (can && !root.seq.composing) root.seq.labPattern(fam.modelData.name, root.ctx) }
                                NeoButton { text: "Referencia"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                                            pressedState: !!fam.modelData.reference
                                            color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                                            tip: "Siempre entra en el contexto de las demás generaciones"
                                            onClicked: root.lb.reference(fam.modelData.name, !fam.modelData.reference) }
                                NeoButton { visible: !!fam.draft; text: "S"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                                            pressedState: !!(fam.draft && fam.draft.solo)
                                            color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                                            tip: "Solo de esta familia en la preescucha"; onClicked: root.lb.soloFamily(fam.modelData.name) }
                                NeoButton { visible: !!fam.draft; text: "M"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                                            pressedState: !!(fam.draft && fam.draft.mute)
                                            color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                                            tip: "Silenciar esta familia en la preescucha"; onClicked: root.lb.muteFamily(fam.modelData.name) }
                                NeoButton { visible: !!fam.draft; text: "Editar"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                                            tip: "Elige su pista borrador: efectos nativos abajo, volumen y envíos en el Inspector, cortes y fundidos en el Arreglo"
                                            onClicked: root.edit(fam.modelData.name) }
                            }
                            Text { visible: !fam.modelData.variants.length; width: parent.width; wrapMode: Text.Wrap; color: Theme.ink
                                   font.family: Theme.font; font.pixelSize: 12
                                   text: "Aún sin variantes: «Componer guía» da la V1, o «+ Variante»." }
                            Flow {
                                width: parent.width; spacing: 10
                                Repeater {
                                    model: fam.modelData.variants
                                    Disc { family: fam.modelData.name; variant: modelData; fc: fam.fc; required property var modelData }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ================= abajo: preescucha =================
    Rectangle {
        id: bottom
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
        height: brow.implicitHeight + 16
        color: Theme.panelBody; radius: Theme.radius; border.width: 1; border.color: Theme.line
        Flow {
            id: brow
            x: 10; y: 8; width: parent.width - 20; spacing: 8
            NeoButton { text: root.lb && root.lb.previewing ? "Actualizar preescucha" : "Preescuchar"; fontSize: 12; padY: 3
                        color: Theme.accent; textColor: Theme.inkOnAccent; opacity: root.st ? 1 : 0.5
                        tip: "Una pista real «Lab (borrador)» por familia con la variante elegida, desde el compás 1"
                        onClicked: if (root.st) root.lb.preview() }
            NeoButton { text: root.studio && root.studio.playing ? "■ Parar" : "▶ Reproducir"; fontSize: 12; padY: 3
                        tip: "Reproducir / parar el proyecto (Espacio)"
                        onClicked: { var r = root.studio.call("togglePlay"); if (!r.ok) root.studio.toast(r.error) } }
            NeoButton { text: "Enviar al proyecto"; fontSize: 12; padY: 3; opacity: root.lb && root.lb.previewing ? 1 : 0.5
                        tip: "Las pistas borrador pasan a ser pistas normales del proyecto"
                        onClicked: if (root.lb.previewing) root.lb.send() }
            NeoButton { text: "Descartar"; fontSize: 12; padY: 3; opacity: root.lb && root.lb.previewing ? 1 : 0.5; confirm: "¿Descartar?"
                        tip: "Quita las pistas borrador del proyecto (las variantes siguen en la sesión)"
                        onClicked: if (root.lb.previewing) root.lb.discard() }
            Text { height: 28; verticalAlignment: Text.AlignVCenter; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
                   text: root.lb && root.lb.previewing ? Object.keys(root.lb.drafts).length + " pistas borrador en el proyecto" : "Sin preescucha" }
        }
    }

    // Confirmación en el sitio: cambiar el audio de una pista
    Rectangle {
        visible: !!root.pending
        anchors.horizontalCenter: parent.horizontalCenter; y: parent.height * 0.35
        width: Math.min(parent.width - 40, 460); height: pcol.implicitHeight + 24; radius: Theme.radius
        color: Theme.panelBody; border.width: 2; border.color: Theme.focus; z: 20
        Column {
            id: pcol
            x: 12; y: 12; width: parent.width - 24; spacing: 10
            Text { width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13
                   text: root.pending ? "¿Cambiar el audio de «" + root.pending.track.name + "» por " + root.pending.family + " "
                                        + root.pending.variant.label + "? Su audio actual deja de sonar en esa pista." : "" }
            Row {
                spacing: 8
                NeoButton { text: "Cambiar"; fontSize: 12; padY: 3; color: Theme.accent; textColor: Theme.inkOnAccent; onClicked: root.doReplace() }
                NeoButton { text: "Cancelar"; fontSize: 12; padY: 3; onClicked: root.pending = null }
            }
        }
    }

    // ---------------- un disco (una variante) ----------------
    component Disc: Column {
        id: dk
        property string family
        property var variant
        property color fc
        readonly property bool spin: root.sounding(family, variant)
        objectName: "labDisc"
        width: 96; spacing: 4
        Item {
            id: holder
            width: 96; height: 96
            Canvas {
                id: cv
                anchors.fill: parent
                readonly property var d: dk.variant.disc || ({ env: [], bands: [] })
                property color ink: Theme.ink
                property color col: dk.fc
                property bool on: !!dk.variant.chosen
                onDChanged: requestPaint(); onColChanged: requestPaint(); onOnChanged: requestPaint(); onInkChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d"); c.reset()
                    var w = width, cx = w / 2, cy = w / 2, R = w / 2 - 2
                    c.fillStyle = String(Theme.screen); c.beginPath(); c.arc(cx, cy, R, 0, 2 * Math.PI); c.fill()
                    // surcos: la envolvente de la variante, de fuera (principio) a dentro (final)
                    var env = d.env || [], n = env.length || 1
                    for (var i = 0; i < env.length; i++) {
                        var r = R - 3 - i * (R * 0.55 / n)
                        c.strokeStyle = Qt.rgba(col.r, col.g, col.b, 0.15 + 0.85 * env[i])
                        c.lineWidth = 0.6 + 1.2 * env[i]
                        c.beginPath(); c.arc(cx, cy, r, 0, 2 * Math.PI); c.stroke()
                    }
                    // anillo de bandas: graves → agudos alrededor de la etiqueta
                    var b = d.bands || [], mx = 1e-9
                    for (var k = 0; k < b.length; k++) mx = Math.max(mx, b[k])
                    for (k = 0; k < b.length; k++) {
                        var a0 = -Math.PI / 2 + k * 2 * Math.PI / b.length, a1 = a0 + 2 * Math.PI / b.length - 0.06
                        c.strokeStyle = Qt.rgba(col.r, col.g, col.b, 0.25 + 0.75 * b[k] / mx)
                        c.lineWidth = 2 + 6 * b[k] / mx
                        c.beginPath(); c.arc(cx, cy, R * 0.34, a0, a1); c.stroke()
                    }
                    c.fillStyle = on ? Qt.rgba(col.r, col.g, col.b, 1) : String(Theme.screenLine)
                    c.beginPath(); c.arc(cx, cy, R * 0.2, 0, 2 * Math.PI); c.fill()
                    c.fillStyle = String(Theme.line); c.beginPath(); c.arc(cx, cy, 2.5, 0, 2 * Math.PI); c.fill()
                }
                RotationAnimation on rotation { running: dk.spin; loops: Animation.Infinite; from: 0; to: 360; duration: 1800 }
            }
            Rectangle { anchors.fill: parent; radius: width / 2; color: "transparent"
                        border.width: dk.variant.chosen ? 3 : 0; border.color: Theme.focus }
            Text { anchors.right: parent.right; anchors.top: parent.top; visible: !!dk.variant.locked; text: "🔒"
                   font.family: "Segoe UI Symbol"; font.pixelSize: 13; color: Theme.ink }
            Drag.active: dma.drag.active
            Drag.keys: ["afo-lab-disc"]
            Drag.source: dk
            Drag.hotSpot.x: 48; Drag.hotSpot.y: 48
            HoverHandler { id: dh }
            ToolTipLite { show: dh.hovered && !dma.drag.active
                          text: "Clic: elegir · arrástralo a una pista · " + (dk.variant.disc ? dk.variant.disc.rms_db + " dB RMS" : "")
                                + (dk.variant.grid ? " · a tempo " + dk.variant.grid : "") }
            MouseArea {
                id: dma
                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                drag.target: holder; drag.threshold: 6
                onClicked: root.lb.choose(dk.family, dk.variant.id)
                onReleased: { if (drag.active) holder.Drag.drop(); holder.x = 0; holder.y = 0; root.dragHover = -2 }
            }
        }
        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; color: Theme.ink; font.family: Theme.font
               font.pixelSize: 12; font.weight: dk.variant.chosen ? 700 : 500
               text: dk.variant.label + (dk.variant.chosen ? " · elegida" : "") + (dk.variant.favorite ? " ★" : "") }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 2
            NeoButton { text: "🔒"; fontSize: 10; padX: 3; padY: 1; shadow: 1; pressedState: !!dk.variant.locked
                        color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                        tip: "Bloquear: se conserva al regenerar"; onClicked: root.lb.lock(dk.family, dk.variant.id, !dk.variant.locked) }
            NeoButton { text: "★"; fontSize: 10; padX: 3; padY: 1; shadow: 1; pressedState: !!dk.variant.favorite
                        color: pressedState ? Theme.pressedBg : Theme.button; textColor: pressedState ? Theme.pressedInk : Theme.ink
                        tip: "Favorita: sale en otras sesiones y proyectos"; onClicked: root.lb.favorite(dk.family, dk.variant.id, !dk.variant.favorite) }
            NeoButton { text: "≈"; fontSize: 10; padX: 3; padY: 1; shadow: 1; opacity: root.stat.textOk ? 1 : 0.5
                        tip: "Parecida a esta (ACE-Step cover: mismo carácter, otros detalles)"
                        onClicked: if (root.stat.textOk && !root.lb.busy) root.lb.similar(dk.family, dk.variant.id) }
            NeoButton { text: "✕"; fontSize: 10; padX: 3; padY: 1; shadow: 1; confirm: "¿Quitar?"
                        tip: "A la papelera de la sesión (pulsa otra vez para confirmar)"; onClicked: root.lb.remove(dk.family, dk.variant.id) }
        }
    }
}
