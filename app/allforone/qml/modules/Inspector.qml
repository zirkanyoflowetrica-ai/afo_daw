import QtQuick
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Inspector › Pista (X17, DISENO_DAW §2): los ajustes de la pista elegida en el Arreglo o el Mezclador:
// volumen, paneo, Solo / Mute, rol de voz para la Mezcla IA, envíos a los buses Aux y su cadena de
// efectos. Lo mismo que la tira del Mezclador, pero de una sola pista y siempre a la vista.
Column {
    id: root
    property var studio
    property var mixer
    property bool shown: true
    width: parent ? parent.width : 400
    spacing: 8

    readonly property var track: studio && studio.selected >= 0 && studio.selected < studio.tracks.length ? studio.tracks[studio.selected] : null
    readonly property int tid: track ? track.id : -1
    readonly property bool live: tid > 0
    readonly property color cc: track ? (Theme.pc[studio.seqSrc(track.type)] || Theme.pc.pistas) : Theme.pc.pistas
    readonly property var auxes: (studio ? studio.tracks : []).filter(function (t) { return t.type === "aux" && t.id > 0 && t.id !== root.tid })
    property var sends: []                       // [{aux, db, pre}] del motor
    readonly property var chain: { if (!mixer || !live) return []; var l = mixer.live[tid]; return l ? (l.chain || []) : [] }

    function reload() {
        if (!studio || !studio.engineOk || tid <= 0) { sends = []; return }
        var r = studio.call("sendList", tid)
        sends = r.ok ? r.sends : []
    }
    function sendOf(auxId) { for (var i = 0; i < sends.length; i++) if (sends[i].aux === auxId) return sends[i]; return null }
    function setSend(auxId, db, pre) {
        var r = studio.call("sendSet", tid, auxId, db, pre)
        if (!r.ok) { studio.toast(r.error); return }
        sends = r.sends; studio.dirty = true
    }
    function sendDb(pos) { return pos <= 0.02 ? -100 : -48 + 54 * pos / 100 }
    function sendPos(db) { return db <= -99 ? 0 : Math.max(3, Math.min(100, (db + 48) / 54 * 100)) }
    onTidChanged: reload()
    onShownChanged: if (shown) reload()

    Text {
        visible: !root.track; width: root.width; wrapMode: Text.Wrap
        text: "Elige una pista en el Arreglo o en el Mezclador: aquí salen su volumen, paneo, envíos y efectos."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 13
    }

    // ---------------- cabecera de la pista ----------------
    Rectangle {
        visible: !!root.track
        width: root.width; height: 40; radius: Theme.radius
        color: Theme.chip; border.width: Theme.buttonBorder; border.color: Theme.line
        Rectangle { width: 6; height: parent.height; radius: Theme.radius; color: root.cc }
        Text { x: 14; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
               text: root.track ? root.track.name : ""; color: Theme.chipInk
               font.family: Theme.font; font.pixelSize: 16; font.weight: 700 }
    }
    // F5: lo hecho con «Generar con IA» se regenera aquí; la versión nueva entra como toma de la pista
    Row {
        visible: !!root.track && !!root.track.gen
        spacing: 8
        NeoButton { objectName: "inspRegen"; text: root.studio && root.studio.seq.genUid ? "Regenerando…" : "Regenerar con IA"
                    fontSize: 12; padY: 3; enabled: !!root.studio && !root.studio.seq.generating
                    tip: "Otra versión con el mismo texto y estilo; entra como toma nueva de esta pista (las anteriores siguen en sus tomas)"
                    onClicked: root.studio.seq.regenerate(root.track.uid) }
        NeoButton { text: "Ajustes…"; fontSize: 12; padY: 3; enabled: !!root.studio && !root.studio.seq.generating
                    tip: "Cambiar el texto, el estilo o la duración antes de regenerar"
                    onClicked: { root.studio.seq.draftIa = Object.assign({}, root.studio.seq.draftIa, root.track.gen.cfg || {})
                                 root.studio.newTrack("gen"); root.studio.seq.genUid = root.track.uid } }
    }
    Text {
        visible: !!root.track && !root.live; width: root.width; wrapMode: Text.Wrap
        text: "Esta pista aún no está en el motor (no tiene sonido): no se puede mezclar todavía."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
    }

    // ---------------- volumen, paneo, solo y mute ----------------
    Row {
        visible: root.live
        spacing: 18
        Column {
            spacing: 4
            Fader { objectName: "inspVol"; height: 120; value: root.track && root.track.vol !== undefined ? root.track.vol : 70
                    tip: "Volumen de " + (root.track ? root.track.name : "")
                    onMoved: function (v) { root.studio.setTrackMixUid(root.track.uid, v, root.track.pan) }
                    onReleased: root.studio.trackRelease(root.track.uid) }
            Text { text: MD.faderDbText(root.track && root.track.vol !== undefined ? root.track.vol : 70); color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
        }
        Column {
            spacing: 10
            Knob { label: "Paneo"; value: root.track && root.track.pan !== undefined ? root.track.pan : 50
                   tip: "Paneo: izquierda ↔ derecha (doble clic al centro)"
                   onMoved: function (v) { root.studio.setTrackMixUid(root.track.uid, root.track.vol, v) }
                   onReleased: root.studio.trackRelease(root.track.uid) }
            Row {
                spacing: 6
                NeoButton { text: "Solo"; fontSize: 12; padX: 8; padY: 3; shadow: 2
                            readonly property bool on: !!(root.track && root.track.solo)
                            color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                            tip: "Escuchar solo esta pista"; onClicked: root.studio.toggleTrackFlag(root.track.uid, "solo") }
                NeoButton { text: "Mute"; fontSize: 12; padX: 8; padY: 3; shadow: 2
                            readonly property bool on: !!(root.track && root.track.mute)
                            color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                            tip: "Silenciar esta pista"; onClicked: root.studio.toggleTrackFlag(root.track.uid, "mute") }
            }
            Column {
                spacing: 4
                Text { text: "Rol de voz (Mezcla IA)"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600 }
                Select { width: 120; options: MD.ROLES; current: root.mixer ? root.mixer.roleOfTrack(root.tid) : "—"; tip: MD.roleTip()
                         onPicked: function (v) { root.mixer.setTrackRole(root.tid, v) } }
            }
        }
    }

    // ---------------- envíos ----------------
    Text { visible: root.live; topPadding: 6; text: "Envíos a buses Aux"; color: Theme.ink
           font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
    Text {
        visible: root.live && !root.auxes.length; width: root.width; wrapMode: Text.Wrap
        text: "No hay buses Aux. Crea uno en el Mezclador («+ AUX») para mandar reverb o delay compartidos."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
    }
    Repeater {
        model: root.live ? root.auxes : []
        Row {
            id: sr
            required property var modelData
            readonly property var s: root.sendOf(modelData.id)
            spacing: 10
            Knob { label: sr.modelData.name; value: sr.s ? root.sendPos(sr.s.db) : 0
                   tip: "Envío a " + sr.modelData.name + (sr.s ? ": " + sr.s.db.toFixed(1) + " dB" : ": apagado")
                   onMoved: function (v) { root.setSend(sr.modelData.id, root.sendDb(v), sr.s ? sr.s.pre : false) } }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 4
                Text { text: sr.s ? sr.s.db.toFixed(1) + " dB" : "apagado"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                NeoButton { visible: !!sr.s; text: sr.s && sr.s.pre ? "Pre-fader" : "Post-fader"; fontSize: 11; padX: 6; padY: 2; shadow: 2
                            tip: "Pre: el envío no sigue al fader de la pista. Post: sí"
                            onClicked: root.setSend(sr.modelData.id, sr.s.db, !sr.s.pre) }
            }
        }
    }

    // ---------------- efectos ----------------
    Text { visible: root.live; topPadding: 6; text: "Efectos"; color: Theme.ink
           font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
    Text {
        visible: root.live; width: root.width; wrapMode: Text.Wrap
        text: root.chain.length ? root.chain.join(" → ") : "Sin efectos. Añádelos desde el Navegador › Efectos."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
    }
    NeoButton { visible: root.live; text: "Ver la cadena abajo"; fontSize: 12; padY: 3
                tip: "Abre la cadena de efectos de la pista en el panel de detalle"
                onClicked: { root.studio.rackTrack = root.tid; root.studio.goTo("fx") } }
}
