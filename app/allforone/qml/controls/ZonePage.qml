import QtQuick
import "../theme"

// Página de una zona: el cuerpo de un módulo con desplazamiento propio. Se ve cuando su zona tiene
// elegida esta pestaña; si no, se oculta (sigue existiendo). `minWidth`: ancho por debajo del cual
// el cuerpo no se aprieta y se desplaza en horizontal.
Item {
    id: root
    property string zid
    property real minWidth: 300
    property string tint: ""                  // color de módulo para el fondo (Theme.panelColor)
    readonly property var zone: parent ? parent.parent : null
    readonly property bool shown: !!zone && zone.current === zid && !zone.folded
    default property alias body: content.data
    anchors.fill: parent
    visible: shown

    Rectangle { anchors.fill: parent; color: Theme.panelColor(root.tint, Theme.pc[root.tint] || Theme.sidebar) }
    Flickable {
        id: flick
        x: 12; y: 10
        width: parent.width - 24; height: parent.height - 20
        contentWidth: content.width
        contentHeight: content.childrenRect.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height + 1 || contentWidth > width + 1
        Item { id: content; width: Math.max(flick.width, root.minWidth); height: childrenRect.height }
    }
    Rectangle {
        visible: flick.contentHeight > flick.height + 1
        x: parent.width - 7; width: 4; radius: 2
        y: flick.y + flick.visibleArea.yPosition * flick.height
        height: Math.max(24, flick.visibleArea.heightRatio * flick.height)
        color: Theme.ink; opacity: 0.35
    }
    Rectangle {
        visible: flick.contentWidth > flick.width + 1
        y: parent.height - 7; height: 4; radius: 2
        x: flick.x + flick.visibleArea.xPosition * flick.width
        width: Math.max(24, flick.visibleArea.widthRatio * flick.width)
        color: Theme.ink; opacity: 0.35
    }
}
