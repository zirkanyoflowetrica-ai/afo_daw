import QtQuick
import "../theme"

// Barra de estado fija (docs/GUIA_DISENO_INTERFAZ.md §1): qué dispositivo suena y con qué latencia,
// qué proyecto está abierto y si tiene cambios sin guardar, una ayuda corta y el zoom.
// Sin salida de audio lo dice en rojo, con icono y texto (no solo color), y un clic abre «⚙ Audio».
Rectangle {
    id: root
    property var studio
    readonly property var dev: studio.deviceInfo || {}
    readonly property bool noAudio: studio.engineOk && !dev.open
    height: 28
    color: Theme.header
    Rectangle { width: parent.width; height: Math.max(1, Theme.border > 1 ? 2 : 1); color: Theme.line }

    Row {
        id: left
        x: 12; height: parent.height; spacing: 16
        Rectangle {                                  // dispositivo de audio
            id: devBox
            anchors.verticalCenter: parent.verticalCenter
            width: devRow.width + 16; height: 22; radius: Theme.radius
            color: root.noAudio ? "#b3261e" : devMouse.containsMouse ? Theme.pn2 : "transparent"
            Row {
                id: devRow
                x: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                Rectangle { width: 9; height: 9; radius: 4.5; anchors.verticalCenter: parent.verticalCenter
                            color: root.noAudio ? "#ffffff" : !root.studio.engineOk ? "#888888" : "#2fbf71"
                            border.width: 1; border.color: root.noAudio ? "#ffffff" : Theme.line }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: !root.studio.engineOk ? "Motor de audio no disponible"
                          : root.noAudio ? "⚠ Sin salida de audio: clic para elegir un dispositivo"
                          : root.dev.type + " · " + root.dev.output + " · " + (root.dev.sample_rate / 1000).toFixed(1) + " kHz · "
                            + root.dev.buffer_size + " muestras · " + root.studio.latencyMs.toFixed(1) + " ms"
                    color: root.noAudio ? "#ffffff" : Theme.ink
                    font.family: Theme.font; font.pixelSize: 12; font.weight: root.noAudio ? 700 : 600
                    elide: Text.ElideRight; width: Math.min(implicitWidth, root.width * 0.42)
                }
            }
            MouseArea { id: devMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: root.studio.openAudioSettings() }
        }
        Text {                                       // proyecto y cambios sin guardar
            anchors.verticalCenter: parent.verticalCenter
            text: (root.studio.project.name || "Sin título") + (root.studio.dirty ? "  ● cambios sin guardar (Ctrl+S)" : "  ✓ guardado")
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
            visible: root.studio.engineOk
        }
        Text {                                       // IA local trabajando (generación o descarga de modelos)
            readonly property var sq: root.studio.seq
            anchors.verticalCenter: parent.verticalCenter
            visible: !!sq && (sq.generating || sq.downloading || sq.splitting)
            text: !sq ? "" : sq.splitting ? "● Dividiendo en pistas " + Math.round(sq.splitProgress * 100) + " %"
                 : sq.generating ? "● IA generando " + Math.round(sq.aiProgress * 100) + " %"
                                         : "● IA descargando modelos " + Math.round(sq.dlProgress * 100) + " %"
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700
        }
    }
    Text {                                           // ayuda corta de la vista
        anchors.verticalCenter: parent.verticalCenter
        x: left.x + left.width + 24; width: zoomText.x - x - 16
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideRight
        text: root.studio.view === "arrange"
              ? "Clic en la regla o un clip: mover el cursor · en una curva: clic añade punto, clic derecho lo borra · R/T/L/W: automatización · Ctrl+rueda: zoom · Tab: Mezclador"
              : "Clic en una tira: su cadena en Efectos · Tab: Arreglo · Ctrl+B / Ctrl+I / Ctrl+E: plegar navegador, inspector y detalle"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }
    Text {
        id: zoomText
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: parent.right; anchors.rightMargin: 12
        text: root.studio.view === "arrange" ? root.studio.arrangeView.pps.toFixed(0) + " px/s" : "Mezclador"
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
    }
}
