import QtQuick
import "../theme"

// Marca «IA» (F6): lo que puso o decide la IA (efectos de la mezcla automática, Master IA, órdenes de
// IA) lleva esta etiqueta pequeña, siempre la misma; los controles en sí son los normales.
Rectangle {
    id: root
    property string tip: "Lo puso la IA; puedes cambiarlo como cualquier otro"
    property int size: 11
    width: t.implicitWidth + 8; height: size + 7; radius: 2
    color: Theme.knobArc
    Text { id: t; anchors.centerIn: parent; text: "IA"; color: Theme.inkOnColor
           font.family: Theme.font; font.pixelSize: root.size; font.weight: 800 }
    MouseArea { id: m; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
    ToolTipLite { text: root.tip; show: m.containsMouse && root.tip.length > 0 }
}
