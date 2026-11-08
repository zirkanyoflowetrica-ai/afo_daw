import QtQuick

// input[type=range] vertical de la plantilla (.fad): riel negro de 8 px y tirador 30×18 con raya.
Item {
    id: root
    property real value: 70                    // 0..100 (70 = 0 dB)
    property string tip: ""
    signal moved(real value)
    width: 32
    height: 150

    readonly property real travel: height - 18
    function setValue(v) {
        v = Math.round(Math.max(0, Math.min(100, v)))
        if (v !== value) { value = v; moved(v) }
    }

    Rectangle { x: 12; width: 8; height: parent.height; color: "#000" }
    Item {
        id: thumb
        x: 1; width: 30; height: 18
        y: root.travel * (1 - root.value / 100)
        Rectangle { x: 3; y: 3; width: 30; height: 18; color: "#000" }
        Rectangle {
            width: 30; height: 18; color: "#eeeeee"; border.width: 3; border.color: "#000"
            Rectangle { x: 3; y: 7.5; width: 24; height: 3; color: "#000" }
        }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        function at(y) { return 100 * (1 - (y - 9) / root.travel) }
        onPressed: function (m) { root.forceActiveFocus(); root.setValue(at(m.y)) }
        onPositionChanged: function (m) { if (pressed) root.setValue(at(m.y)) }
        onWheel: function (w) { root.setValue(root.value + (w.angleDelta.y > 0 ? 1 : -1)); w.accepted = true }
    }
    activeFocusOnTab: true
    Keys.onUpPressed: setValue(value + 1)
    Keys.onDownPressed: setValue(value - 1)
    ToolTipLite { text: root.tip; show: ma.containsMouse && !ma.pressed && root.tip.length > 0 }
}
