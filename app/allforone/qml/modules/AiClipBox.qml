import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"
import "../controls"

// IA sobre el clip (F4, FLUJO_PROFESIONAL §3), desde el clic derecho del clip o la paleta: un cuadro
// junto al clip en vez de botones fijos en la barra del Arreglo. Dice dónde quedará el resultado:
// «Rehacer» y «Alinear» dejan una toma nueva en la misma pista; «Versión» va a la carpeta de la original.
B.Popup {
    id: root
    property var studio
    property string mode: "repaint"           // repaint | cover | align
    property string uid: ""
    readonly property var seq: studio ? studio.seq : null
    readonly property var arr: studio ? studio.arrangeView : null
    readonly property var trk: seq && uid ? seq.trackOf(uid) : null
    readonly property var clp: arr ? arr.selInfo : null
    readonly property var titles: ({ repaint: "Rehacer con IA", cover: "Versión con IA", align: "Alinear a la guía" })
    readonly property var where: ({
        repaint: "El trozo del clip se vuelve a tocar con el mismo estilo (acótalo antes con «Dividir»). Entra como toma nueva de esta pista: la anterior sigue en sus tomas (cabecera de la pista) y Ctrl+Z la quita.",
        cover: "La IA toca el clip a su manera. Va a una pista nueva dentro de la carpeta de la original, en el mismo sitio; el original no cambia.",
        align: "Ajusta el tiempo de la pista a la guía sin cambiar el tono (doblajes, coros). Entra como toma nueva; la original sigue en sus tomas." })
    function openFor(m, u) { mode = m; uid = u; open(); if (m === "repaint") Qt.callLater(function () { promptIn.forceActiveFocus() }) }
    function run() {
        if (!seq || !trk) return
        if (mode === "repaint") seq.repaintClip(uid, clp, promptIn.text.trim())
        else if (mode === "cover") seq.coverClip(uid, clp)
        else seq.alignTrack(uid, arr.alignGuide ? arr.alignGuide.uid : "")
        close()
    }
    readonly property bool can: !!trk && !!clp && !!seq && (mode === "align" ? !!arr.alignGuide && !seq.alignUid : !seq.generating)

    modal: false
    focus: true
    width: 440
    x: ((parent ? parent.width : 800) - width) / 2
    y: 90
    padding: 14
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    contentItem: Column {
        spacing: 10
        Text {
            width: parent.width; elide: Text.ElideRight
            text: (root.titles[root.mode] || "") + " · " + (root.trk ? root.trk.name : "")
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; font.weight: 800
        }
        Text {
            objectName: "aiClipWhere"
            width: parent.width; wrapMode: Text.Wrap
            color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
            text: root.where[root.mode] || ""
        }
        // Rehacer: qué cambiar (opcional)
        Rectangle {
            visible: root.mode === "repaint"
            width: parent.width; height: 32; color: Theme.input; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
            TextInput {
                id: promptIn
                objectName: "aiClipPrompt"
                x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter
                color: Theme.ink; selectByMouse: true; clip: true; font.family: Theme.font; font.pixelSize: 13
                onAccepted: if (root.can) root.run()
                Text { visible: !promptIn.text; text: "Qué cambiar (opcional): «más suave», «sin batería»…"
                       color: Theme.inkDim; font: promptIn.font }
            }
        }
        // Versión: parecida o libre, y estilo
        Row {
            visible: root.mode === "cover"
            spacing: 8
            Select { objectName: "coverMode"; width: 120; options: ["Parecida", "Libre"]
                     current: root.seq ? root.seq.coverOpts.mode : ""
                     tip: "Parecida: guarda melodía y timbre. Libre: solo la forma; suena más distinta"
                     onPicked: function (v) { root.seq.coverOpts = Object.assign({}, root.seq.coverOpts, { mode: v }) } }
            Select { objectName: "coverStyle"; width: 150
                     options: root.seq && root.seq.ai.styles && root.seq.ai.styles.length ? root.seq.ai.styles : ["Libre"]
                     current: root.seq ? root.seq.coverOpts.style : ""
                     tip: "Estilo de la versión («Libre»: el mismo que el original)"
                     onPicked: function (v) { root.seq.coverOpts = Object.assign({}, root.seq.coverOpts, { style: v }) } }
        }
        // Alinear: guía y fuerza
        Row {
            visible: root.mode === "align"
            spacing: 8
            Select { objectName: "alignGuide"; width: 220
                     options: root.arr && root.arr.alignGuides.length ? root.arr.alignGuides.map(function (t) { return "con " + t.name }) : ["(falta otra pista de audio)"]
                     current: root.arr && root.arr.alignGuide ? "con " + root.arr.alignGuide.name : "(falta otra pista de audio)"
                     tip: "Pista guía: la voz que lleva el tiempo bueno"
                     onPicked: function (v) {
                         var g = root.arr.alignGuides.filter(function (t) { return "con " + t.name === v })
                         if (g.length) root.seq.alignOpts = Object.assign({}, root.seq.alignOpts, { guide: g[0].uid })
                     } }
            Select { objectName: "alignStrength"; width: 90; options: ["100 %", "75 %", "50 %"]
                     current: root.seq ? root.seq.alignOpts.strength + " %" : ""
                     tip: "Fuerza: 100 % la deja en el tiempo de la guía; menos, la acerca y conserva algo de su soltura"
                     onPicked: function (v) { root.seq.alignOpts = Object.assign({}, root.seq.alignOpts, { strength: parseInt(v) }) } }
        }
        Text {
            visible: !root.clp
            width: parent.width; wrapMode: Text.Wrap
            color: Theme.recInk; font.family: Theme.font; font.pixelSize: 12
            text: "Elige antes un clip de audio en el Arreglo"
        }
        Row {
            spacing: 6
            NeoButton { objectName: "aiClipRun"; enabled: root.can
                        text: root.mode === "repaint" ? "Rehacer" : root.mode === "cover" ? "Hacer versión" : "Alinear"
                        tip: root.mode === "repaint" ? "Rehacer el trozo (Intro)" : root.mode === "cover" ? "Hacer la versión" : "Alinear a la guía"
                        onClicked: root.run() }
            NeoButton { text: "Cerrar"; tip: "Cerrar (Esc)"; onClicked: root.close() }
        }
    }
}
