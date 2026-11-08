import QtQuick

// .panel de la plantilla: borde 3 px, sombra dura 7 px, rayado vertical, franja negra para mover,
// tornillos abajo y 8 cuadritos para cambiar ancho y alto.
Item {
    id: root
    property string pid
    property string title
    property string modelName
    property color accent: Theme.pc[pid] || "#ffffff"
    property real viewZ: 1                    // zoom del lienzo (para convertir el arrastre)
    property bool wood: pid === "inst" || pid === "drums" || pid === "piano"
    property bool autoHeight: false           // alto según el contenido mientras no se redimensione
    property real fixedHeight: 300
    property bool resized: false
    readonly property real minW: 240
    readonly property real minH: 190
    default property alias body: bodyContent.data
    property alias bodyWidth: bodyContent.width
    readonly property real headerHeight: head.height
    signal geometryEdited()
    signal editFinished()
    signal focusRequested()
    signal closeRequested()
    signal raiseRequested()

    height: autoHeight && !resized ? Math.max(minH, head.height + 12 + bodyContent.childrenRect.height + 30 + 6) : fixedHeight

    Rectangle {                                // sombra dura
        x: 7; y: 7; width: parent.width; height: parent.height
        color: Theme.panelShadow(root.accent)
    }
    Rectangle {
        id: face
        anchors.fill: parent
        color: Theme.panelColor(root.pid, root.accent)
        border.width: 3; border.color: Theme.line
        clip: true
        MouseArea { anchors.fill: parent }    // un clic en el módulo no arrastra el lienzo

        // rayado vertical 1 px cada 4 px + degradado de luz (repeating-linear-gradient + linear-gradient)
        Canvas {
            id: stripes
            anchors.fill: parent; anchors.margins: 3
            property bool dark: Theme.dark
            property bool darkBody: root.pid === "piano"
            onDarkChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var a = (dark || darkBody) ? (darkBody && !dark ? 0.05 : 0.035) : 0.22
                ctx.fillStyle = Qt.rgba(1, 1, 1, a)
                for (var x = -3; x < width; x += 4) ctx.fillRect(x, 0, 1, height)
                if (darkBody) return
                var g = ctx.createLinearGradient(0, -3, 0, height + 3)
                if (dark) { g.addColorStop(0, Qt.rgba(1, 1, 1, 0.05)); g.addColorStop(1, Qt.rgba(0, 0, 0, 0.2)) }
                else { g.addColorStop(0, Qt.rgba(1, 1, 1, 0.3)); g.addColorStop(1, Qt.rgba(0, 0, 0, 0.1)) }
                ctx.fillStyle = g
                ctx.fillRect(0, 0, width, height)
            }
        }
        // laterales de madera de Piano roll, Instrumentos y Batería
        Rectangle { visible: root.wood; x: 3; y: 3; width: 16; height: parent.height - 6; color: Theme.dark ? "#3b2616" : "#8a5a2b" }
        Rectangle { visible: root.wood; x: parent.width - 19; y: 3; width: 16; height: parent.height - 6; color: Theme.dark ? "#3b2616" : "#8a5a2b" }

        // .ph: franja negra para mover
        Rectangle {
            id: head
            x: 3; y: 3; width: parent.width - 6
            height: Math.round(Math.max(titleText.implicitHeight, focusBtn.height) + 16)
            color: "#000"
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.SizeAllCursor
                property point start
                property point orig
                onPressed: function (m) {
                    root.raiseRequested()
                    start = mapToGlobal(m.x, m.y); orig = Qt.point(root.x, root.y)
                }
                onPositionChanged: function (m) {
                    var p = mapToGlobal(m.x, m.y)
                    root.x = orig.x + (p.x - start.x) / root.viewZ
                    root.y = orig.y + (p.y - start.y) / root.viewZ
                    root.geometryEdited()
                }
                onReleased: root.editFinished()
            }
            Row {
                x: 12; spacing: 8
                width: parent.width - 24
                anchors.verticalCenter: parent.verticalCenter
                Item {                          // punto de color con brillo
                    width: 12; height: 12; anchors.verticalCenter: parent.verticalCenter
                    Rectangle { anchors.centerIn: parent; width: 22; height: 22; radius: 11; color: root.accent; opacity: 0.25 }
                    Rectangle { anchors.fill: parent; radius: 6; color: root.accent; border.width: 2; border.color: "#fff" }
                }
                Text {
                    id: titleText
                    text: root.title
                    color: root.accent
                    font.family: Theme.font; font.pixelSize: 17; font.weight: 700
                    width: parent.width - 12 - mdl.width - focusBtn.width - closeBtn.width - 4 * 8
                    elide: Text.ElideRight
                    anchors.verticalCenter: parent.verticalCenter
                }
                Rectangle {
                    id: mdl
                    width: mdlText.implicitWidth + 16; height: mdlText.implicitHeight + 4
                    color: Theme.mdl; border.width: 2; border.color: "#000"
                    anchors.verticalCenter: parent.verticalCenter
                    Text { id: mdlText; anchors.centerIn: parent; text: root.modelName; color: Theme.ink
                           font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                }
                NeoButton { id: focusBtn; text: "Enfocar"; fontSize: 12; padX: 8; padY: 2; anchors.verticalCenter: parent.verticalCenter
                            onClicked: root.focusRequested() }
                NeoButton { id: closeBtn; text: "✕"; fontSize: 12; padX: 8; padY: 2; anchors.verticalCenter: parent.verticalCenter
                            tip: "Quitar " + root.title; onClicked: root.closeRequested() }
            }
        }

        // .pb: cuerpo con desplazamiento propio
        Flickable {
            id: flick
            x: 3 + (root.wood ? 30 : 12)            // padding de .pb dentro del borde de 3 px
            y: head.y + head.height + 12
            width: parent.width - 2 * x
            height: parent.height - y - 30 - 3
            contentWidth: width
            contentHeight: bodyContent.childrenRect.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            Item { id: bodyContent; width: flick.width; height: childrenRect.height }
        }

        // tornillos
        Repeater {
            model: 2
            Rectangle {
                width: 14; height: 14; radius: 7
                x: index === 0 ? 3 + 8 : parent.width - 3 - 8 - 14
                y: parent.height - 3 - 7 - 14
                border.width: 2; border.color: "#000"
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#ffffff" }
                    GradientStop { position: 0.55; color: "#a8a8a8" }
                    GradientStop { position: 1.0; color: "#555555" }
                }
                Rectangle { anchors.centerIn: parent; width: 10; height: 1.6; rotation: -55; color: "#000" }
            }
        }
    }

    // cuadritos para redimensionar
    HoverHandler { id: hover }
    Repeater {
        model: ["nw", "n", "ne", "e", "se", "s", "sw", "w"]
        Rectangle {
            id: grip
            readonly property string side: modelData
            width: 16; height: 16
            x: side.indexOf("w") >= 0 ? -9 : side.indexOf("e") >= 0 ? root.width - 7 : root.width / 2 - 8
            y: side.indexOf("n") >= 0 ? -9 : side.indexOf("s") >= 0 ? root.height - 7 : root.height / 2 - 8
            z: 9
            color: hover.hovered || gm.containsMouse ? Theme.accent : Theme.grip
            opacity: hover.hovered || gm.containsMouse ? 1 : 0.8
            border.width: 3; border.color: "#000"
            Rectangle { x: 2; y: 2; z: -1; width: 16; height: 16; color: "#000" }
            MouseArea {
                id: gm
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: grip.side === "n" || grip.side === "s" ? Qt.SizeVerCursor
                           : grip.side === "e" || grip.side === "w" ? Qt.SizeHorCursor
                           : grip.side === "nw" || grip.side === "se" ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
                property point start
                property rect orig
                onPressed: function (m) {
                    root.raiseRequested()
                    start = mapToGlobal(m.x, m.y)
                    orig = Qt.rect(root.x, root.y, root.width, root.height)
                    root.fixedHeight = root.height
                    root.resized = true
                }
                onPositionChanged: function (m) {
                    var p = mapToGlobal(m.x, m.y), dx = (p.x - start.x) / root.viewZ, dy = (p.y - start.y) / root.viewZ
                    var s = grip.side, x = orig.x, y = orig.y, w = orig.width, h = orig.height
                    if (s.indexOf("w") >= 0) { w = Math.max(root.minW, orig.width - dx); x = orig.x + orig.width - w }
                    else if (s.indexOf("e") >= 0) w = Math.max(root.minW, orig.width + dx)
                    if (s.indexOf("n") >= 0) { h = Math.max(root.minH, orig.height - dy); y = orig.y + orig.height - h }
                    else if (s.indexOf("s") >= 0) h = Math.max(root.minH, orig.height + dy)
                    root.x = x; root.y = y; root.width = w; root.fixedHeight = h
                    root.geometryEdited()
                }
                onReleased: root.editFinished()
            }
        }
    }
}
