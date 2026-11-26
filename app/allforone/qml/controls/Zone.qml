import QtQuick
import "../theme"

// Zona fija de la ventana (docs/DISENO_DAW.md §2): cabecera con pestañas y botón de plegar, y debajo
// la página elegida. Las páginas (ZonePage) son hijas de la zona y existen siempre: plegar o cambiar
// de pestaña solo las oculta (los módulos siguen conectados y conservan su estado).
Rectangle {
    id: root
    property string title
    property var tabs: []                     // [[id, nombre, tooltip], ...]
    property string current: tabs.length ? tabs[0][0] : ""
    property bool folded: false
    property string foldTip: ""               // «Plegar el navegador (Ctrl+B)»…
    property bool vertical: false             // plegada, la zona queda como franja vertical (lados) u horizontal (abajo)
    property var extra: null                  // componente opcional a la derecha de la cabecera
    readonly property real headH: 34
    readonly property color titleInk: Theme.headInk(Theme.pc.pistas)   // par título/cabecera medido por el selftest
    default property alias pages: body.data
    signal picked(string id)
    color: Theme.panelColor("", Theme.sidebar)
    clip: true
    border.width: 0

    Rectangle {                               // separación con las zonas vecinas
        anchors.fill: parent; color: "transparent"; border.width: Math.max(1, Theme.border); border.color: Theme.line; z: 5
    }

    // cabecera
    Rectangle {
        id: head
        width: parent.width; height: root.folded && root.vertical ? parent.height : root.headH
        color: Theme.panelHead
        Rectangle { y: parent.height - 1; width: parent.width; height: 1; color: Theme.line; visible: !(root.folded && root.vertical) }
        Text {                                // plegada a un lado: el título en vertical
            visible: root.folded && root.vertical
            anchors.centerIn: parent; rotation: -90
            text: root.title.toUpperCase(); color: root.titleInk
            font.family: Theme.font; font.pixelSize: 12; font.weight: 700; font.letterSpacing: 1
        }
        Row {
            id: tabRow
            visible: !(root.folded && root.vertical)
            x: 6; height: parent.height; spacing: 2
            // F12: si las pestañas no caben (zona estrecha), todas se estrechan por igual y recortan el
            // nombre; el tooltip lo da entero
            readonly property real natW: {
                var s = 0
                for (var i = 0; i < tabRep.count; i++) { var it = tabRep.itemAt(i); if (it) s += it.nat + spacing }
                return s
            }
            readonly property real availW: head.width - 6 - (extraLd.item && extraLd.visible ? extraLd.width + 6 : 0) - 38
            readonly property real k: natW > availW && natW > 0 ? Math.max(0.3, availW / natW) : 1
            Repeater {
                id: tabRep
                model: root.tabs
                Rectangle {
                    id: tb
                    required property var modelData
                    readonly property real nat: tl.implicitWidth + 18
                    readonly property bool on: root.current === modelData[0] && !root.folded
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(24, Math.floor(nat * tabRow.k)); height: 26; radius: Theme.radius
                    // elegida: color de acento (texto negro); las demás, como el chip del modelo
                    color: on ? Theme.accent : Theme.chip
                    border.color: th.hovered && !on ? Theme.accent : Theme.line
                    border.width: 1
                    Text { id: tl; anchors.centerIn: parent; text: tb.modelData[1]
                           width: Math.min(implicitWidth, tb.width - 8); elide: Text.ElideRight
                           color: tb.on ? Theme.inkOnAccent : Theme.chipInk
                           font.family: Theme.font; font.pixelSize: 12; font.weight: tb.on ? 700 : 600 }
                    HoverHandler { id: th }
                    ToolTipLite { text: (tl.truncated ? tb.modelData[1] + ": " : "") + (tb.modelData[2] || ""); show: th.hovered && text.length > 0 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: { root.current = tb.modelData[0]; root.folded = false; root.picked(tb.modelData[0]) } }
                }
            }
        }
        Loader {
            id: extraLd
            visible: !root.folded
            anchors { right: foldBtn.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
            sourceComponent: root.extra
        }
        Rectangle {
            id: foldBtn
            anchors { right: parent.right; rightMargin: root.folded && root.vertical ? (parent.width - width) / 2 : 6 }
            y: root.folded && root.vertical ? 6 : (root.headH - height) / 2
            width: 26; height: 26; radius: Theme.radius
            color: Theme.chip; border.width: 1; border.color: fh.hovered ? Theme.accent : Theme.line
            Text { anchors.centerIn: parent; text: root.folded ? "+" : "−"; color: Theme.chipInk
                   font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
            HoverHandler { id: fh }
            ToolTipLite { text: root.foldTip; show: fh.hovered && text.length > 0 }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.folded = !root.folded }
        }
    }

    Item {
        id: body
        y: head.height
        width: parent.width; height: parent.height - y
        visible: !root.folded
    }
}
