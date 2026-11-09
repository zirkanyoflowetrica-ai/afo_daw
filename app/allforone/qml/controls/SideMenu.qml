import QtQuick
import "../theme"
import "../state/fxlibrary.js" as FL

// Menú lateral: Módulos (ir a cada uno, + para agregar otro, doble clic para renombrar),
// Instrumentos (crea una pista con ese instrumento) y Efectos (los agrega al rack del canal elegido).
Rectangle {
    id: root
    property var studio
    property int tab: 0
    property string filter: ""
    readonly property var fxBody: studio.fxBody
    color: Theme.dark ? "#17141d" : "#fff6dc"
    clip: true
    Rectangle { x: parent.width - 3; width: 3; height: parent.height; color: Theme.line; z: 3 }

    // pestañas
    Row {
        id: tabs
        x: 10; y: 10; spacing: 4
        Repeater {
            model: ["MÓDULOS", "INSTRUMENTOS", "EFECTOS"]
            Rectangle {
                required property var modelData
                required property int index
                readonly property bool on: root.tab === index
                width: (root.width - 20 - 3 - 8) / 3; height: 30
                color: on ? "#000" : Theme.button
                border.width: 2; border.color: "#000"
                Text { anchors.centerIn: parent; text: parent.modelData; color: parent.on ? Theme.accent : Theme.ink
                       font.family: Theme.font; font.pixelSize: 10; font.weight: 700; font.letterSpacing: 0.4 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.tab = parent.index }
            }
        }
    }

    Flickable {
        id: flick
        x: 10; y: tabs.y + tabs.height + 10
        width: root.width - 20 - 3; height: root.height - y - 10
        contentHeight: content.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Column {
            id: content
            width: flick.width
            spacing: 6

            // ---------------- módulos ----------------
            Repeater {
                model: root.tab === 0 ? root.studio.panelList : []
                Item {
                    id: entry
                    required property var modelData
                    readonly property string pid: modelData.pid
                    readonly property var pnl: root.studio.panelItems[pid] || null
                    readonly property bool shown: !root.studio.hidden[pid]
                    readonly property bool cur: root.studio.currentId === pid
                    readonly property var more: root.studio.addLabel(modelData.base)
                    width: content.width; height: 58
                    Rectangle { x: 3; y: 3; width: parent.width - 3; height: parent.height - 3; color: "#000" }
                    Rectangle {
                        width: parent.width - 3; height: parent.height - 3
                        color: entry.cur ? Theme.tint(Theme.pcOf(entry.pid)) : Theme.button
                        border.width: 2; border.color: "#000"
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            onClicked: root.studio.goTo(entry.pid)
                        }
                        Rectangle {                     // miniatura del módulo
                            id: thumbBox
                            x: 6; y: 6; width: 70; height: parent.height - 12
                            color: Theme.pcOf(entry.pid); border.width: 2; border.color: "#000"; clip: true
                            ShaderEffectSource {
                                id: thumb
                                visible: !!entry.pnl && entry.shown
                                readonly property real k: entry.pnl ? Math.min((parent.width - 4) / entry.pnl.width, (parent.height - 4) / entry.pnl.height) : 1
                                anchors.centerIn: parent
                                width: entry.pnl ? entry.pnl.width * k : 0; height: entry.pnl ? entry.pnl.height * k : 0
                                sourceItem: entry.shown ? entry.pnl : null
                                live: false
                                textureSize: Qt.size(Math.max(1, Math.round(width * 2)), Math.max(1, Math.round(height * 2)))
                                Connections { target: thumbTimer; function onTriggered() { if (thumb.visible) thumb.scheduleUpdate() } }
                            }
                            Text { visible: !thumb.visible; anchors.centerIn: parent; text: "oculto"; color: "#000"
                                   font.family: Theme.font; font.pixelSize: 10; font.weight: 700 }
                        }
                        Column {
                            x: thumbBox.x + thumbBox.width + 8; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - x - btns.width - 8
                            spacing: 1
                            Text {
                                id: nm
                                visible: !nmEdit.visible
                                width: parent.width; elide: Text.ElideRight
                                text: root.studio.titleOf(entry.pid)
                                color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                                MouseArea {
                                    anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: root.studio.goTo(entry.pid)
                                    onDoubleClicked: { nmEdit.text = nm.text; nmEdit.visible = true; nmEdit.forceActiveFocus(); nmEdit.selectAll() }
                                }
                                ToolTipLite { text: "Clic: ir al módulo · Doble clic: renombrar"; show: false }
                            }
                            Rectangle {
                                visible: nmEdit.visible
                                width: parent.width; height: 22; color: Theme.input; border.width: 2; border.color: "#000"
                                TextInput {
                                    id: nmEdit
                                    visible: false
                                    x: 4; width: parent.width - 8; anchors.verticalCenter: parent.verticalCenter
                                    color: Theme.ink; selectByMouse: true; clip: true
                                    font.family: Theme.font; font.pixelSize: 12; font.weight: 700
                                    onAccepted: { visible = false; root.studio.renamePanel(entry.pid, text) }
                                    onActiveFocusChanged: if (!activeFocus && visible) accepted()
                                    Keys.onEscapePressed: visible = false
                                }
                            }
                            Text {
                                width: parent.width; elide: Text.ElideRight
                                text: root.studio.modelOf(entry.pid) + (entry.shown ? "" : " · oculto")
                                color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 10; font.weight: 600
                            }
                        }
                        Row {
                            id: btns
                            x: parent.width - width - 6; anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            SmallBtn {
                                glyph: entry.shown ? "◉" : "○"
                                tip: entry.shown ? "Ocultar del lienzo (sus pistas dejan de sonar si es una fuente)" : "Mostrar en el lienzo"
                                visible: !entry.modelData.extra
                                onClicked: entry.shown ? root.studio.setHidden(entry.pid, true) : root.studio.goTo(entry.pid)
                            }
                            SmallBtn {
                                glyph: "✕"; tip: "Quitar este rack"
                                visible: !!entry.modelData.extra
                                onClicked: root.studio.removeExtra(entry.pid)
                            }
                            SmallBtn {
                                glyph: "+"; accent: true
                                visible: !!entry.more
                                tip: entry.more || ""
                                onClicked: root.studio.addMore(entry.modelData.base)
                            }
                        }
                    }
                }
            }
            Text {
                visible: root.tab === 0
                width: content.width; wrapMode: Text.Wrap; topPadding: 4
                text: "Clic: ir al módulo · □ en su cabecera: maximizar · Doble clic en el nombre: renombrar · +: agregar otro"
                color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
            }

            // ---------------- instrumentos ----------------
            Section { visible: root.tab === 1; text: "INSTRUMENTOS DEL MOTOR" }
            Repeater {
                model: root.tab === 1 ? root.studio.seq.insts : []
                Entry {
                    required property var modelData
                    required property int index
                    title: modelData[0]; sub: modelData[1] + " · nueva pista de instrumento"; color2: Theme.pc.inst
                    onClicked: root.studio.addInstrument(index)
                }
            }
            Section { visible: root.tab === 1; text: "BATERÍA" }
            Entry { visible: root.tab === 1; title: "Drum pad R-16"; sub: "8 pads tocables + secuenciador de 16 pasos"; color2: Theme.pc.drums
                    onClicked: root.studio.addMore("drums") }
            Section { visible: root.tab === 1; text: "VOZ Y AUDIO" }
            Entry { visible: root.tab === 1; title: "Grabar voz"; sub: "Pista de grabación (Cinta RX-2)"; color2: Theme.pc.cinta
                    onClicked: root.studio.addMore("cinta") }
            Entry { visible: root.tab === 1; title: "Importar audio…"; sub: "WAV, AIFF, FLAC, OGG, MP3"; color2: Theme.pc.audios
                    onClicked: root.studio.addMore("audios") }
            Entry { visible: root.tab === 1; title: "Pista con IA"; sub: "Patrones generados (DEMO)"; color2: Theme.pc.ia
                    onClicked: root.studio.addMore("ia") }
            Section { visible: root.tab === 1; text: "PLUGINS VST3 (INSTRUMENTOS)" }
            Repeater {
                model: root.tab === 1 ? root.studio.plugins.filter(function (p) { return p.instrument }) : []
                Entry {
                    required property var modelData
                    title: modelData.name; sub: modelData.vendor + " · VST3"; color2: Theme.pc.inst
                    onClicked: root.studio.addPluginInstrument(modelData)
                }
            }
            PluginScan { visible: root.tab === 1 }
            Section { visible: root.tab === 1; text: "SINTES AFO (POR CONSTRUIR)" }
            Repeater {
                model: root.tab === 1 ? FL.FAMILIES[0].folders : []
                Text {
                    required property var modelData
                    width: content.width; wrapMode: Text.Wrap
                    text: modelData.name + ": " + modelData.items.map(function (i) { return i[1] }).join(", ")
                    color: Theme.ink; opacity: 0.55; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
                }
            }

            // ---------------- efectos ----------------
            Rectangle {
                visible: root.tab === 2
                width: content.width; height: tgt.implicitHeight + 12
                color: "#000"
                Text {
                    id: tgt; x: 8; y: 6; width: parent.width - 16; wrapMode: Text.Wrap
                    text: "Se agrega a: " + (root.fxBody ? root.fxBody.targetName : "—") + "  (elige el canal en Mezcla)"
                    color: Theme.accent; font.family: Theme.font; font.pixelSize: 12; font.weight: 700
                }
            }
            Rectangle {
                visible: root.tab === 2
                width: content.width; height: 30; color: Theme.input; border.width: 2; border.color: "#000"
                TextInput {
                    id: search
                    x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter
                    color: Theme.ink; selectByMouse: true; clip: true
                    font.family: Theme.font; font.pixelSize: 13
                    onTextChanged: root.filter = text.toLowerCase()
                }
                Text { visible: !search.text; x: 8; anchors.verticalCenter: parent.verticalCenter; text: "Buscar efecto…"
                       color: Theme.ink; opacity: 0.45; font.family: Theme.font; font.pixelSize: 13 }
            }
            Repeater {
                model: root.tab === 2 ? FL.FAMILIES.slice(1) : []
                Column {
                    id: fam
                    required property var modelData
                    width: content.width; spacing: 4
                    Section { text: fam.modelData.name.toUpperCase() }
                    Repeater {
                        model: fam.modelData.folders
                        Column {
                            id: fold
                            required property var modelData
                            readonly property var items: modelData.items.filter(function (i) {
                                return !root.filter || (i[0] + " " + i[1]).toLowerCase().indexOf(root.filter) >= 0 })
                            visible: items.length > 0
                            width: content.width; spacing: 3
                            Text { text: fold.modelData.name; color: Theme.ink; opacity: 0.75; topPadding: 2
                                   font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                            Repeater {
                                model: fold.items.filter(function (i) { return root.fxBody && root.fxBody.built[i[0]] })
                                Entry {
                                    required property var modelData
                                    readonly property var fx: root.fxBody.built[modelData[0]]
                                    compact: true
                                    title: modelData[1]; sub: modelData[0] + " · " + (fx.summary || "")
                                    color2: Theme.pc.fx
                                    onClicked: root.studio.addEffect(fx.key)
                                }
                            }
                            Text {           // lo que aún no existe: una línea, sin botones
                                readonly property var todo: fold.items.filter(function (i) { return !(root.fxBody && root.fxBody.built[i[0]]) })
                                visible: todo.length > 0
                                width: content.width; wrapMode: Text.Wrap
                                text: "Por construir: " + todo.map(function (i) { return i[1] }).join(", ")
                                color: Theme.ink; opacity: 0.5; font.family: Theme.font; font.pixelSize: 10; font.weight: 500
                            }
                        }
                    }
                }
            }
            Section { visible: root.tab === 2; text: "PLUGINS VST3 (EFECTOS)" }
            Repeater {
                model: root.tab === 2 ? root.studio.plugins.filter(function (p) {
                    return !p.instrument && (!root.filter || p.name.toLowerCase().indexOf(root.filter) >= 0) }) : []
                Entry {
                    required property var modelData
                    compact: true
                    title: modelData.name; sub: modelData.vendor + " · VST3"; color2: Theme.pc.fx
                    onClicked: root.studio.addPluginEffect(modelData)
                }
            }
            PluginScan { visible: root.tab === 2 }
        }
    }
    Timer { id: thumbTimer; interval: 1500; repeat: true; running: root.visible && root.tab === 0; triggeredOnStart: true }

    component Section: Text {
        width: content.width; topPadding: 8
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 700; font.letterSpacing: 0.8
        Rectangle { y: parent.height + 2; width: parent.width; height: 2; color: Theme.line }
        bottomPadding: 4
    }
    component Entry: Item {
        id: en
        property string title
        property string sub
        property color color2: Theme.accent
        property bool compact: false
        signal clicked()
        width: content.width; height: compact ? 38 : 44
        opacity: enabled ? 1 : 0.5
        Rectangle { x: 2; y: 2; width: parent.width - 2; height: parent.height - 2; color: "#000"; visible: en.enabled }
        Rectangle {
            width: parent.width - 2; height: parent.height - 2
            color: em.containsMouse && en.enabled ? Theme.pn2 : Theme.button
            border.width: 2; border.color: "#000"
            Rectangle { x: 2; y: 2; width: 6; height: parent.height - 4; color: en.color2 }
            Column {
                x: 14; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 40
                Text { width: parent.width; elide: Text.ElideRight; text: en.title; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: en.compact ? 12 : 13; font.weight: 700 }
                Text { width: parent.width; elide: Text.ElideRight; text: en.sub; color: Theme.ink; opacity: 0.65
                       font.family: Theme.font; font.pixelSize: 10; font.weight: 500; visible: text.length > 0 }
            }
            Text { visible: en.enabled; x: parent.width - 22; anchors.verticalCenter: parent.verticalCenter; text: "+"
                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 18; font.weight: 700 }
        }
        MouseArea { id: em; anchors.fill: parent; hoverEnabled: true; enabled: en.enabled
                    cursorShape: Qt.PointingHandCursor; onClicked: en.clicked() }
    }
    component SmallBtn: Rectangle {
        id: sb
        property string glyph
        property string tip
        property bool accent: false
        signal clicked()
        width: 24; height: 24
        color: sbm.containsMouse ? Theme.accent : sb.accent ? Theme.pc.mezcla : Theme.button
        border.width: 2; border.color: "#000"
        Text { anchors.centerIn: parent; text: sb.glyph; color: sb.accent ? "#000" : Theme.ink
               font.family: "Segoe UI Symbol"; font.pixelSize: 14; font.weight: 700 }
        MouseArea { id: sbm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: sb.clicked() }
        ToolTipLite { text: sb.tip; show: sbm.containsMouse }
    }
    component PluginScan: Column {
        width: content.width; spacing: 4
        Text {
            width: parent.width; wrapMode: Text.Wrap
            text: root.studio.pluginStatus
            color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
        }
        NeoButton {
            text: root.studio.pluginScanning ? "Buscando…" : "Buscar plugins VST3"
            fontSize: 12; padX: 8; padY: 3
            tip: "Busca .vst3 en las carpetas estándar de Windows (Common Files\\VST3) y en las que agregues"
            onClicked: root.studio.scanPlugins()
        }
    }
}
