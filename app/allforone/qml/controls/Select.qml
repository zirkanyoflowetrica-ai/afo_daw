import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"

// <select> de la plantilla: fondo blanco, borde 2 px, sin esquinas. `options` es una lista de
// valores o de pares [valor, texto].
B.ComboBox {
    id: root
    property var options: []
    property string current: ""
    property int fontSize: 13
    property int fontWeight: 500
    property color fill: Theme.input
    property color ink: Theme.ink
    property int padX: 7
    property int padY: 7
    property bool centered: false
    property string tip: ""
    signal picked(string value)

    function val(o) { return Array.isArray(o) ? String(o[0]) : String(o) }
    function txt(o) { return Array.isArray(o) ? String(o[1]) : String(o) }
    model: options.map(txt)
    currentIndex: Math.max(0, options.map(val).indexOf(current))
    onActivated: function (i) { picked(val(options[i])) }

    implicitHeight: fontSize * 1.25 + 2 * padY + 4
    font.family: Theme.font
    font.pixelSize: fontSize
    font.weight: fontWeight

    background: Rectangle { color: root.fill; border.width: 2; border.color: "#000" }
    contentItem: Text {
        leftPadding: root.padX; rightPadding: root.indicator.width + 2
        text: root.displayText
        font: root.font
        color: root.ink
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: root.centered ? Text.AlignHCenter : Text.AlignLeft
    }
    indicator: Canvas {
        x: root.width - width - 6; y: (root.height - height) / 2
        width: 9; height: 6
        property color c: root.ink
        onCChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            ctx.strokeStyle = c; ctx.lineWidth = 1.8
            ctx.beginPath(); ctx.moveTo(0.5, 0.5); ctx.lineTo(4.5, 5); ctx.lineTo(8.5, 0.5); ctx.stroke()
        }
    }
    delegate: B.ItemDelegate {
        required property int index
        required property var modelData
        width: root.popup.width
        height: Math.max(22, root.fontSize * 1.6)
        highlighted: root.highlightedIndex === index
        contentItem: Text {
            text: parent.modelData; font: root.font; elide: Text.ElideRight
            color: parent.highlighted ? "#fff" : "#000"; verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: parent.highlighted ? "#2a6bff" : "#fff" }
    }
    popup.background: Rectangle { color: "#fff"; border.width: 1; border.color: "#000" }
    HoverHandler { id: hov }
    ToolTipLite { text: root.tip; show: hov.hovered && root.tip.length > 0 && !root.popup.visible }
}
