import QtQuick

// Módulo Antes / Después (A/B Comp): original y procesada de cada pista al mismo volumen, en el motor.
Column {
    id: root
    property var mixer
    readonly property var list: mixer.currentRun ? mixer.currentRun.review || [] : []
    readonly property var cur: list[mixer.reviewSel]
    width: parent ? parent.width : 380
    spacing: 0

    function two(n) { return (n < 10 ? "0" : "") + n }

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: cnt; text: root.list.length ? root.two(root.mixer.reviewSel + 1) + "/" + root.two(root.list.length) : "--/--"
              anchors.verticalCenter: parent.verticalCenter }
        Text {
            width: root.width - cnt.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
            text: "Original y procesada al mismo volumen. Pista seca antes de buses y efectos compartidos."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
        }
    }
    Column {
        width: root.width; spacing: 4
        Text { text: "Pista"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        Select {
            width: parent.width
            enabled: root.list.length > 0
            options: root.list.length ? root.list.map(function (x, i) { return [String(i), x.label] }) : [["0", "Sin mezcla todavía"]]
            current: String(root.mixer.reviewSel)
            onPicked: function (v) { root.mixer.reviewSel = parseInt(v) }
        }
    }
    Row {                                       // .afo-ab
        id: ab
        width: root.width; spacing: 6; topPadding: 8; bottomPadding: 8 + 3
        readonly property real bh: Math.max(a.implicitHeight, b.implicitHeight, s.implicitHeight)
        NeoButton { id: a; wrap: true; width: (root.width - 12) / 3 - 1; height: ab.bh; text: "▶ A · original"; fontWeight: 700
                    readonly property bool on: root.mixer.reviewAb === "A"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    opacity: root.cur ? 1 : 0.5; onClicked: if (root.cur) root.mixer.listen("review", "A") }
        NeoButton { id: b; wrap: true; width: (root.width - 12) / 3 - 1; height: ab.bh; text: "▶ B · procesada"; fontWeight: 700
                    readonly property bool on: root.mixer.reviewAb === "B"
                    color: on ? Theme.pressedBg : Theme.button; textColor: on ? Theme.pressedInk : Theme.ink; pressedState: on
                    opacity: root.cur ? 1 : 0.5; onClicked: if (root.cur) root.mixer.listen("review", "B") }
        NeoButton { id: s; width: (root.width - 12) / 3 - 1; height: ab.bh; text: "■"; fontWeight: 700; tip: "Parar la escucha"
                    opacity: root.cur ? 1 : 0.5; onClicked: if (root.cur) root.mixer.listen("review", "stop") }
    }
    Note {
        width: root.width
        text: root.cur ? root.cur.note : "Tras mezclar verás aquí las decisiones tomadas para cada pista (tipo, posición, EQ, compresión, afinación, espacio)."
    }
}
