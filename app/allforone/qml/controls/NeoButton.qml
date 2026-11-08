import QtQuick
import "../theme"

// button de la plantilla: borde 2 px, sombra dura 3 px que desaparece al pulsar (se hunde 3 px).
Item {
    id: root
    property string text: ""
    property color color: Theme.button
    property color textColor: Theme.ink
    property color hoverColor: Theme.pn2
    property bool pressedState: false          // aria-pressed
    property int fontSize: 14
    property int fontWeight: 600
    property int padX: 10
    property int padY: 5
    property int shadow: 3
    property int border: 2
    property string tip: ""
    property alias label: lbl
    property bool hovered: mouse.containsMouse
    default property alias content: extra.data
    signal clicked()

    // Los símbolos (■ ▶ ◐ ✕ …) no están en Space Grotesk: el navegador los toma de Segoe UI Symbol
    function styled(t) {
        return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                .replace(/([←-➿⬀-⯿])/g, '<font face="Segoe UI Symbol">$1</font>')
    }
    readonly property real gap: extra.children.length && text.length ? 7 : 0
    implicitWidth: Math.round(lbl.implicitWidth + extra.childrenRect.width + gap + 2 * padX + 2 * border)
    implicitHeight: Math.round(lbl.height + 2 * padY + 2 * border)
    property bool wrap: false
    property bool leftAlign: false              // text-align:left (contenido a la izquierda)                   // texto en varias líneas si el botón es más estrecho que el texto
    width: implicitWidth
    height: implicitHeight
    activeFocusOnTab: true

    Rectangle {                                 // sombra
        x: root.shadow; y: root.shadow
        width: parent.width; height: parent.height
        color: Theme.line
        visible: root.shadow > 0 && !mouse.pressed
    }
    Rectangle {
        id: face
        x: mouse.pressed ? root.shadow : 0
        y: mouse.pressed ? root.shadow : 0
        width: parent.width; height: parent.height
        color: mouse.containsMouse && root.hoverColor !== root.color && !root.pressedState ? root.hoverColor : root.color
        border.width: root.border
        border.color: Theme.line
        Row {
            x: root.leftAlign ? root.padX + root.border : (parent.width - width) / 2
            anchors.verticalCenter: parent.verticalCenter
            spacing: root.gap
            Item { id: extra; width: childrenRect.width; height: childrenRect.height; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: lbl
                text: root.styled(root.text)
                textFormat: Text.RichText
                color: root.textColor
                font.family: Theme.font
                font.pixelSize: root.fontSize
                font.weight: root.fontWeight
                // line-height: 1.4, texto centrado en la línea
                width: root.wrap ? Math.min(implicitWidth, root.width - 2 * root.padX - 2 * root.border - extra.width - root.gap) : implicitWidth
                wrapMode: root.wrap ? Text.WordWrap : Text.NoWrap
                horizontalAlignment: Text.AlignHCenter
                // (con RichText, lineCount siempre vale 1: las líneas se cuentan por la altura del contenido)
                height: Math.max(1, Math.round(contentHeight / fm.lineSpacing)) * root.fontSize * 1.4
                FontMetrics { id: fm; font: lbl.font }
                verticalAlignment: Text.AlignVCenter
                anchors.verticalCenter: parent.verticalCenter
                visible: text.length > 0
            }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -5
            color: "transparent"; border.width: 3; border.color: Theme.focus
            visible: root.activeFocus
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
    Keys.onSpacePressed: root.clicked()
    Keys.onReturnPressed: root.clicked()
    ToolTipLite { text: root.tip; show: mouse.containsMouse && root.tip.length > 0 }
}
