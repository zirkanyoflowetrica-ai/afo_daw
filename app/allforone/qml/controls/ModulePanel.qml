import QtQuick
import "../theme"

// Módulo del lienzo: marco grueso del color del módulo, cabecera negra para moverlo (con su nombre,
// modelo, maximizar y quitar), cuerpo claro con desplazamiento propio y cuadritos para cambiar ancho
// y alto. Los módulos chocan entre sí: `mover`/`sizer` (de Main) recortan el movimiento.
Item {
    id: root
    property string pid
    property string title
    property string modelName
    property color accent: Theme.pc[pid] || "#ffffff"
    property real viewZ: 1                    // zoom del lienzo (para convertir el arrastre)
    property bool autoHeight: false           // alto según el contenido mientras no se redimensione
    property real fixedHeight: 300
    property bool resized: false
    property bool maximized: false
    property var mover: null                  // function(panel, x, y) → {x, y} sin chocar
    property var sizer: null                  // function(panel, {x, y, w, h}) → rect sin chocar
    readonly property real minW: 240
    readonly property real minH: 190
    readonly property int frame: 9            // grosor del marco de color
    default property alias body: bodyContent.data
    property alias bodyWidth: bodyContent.width
    readonly property real headerHeight: head.height
    signal geometryEdited()
    signal editFinished()
    signal focusRequested()
    signal closeRequested()
    signal raiseRequested()
    signal maximizeRequested()
    signal renamed(string name)

    height: autoHeight && !resized ? Math.max(minH, frame + head.height + 12 + bodyContent.childrenRect.height + 16 + frame + 3)
                                   : fixedHeight

    Rectangle {                                // sombra dura
        x: 7; y: 7; width: parent.width; height: parent.height
        color: Theme.panelShadow(root.accent)
    }
    Rectangle {                                // marco de color
        id: face
        anchors.fill: parent
        color: root.accent
        border.width: 3; border.color: Theme.line
        MouseArea { anchors.fill: parent }    // un clic en el módulo no arrastra el lienzo

        // cabecera negra: arrastrar mueve el módulo, doble clic en el nombre lo renombra
        Rectangle {
            id: head
            x: root.frame; y: root.frame; width: parent.width - 2 * root.frame
            height: 44
            color: "#000"
            MouseArea {
                anchors.fill: parent
                enabled: !root.maximized
                cursorShape: root.maximized ? Qt.ArrowCursor : Qt.SizeAllCursor
                property point start
                property point orig
                onPressed: function (m) {
                    root.raiseRequested()
                    start = mapToGlobal(m.x, m.y); orig = Qt.point(root.x, root.y)
                }
                onPositionChanged: function (m) {
                    var p = mapToGlobal(m.x, m.y)
                    var x = orig.x + (p.x - start.x) / root.viewZ, y = orig.y + (p.y - start.y) / root.viewZ
                    var q = root.mover ? root.mover(root, x, y) : { x: x, y: y }
                    root.x = q.x; root.y = q.y
                    root.geometryEdited()
                }
                onReleased: root.editFinished()
                onDoubleClicked: root.maximizeRequested()
            }
            Row {
                x: 14; spacing: 10
                width: parent.width - 22
                anchors.verticalCenter: parent.verticalCenter
                Rectangle { width: 14; height: 14; radius: 7; color: root.accent; anchors.verticalCenter: parent.verticalCenter }
                Item {
                    id: titleBox
                    width: parent.width - 14 - mdl.width - maxBtn.width - closeBtn.width - 4 * 10
                    height: titleText.implicitHeight
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        id: titleText
                        visible: !nameEdit.visible
                        width: parent.width
                        text: root.title.toUpperCase()
                        color: root.accent
                        font.family: Theme.font; font.pixelSize: 19; font.weight: 700; font.letterSpacing: 0.6
                        elide: Text.ElideRight
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: root.maximized ? Qt.ArrowCursor : Qt.SizeAllCursor
                            propagateComposedEvents: true
                            onPressed: function (m) { m.accepted = false }
                            onDoubleClicked: { nameEdit.text = root.title; nameEdit.visible = true; nameEdit.forceActiveFocus(); nameEdit.selectAll() }
                        }
                    }
                    TextInput {
                        id: nameEdit
                        visible: false
                        width: parent.width
                        color: "#fff"; selectByMouse: true; clip: true
                        font.family: Theme.font; font.pixelSize: 17; font.weight: 700
                        onAccepted: { visible = false; if (text.trim().length) root.renamed(text.trim()) }
                        onActiveFocusChanged: if (!activeFocus && visible) accepted()
                        Keys.onEscapePressed: visible = false
                        Rectangle { anchors.fill: parent; anchors.margins: -3; z: -1; color: "#222"; border.width: 1; border.color: root.accent }
                    }
                }
                Rectangle {
                    id: mdl
                    width: mdlText.implicitWidth + 18; height: 28
                    color: "#fff"; border.width: 2; border.color: "#000"
                    anchors.verticalCenter: parent.verticalCenter
                    Text { id: mdlText; anchors.centerIn: parent; text: root.modelName.toUpperCase(); color: "#000"
                           font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                }
                HeadButton { id: maxBtn; glyph: root.maximized ? "❐" : "□"
                             tip: root.maximized ? "Volver al lienzo" : "Maximizar: este módulo ocupa toda la ventana"
                             onClicked: root.maximizeRequested() }
                HeadButton { id: closeBtn; glyph: "✕"; tip: "Quitar " + root.title + " del lienzo (vuelve desde el menú)"
                             onClicked: root.closeRequested() }
            }
        }

        // cuerpo claro con desplazamiento propio
        Rectangle {
            id: inner
            x: root.frame; y: head.y + head.height
            width: parent.width - 2 * root.frame
            height: parent.height - y - root.frame
            color: Theme.panelColor(root.pid, root.accent)
            border.width: 3; border.color: Theme.line
            Flickable {
                id: flick
                x: 14; y: 12
                width: parent.width - 28
                height: parent.height - y - 14
                contentWidth: width
                contentHeight: bodyContent.childrenRect.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                interactive: contentHeight > height
                Item { id: bodyContent; width: flick.width; height: childrenRect.height }
            }
            Rectangle {                        // barra de desplazamiento cuando el contenido no cabe
                visible: flick.contentHeight > flick.height + 1
                x: parent.width - 8; width: 4; radius: 2
                y: flick.y + flick.visibleArea.yPosition * flick.height
                height: Math.max(24, flick.visibleArea.heightRatio * flick.height)
                color: Theme.ink; opacity: 0.35
            }
        }
    }

    component HeadButton: Rectangle {
        id: hb
        property string glyph
        property string tip
        signal clicked()
        width: 28; height: 28
        color: hbm.containsMouse ? Theme.accent : "#fff"
        border.width: 2; border.color: "#000"
        anchors.verticalCenter: parent ? parent.verticalCenter : undefined
        Text { anchors.centerIn: parent; text: hb.glyph; color: "#000"
               font.family: "Segoe UI Symbol"; font.pixelSize: 15; font.weight: 700 }
        MouseArea { id: hbm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: hb.clicked() }
        ToolTipLite { text: hb.tip; show: hbm.containsMouse }
    }

    // cuadritos para redimensionar (al pasar el ratón; no con la vista muy alejada ni maximizado)
    HoverHandler { id: hover }
    Repeater {
        model: ["nw", "n", "ne", "e", "se", "s", "sw", "w"]
        Rectangle {
            id: grip
            readonly property string side: modelData
            visible: root.viewZ >= 0.45 && !root.maximized && (hover.hovered || gm.pressed)
            width: 14; height: 14
            x: side.indexOf("w") >= 0 ? -7 : side.indexOf("e") >= 0 ? root.width - 7 : root.width / 2 - 7
            y: side.indexOf("n") >= 0 ? -7 : side.indexOf("s") >= 0 ? root.height - 7 : root.height / 2 - 7
            z: 9
            color: gm.containsMouse || gm.pressed ? Theme.accent : "#fff"
            border.width: 2; border.color: "#000"
            MouseArea {
                id: gm
                anchors.fill: parent
                anchors.margins: -4
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
                    var r = root.sizer ? root.sizer(root, { x: x, y: y, w: w, h: h }) : { x: x, y: y, w: w, h: h }
                    root.x = r.x; root.y = r.y; root.width = r.w; root.fixedHeight = r.h
                    root.geometryEdited()
                }
                onReleased: root.editFinished()
            }
        }
    }
}
