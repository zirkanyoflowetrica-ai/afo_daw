import QtQuick
import "../theme"
import "../controls"

// Módulo Pistas con IA (Cerebro AI-1): genera instrumentales reales con ACE-Step 1.5 en este equipo
// (acestep.cpp con Vulkan, en otro proceso: ai_music.py). El WAV entra como pista de audio en Pistas.
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
    Component.onCompleted: seq.aiRefresh()

    function gb(b) { return (b / 1073741824).toFixed(1).replace(".", ",") + " GB" }
    function set(k, v) { seq.setCfg("ia", k, v) }
    function packName(id) { for (var i = 0; i < ai.packs.length; i++) if (ai.packs[i].id === id) return ai.packs[i].name; return id }

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
        color: "transparent"; border.width: 2; border.color: Theme.line; radius: Theme.radius
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
            text: root.seq.generating ? "Generando…" : "Generar instrumental"
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

    // Barra de avance del color del módulo
    component Bar: Rectangle {
        property real value: 0
        height: 10; color: "transparent"; border.width: 2; border.color: Theme.line; radius: Theme.radius
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
        color: "#08170f"; border.width: 3; border.color: "#000"; radius: Theme.radius
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
