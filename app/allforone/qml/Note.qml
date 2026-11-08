import QtQuick

// .afo-note: recuadro claro con borde 2 px, texto con saltos de línea y desplazamiento propio.
Rectangle {
    id: root
    property string text: ""
    property int maxHeight: 120
    height: Math.min(maxHeight, t.implicitHeight + 16 + 4)
    color: Theme.dark ? Qt.rgba(0, 0, 0, 0.3) : Qt.rgba(1, 1, 1, 0.55)
    border.width: 2; border.color: "#000"
    Flickable {
        x: 2; y: 2; width: parent.width - 4; height: parent.height - 4
        contentHeight: t.implicitHeight + 16; clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        Text {
            id: t
            x: 8; y: 8; width: parent.width - 16
            text: root.text; wrapMode: Text.Wrap
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
        }
    }
}
