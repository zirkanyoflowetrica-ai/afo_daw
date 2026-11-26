import QtQuick
import "../theme"
import "../controls"
import "../state/fxgraph.js" as FG

// Cadena de dispositivos del panel de detalle (DISENO_DAW §2): los efectos de la pista elegida en fila,
// en orden de señal, todos con el mismo marco: encendido, nombre (arrastrar para reordenar, doble clic
// para plegar), ◀ ▶, A/B, ≡ y ✕; dentro, preset, pantalla y perillas. «+» al final abre la biblioteca.
// La lógica (motor, presets, A/B) es del rack: `rk` (FxBody).
Rectangle {
    id: chainBox
    property var rk                            // el rack (FxBody): cadena, catálogo y acciones
    property real dropX: -1                    // dónde caerá el dispositivo que se arrastra
    property int dragId: -1
    // Posición final de un dispositivo soltado en x (coordenadas de la fila): los demás cuyo centro queda a la izquierda
    function dropIndex(id, x) {
        var n = 0
        for (var i = 0; i < devRow.children.length; i++) {
            var c = devRow.children[i]
            if (c.modelData === undefined || !c.modelData || c.modelData.id === id) continue
            if (c.x + c.width / 2 < x) n++
        }
        return n
    }
    function dropAt(id, x) {
        var from = -1
        for (var i = 0; i < rk.chain.length; i++) if (rk.chain[i].id === id) from = i
        var to = dropIndex(id, x)
        if (from >= 0 && to !== from) rk.move(id, to)
        return to
    }
    width: rk.width; height: Math.max(300, rk.cardNeed + 12)
    color: Theme.chain; radius: Theme.radius
    border.width: 1; border.color: Theme.line
    Flickable {
        id: chainFlick
        x: 6; y: 6; width: parent.width - 12; height: parent.height - 12
        contentWidth: devRow.width; contentHeight: height
        clip: true; boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        interactive: contentWidth > width
        Rectangle {                              // dónde caerá al soltar
            visible: chainBox.dragId >= 0 && chainBox.dropX >= 0; z: 3
            x: chainBox.dropX - 2; width: 4; height: devRow.height; radius: 2; color: Theme.accent
        }
        Row {
            id: devRow
            height: chainFlick.height; spacing: 6
            Repeater {
                model: rk.chain
                Rectangle {
                    id: card
                    required property var modelData
                    required property int index
                    readonly property var desc: rk.typeOf(modelData.key)
                    readonly property bool picked: modelData.id === rk.sel
                    readonly property var knobs: desc ? desc.params.filter(function (p) { return !p.choices.length }) : []
                    readonly property var picks: desc ? desc.params.filter(function (p) { return p.choices.length > 0 }) : []
                    readonly property int cols: Math.max(2, Math.ceil(knobs.length / 2))
                    readonly property bool isFolded: !!rk.folded[modelData.id]
                    readonly property bool labPart: rk.isLabPart(modelData.key)
                    readonly property var lab: modelData.lab || null   // FX Lab: start | A | split | B | end
                    width: isFolded ? 36 : labPart ? 150 : modelData.key === "vst3" ? 200 : Math.max(200, cols * 64 + 16)
                    readonly property int needH: isFolded ? 0 : devHead.height + 6 + cardBody.implicitHeight + 10
                    onNeedHChanged: if (needH > rk.cardNeed) rk.cardNeed = needH
                    clip: true
                    height: devRow.height
                    color: Theme.device; radius: Theme.radius
                    border.width: picked ? 2 : 1; border.color: picked ? Theme.knobArc : Theme.deviceBorder
                    MouseArea { anchors.fill: parent; onClicked: rk.sel = card.modelData.id }
                    HoverHandler { id: cardHover }   // ◀ ▶ ≡ solo al pasar o con la tarjeta elegida: el nombre cabe
                    readonly property bool tools: cardHover.hovered || picked
                    Rectangle {                      // cabecera: activar · nombre · ◀ ▶ ≡ ✕
                        id: devHead
                        visible: !card.isFolded
                        x: 1; y: 1; width: parent.width - 2; height: 28
                        color: Theme.deviceHead; radius: Theme.radius
                        Rectangle {
                            x: 8; anchors.verticalCenter: parent.verticalCenter
                            width: 14; height: 14; radius: 7
                            color: card.modelData.enabled ? Theme.knobArc : Theme.knobTrack
                            border.width: 1; border.color: Theme.deviceBorder
                            MouseArea { id: bypassMouse; hoverEnabled: true; anchors.fill: parent; anchors.margins: -5; cursorShape: Qt.PointingHandCursor
                                        onClicked: rk.enable(card.modelData.id, !card.modelData.enabled) }
                            ToolTipLite { text: card.modelData.enabled ? "Activo: clic para puentear" : "Puenteado: clic para activar"; show: bypassMouse.containsMouse }
                        }
                        Text {
                            id: devName
                            x: 30; width: parent.width - 30 - devBtns.width - 8; anchors.verticalCenter: parent.verticalCenter
                            elide: Text.ElideRight
                            text: rk.nameOf(card.modelData) + ((card.modelData.automated || []).length ? " ∿" : "")
                            color: Theme.deviceInk; font.strikeout: !card.modelData.enabled
                            font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                            MouseArea {
                                id: foldMouse; hoverEnabled: true; anchors.fill: parent
                                cursorShape: chainBox.dragId === card.modelData.id ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                preventStealing: true
                                property real px: 0
                                onPressed: function (m) { px = m.x }
                                onPositionChanged: function (m) {
                                    if (!pressed) return
                                    if (chainBox.dragId < 0 && Math.abs(m.x - px) > 8) chainBox.dragId = card.modelData.id
                                    if (chainBox.dragId === card.modelData.id) chainBox.dropX = mapToItem(devRow, m.x, m.y).x
                                }
                                onReleased: function (m) {
                                    if (chainBox.dragId === card.modelData.id) chainBox.dropAt(card.modelData.id, mapToItem(devRow, m.x, m.y).x)
                                    chainBox.dragId = -1; chainBox.dropX = -1
                                }
                                onCanceled: { chainBox.dragId = -1; chainBox.dropX = -1 }
                                onClicked: rk.sel = card.modelData.id
                                onDoubleClicked: rk.toggleFold(card.modelData.id)
                            }
                            ToolTipLite { text: "Arrastra para cambiar el orden · doble clic: plegar"; show: foldMouse.containsMouse && chainBox.dragId < 0 }
                        }
                        Row {
                            id: devBtns
                            anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                            spacing: 0
                            Rectangle {              // lo puso la mezcla automática (antes, un texto al pie que pisaba los valores)
                                visible: !!card.modelData.auto
                                width: autoTxt.implicitWidth + 8; height: 18; radius: 2
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.knobArc
                                Text { id: autoTxt; anchors.centerIn: parent; text: "AUTO"; color: Theme.inkOnColor
                                       font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                MouseArea { id: autoM; anchors.fill: parent; hoverEnabled: true }
                                ToolTipLite { text: "Lo puso la mezcla automática; puedes cambiarlo"; show: autoM.containsMouse }
                            }
                            DevBtn { glyph: "◀"; tip: "Mover antes"; visible: card.tools && card.index > 0; onClicked: rk.move(card.modelData.id, card.index - 1) }
                            DevBtn { glyph: "▶"; tip: "Mover después"; visible: card.tools && card.index < rk.chain.length - 1; onClicked: rk.move(card.modelData.id, card.index + 1) }
                            DevBtn {
                                readonly property var st: rk.ab[card.modelData.id]
                                visible: card.tools && card.modelData.key !== "vst3" && !card.labPart; width: 30
                                glyph: st ? st.side : "A/B"; on: !!st && st.side === "B"
                                tip: st ? "Escuchas " + st.side + ". Pulsa para pasar a " + (st.side === "A" ? "B" : "A") + " (los ajustes de cada uno se guardan aparte)"
                                        : "Comparar A/B: guarda los ajustes actuales como A; lo que cambies después es B"
                                onClicked: rk.abToggle(card.modelData)
                            }
                            DevBtn { glyph: "≡"; tip: "Detalle: medidores, presets propios y automatización"; visible: card.tools; onClicked: rk.sel = card.modelData.id }
                            DevBtn { glyph: "✕"
                                     tip: card.labPart || card.modelData.key === "fxlab" ? "Quitar el FX Lab (sus tres piezas; los efectos de sus ramas se quedan, en serie)" : "Quitar de la cadena"
                                     onClicked: rk.remove(card.modelData.id) }
                        }
                    }
                    Column {                         // plegado: activador y nombre en vertical
                        visible: card.isFolded
                        anchors.fill: parent; anchors.topMargin: 8; spacing: 10
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 14; height: 14; radius: 7
                            color: card.modelData.enabled ? Theme.knobArc : Theme.knobTrack
                            border.width: 1; border.color: Theme.deviceBorder
                            MouseArea { anchors.fill: parent; anchors.margins: -5; cursorShape: Qt.PointingHandCursor
                                        onClicked: rk.enable(card.modelData.id, !card.modelData.enabled) }
                        }
                        Item {
                            width: parent.width; height: parent.height - 40
                            Text {
                                anchors.centerIn: parent; rotation: -90
                                width: parent.height; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                                text: rk.nameOf(card.modelData)
                                color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 13; font.weight: 700
                            }
                            MouseArea { anchors.fill: parent; onDoubleClicked: rk.toggleFold(card.modelData.id)
                                        onClicked: rk.sel = card.modelData.id }
                        }
                    }
                    Column {
                        id: cardBody
                        visible: !card.isFolded
                        x: 8; y: devHead.height + 6; width: parent.width - 16; spacing: 6
                        opacity: card.modelData.enabled ? 1 : 0.55
                        Rectangle {                  // FX Lab: a qué rama pertenece este efecto
                            visible: !!card.lab && (card.lab.role === "A" || card.lab.role === "B")
                            width: parent.width; height: visible ? 20 : 0; radius: 2
                            color: Theme.chip; border.width: 1; border.color: Theme.line
                            Text { anchors.centerIn: parent; text: card.lab ? "FX LAB · RAMA " + card.lab.role : ""
                                   color: Theme.chipInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                        }
                        Text {                       // separadores del FX Lab: qué hacen
                            visible: card.labPart
                            width: parent.width; wrapMode: Text.Wrap
                            text: !card.lab ? "Sin su FX Lab delante: no hace nada. Ponla después de un FX Lab o quítala."
                                  : !card.lab.linked ? "El FX Lab no está enlazado: revisa el orden (FX Lab → A → Rama B → B → Fin)."
                                  : card.modelData.key === "fxlab_b" ? "Antes: rama A. Después: rama B. Las dos reciben la misma señal."
                                  : "Aquí se mezclan la rama A, la B y el seco, con los ajustes del FX Lab."
                            color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
                        }
                        Column {                     // plugin VST3: su propia ventana
                            visible: card.modelData.key === "vst3"
                            width: parent.width; spacing: 8
                            NeoButton { text: "Abrir plugin"; width: parent.width; fontSize: 12; padY: 6
                                        tip: "Abre la ventana del plugin (sus controles y presets)"
                                        onClicked: { var r = rk.studio.call("fxPluginEditor", card.modelData.id); if (!r.ok) rk.studio.toast(r.error) } }
                            Text { width: parent.width; wrapMode: Text.Wrap; text: "VST3 externo. Su estado se guarda con el proyecto."
                                   color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                        }
                        Select {
                            visible: card.modelData.key !== "vst3" && !card.labPart
                            width: parent.width; fontSize: 10; padX: 4; padY: 2
                            fill: Theme.deviceHead; ink: Theme.deviceInk
                            options: [["", "Preset…"]].concat((rk.presetCache[card.modelData.key] || []).map(function (p) { return [p.name, p.name + (p.factory ? "" : " ★")] }))
                            current: ""
                            tip: "Presets de fábrica y los tuyos (★)"
                            onPicked: function (v) { if (v) rk.applyPresetTo(card.modelData, v) }
                        }
                        Canvas {                     // pantalla del dispositivo: lo que hará con estos valores
                            visible: !!card.desc
                            width: parent.width; height: visible ? 64 : 0
                            property var fx: card.modelData
                            property var live: rk.cardLive[card.modelData.id]
                            onFxChanged: requestPaint()
                            onLiveChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onPaint: { FG.setPalette(Theme.lcd, Theme.lcdSoft, Theme.screen, Theme.meterOk, Theme.screenDim, Theme.meterPeak); if (card.desc) FG.draw(getContext("2d"), width, height, fx, card.desc, live) }
                        }
                        Grid {                       // perillas en dos filas
                            columns: card.cols; columnSpacing: 4; rowSpacing: 2
                            Repeater {
                                model: card.knobs
                                Column {
                                    id: kc
                                    required property var modelData
                                    readonly property int pi: rk.paramIndex(card.desc, modelData.id)
                                    readonly property real v: card.modelData.values[pi] !== undefined ? card.modelData.values[pi] : modelData.def
                                    readonly property bool auto: (card.modelData.automated || []).indexOf(modelData.id) >= 0
                                    width: 60; spacing: 0
                                    Knob {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        value: rk.toPos(kc.modelData, kc.v)
                                        label: kc.modelData.name + (kc.auto ? " ∿" : "")
                                        labelColor: kc.auto ? Theme.knobArc : Theme.deviceInk
                                        tip: kc.modelData.help
                                        onMoved: function (pos) { rk.setParamOf(card.modelData, kc.pi, rk.fromPos(kc.modelData, pos)) }
                                        onReleased: rk.studio.autoRelease("fx", card.modelData.id, kc.modelData.id, kc.v)
                                    }
                                    Text { anchors.horizontalCenter: parent.horizontalCenter
                                           text: rk.fmtVal(kc.modelData, kc.v); color: Theme.deviceInk
                                           font.family: Theme.font; font.pixelSize: 11; font.weight: 700 }
                                }
                            }
                        }
                        Flow {                       // parámetros de elegir (modo, tipo…)
                            width: parent.width; spacing: 6
                            Repeater {
                                model: card.picks
                                Column {
                                    id: pcol
                                    required property var modelData
                                    readonly property int pi: rk.paramIndex(card.desc, modelData.id)
                                    readonly property real v: card.modelData.values[pi] !== undefined ? card.modelData.values[pi] : modelData.def
                                    spacing: 1
                                    Text { text: pcol.modelData.name; color: Theme.deviceInk; font.family: Theme.font; font.pixelSize: 11; font.weight: 600 }
                                    Select {
                                        width: 96; fontSize: 10; padY: 2; padX: 4
                                        fill: Theme.deviceHead; ink: Theme.deviceInk
                                        options: pcol.modelData.choices.map(function (c, i) { return [String(i), c] })
                                        current: String(Math.round(pcol.v))
                                        tip: pcol.modelData.help
                                        onPicked: function (val) { rk.setParamOf(card.modelData, pcol.pi, Number(val)) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Rectangle {                              // hueco final: agregar efecto
                width: 150; height: devRow.height
                color: "transparent"; radius: Theme.radius
                border.width: 1; border.color: Theme.deviceBorder
                Column {
                    anchors.centerIn: parent; spacing: 6; width: parent.width - 20
                    Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: rk.libOpen ? "×" : "+"
                           color: Theme.ink; font.family: Theme.font; font.pixelSize: 30; font.weight: 300 }
                    Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                           text: rk.libOpen ? "Cerrar biblioteca" : (rk.chain.length ? "Agregar efecto" : "Sin efectos en " + rk.targetName + ". Agrega uno" + (rk.master ? " o pulsa MASTERIZAR abajo" : "") + ".")
                           color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: rk.libOpen = !rk.libOpen }
            }
        }
    }
    Rectangle {                                      // barra de desplazamiento horizontal
        visible: chainFlick.contentWidth > chainFlick.width + 1
        y: parent.height - 5; height: 3; radius: 1.5
        x: chainFlick.x + chainFlick.visibleArea.xPosition * chainFlick.width
        width: Math.max(24, chainFlick.visibleArea.widthRatio * chainFlick.width)
        color: Theme.ink; opacity: 0.35
    }

    // Botón de la cabecera de un dispositivo (solo el símbolo)
    component DevBtn: Rectangle {
        id: db
        property string glyph
        property string tip
        property bool on: false
        signal clicked()
        width: 24; height: 24; radius: 2              // objetivo mínimo de 24 px (WCAG 2.5.8)
        color: dbm.containsMouse || on ? Theme.knobArc : "transparent"
        Text { anchors.centerIn: parent; text: db.glyph; color: dbm.containsMouse || db.on ? Theme.inkOnAccent : Theme.deviceInk
               font.family: db.glyph.length > 1 ? Theme.font : "Segoe UI Symbol"; font.pixelSize: db.glyph.length > 1 ? 10 : 12; font.weight: 700 }
        MouseArea { id: dbm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: db.clicked() }
        ToolTipLite { text: db.tip; show: dbm.containsMouse }
    }
}
