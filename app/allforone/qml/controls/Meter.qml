import QtQuick
import "../theme"

// .meter de la plantilla: barra vertical verde → ámbar → rojo, con segmentos de 7 px.
Rectangle {
    id: root
    property real level: 0                     // 0..100 (escala -60..0 dBFS)
    width: 12
    height: 150
    color: "#120f0a"
    border.width: 2; border.color: "#000"
    clip: true
    Rectangle {
        x: 2; width: parent.width - 4
        height: (parent.height - 4) * Math.max(0, Math.min(100, root.level)) / 100
        y: parent.height - 2 - height
        gradient: Gradient {
            // de abajo (#5ee0b0 hasta el 70 %) a arriba (#ff7a70)
            GradientStop { position: 0.0; color: "#ff7a70" }
            GradientStop { position: 0.15; color: "#ffc233" }
            GradientStop { position: 0.30; color: "#5ee0b0" }
            GradientStop { position: 1.0; color: "#5ee0b0" }
        }
    }
    Column {                                   // separación entre segmentos
        x: 2; width: parent.width - 4
        anchors.bottom: parent.bottom; anchors.bottomMargin: 2
        spacing: 5
        Repeater {
            model: Math.max(0, Math.ceil((root.height - 4) / 7))
            Rectangle { width: parent.width; height: 2; color: "#120f0a" }
        }
    }
}
