import QtQuick
import "../theme"

// .lcd de la plantilla: fondo #120f0a, cifras en Theme.lcd con brillo, borde 3 px y filete interior.
Rectangle {
    id: root
    property string text: ""
    property int fontSize: 18
    property int padX: 10
    property int padY: 2
    property real spacing: 0.08
    implicitWidth: t.implicitWidth + 2 * padX + 6
    implicitHeight: Math.round(fontSize * 1.4 + 2 * padY + 6)
    width: implicitWidth
    height: implicitHeight
    color: "#120f0a"
    border.width: Math.max(1, Theme.border); border.color: Theme.line; radius: Theme.radius
    Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: Theme.buttonBorder; border.color: "#3a3020"; visible: Theme.border > 1 }
    Text { anchors.centerIn: parent; text: t.text; font: t.font; color: Theme.lcd; opacity: 0.4; scale: 1.05 }
    Text {
        id: t
        anchors.centerIn: parent
        text: root.text
        color: Theme.lcd
        font.family: Theme.font; font.pixelSize: root.fontSize; font.weight: 700
        font.letterSpacing: root.fontSize * root.spacing
    }
}
