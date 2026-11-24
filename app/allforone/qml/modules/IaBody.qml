import QtQuick
import "../theme"
import "../controls"

// Módulo Pistas con IA (Cerebro AI-1), con dos modos que no se mezclan:
//  * «Canción (audio)»: canción completa (instrumental o con voz y letra) con ACE-Step 1.5 en este
//    equipo (acestep.cpp con Vulkan, en otro proceso: ai_music.py). El WAV entra como pista de audio.
//  * «Solo MIDI»: compone solo las notas con MIDI-LLM (llama-server con Vulkan: midi_ai.py). Cada
//    instrumento entra como pista de Instrumento o Batería editable que suena con el sintetizador del
//    motor o con el VST3 que elijas; también importa archivos .mid.
// Si faltan el motor o los modelos, el módulo lo dice y ofrece descargarlos aquí mismo.
Column {
    id: root
    property var seq
    readonly property var studio: seq.studio
    readonly property var ai: seq.ai
    readonly property var c: seq.draftIa
    readonly property bool ready: !!ai.engineOk && !!ai.installed
    readonly property color accent: Theme.pcOf("ia")
    width: parent ? parent.width : 420
    spacing: 10
    readonly property bool midiMode: seq.iaMode === "midi"
    readonly property var mai: seq.midiAi
    readonly property var mc: seq.draftMidi
    readonly property bool midiReady: !!mai.engineOk && !!(mai.model && mai.model.done)
    Component.onCompleted: { seq.aiRefresh(); seq.midiRefresh() }

    function gb(b) { return (b / 1073741824).toFixed(1).replace(".", ",") + " GB" }
    function set(k, v) { seq.setCfg("ia", k, v) }
    function packName(id) { for (var i = 0; i < ai.packs.length; i++) if (ai.packs[i].id === id) return ai.packs[i].name; return id }

    // ---------------- modo: canción en audio o solo MIDI ----------------
    Row {
        width: root.width; spacing: 6
        NeoButton { text: "Canción (audio)"; pressedState: !root.midiMode
                    color: !root.midiMode ? Theme.pressedBg : Theme.button; textColor: !root.midiMode ? Theme.pressedInk : Theme.ink
                    tip: "Canción completa en WAV: instrumental o con voz y tu letra (ACE-Step)"
                    onClicked: root.seq.iaMode = "song" }
        NeoButton { text: "Solo MIDI"; pressedState: root.midiMode
                    color: root.midiMode ? Theme.pressedBg : Theme.button; textColor: root.midiMode ? Theme.pressedInk : Theme.ink
                    tip: "Solo las notas: pistas de Instrumento y Batería editables, con tus sonidos (MIDI-LLM)"
                    onClicked: { root.seq.iaMode = "midi"; root.seq.midiRefresh() } }
    }

    // ================= SOLO MIDI =================
    Column {
        visible: root.midiMode
        width: root.width; spacing: 10
        Row {
            width: root.width; spacing: 10
            Lcd { id: mchip; text: root.midiReady ? "MIDI" : "SIN IA"; anchors.verticalCenter: parent.verticalCenter }
            Text {
                width: root.width - mchip.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
                text: !root.mai.ok && root.mai.error ? root.mai.error
                    : !root.mai.engineOk ? "Falta el motor de composición (motores\\llama junto a AllForOne.exe)."
                    : !root.mai.model.done ? "Motor listo. Falta el modelo MIDI: descárgalo abajo (una sola vez)."
                    : "MIDI-LLM (Llama 3.2 1B) en tu equipo · compone notas, no audio"
            }
        }
        Rectangle {
            visible: !!root.mai.engineOk && (!root.mai.model.done || root.seq.midiDownloading)
            width: root.width; height: mdl.implicitHeight + 20
            color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
            Column {
                id: mdl
                x: 10; y: 10; width: parent.width - 20; spacing: 8
                Text { text: "Modelo MIDI · " + root.gb(root.mai.model.size || 0); color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Text {
                    width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
                    text: "Se descarga de Hugging Face (mradermacher/MIDI-LLM_Llama-3.2-1B-GGUF) a modelos\\midi junto al programa. "
                          + "Si se corta, «Reanudar» sigue donde quedó."
                }
                Row {
                    width: parent.width; spacing: 8
                    NeoButton { visible: !root.seq.midiDownloading; color: root.accent
                                text: root.mai.model.have > 0 ? "Reanudar (" + root.gb(root.mai.model.size - root.mai.model.have) + ")" : "Descargar"
                                tip: "Un archivo GGUF de " + root.gb(root.mai.model.size || 0)
                                onClicked: root.seq.midiDownload() }
                    NeoButton { visible: root.seq.midiDownloading; text: "Pausar"; onClicked: root.seq.cancelMidiDownload() }
                }
                Bar { width: parent.width; value: root.seq.midiDlProgress; visible: root.seq.midiDownloading }
                Text { visible: root.seq.midiDlMsg.length > 0; width: parent.width; wrapMode: Text.Wrap; text: root.seq.midiDlMsg
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
            }
        }
        Column {
            width: root.width; spacing: 4
            Text { text: "Describe la música (mejor en inglés)"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Field {
                width: parent.width; lines: 3
                text: root.mc.prompt || ""
                placeholder: "A cheerful latin pop song with piano, acoustic guitar, bass and drums"
                onEdited: function (v) { root.seq.setMidiCfg("prompt", v) }
            }
        }
        Row {
            width: root.width; spacing: 14
            Knob { id: mcre; label: "Creatividad"; value: root.mc.cre; tip: "Baja: más predecible. Alta: más sorpresas."
                   onMoved: function (v) { root.seq.setMidiCfg("cre", Math.round(v)) } }
            Column {
                width: root.width - mcre.width - 14; spacing: 4; anchors.verticalCenter: parent.verticalCenter
                Text { text: "Largo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
                Select { width: parent.width; options: [["1200", "Corto (unos 15 s)"], ["2046", "Medio (unos 25 s)"], ["3900", "Largo (unos 50 s)"]]
                         current: String(root.mc.len); tip: "Segundos a 120 BPM; al tempo del proyecto se estiran o encogen"
                         onPicked: function (v) { root.seq.setMidiCfg("len", Number(v)) } }
            }
        }
        Row {
            width: root.width; spacing: 8
            NeoButton {
                id: mgen
                text: root.seq.composing ? "Componiendo…" : "Componer MIDI"
                color: root.accent; textColor: "#000"; padX: 14; padY: 8; shadow: 4
                enabled: root.midiReady && !root.seq.composing
                opacity: enabled ? 1 : 0.55
                tip: root.midiReady ? "Compone en tu tarjeta gráfica; cada instrumento entra como pista editable" : "Instala el modelo MIDI primero"
                onClicked: root.seq.compose()
            }
            NeoButton { visible: root.seq.composing; text: "Cancelar"; anchors.verticalCenter: mgen.verticalCenter
                        onClicked: root.seq.cancelCompose() }
            NeoButton { text: "Importar .mid…"; anchors.verticalCenter: mgen.verticalCenter
                        tip: "Un archivo MIDI tuyo entra igual: una pista por instrumento"
                        onClicked: root.seq.openMidi("", "") }
        }
        Column {
            visible: root.seq.composing || root.seq.midiMsg.length > 0
            width: root.width; spacing: 4
            Bar { width: parent.width; value: root.seq.midiProgress; visible: root.seq.composing }
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.seq.midiMsg
                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
        }
        Text { visible: (root.mai.compositions || []).length > 0; text: "Compuestas (en datos\\media\\ia, .mid)"
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        Repeater {
            model: (root.mai.compositions || []).slice(0, 6)
            Row {
                width: root.width; spacing: 8
                Column {
                    width: parent.width - madd.width - 8; spacing: 1; anchors.verticalCenter: parent.verticalCenter
                    Text { width: parent.width; elide: Text.ElideRight; text: modelData.title
                           color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                    Text { width: parent.width; elide: Text.ElideRight; text: modelData.notes + " notas · " + Math.round(modelData.seconds) + " s"
                           color: Theme.ink; font.family: Theme.font; font.pixelSize: 11 }
                }
                NeoButton { id: madd; text: "+ Pistas"; tip: "Añadir otra vez al proyecto (una pista por instrumento)"
                            onClicked: root.seq.openMidi(modelData.path, modelData.title) }
            }
        }
    }

    // ================= CANCIÓN EN AUDIO =================
    Column {
    visible: !root.midiMode
    width: root.width; spacing: 10
    // ---------------- estado del motor ----------------
    Row {
        width: root.width; spacing: 10
        Lcd { id: chip; text: root.ready ? "LOCAL" : "SIN IA"; anchors.verticalCenter: parent.verticalCenter }
        Text {
            width: root.width - chip.width - 10; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.Wrap
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
            text: !root.ai.ok && root.ai.error ? root.ai.error
                : !root.ai.engineOk ? "Falta el motor de IA (motores\\acestep junto a AllForOne.exe)."
                : !root.ai.installed ? "Motor listo. Faltan los modelos: descárgalos abajo (una sola vez)."
                : "ACE-Step 1.5 en tu equipo · modelos «" + root.packName(root.ai.installed) + "»"
                  + (root.ai.gpu && root.ai.gpu.name ? " · " + root.ai.gpu.name + " " + root.ai.gpu.vram_gb + " GB" : "")
        }
    }

    // ---------------- modelos (solo si faltan o se están descargando) ----------------
    Rectangle {
        visible: !!root.ai.engineOk && (!root.ai.installed || root.seq.downloading)
        width: root.width; height: dl.implicitHeight + 20
        color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
        Column {
            id: dl
            x: 10; y: 10; width: parent.width - 20; spacing: 8
            Text { text: "Modelos de IA"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
            Text {
                width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
                text: "Se descargan de Hugging Face (Serveurperso/ACE-Step-1.5-GGUF) a modelos\\acestep junto al programa. "
                      + "Si se corta, «Reanudar» sigue donde quedó."
            }
            Repeater {
                model: root.ai.packs || []
                Row {
                    width: dl.width; spacing: 8
                    Column {
                        width: parent.width - btn.width - 8; spacing: 2
                        Text { text: modelData.name + " · " + root.gb(modelData.size) + (modelData.id === root.ai.recommended ? "  (recomendado para tu tarjeta)" : "")
                               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700; width: parent.width; wrapMode: Text.Wrap }
                        Text { text: modelData.desc; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; width: parent.width; wrapMode: Text.Wrap }
                    }
                    NeoButton {
                        id: btn
                        enabled: !root.seq.downloading
                        opacity: enabled ? 1 : 0.5
                        text: modelData.got > 0 ? "Reanudar (" + root.gb(modelData.size - modelData.got) + ")" : "Descargar"
                        color: modelData.id === root.ai.recommended ? root.accent : Theme.button
                        tip: "Descarga " + modelData.files.length + " archivos GGUF (" + root.gb(modelData.size) + ")"
                        onClicked: root.seq.download(modelData.id)
                    }
                }
            }
            Column {
                visible: root.seq.downloading || root.seq.dlMsg.length > 0
                width: parent.width; spacing: 4
                Bar { width: parent.width; value: root.seq.dlProgress; visible: root.seq.downloading }
                Row {
                    width: parent.width; spacing: 8
                    Text { width: parent.width - (pause.visible ? pause.width + 8 : 0); wrapMode: Text.Wrap; text: root.seq.dlMsg
                           color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    NeoButton { id: pause; visible: root.seq.downloading; text: "Pausar"; onClicked: root.seq.cancelDownload() }
                }
            }
        }
    }

    // ---------------- qué generar ----------------
    Column {
        width: root.width; spacing: 4
        Text { text: "Describe la instrumental"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        Field {
            id: prompt
            width: parent.width; lines: 3
            text: root.c.prompt || ""
            placeholder: "Piano oscuro con 808 profundo y hi-hats rápidos"
            onEdited: function (v) { root.set("prompt", v) }
        }
    }
    Row {
        width: root.width; spacing: 10
        Column {
            width: (root.width - 10) / 2; spacing: 4
            Text { text: "Estilo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: root.ai.styles && root.ai.styles.length ? root.ai.styles : [root.c.style]
                     current: root.c.style; tip: "Añade etiquetas del género a tu descripción"
                     onPicked: function (v) { root.set("style", v) } }
        }
        Column {
            width: (root.width - 10) / 2; spacing: 4
            Text { text: "Tonalidad"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width
                     options: (root.ai.keys && root.ai.keys.length ? root.ai.keys : ["Auto"]).map(function (k) {
                         return [k, k === "Auto" ? "La elige la IA" : k.replace(" major", " mayor").replace(" minor", " menor")] })
                     current: root.c.key; onPicked: function (v) { root.set("key", v) } }
        }
    }
    Row {
        width: root.width; spacing: 10
        Column {
            width: (root.width - 10) / 2; spacing: 4
            Text { text: "Duración"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: [[30, "30 s"], [60, "1 min"], [90, "1 min 30 s"], [120, "2 min"], [180, "3 min"]]
                     current: String(root.c.dur); onPicked: function (v) { root.set("dur", Number(v)) } }
        }
        Column {
            width: (root.width - 10) / 2; spacing: 4
            Text { text: "Tempo"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Select { width: parent.width; options: [["1", "El del proyecto (" + root.studio.bpm + " BPM)"], ["0", "Lo elige la IA"]]
                     current: root.c.bpmSync ? "1" : "0"; onPicked: function (v) { root.set("bpmSync", v === "1") } }
        }
    }
    Row {
        width: root.width; spacing: 14
        Knob { id: cre; label: "Creatividad"; value: root.c.cre; tip: "Baja: más predecible. Alta: más sorpresas."
               onMoved: function (v) { root.set("cre", Math.round(v)) } }
        Column {
            width: root.width - cre.width - 14; spacing: 6; anchors.verticalCenter: parent.verticalCenter
            Text { text: "Voz"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
            Row {
                spacing: 6
                NeoButton { text: "Instrumental"; pressedState: root.c.inst; color: root.c.inst ? Theme.pressedBg : Theme.button; textColor: root.c.inst ? Theme.pressedInk : Theme.ink; onClicked: root.set("inst", true) }
                NeoButton { text: "Con voz"; pressedState: !root.c.inst; color: !root.c.inst ? Theme.pressedBg : Theme.button; textColor: !root.c.inst ? Theme.pressedInk : Theme.ink; tip: "Canta la letra de abajo (vacía: la escribe la IA)"
                            onClicked: root.set("inst", false) }
            }
        }
    }
    Field {
        visible: !root.c.inst
        width: root.width; lines: 4
        text: root.c.lyrics || ""
        placeholder: "[Verso]\nTu letra aquí…   (vacía: la escribe la IA)"
        onEdited: function (v) { root.set("lyrics", v) }
    }

    // ---------------- generar ----------------
    Row {
        width: root.width; spacing: 8
        NeoButton {
            id: gen
            text: root.seq.generating ? "Generando…" : root.c.inst ? "Generar instrumental" : "Generar canción"
            color: root.accent; textColor: "#000"; padX: 14; padY: 8; shadow: 4
            enabled: root.ready && !root.seq.generating
            opacity: enabled ? 1 : 0.55
            tip: root.ready ? "Compone y sintetiza en tu tarjeta gráfica; el audio entra como pista en Pistas" : "Instala los modelos primero"
            onClicked: root.seq.generate()
        }
        NeoButton { visible: root.seq.generating; text: "Cancelar"; anchors.verticalCenter: gen.verticalCenter
                    onClicked: root.seq.cancelGenerate() }
    }
    Column {
        visible: root.seq.generating || root.seq.aiMsg.length > 0
        width: root.width; spacing: 4
        Bar { width: parent.width; value: root.seq.aiProgress; visible: root.seq.generating }
        Text { width: parent.width; wrapMode: Text.Wrap; text: root.seq.aiMsg
               color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
    }

    // ---------------- parte para el proyecto (ACE-Step «lego», modelo base) ----------------
    Rectangle {
        visible: !!root.ai.engineOk
        width: root.width; height: part.implicitHeight + 20
        color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
        Column {
            id: part
            x: 10; y: 10; width: parent.width - 20; spacing: 8
            Text { text: "Parte para el proyecto"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
            Text {
                width: parent.width; wrapMode: Text.Wrap; color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
                text: "Escucha lo que ya suena (todas las pistas) y genera un instrumento nuevo encima, al tempo del proyecto ("
                      + root.studio.bpm + " BPM)" + (root.studio.mixer && root.studio.mixer.tune.confirmed
                      ? " y en " + root.studio.mixer.tune.confirmed.key + " " + root.studio.mixer.tune.confirmed.scale : "")
                      + ". Entra como pista nueva en Pistas."
            }
            Row {
                width: parent.width; spacing: 8
                Select {
                    width: Math.min(200, parent.width * 0.4)
                    options: (root.ai.parts || []).map(function (p) { return [p, p] })
                    current: root.c.part || "Guitarra"
                    onPicked: function (v) { root.set("part", v) }
                }
                NeoButton {
                    id: pgen
                    visible: !!root.ai.partsReady
                    text: root.seq.generating ? "Generando…" : "Generar parte"
                    color: root.accent; textColor: "#000"
                    enabled: !root.seq.generating && (root.studio.tracks || []).length > 0
                    opacity: enabled ? 1 : 0.55
                    tip: (root.studio.tracks || []).length ? "Genera " + (root.c.part || "Guitarra").toLowerCase() + " acorde a las pistas del proyecto (≈ 10 s por cada 30 s en tu tarjeta)"
                                                           : "Añade antes alguna pista: la parte se genera sobre lo que ya suena"
                    onClicked: root.seq.generatePart()
                }
                NeoButton {
                    visible: !root.ai.partsReady
                    enabled: !root.seq.downloading; opacity: enabled ? 1 : 0.5
                    text: "Descargar sintetizador base (2,5 GB)"
                    tip: "Partes sobre el proyecto: necesita el modelo base de ACE-Step (el turbo no sabe hacerlo)"
                    onClicked: root.seq.download("partes")
                }
            }
        }
    }

    // ---------------- generaciones guardadas ----------------
    Text { visible: (root.ai.generations || []).length > 0; text: "Generadas (en datos\\media\\ia)"
           color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
    Repeater {
        model: (root.ai.generations || []).slice(0, 6)
        Row {
            width: root.width; spacing: 8
            Column {
                width: parent.width - add.width - 8; spacing: 1; anchors.verticalCenter: parent.verticalCenter
                Text { width: parent.width; elide: Text.ElideRight; text: modelData.title
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                Text {
                    width: parent.width; elide: Text.ElideRight
                    color: Theme.ink; font.family: Theme.font; font.pixelSize: 11
                    readonly property var m: modelData.composed || {}
                    text: [m.bpm ? m.bpm + " BPM" : "", (m.keyscale || "").replace(" major", " mayor").replace(" minor", " menor"), m.duration ? Math.round(m.duration) + " s" : "",
                           modelData.seconds ? "hecha en " + Math.round(modelData.seconds) + " s" : ""].filter(function (x) { return x }).join(" · ")
                }
            }
            NeoButton { id: add; text: "+ Pista"; tip: "Añadir otra vez al proyecto como pista de audio"
                        onClicked: if (root.seq.addGenerated(modelData.path, modelData.title)) root.studio.toast("«" + modelData.title + "» añadida a Pistas") }
        }
    }

    }

    // Barra de avance del color del módulo
    component Bar: Rectangle {
        property real value: 0
        height: 10; color: "transparent"; border.width: Theme.buttonBorder; border.color: Theme.line; radius: Theme.radius
        Rectangle { x: 2; y: 2; height: parent.height - 4; width: Math.max(0, (parent.width - 4) * Math.min(1, parent.value))
                    color: Theme.pcOf("ia"); radius: Math.max(0, Theme.radius - 2) }
    }
    // Caja de texto de varias líneas con el estilo de terminal de la plantilla
    component Field: Rectangle {
        id: fld
        property alias text: te.text
        property string placeholder: ""
        property int lines: 3
        signal edited(string v)
        height: lines * 19 + 20
        color: "#08170f"; border.width: Theme.border; border.color: Theme.line; radius: Theme.radius
        TextEdit {
            id: te
            x: 10; y: 9; width: parent.width - 20; height: parent.height - 18
            wrapMode: TextEdit.Wrap; selectByMouse: true; clip: true
            color: "#7dffb0"; font.family: "Consolas"; font.pixelSize: 14
            onTextChanged: if (activeFocus) fld.edited(text)
            Text { visible: !te.text.length; text: fld.placeholder; color: "#5fae80"; font: te.font; width: te.width; wrapMode: Text.Wrap }
        }
    }
}
