import QtQuick
import QtQuick.Shapes

// .empty de la plantilla: recuadro con borde discontinuo de 2 px.
Item {
    id: root
    property color strokeColor: Theme.ink
    property color fill: Theme.dark ? Qt.rgba(1, 1, 1, 0.05) : Qt.rgba(1, 1, 1, 0.4)
    property alias text: label.text
    property alias textFormat: label.textFormat
    property color textColor: Theme.ink
    implicitHeight: label.implicitHeight + 28
    Rectangle { anchors.fill: parent; color: root.fill }
    Shape {
        anchors.fill: parent
        ShapePath {
            strokeColor: root.strokeColor; strokeWidth: 2; fillColor: "transparent"
            strokeStyle: ShapePath.DashLine; dashPattern: [3, 2]; capStyle: ShapePath.FlatCap
            startX: 1; startY: 1
            PathLine { x: root.width - 1; y: 1 }
            PathLine { x: root.width - 1; y: root.height - 1 }
            PathLine { x: 1; y: root.height - 1 }
            PathLine { x: 1; y: 1 }
        }
    }
    Text {
        id: label
        x: 14; y: 14; width: root.width - 28
        wrapMode: Text.Wrap
        color: root.textColor
        font.family: Theme.font; font.pixelSize: 12; font.weight: 500
        lineHeight: 1.4
    }
}
