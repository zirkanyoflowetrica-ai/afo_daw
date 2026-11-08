import QtQuick

// Equivalente al atributo title del HTML: aparece tras una pausa con el ratón encima.
Item {
    id: root
    property string text: ""
    property bool show: false
    anchors.fill: parent
    z: 1000
    Timer { id: delay; interval: 700; onTriggered: tip.visible = true }
    onShowChanged: { if (show) delay.restart(); else { delay.stop(); tip.visible = false } }
    Rectangle {
        id: tip
        visible: false
        x: 0; y: parent.height + 6
        width: Math.min(360, t.implicitWidth + 12); height: t.implicitHeight + 8
        color: "#ffffe8"; border.color: "#000"; border.width: 1
        Text {
            id: t; x: 6; y: 4; width: Math.min(348, implicitWidth)
            text: root.text; wrapMode: Text.Wrap
            font.family: Theme.font; font.pixelSize: 12; color: "#000"
        }
    }
}
