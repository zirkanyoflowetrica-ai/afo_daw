import QtQuick
import QtQuick.Shapes

// .knob de la plantilla: 46 px, metal cónico, centro negro, indicador rojo; -135° a +135°.
// Arrastrar en vertical (0,8 por píxel) o flechas del teclado (±5).
Column {
    id: root
    property real value: 50                    // 0..100
    property string label: ""
    property string tip: ""
    property color labelColor: Theme.ink
    signal moved(real value)
    spacing: 4
    width: Math.max(46, lbl.implicitWidth)

    function setValue(v) {
        v = Math.max(0, Math.min(100, v))
        if (v !== value) { value = v; moved(v) }
    }

    Item {
        id: dial
        width: 46; height: 46
        anchors.horizontalCenter: parent.horizontalCenter
        activeFocusOnTab: true
        Keys.onUpPressed: root.setValue(root.value + 5)
        Keys.onRightPressed: root.setValue(root.value + 5)
        Keys.onDownPressed: root.setValue(root.value - 5)
        Keys.onLeftPressed: root.setValue(root.value - 5)
        Rectangle { x: 3; y: 3; width: 46; height: 46; radius: 23; color: "#000" }
        Item {
            anchors.fill: parent
            rotation: -135 + root.value * 2.7
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: "#000"; strokeWidth: 3
                    fillGradient: ConicalGradient {
                        centerX: 23; centerY: 23; angle: 90
                        GradientStop { position: 0.0; color: "#5a5a5a" }
                        GradientStop { position: 0.25; color: "#e6e6e6" }
                        GradientStop { position: 0.5; color: "#6a6a6a" }
                        GradientStop { position: 0.75; color: "#d4d4d4" }
                        GradientStop { position: 1.0; color: "#5a5a5a" }
                    }
                    PathAngleArc { centerX: 23; centerY: 23; radiusX: 21.5; radiusY: 21.5; startAngle: 0; sweepAngle: 360 }
                }
            }
            Rectangle { x: 12; y: 12; width: 22; height: 22; radius: 11; color: "#222"; border.width: 2; border.color: "#000" }
            Rectangle { x: 20.5; y: 5; width: 5; height: 13; radius: 2; color: "#ff4d3d"; border.width: 1; border.color: "#000" }
        }
        Rectangle { anchors.fill: parent; anchors.margins: -5; radius: 28; color: "transparent"
                    border.width: 3; border.color: Theme.focus; visible: dial.activeFocus }
        MouseArea {
            id: drag
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SizeVerCursor
            property real y0
            property real v0
            onPressed: function (m) { y0 = mapToGlobal(m.x, m.y).y; v0 = root.value; dial.forceActiveFocus() }
            onPositionChanged: function (m) { if (pressed) root.setValue(v0 + (y0 - mapToGlobal(m.x, m.y).y) * 0.8) }
        }
        ToolTipLite { text: root.tip; show: drag.containsMouse && !drag.pressed && root.tip.length > 0 }
    }
    Text {
        id: lbl
        anchors.horizontalCenter: parent.horizontalCenter
        text: root.label
        color: root.labelColor
        font.family: Theme.font; font.pixelSize: 11; font.weight: 600
    }
}
