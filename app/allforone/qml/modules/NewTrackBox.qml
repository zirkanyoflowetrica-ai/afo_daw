import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"
import "../controls"

// Pista nueva (F5, FLUJO_PROFESIONAL §3), un solo diálogo como en Logic: Audio · Instrumento ·
// Batería · Voz · Intérprete IA · Generar con IA · Por piezas. Las tres de IA se piden aquí (antes
// eran Navegador › IA y la vista Crear IA): lo generado entra como pista y lo regenerado como toma
// nueva de esa pista. Se abre desde el menú Pista, «+ Pista» del Arreglo y el Navegador › Añadir.
B.Popup {
    id: root
    property var studio
    property string page: ""                   // "" (elegir) | interp | gen | lab
    readonly property var seq: studio ? studio.seq : null
    readonly property var regen: seq && seq.genUid ? seq.trackOf(seq.genUid) : null
    readonly property var kinds: [
        ["audio", "Audio", "Importa WAV, AIFF, FLAC, OGG o MP3 en una pista nueva", "audios"],
        ["inst", "Instrumento", "Pista MIDI con el sintetizador del motor o un VST3", "inst"],
        ["drum", "Batería", "Pads y patrón de 16 pasos", "drums"],
        ["voz", "Voz", "Pista para grabar voz (Cinta)", "cinta"],
        ["interp", "Intérprete IA", "La IA (MIDI-LLM, en tu equipo) escribe las notas: pistas de instrumento normales, editables en el piano roll", "ia"],
        ["gen", "Generar con IA", "Canción o parte en audio con ACE-Step, en tu equipo. Lo regenerado entra como toma nueva de su pista", "ia"],
        ["lab", "Por piezas", "Instrumental por familias (batería, bajo…) con variantes; cada familia es una pista y sus variantes, tomas", "ia"]]
    function openFor(p) {
        page = p || ""
        if (page === "interp") seq.iaMode = "midi"
        if (page === "gen") seq.iaMode = "song"
        if (page === "lab" && studio.lab) { studio.lab.refresh(); studio.lab.listSessions() }
        if (page !== "gen") seq.genUid = ""
        open()
    }
    function pick(k) {
        if (k === "audio") { close(); studio.runAction("track.newAudio") }
        else if (k === "inst") { close(); studio.runAction("track.newInst") }
        else if (k === "drum") { close(); studio.runAction("track.newDrum") }
        else if (k === "voz") { close(); studio.runAction("track.newVoice") }
        else openFor(k)
    }
    onClosed: if (seq && !seq.generating) seq.genUid = ""

    modal: false
    focus: true
    readonly property real maxH: (parent ? parent.height : 800) - 110
    width: Math.min(page === "lab" ? 1220 : 640, (parent ? parent.width : 900) - 40)
    height: page === "" ? implicitHeight : maxH
    x: ((parent ? parent.width : 900) - width) / 2
    y: 60
    padding: 14
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    contentItem: Item {
        implicitHeight: col.implicitHeight
        Column {
            id: col
            width: parent.width
            spacing: 10
            Row {
                width: parent.width; spacing: 8
                Text { text: root.regen ? "Regenerar · " + root.regen.name : "Pista nueva"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 16; font.weight: 800; anchors.verticalCenter: parent.verticalCenter }
                Item { width: 1; height: 1 }
            }
            Flow {
                width: parent.width; spacing: 6
                Repeater {
                    model: root.kinds
                    NeoButton {
                        required property var modelData
                        objectName: "newTrack_" + modelData[0]
                        readonly property bool on: root.page === modelData[0]
                        text: modelData[1]; fontSize: 13; padX: 10; padY: 5
                        color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                        tip: modelData[2]
                        onClicked: root.pick(modelData[0])
                    }
                }
            }
            Text {
                objectName: "newTrackWhere"
                width: parent.width; wrapMode: Text.Wrap
                color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
                text: root.regen ? "El resultado entra como toma nueva de «" + root.regen.name + "»: la anterior sigue en sus tomas (cabecera de la pista) y Ctrl+Z la quita."
                      : root.page === "interp" ? "Las notas entran como pistas de instrumento y batería normales: se editan en el piano roll y suenan con tus sonidos."
                      : root.page === "gen" ? "La canción o la parte entra como pista de audio. «Regenerar» (Inspector o clic derecho de la pista) pone otra versión como toma de esa misma pista."
                      : root.page === "lab" ? "Cada familia es una pista borrador; elegir otra variante cambia el audio de esa misma pista. «Enviar al proyecto» las deja como pistas normales."
                      : "Elige qué pista crear. Las de IA se generan en tu equipo, sin internet."
            }
        }
        Flickable {
            id: fl
            visible: root.page === "interp" || root.page === "gen"
            anchors { top: col.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom }
            clip: true
            contentHeight: iaBody.height
            boundsBehavior: Flickable.StopAtBounds
            B.ScrollBar.vertical: B.ScrollBar { policy: B.ScrollBar.AsNeeded }
            IaBody { id: iaBody; objectName: "newTrackIa"; width: fl.width - 14; seq: root.seq; showModes: false }
        }
        LabView {
            id: labView
            objectName: "labView"
            visible: root.page === "lab" && root.opened
            studio: root.studio
            anchors { top: col.bottom; topMargin: 10; left: parent.left; right: parent.right; bottom: parent.bottom }
        }
    }
}
