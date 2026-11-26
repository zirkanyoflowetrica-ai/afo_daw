import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"
import "../controls"

// Tempo y tonalidad de un audio (F11), desde el clic derecho del clip: lo que detectó el análisis (se
// puede corregir a mano) y las cuatro órdenes: el audio al tempo o al tono del proyecto, o el proyecto
// al tempo o al tono del audio. Estirar y transponer los hace el motor (SoundTouch); Ctrl+Z deshace.
B.Popup {
    id: root
    property var studio
    property string uid: ""
    readonly property var trk: studio && uid ? studio.seq.trackOf(uid) : null
    readonly property var info: studio && uid ? (studio.audioInfo[uid] || null) : null
    readonly property var clp: studio ? studio.arrangeView.selInfo : null
    readonly property bool busy: !!info && !!info.busy
    function openFor(u) { uid = u; open() }

    modal: false
    focus: true
    width: 430
    x: ((parent ? parent.width : 800) - width) / 2
    y: 90
    padding: 14
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    contentItem: Column {
        spacing: 10
        Text {
            width: parent.width; elide: Text.ElideRight
            text: "Tempo y tonalidad · " + (root.trk ? root.trk.name : "")
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 15; font.weight: 800
        }
        Text {
            width: parent.width; wrapMode: Text.Wrap
            color: root.info && root.info.error ? Theme.recInk : Theme.inkDim
            font.family: Theme.font; font.pixelSize: 12
            text: root.busy ? "Analizando el audio…"
                  : root.info && root.info.error ? root.info.error
                  : root.info ? "Detectado" + (root.info.sure ? "" : " (dudoso: corrígelo si no es así)")
                  : "Sin analizar"
        }
        Row {
            spacing: 8
            Text { width: 70; text: "Audio"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600
                   anchors.verticalCenter: parent.verticalCenter }
            Rectangle {
                width: 74; height: 30; color: Theme.input; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
                TextInput {
                    objectName: "tkBpm"
                    x: 6; width: parent.width - 12; anchors.verticalCenter: parent.verticalCenter
                    text: root.info && root.info.bpm ? String(root.info.bpm) : ""
                    color: Theme.ink; selectByMouse: true; font.family: Theme.font; font.pixelSize: 14
                    validator: DoubleValidator { bottom: 30; top: 300; decimals: 2; notation: DoubleValidator.StandardNotation }
                    onEditingFinished: { var v = parseFloat(text); if (v >= 30 && v <= 300) root.studio.setAudioTempo(root.uid, v) }
                }
            }
            Text { text: "BPM"; color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
            Select {
                objectName: "tkKey"
                width: 140; anchors.verticalCenter: parent.verticalCenter
                options: root.studio ? root.studio.keyOptions : []
                current: root.info && root.info.key ? root.info.key + "|" + root.info.scale : ""
                tip: "Tonalidad del audio (corrígela si el análisis se equivocó)"
                onPicked: function (v) { var p = v.split("|"); root.studio.setAudioKey(root.uid, p[0], p[1] || "") }
            }
        }
        Row {
            spacing: 8
            Text { width: 70; text: "Proyecto"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Text {
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 13
                text: root.studio ? root.studio.bpm + " BPM · " + root.studio.keyLabel(root.studio.songKey.key, root.studio.songKey.scale) : ""
            }
        }
        Text {
            visible: !!root.clp && ((root.clp.speed || 1) !== 1 || (root.clp.semitones || 0) !== 0)
            color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
            text: root.clp ? "El clip suena al " + Math.round((root.clp.speed || 1) * 1000) / 10 + " % de velocidad, "
                              + ((root.clp.semitones || 0) > 0 ? "+" : "") + (root.clp.semitones || 0) + " semitonos" : ""
        }
        Grid {
            columns: 2; spacing: 6
            NeoButton { objectName: "tkToProjectTempo"; text: "Audio → tempo del proyecto"; enabled: !root.busy
                        tip: "Estira el clip para que vaya al tempo del proyecto sin cambiar su tono"
                        onClicked: root.studio.runAction("clip.toProjectTempo") }
            NeoButton { objectName: "tkProjectToTempo"; text: "Proyecto → tempo del audio"; enabled: !root.busy
                        tip: "Pone el proyecto al tempo del audio; el clip vuelve a su velocidad original"
                        onClicked: root.studio.runAction("clip.projectToTempo") }
            NeoButton { objectName: "tkToProjectKey"; text: "Audio → tono del proyecto"; enabled: !root.busy
                        tip: "Transpone el clip a la tonalidad del proyecto sin cambiar su tempo"
                        onClicked: root.studio.runAction("clip.toProjectKey") }
            NeoButton { objectName: "tkProjectToKey"; text: "Proyecto → tono del audio"; enabled: !root.busy
                        tip: "Transpone el resto del proyecto (audio e instrumentos, no la batería) a la tonalidad del audio"
                        onClicked: root.studio.runAction("clip.projectToKey") }
        }
        Row {
            spacing: 6
            NeoButton { text: "Volver a analizar"; enabled: !root.busy; tip: "Vuelve a medir el tempo y la tonalidad del clip"
                        onClicked: root.studio.analyzeClip("clip.tempoKey") }
            NeoButton { text: "Original"; enabled: !!root.clp && ((root.clp.speed || 1) !== 1 || (root.clp.semitones || 0) !== 0)
                        tip: "El clip vuelve a su tempo y su tono"
                        onClicked: root.studio.runAction("clip.original") }
            NeoButton { text: "Cerrar"; onClicked: root.close() }
        }
    }
}
