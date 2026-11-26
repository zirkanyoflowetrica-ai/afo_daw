import QtQuick
import "../theme"
import "../controls"

// Módulo Instrumentos (Banco VST-1): una sola instancia; cada pista guarda su preset.
Column {
    id: root
    property var seq
    readonly property var t: seq.active("inst")
    readonly property bool is808: !!t && !t.cfg.plugin && t.cfg.v === 8        // preset «Bajo 808»
    readonly property bool isAnalog: !!t && !t.cfg.plugin && t.cfg.v === 9     // preset «Sinte analógico»
    readonly property bool isWave: !!t && !t.cfg.plugin && t.cfg.v === 10      // preset «Sinte de tablas»
    readonly property bool isSampler: !!t && !t.cfg.plugin && t.cfg.v === 11   // preset «Sampler»
    readonly property var noteNames: ["do", "do#", "re", "re#", "mi", "fa", "fa#", "sol", "sol#", "la", "la#", "si"]
    width: parent ? parent.width : 380
    spacing: 0

    Row {                                       // .vst
        width: root.width; spacing: 10; bottomPadding: 10
        Lcd { id: one; text: "1 instancia"; anchors.verticalCenter: parent.verticalCenter }
        Text { width: root.width - one.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
               text: "El instrumento se carga una sola vez. Cada pista guarda solo su preset."
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 500 }
    }
    TrackTabs { seq: root.seq; type: "inst" }
    DashedBox { visible: !root.t; width: root.width; height: visible ? implicitHeight : 0
                text: "Crea una pista de instrumento para cargar su preset." }

    Row {                                       // instrumento VST3 externo de esta pista
        visible: !!root.t
        width: root.width; spacing: 8; topPadding: 8; height: visible ? implicitHeight : 0
        readonly property var studio: root.seq.studio
        readonly property var insts: studio.plugins.filter(function (p) { return p.instrument })
        Text { text: "Sonido"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
        Select {
            width: Math.min(260, root.width - 220)
            options: [["", "Sintetizador del motor (preset abajo)"]].concat(parent.insts.map(function (p) { return [p.id, p.name + " · " + p.vendor] }))
            current: root.t ? root.t.cfg.plugin || "" : ""
            tip: parent.insts.length ? "Instrumento VST3: recibe las notas del piano roll de esta pista"
                                     : "Busca plugins VST3 en el menú Instrumentos para elegirlos aquí"
            onPicked: function (v) { root.seq.setCfg("inst", "plugin", v) }
        }
        NeoButton {
            visible: !!root.t && !!root.t.cfg.plugin
            text: "Abrir instrumento"; fontSize: 12; padX: 8; padY: 3
            onClicked: { var r = parent.studio.call("instPluginEditor", root.t.id); if (!r.ok) parent.studio.toast(r.error) }
        }
    }

    Grid {                                      // .insts: repeat(auto-fill, minmax(120px, 1fr))
        id: grid
        visible: !!root.t && !root.t.cfg.plugin
        columns: Math.max(1, Math.floor((root.width + 8) / 128))
        columnSpacing: 8; rowSpacing: 8
        topPadding: 10; bottomPadding: 10 + 3
        readonly property real cw: (root.width - (columns - 1) * 8) / columns - 3
        Repeater {
            model: root.seq.insts
            Item {
                id: card
                required property var modelData
                required property int index
                readonly property bool on: !!root.t && root.t.cfg.v === index
                width: grid.cw; height: col.height + 12 + 4
                Rectangle { x: 3; y: 3; width: parent.width; height: parent.height; color: Theme.shadowColor; visible: Theme.buttonShadow > 0 && (!cm.pressed) }
                Rectangle {
                    x: cm.pressed ? 3 : 0; y: cm.pressed ? 3 : 0
                    width: parent.width; height: parent.height
                    color: Theme.screenCard; border.width: Theme.buttonBorder; border.color: Theme.line
                    Column {
                        id: col
                        x: 12; y: 7; width: parent.width - 24; spacing: 2
                        Item {
                            width: 11; height: 15
                            Rectangle { anchors.centerIn: parent; anchors.verticalCenterOffset: -2; width: 20; height: 20; radius: 10
                                        color: Theme.rec; opacity: 0.25; visible: card.on }
                            Rectangle { width: 11; height: 11; radius: 5.5; border.width: Theme.buttonBorder; border.color: Theme.line
                                        color: card.on ? Theme.rec : Theme.ledOff }
                        }
                        Text { width: parent.width; elide: Text.ElideRight; text: card.modelData[0]
                               color: Theme.screenInk; font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                        Text { width: parent.width; elide: Text.ElideRight; text: card.modelData[1]
                               color: Theme.screenDim; font.family: Theme.font; font.pixelSize: 13; font.weight: 500 }
                    }
                }
                MouseArea {
                    id: cm; anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                    onClicked: { root.seq.setCfg("inst", "v", card.index); root.seq.previewMidi(root.t.cfg, 69) }
                }
            }
        }
    }
    Note {                                      // X6: con un VST3, las perillas del sintetizador interno no actúan
        objectName: "instVstNote"
        visible: !!root.t && !!root.t.cfg.plugin
        width: root.width
        text: "Velocidad, Brillo y Reverb son del sintetizador interno; ajusta el VST3 en su editor («Abrir instrumento»)."
    }
    Row {                                       // .krow
        objectName: "instKnobs"
        visible: !!root.t && !root.t.cfg.plugin
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
        Knob { label: "Velocidad"; value: root.t ? root.t.cfg.vel : 70; onMoved: function (v) { root.seq.setCfg("inst", "vel", v) } }
        Knob { label: "Brillo"; value: root.t ? root.t.cfg.bri : 50; onMoved: function (v) { root.seq.setCfg("inst", "bri", v) } }
        Knob { label: "Reverb"; value: root.t ? root.t.cfg.rev : 30; tip: "Reverb de sala del motor (0 = seca)"
               onMoved: function (v) { root.seq.setCfg("inst", "rev", v) } }
        // 808 Lab: solo con el preset «Bajo 808»
        Knob { objectName: "knob808Glide"; visible: root.is808; label: "Glide"
               value: root.t && root.t.cfg.glide !== undefined ? root.t.cfg.glide : 30
               tip: "Las notas que se pisan en el piano roll se deslizan (0 = cada nota vuelve a sonar)"
               onMoved: function (v) { root.seq.setCfg("inst", "glide", v) } }
        Knob { objectName: "knob808Drive"; visible: root.is808; label: "Saturación"
               value: root.t && root.t.cfg.drive !== undefined ? root.t.cfg.drive : 30
               tip: "Armónicos para que el 808 se oiga también en altavoces pequeños"
               onMoved: function (v) { root.seq.setCfg("inst", "drive", v) } }
        Knob { objectName: "knob808Punch"; visible: root.is808; label: "Golpe"
               value: root.t && root.t.cfg.punch !== undefined ? root.t.cfg.punch : 50
               tip: "Caída rápida de afinación al empezar cada nota: el golpe del 808"
               onMoved: function (v) { root.seq.setCfg("inst", "punch", v) } }
    }
    // Sinte analógico: dos osciladores y filtro resonante con envolvente (solo con su preset)
    Grid {
        objectName: "instAnalog"
        visible: root.isAnalog
        height: visible ? implicitHeight : 0
        columns: 3; columnSpacing: 16; rowSpacing: 4
        anchors.horizontalCenter: parent.horizontalCenter; topPadding: 8
        Repeater {
            model: [["anDet", "Desafinar", 30, "Separación entre los dos osciladores (0 = al unísono, 100 = ±25 cents)"],
                    ["anCut", "Corte", 55, "Frecuencia del filtro paso bajo: más = más brillante"],
                    ["anRes", "Resonancia", 30, "Realce en la frecuencia de corte (100 = casi silba)"],
                    ["anEnv", "Envolvente", 50, "Cuánto abre el filtro al empezar cada nota (cae en 0,3 s)"],
                    ["anAtk", "Ataque", 5, "Lo que tarda la nota en llegar arriba: de 1 ms a 2 s"],
                    ["anRel", "Liberación", 30, "Lo que tarda en apagarse al soltarla: de 10 ms a 3 s"]]
            Knob {
                required property var modelData
                objectName: "knobAnalog_" + modelData[0]
                label: modelData[1]; tip: modelData[3]
                value: root.t && root.t.cfg[modelData[0]] !== undefined ? root.t.cfg[modelData[0]] : modelData[2]
                onMoved: function (v) { root.seq.setCfg("inst", modelData[0], v) }
            }
        }
    }
    // Sinte de tablas: 8 ondas por tabla; la posición elige (y mezcla) la onda que suena
    Column {
        objectName: "instWave"
        visible: root.isWave
        height: visible ? implicitHeight : 0
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 6; topPadding: 8
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
            Text { text: "Tabla"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
            Select {
                objectName: "wtTab"; width: 220; anchors.verticalCenter: parent.verticalCenter
                options: [["0", "Básica · seno → cuadrada"], ["1", "Vocal · u o a e i"], ["2", "Metálica · peines"], ["3", "Digital · pulso estrecho"]]
                current: String(root.t && root.t.cfg.wtTab !== undefined ? root.t.cfg.wtTab : 0)
                tip: "Las 8 ondas que recorre la perilla Posición"
                onPicked: function (v) { root.seq.setCfg("inst", "wtTab", parseInt(v)) }
            }
        }
        Grid {
            columns: 3; columnSpacing: 16; rowSpacing: 4
            anchors.horizontalCenter: parent.horizontalCenter
            Repeater {
                model: [["wtPos", "Posición", 40, "Qué onda de la tabla suena (0 = la primera, 100 = la última)"],
                        ["wtEnv", "Barrido", 30, "Al empezar cada nota la posición arranca más adelante y vuelve en 0,4 s"],
                        ["wtLfo", "Movimiento", 0, "La posición oscila despacio (1 Hz) para que el sonido se mueva"],
                        ["wtAtk", "Ataque", 5, "Lo que tarda la nota en llegar arriba: de 1 ms a 2 s"],
                        ["wtRel", "Liberación", 30, "Lo que tarda en apagarse al soltarla: de 10 ms a 3 s"]]
                Knob {
                    required property var modelData
                    objectName: "knobWave_" + modelData[0]
                    label: modelData[1]; tip: modelData[3]
                    value: root.t && root.t.cfg[modelData[0]] !== undefined ? root.t.cfg[modelData[0]] : modelData[2]
                    onMoved: function (v) { root.seq.setCfg("inst", modelData[0], v) }
                }
            }
        }
    }
    // Sampler: el sonido de la pista, afinado nota a nota desde su nota raíz
    Column {
        objectName: "instSampler"
        visible: root.isSampler
        height: visible ? implicitHeight : 0
        width: root.width; spacing: 6; topPadding: 8
        readonly property string file: root.t && root.t.cfg.smpFile ? root.t.cfg.smpFile : ""
        readonly property bool looped: !!(root.t && root.t.cfg.smLoop)
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
            NeoButton {
                objectName: "smpLoad"; text: parent.parent.file ? "Cambiar sonido…" : "Cargar sonido…"; fontSize: 12; padX: 8; padY: 3
                tip: "WAV, AIFF, FLAC, OGG o MP3 (hasta 30 s): la pista lo toca en cada nota del piano roll"
                onClicked: {
                    var r = root.seq.studio.call("pickSamplerFile")
                    if (r.ok) { root.seq.setCfg("inst", "smpFile", r.path); root.seq.studio.toast("Sampler: " + r.name) }
                    else if (!r.cancelled && r.error) root.seq.studio.toast(r.error)
                }
            }
            Text {
                objectName: "smpName"; width: Math.min(260, root.width - 160); anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideMiddle; font.family: Theme.font; font.pixelSize: 13; font.weight: 600; color: Theme.ink
                text: parent.parent.file ? parent.parent.file.split(/[\\/]/).pop() : "Sin sonido: la pista no suena hasta que cargues uno"
            }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
            Text { text: "Raíz"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
                   font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
            Select {
                objectName: "smRoot"; width: 96; anchors.verticalCenter: parent.verticalCenter
                options: { var o = []; for (var n = 24; n <= 96; n++) o.push([String(n), root.noteNames[n % 12] + (Math.floor(n / 12) - 1)]); return o }
                current: String(root.t && root.t.cfg.smRoot !== undefined ? root.t.cfg.smRoot : 60)
                tip: "La nota en la que el sonido suena tal cual se grabó; las demás lo suben o bajan"
                onPicked: function (v) { root.seq.setCfg("inst", "smRoot", parseInt(v)) }
            }
            Select {
                objectName: "smLoop"; width: 130; anchors.verticalCenter: parent.verticalCenter
                options: [["0", "Sin bucle"], ["1", "Con bucle"]]
                current: parent.parent.looped ? "1" : "0"
                tip: "Con bucle, mientras la nota sigue pulsada el sonido se repite desde «Inicio bucle» hasta el final"
                onPicked: function (v) { root.seq.setCfg("inst", "smLoop", parseInt(v)) }
            }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 16
            Repeater {
                model: [["smStart", "Inicio", 0, "Desde qué punto del sonido empieza cada nota (0 = el principio)"],
                        ["smLoopAt", "Inicio bucle", 50, "Dónde empieza la parte que se repite (solo con bucle)"],
                        ["smAtk", "Ataque", 2, "Lo que tarda la nota en llegar arriba: de 1 ms a 2 s"],
                        ["smRel", "Liberación", 25, "Lo que tarda en apagarse al soltarla: de 10 ms a 3 s"]]
                Knob {
                    required property var modelData
                    objectName: "knobSampler_" + modelData[0]
                    label: modelData[1]; tip: modelData[3]
                    enabled: modelData[0] !== "smLoopAt" || !!(root.t && root.t.cfg.smLoop)
                    value: root.t && root.t.cfg[modelData[0]] !== undefined ? root.t.cfg[modelData[0]] : modelData[2]
                    onMoved: function (v) { root.seq.setCfg("inst", modelData[0], v) }
                }
            }
        }
    }
    // Arpegiador del motor: las notas pulsadas suenan de una en una, al tempo de la sesión
    Column {
        id: arpBox
        objectName: "instArp"
        readonly property int arp: root.t && root.t.cfg.arp !== undefined ? root.t.cfg.arp : 0
        visible: !!root.t && !root.t.cfg.plugin
        height: visible ? implicitHeight : 0
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 6; topPadding: 10
      Row {
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
        Text { text: "Arpegiador"; anchors.verticalCenter: parent.verticalCenter; color: Theme.ink
               font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
        Select {
            objectName: "arpMode"; width: 128; anchors.verticalCenter: parent.verticalCenter
            options: [["0", "Apagado"], ["1", "Arriba"], ["2", "Abajo"], ["3", "Arriba y abajo"], ["4", "Al azar"]]
            current: String(arpBox.arp)
            tip: "Las notas del acorde suenan una tras otra en la rejilla del tempo («Al azar» repite el mismo orden en cada render)"
            onPicked: function (v) { root.seq.setCfg("inst", "arp", parseInt(v)) }
        }
      }
      Row {
        anchors.horizontalCenter: parent.horizontalCenter; spacing: 8
        Select {
            objectName: "arpRate"; width: 118; enabled: arpBox.arp > 0; anchors.verticalCenter: parent.verticalCenter
            options: [["0", "Negras"], ["1", "Corcheas"], ["2", "Semicorcheas"], ["3", "Fusas"]]
            current: String(root.t && root.t.cfg.arpRate !== undefined ? root.t.cfg.arpRate : 2)
            tip: "Cada cuánto suena la nota siguiente, sincronizado con el tempo"
            onPicked: function (v) { root.seq.setCfg("inst", "arpRate", parseInt(v)) }
        }
        Select {
            objectName: "arpOct"; width: 90; enabled: arpBox.arp > 0; anchors.verticalCenter: parent.verticalCenter
            options: [["1", "1 octava"], ["2", "2 octavas"], ["3", "3 octavas"], ["4", "4 octavas"]]
            current: String(root.t && root.t.cfg.arpOct !== undefined ? root.t.cfg.arpOct : 1)
            tip: "Octavas que recorre el arpegio hacia arriba"
            onPicked: function (v) { root.seq.setCfg("inst", "arpOct", parseInt(v)) }
        }
        Knob { objectName: "arpGate"; label: "Duración"; enabled: arpBox.arp > 0
               value: root.t && root.t.cfg.arpGate !== undefined ? root.t.cfg.arpGate : 50
               tip: "Parte del paso que suena cada nota (100 = ligadas)"
               onMoved: function (v) { root.seq.setCfg("inst", "arpGate", v) } }
      }
    }
}
