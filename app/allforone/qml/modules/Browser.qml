import QtQuick
import "../theme"
import "../controls"

// Navegador (X16, DISENO_DAW §3): los efectos nativos del motor agrupados por categoría y los VST3;
// o, en modo «home», los proyectos recientes de la biblioteca. Clic elige (y muestra qué hace),
// doble clic añade a la pista elegida (o abre el proyecto). El botón de abajo hace lo mismo que el
// doble clic, para quien no lo sepa.
Column {
    id: root
    property var studio
    property string mode: "fx"                  // "fx" | "home"
    width: parent ? parent.width : 320
    spacing: 8

    // Tabla de §3 (las claves del catálogo del motor); lo que el motor tenga y no esté aquí va a «Otros»
    readonly property var groups: [
        ["Dinámica", ["compressor", "glue", "transient", "gate", "limiter", "deesser"]],
        ["EQ y filtro", ["eq", "strip"]],
        ["Tono y voz", ["tune", "saturator"]],
        ["Espacio", ["space", "shimmer", "textureverb", "infinity", "delay", "multitap"]],
        ["Utilidad", ["gain", "analyzer"]],
        ["Ritmo", ["trancegate"]],
        ["Granular y espectral", ["granular", "spectral"]]]
    readonly property var catalog: studio && studio.fxBody ? studio.fxBody.catalog : []
    property string filter: ""
    property string selKey: ""                  // efecto nativo elegido («vst3:<id>» para un plugin)
    property var recent: []
    property string selPath: ""

    function desc(key) { for (var i = 0; i < catalog.length; i++) if (catalog[i].key === key) return catalog[i]; return null }
    function match(t) { return !filter || t.toLowerCase().indexOf(filter) >= 0 }
    readonly property var sections: {
        var out = [], used = {}
        for (var g = 0; g < groups.length; g++) {
            var its = []
            for (var k = 0; k < groups[g][1].length; k++) {
                var d = desc(groups[g][1][k]); used[groups[g][1][k]] = true
                if (d && match(d.name + " " + d.af + " " + d.summary)) its.push(d)
            }
            if (its.length) out.push([groups[g][0], its])
        }
        var rest = catalog.filter(function (d) { return !used[d.key] && match(d.name + " " + d.af) })
        if (rest.length) out.push(["Otros", rest])
        return out
    }
    readonly property var vst: studio ? studio.plugins.filter(function (p) { return !p.instrument && match(p.name + " " + p.vendor) }) : []
    readonly property string targetName: studio && studio.fxBody ? studio.fxBody.targetName : "—"

    // Añadir a la pista elegida (lo mismo que el doble clic)
    function add(key) {
        if (!studio) return
        if (key.indexOf("vst3:") === 0) {
            var id = key.slice(5), p = studio.plugins.filter(function (x) { return String(x.id) === id })[0]
            if (p) studio.addPluginEffect(p)
        } else studio.addEffect(key)
    }
    function reloadRecent() { if (studio) { var r = studio.call("libraryRecent"); recent = r.ok ? r.recent : [] } }
    function openRecent(path) { if (studio.project.open(path)) studio.view = "arrange" }
    onVisibleChanged: if (visible && mode === "home") reloadRecent()
    Component.onCompleted: if (mode === "home") reloadRecent()

    // ---------------- efectos ----------------
    Rectangle {
        visible: root.mode === "fx"
        width: root.width; height: tgt.implicitHeight + 12; radius: Theme.radius
        color: Theme.chip; border.width: 1; border.color: Theme.line
        Text {
            id: tgt; x: 8; y: 6; width: parent.width - 16; wrapMode: Text.Wrap
            text: "Se añade a: " + root.targetName + " (elige la pista en el Arreglo o en el Mezclador)"
            color: Theme.chipInk; font.family: Theme.font; font.pixelSize: 12; font.weight: 700
        }
    }
    Rectangle {
        visible: root.mode === "fx"
        width: root.width; height: 30; color: Theme.input; border.width: Theme.buttonBorder; border.color: search.activeFocus ? Theme.focus : Theme.line
        TextInput {
            id: search
            x: 8; width: parent.width - 16; anchors.verticalCenter: parent.verticalCenter
            color: Theme.ink; selectByMouse: true; clip: true
            font.family: Theme.font; font.pixelSize: 13
            onTextChanged: root.filter = text.toLowerCase()
            Keys.onEscapePressed: text = ""
        }
        Text { visible: !search.text; x: 8; anchors.verticalCenter: parent.verticalCenter; text: "Buscar efecto…"
               color: Theme.ink; opacity: 0.7; font.family: Theme.font; font.pixelSize: 13 }
    }
    Repeater {
        model: root.mode === "fx" ? root.sections : []
        Column {
            id: sec
            required property var modelData
            width: root.width; spacing: 2
            Head { text: sec.modelData[0] }
            Repeater {
                model: sec.modelData[1]
                Item_ {
                    required property var modelData
                    key: modelData.key
                    title: modelData.name.replace("AFO ", ""); sub: modelData.af
                }
            }
        }
    }
    Head { visible: root.mode === "fx"; text: "Plugins VST3" }
    Text {
        visible: root.mode === "fx" && !root.vst.length; width: root.width; wrapMode: Text.Wrap
        text: root.filter ? "Ningún VST3 con ese nombre." : "Sin plugins VST3 de efecto. Búscalos en «Añadir» → Buscar plugins."
        color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 12
    }
    Repeater {
        model: root.mode === "fx" ? root.vst : []
        Item_ {
            required property var modelData
            key: "vst3:" + modelData.id
            title: modelData.name; sub: modelData.vendor + " · VST3"
        }
    }
    Rectangle {                                    // qué hace lo elegido y el botón de añadir
        visible: root.mode === "fx" && !!root.selKey
        width: root.width; height: selCol.implicitHeight + 16; radius: Theme.radius
        color: Theme.panelBody; border.width: 1; border.color: Theme.line
        readonly property var d: root.desc(root.selKey)
        Column {
            id: selCol
            x: 8; y: 8; width: parent.width - 16; spacing: 6
            Text { width: parent.width; wrapMode: Text.Wrap
                   text: parent.parent.d ? parent.parent.d.summary : "Plugin VST3 externo: se abre en su propia ventana."
                   color: Theme.ink; font.family: Theme.font; font.pixelSize: 12 }
            NeoButton { text: "Añadir a " + root.targetName; fontSize: 12; padY: 3; color: Theme.accent; textColor: "#000"
                        tip: "Lo mismo que el doble clic"; onClicked: root.add(root.selKey) }
        }
    }

    // ---------------- recientes ----------------
    NeoButton {
        visible: root.mode === "home"
        text: "Abrir Inicio"; fontSize: 12; padY: 3; color: Theme.accent; textColor: "#000"
        tip: "Artistas, álbumes y canciones de la biblioteca (F4)"
        onClicked: root.studio.view = "home"
    }
    Head { visible: root.mode === "home"; text: "Recientes" }
    Text {
        visible: root.mode === "home" && !root.recent.length; width: root.width; wrapMode: Text.Wrap
        text: "Todavía no has abierto ni guardado proyectos."
        color: Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 12
    }
    Repeater {
        model: root.mode === "home" ? root.recent : []
        Item_ {
            required property var modelData
            key: "afo:" + modelData.path
            title: modelData.song || modelData.name
            sub: (modelData.artist ? modelData.artist + " · " + modelData.release + " · " : "") + modelData.modified
        }
    }

    component Head: Text {
        width: root.width; topPadding: 6
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700; font.letterSpacing: 0.6
    }
    component Item_: Rectangle {
        id: it
        property string key
        property string title
        property string sub
        readonly property bool on: key === root.selKey || key === "afo:" + root.selPath
        width: root.width; height: 34; radius: Theme.radius
        color: on ? Theme.pressedBg : ih.hovered ? Theme.pn2 : "transparent"
        HoverHandler { id: ih }
        Text { x: 8; width: parent.width * 0.62 - 8; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
               text: it.title; color: it.on ? Theme.pressedInk : Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 600 }
        Text { anchors.right: parent.right; anchors.rightMargin: 8; width: parent.width * 0.38 - 8
               horizontalAlignment: Text.AlignRight; anchors.verticalCenter: parent.verticalCenter; elide: Text.ElideRight
               text: it.sub; color: it.on ? Theme.pressedInk : Theme.ink; opacity: 0.85; font.family: Theme.font; font.pixelSize: 11 }
        ToolTipLite { text: it.key.indexOf("afo:") === 0 ? "Doble clic: abrir" : "Doble clic: añadir a " + root.targetName; show: ih.hovered }
        MouseArea {
            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            onClicked: { if (it.key.indexOf("afo:") === 0) root.selPath = it.key.slice(4); else root.selKey = it.key }
            onDoubleClicked: { if (it.key.indexOf("afo:") === 0) root.openRecent(it.key.slice(4)); else root.add(it.key) }
        }
    }
}
