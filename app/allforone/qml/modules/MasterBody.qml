import QtQuick
import "../theme"
import "../controls"

// Módulo Rebobinado (Cinta M-2): aquí llegan los masters. Cada master automático (Efectos master →
// Masterizar automáticamente) o manual (Mastering → Guardar versión) queda como una cinta: clic para
// ponerla en el master y escucharla, y Exportar saca el WAV con esa versión.
Column {
    id: root
    property var studio
    property var mixer
    readonly property var vs: mixer.versions
    readonly property var cur: mixer.versionSel >= 0 ? vs[mixer.versionSel] : null
    width: parent ? parent.width : 400
    spacing: 8

    function f(v) { return v === null || v === undefined || v <= -99 ? "—" : (+v).toFixed(1) }

    // ---------------- pletina: dos carretes y la versión que suena ----------------
    Rectangle {
        width: root.width; height: 118
        color: "#2b2720"; border.width: 3; border.color: "#000"
        Row {
            anchors.centerIn: parent; spacing: 18
            Reel { spinning: root.studio.playing && !!root.cur }
            Column {
                spacing: 6; anchors.verticalCenter: parent.verticalCenter
                width: root.width - 2 * 76 - 2 * 18 - 30
                Lcd { width: parent.width; fontSize: 14; padX: 8
                      text: root.cur ? root.cur.name : "SIN VERSIÓN" }
                Text { width: parent.width; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter
                       text: root.cur ? root.f(root.cur.lufs) + " LUFS · pico " + root.f(root.cur.peak) + " dB" : "masteriza para llenar la cinta"
                       color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
            }
            Reel { spinning: root.studio.playing && !!root.cur }
        }
    }

    Text { text: "VERSIONES DE MASTER (" + root.vs.length + ")"; color: Theme.ink
           font.family: Theme.font; font.pixelSize: 12; font.weight: 700; font.letterSpacing: 0.5 }

    DashedBox {
        visible: root.vs.length === 0; width: root.width; height: visible ? implicitHeight : 0
        text: "Aún no hay versiones. En «Efectos master» pulsa Masterizar automáticamente, o ajusta el master a mano y pulsa «Guardar versión» en Mastering."
    }

    Repeater {
        model: root.vs
        Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool on: root.mixer.versionSel === index
            width: root.width; height: 50
            color: on ? Theme.accent : Theme.button
            border.width: 2; border.color: "#000"
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: root.mixer.loadVersion(row.index) }
            Rectangle {                            // piloto
                x: 10; anchors.verticalCenter: parent.verticalCenter
                width: 12; height: 12; radius: 6; border.width: 2; border.color: "#000"
                color: row.on ? "#ff4d3d" : "#4a1d1a"
            }
            Column {
                x: 32; anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 32 - tag.width - del.width - 30
                Text { id: nm; width: parent.width; elide: Text.ElideRight; text: row.modelData.name; visible: !ed.visible
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                       MouseArea { anchors.fill: parent; onClicked: root.mixer.loadVersion(row.index)
                                   onDoubleClicked: { ed.text = row.modelData.name; ed.visible = true; ed.forceActiveFocus(); ed.selectAll() } } }
                TextInput { id: ed; visible: false; width: parent.width; selectByMouse: true; color: Theme.ink
                            font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                            onAccepted: { visible = false; if (text.trim().length) root.mixer.renameVersion(row.index, text.trim()) }
                            onActiveFocusChanged: if (!activeFocus && visible) accepted() }
                Text { width: parent.width; elide: Text.ElideRight
                       text: root.f(row.modelData.lufs) + " LUFS · pico " + root.f(row.modelData.peak) + " dB · " + row.modelData.chain.length + " efecto(s) · " + row.modelData.at
                       color: Theme.ink; opacity: 0.75; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
            }
            Rectangle {
                id: tag
                anchors.right: del.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                width: tagText.implicitWidth + 12; height: 20
                color: row.modelData.kind === "auto" ? "#ff9f45" : "#7ad6ff"; border.width: 2; border.color: "#000"
                Text { id: tagText; anchors.centerIn: parent; text: row.modelData.kind === "auto" ? "AUTO" : "MANUAL"; color: "#000"
                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
            }
            NeoButton { id: del; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        text: "✕"; fontSize: 11; padX: 6; padY: 1; shadow: 2; tip: "Borrar esta versión"
                        onClicked: root.mixer.removeVersion(row.index) }
        }
    }

    NeoButton {
        width: root.width; text: root.cur ? "EXPORTAR «" + root.cur.name + "»" : "EXPORTAR (master tal como está)"
        fontSize: 14; fontWeight: 700; padY: 9; shadow: 4; color: "#ff9f45"; textColor: "#000"
        tip: "WAV de toda la sesión con la versión elegida en el master"
        onClicked: root.mixer.versionSel >= 0 ? root.mixer.exportVersion(root.mixer.versionSel) : root.studio.exportMix()
    }
    Note {
        width: root.width
        text: "Clic en una versión: se carga en el master y suena al reproducir (compáralas). Doble clic en el nombre para renombrarla. Las versiones se guardan con el proyecto."
    }

    component Reel: Rectangle {
        property bool spinning: false
        width: 76; height: 76; radius: 38
        color: "#f3e7c4"; border.width: 3; border.color: "#000"
        anchors.verticalCenter: parent ? parent.verticalCenter : undefined
        Item {
            anchors.fill: parent
            RotationAnimator on rotation { from: 0; to: 360; duration: 2400; loops: Animation.Infinite; running: spinning }
            Repeater {
                model: 3
                Rectangle { required property int index
                            x: 38 - 4; y: 8; width: 8; height: 22; radius: 3; color: "#000"
                            transform: Rotation { origin.x: 4; origin.y: 30; angle: index * 120 } }
            }
            Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: "#000" }
        }
    }
}
