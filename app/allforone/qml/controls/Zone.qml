import QtQuick
import "../theme"

// Zona fija de la ventana (docs/DISENO_DAW.md §2): cabecera con pestañas y botón de plegar, y debajo
// la página elegida. Con `sections` (F2: Inspector y Navegador) no hay pestañas: la cabecera lleva el
// título y cada página es una sección plegable, como el Inspector de Logic: los títulos de las
// secciones cerradas quedan apilados arriba y abajo y la abierta ocupa el resto.
// Las páginas (ZonePage) son hijas de la zona y existen siempre: plegar o cambiar
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
    property bool sections: false             // F2: secciones plegables en vez de pestañas
    property string caption: ""               // F3: qué se edita (el editor de abajo dice de qué es)
    readonly property real rowH: 30
    readonly property int curIdx: { for (var i = 0; i < tabs.length; i++) if (tabs[i][0] === current) return i; return 0 }
    // dónde va la página abierta (ZonePage la sigue); sin secciones, todo el cuerpo
    readonly property real pageY: sections ? (curIdx + 1) * rowH : 0
    readonly property real pageH: sections ? Math.max(0, body.height - tabs.length * rowH) : body.height
    property var help: ({})                   // F13: pestaña → [título, explicación] para el botón «?»
    readonly property var curHelp: help[current] || null
    readonly property real headH: 34
    readonly property color titleInk: Theme.headInk(Theme.pc.pistas)   // par título/cabecera medido por el selftest
    default property alias pages: body.data
    signal picked(string id)
    // para la autoprueba (los delegados de un Repeater no salen en findChildren): las secciones visibles
    // con su «?» y, si se pide, abre la ayuda de una y dice si se abrió
    function sectionInfo(openId) {
        var out = [], opened = false
        for (var i = 0; i < secRep.count; i++) {
            var it = secRep.itemAt(i)
            if (!it || !it.visible || !secRows.visible) continue
            out.push({ id: it.modelData[0], help: !!it.hp, y: Math.round(it.y), h: Math.round(it.height) })
            if (openId === it.modelData[0] && it.helpBtn.visible) {
                it.helpBtn.show(); opened = it.helpBtn.opened && it.helpBtn.text.length > 40; it.helpBtn.hide()
            }
        }
        return { rows: out, opened: opened, pageY: pageY, pageH: pageH }
    }
    color: Theme.veil(Theme.panelColor("", Theme.sidebar))   // F10: con fondo, deja ver un poco
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
        Text {                                // con secciones: el título de la zona
            visible: root.sections && !(root.folded && root.vertical)
            x: 12; anchors.verticalCenter: parent.verticalCenter
            text: root.title.toUpperCase(); color: Theme.ink
            font.family: Theme.font; font.pixelSize: 13; font.weight: 800; font.letterSpacing: 0.8
        }
        Text {                                // F3: «EDITOR · Voz_Principal»
            id: capText
            visible: !!root.caption && !root.sections && !(root.folded && root.vertical)
            x: 12; anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, head.width * 0.3); elide: Text.ElideRight
            text: root.caption; color: Theme.ink
            font.family: Theme.font; font.pixelSize: 13; font.weight: 800; font.letterSpacing: 0.4
        }
        Row {
            id: tabRow
            visible: !root.sections && !(root.folded && root.vertical)
            x: capText.visible ? capText.x + capText.width + 14 : 6; height: parent.height; spacing: 2
            // F12: si las pestañas no caben (zona estrecha), todas se estrechan por igual y recortan el
            // nombre; el tooltip lo da entero
            readonly property real natW: {
                var s = 0
                for (var i = 0; i < tabRep.count; i++) { var it = tabRep.itemAt(i); if (it) s += it.nat + spacing }
                return s
            }
            readonly property real availW: head.width - x - (extraLd.item && extraLd.visible ? extraLd.width + 6 : 0)
                                           - (helpBtn.visible ? helpBtn.width + 6 : 0) - 38
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
        HelpButton {
            id: helpBtn
            objectName: "zoneHelp_" + root.current
            visible: !root.sections && !root.folded && !!root.curHelp
            anchors { right: extraLd.item && extraLd.item.visible ? extraLd.left : foldBtn.left; rightMargin: 6
                      verticalCenter: parent.verticalCenter }
            title: root.curHelp ? root.curHelp[0] : ""
            text: root.curHelp ? root.curHelp[1] : ""
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
    // F2: títulos de las secciones (encima de las páginas)
    Item {
        id: secRows
        visible: root.sections && !root.folded
        y: body.y; width: parent.width; height: body.height
        z: 3
        Repeater {
            id: secRep
            model: root.sections ? root.tabs : []
            Rectangle {
                id: sr
                required property var modelData
                required property int index
                readonly property bool on: root.current === modelData[0]
                readonly property var hp: root.help[modelData[0]] || null
                readonly property alias helpBtn: shb
                objectName: "section_" + modelData[0]
                width: secRows.width; height: root.rowH
                y: index <= root.curIdx ? index * root.rowH : secRows.height - (root.tabs.length - index) * root.rowH
                color: on ? Theme.accent : sh.hovered ? Theme.s3 : Theme.chip
                Rectangle { width: parent.width; height: 1; y: parent.height - 1; color: Theme.line }
                Text {
                    id: stl
                    x: 10; anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - x - (shb.visible ? shb.width + 14 : 10); elide: Text.ElideRight
                    text: (sr.on ? "▾  " : "▸  ") + sr.modelData[1]
                    color: sr.on ? Theme.inkOnAccent : Theme.chipInk
                    font.family: Theme.font; font.pixelSize: 13; font.weight: sr.on ? 800 : 600
                }
                HoverHandler { id: sh; cursorShape: Qt.PointingHandCursor }
                ToolTipLite { text: sr.modelData[2] || ""; show: sh.hovered && !sr.on && text.length > 0 }
                MouseArea { anchors.fill: parent
                            onClicked: { root.current = sr.modelData[0]; root.picked(sr.modelData[0]) } }
                HelpButton {
                    id: shb
                    objectName: "zoneHelp_" + sr.modelData[0]
                    visible: !!sr.hp
                    anchors { right: parent.right; rightMargin: 6; verticalCenter: parent.verticalCenter }
                    title: sr.hp ? sr.hp[0] : ""
                    text: sr.hp ? sr.hp[1] : ""
                }
            }
        }
    }
}
