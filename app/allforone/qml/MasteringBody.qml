import QtQuick

// Módulo Master IA (Master M-4): los 4 masters del V4.2 (+ según referencia) con LUFS, true peak y
// limitación medidos; escucha A (sin master) / B (master) en el motor, enviar a Pistas, ZIP y carpeta.
Column {
    id: root
    property var mixer
    readonly property var res: mixer.currentRun ? mixer.currentRun.masters || {} : {}
    readonly property var names: mixer.data.masters.concat(["Según referencia"])
    readonly property var cur: res[names[mixer.masterSel]]
    width: parent ? parent.width : 400
    spacing: 0

    function need() { if (!mixer.currentRun) { mixer.studio.toast("Todavía no hay una mezcla terminada."); return false } return true }

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: lufs; text: root.cur ? (+root.cur.lufs).toFixed(1) + " LUFS" : "-- LUFS"; anchors.verticalCenter: parent.verticalCenter }
        Text {
            width: root.width - lufs.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
            text: "Masters adaptativos del V4.2: priorizan evitar clipping y exceso de limitación. Se informa el resultado real."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
        }
    }

    Column {                                    // .afo-presets
        width: root.width; spacing: 6; bottomPadding: 10
        Repeater {
            model: root.names
            Item {
                id: pr
                required property string modelData
                required property int index
                readonly property var st: root.res[modelData]
                readonly property bool on: root.mixer.masterSel === index
                readonly property bool disabled: index === 4 && !st
                width: root.width - 3; height: prCol.height + 12 + 4
                opacity: disabled ? 0.5 : 1
                Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: "#000"; visible: !pm.pressed }
                Rectangle {
                    x: pm.pressed ? 3 : 0; y: pm.pressed ? 3 : 0
                    width: parent.width; height: parent.height
                    color: "#2b2720"; border.width: 2; border.color: "#000"
                    Rectangle {                      // piloto
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: 12; height: 12; radius: 6; border.width: 2; border.color: "#000"
                        color: pr.on ? "#ff4d3d" : "#4a1d1a"
                        Rectangle { anchors.centerIn: parent; width: 22; height: 22; radius: 11; color: "#ff4d3d"; opacity: 0.25; visible: pr.on; z: -1 }
                    }
                    Column {
                        id: prCol
                        x: 36; y: 6; width: parent.width - 36 - prLcd.width - 18
                        Text { width: parent.width; elide: Text.ElideRight; text: pr.modelData
                               color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                        Text { width: parent.width; elide: Text.ElideRight
                               text: pr.st ? (+pr.st.lufs).toFixed(1) + " LUFS · " + (+pr.st.true_peak).toFixed(2) + " dBTP · limitación " + (+(pr.st.max_reduction_db || 0)).toFixed(1) + " dB"
                                           : (pr.index === 4 ? "requiere referencia" : "pendiente de mezcla")
                               color: "#bdb398"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                    }
                    Lcd { id: prLcd; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                          text: pr.st ? (+pr.st.lufs).toFixed(1) : "--.-"; fontSize: 12; padX: 6; padY: 1; spacing: 0.04 }
                }
                MouseArea { id: pm; anchors.fill: parent; enabled: !pr.disabled; cursorShape: Qt.PointingHandCursor
                            onClicked: root.mixer.masterSel = pr.index }
            }
        }
    }

    Row {                                       // .afo-ab
        width: root.width; spacing: 6; topPadding: 8; bottomPadding: 8 + 3
        Repeater {
            model: [["A", "A · sin master"], ["B", "B · master"]]
            NeoButton {
                required property var modelData
                readonly property bool on: root.mixer.masterAb === modelData[0]
                width: (root.width - 6) / 2 - 1; text: modelData[1]; fontWeight: 700
                color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                onClicked: if (root.need()) root.mixer.listen("master", modelData[0])
            }
        }
    }
    Flow {                                      // .tb
        width: root.width; spacing: 6
        NeoButton { text: "→ Enviar a Pistas"; onClicked: if (root.need()) root.mixer.sendMasterToTracks() }
        NeoButton { text: "Exportar sesión ZIP"; onClicked: if (root.need()) root.mixer.exportZip() }
        NeoButton { text: "Abrir carpeta"; onClicked: if (root.need()) root.mixer.openFolder() }
    }
}
