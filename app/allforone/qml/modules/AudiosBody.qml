import QtQuick
import QtQuick.Shapes
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Módulo Audios: cada audio crea su pista y su tira. Tipo y rol editables.
Column {
    id: root
    property var mixer
    property bool dropOver: false
    width: parent ? parent.width : 600
    spacing: 0

    readonly property int missing: root.mixer.items.filter(function (i) { return i.trackId < 0 }).length

    Row {                                       // .vst
        width: root.width; spacing: 10
        bottomPadding: 10
        Lcd { id: count; text: (root.mixer.items.length < 10 ? "0" : "") + root.mixer.items.length + "/30"; anchors.verticalCenter: parent.verticalCenter }
        Text {
            width: root.width - count.width - 10
            anchors.verticalCenter: parent.verticalCenter
            wrapMode: Text.Wrap; textFormat: Text.StyledText
            text: "Cada audio crea su <b>pista</b> y, con ella, su <b>tira en la consola</b>. Tipo y rol se deducen del nombre (_L, _R, _B…) y se pueden corregir aquí, en Pistas o en la consola."
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500; lineHeight: 1.2
        }
    }

    Item {                                      // .afo-drop
        width: root.width; height: dropCol.height + 24 + 10
        Rectangle {
            width: parent.width; height: parent.height - 10
            color: root.dropOver ? "#fff" : (Theme.dark ? Qt.rgba(1, 1, 1, 0.06) : Qt.rgba(1, 1, 1, 0.45))
            Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2
                        border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.1) : Qt.rgba(1, 1, 1, 0.33) }
            Shape {
                anchors.fill: parent
                ShapePath {
                    strokeColor: Theme.dark ? "#efe9ff" : "#000"; strokeWidth: 3; fillColor: "transparent"
                    strokeStyle: ShapePath.DashLine; dashPattern: [3, 1.7]; capStyle: ShapePath.FlatCap
                    startX: 1.5; startY: 1.5
                    PathLine { x: root.width - 1.5; y: 1.5 }
                    PathLine { x: root.width - 1.5; y: dropCol.height + 24 - 1.5 }
                    PathLine { x: 1.5; y: dropCol.height + 24 - 1.5 }
                    PathLine { x: 1.5; y: 1.5 }
                }
            }
            Column {
                id: dropCol
                y: 12; width: parent.width
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: '<font face="Segoe UI Symbol">⬇</font> Arrastra aquí tus audios'; textFormat: Text.RichText
                       color: root.dropOver ? "#000" : Theme.ink; font.family: Theme.font; font.pixelSize: 14; font.weight: 700 }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; topPadding: 2
                       text: "WAV · AIFF · FLAC · OGG · MP3 — hasta 30"
                       color: root.dropOver ? "#000" : Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
            }
        }
    }

    Flow {                                      // .tb
        width: root.width; spacing: 6; bottomPadding: 10 + 3
        NeoButton { text: "+ Audios"; onClicked: root.mixer.addFromDialog() }
        NeoButton { text: root.mixer.reference ? "↺ Referencia: " + root.mixer.reference.name : "+ Referencia (opcional)"; onClicked: root.mixer.pickReference() }
        NeoButton { visible: root.missing > 0; text: "⇢ Crear " + root.missing + " pista(s)"; onClicked: root.mixer.makeMissing() }
        NeoButton { visible: root.mixer.items.length > 0; text: "Vaciar lista"; onClicked: root.mixer.clear() }
    }

    Rectangle {                                 // .afo-stems
        width: root.width
        height: Math.min(260, list.height + 6)
        color: "#16130e"; border.width: 3; border.color: "#000"
        Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 2; border.color: "#4a4030"; z: 2 }
        Flickable {
            x: 3; y: 3; width: parent.width - 6; height: parent.height - 6
            contentHeight: list.height; clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: list
                width: parent.width
                Repeater {
                    model: root.mixer.items
                    Rectangle {                 // .afo-stem
                        id: stem
                        required property var modelData
                        required property int index
                        width: list.width; height: 34
                        color: "#2b2720"
                        Rectangle { width: 8; height: parent.height; color: MD.kindColor(stem.modelData.kind) }
                        Rectangle { y: parent.height - 2; width: parent.width; height: 2; color: "#000" }
                        Row {
                            x: 14; width: parent.width - 20; height: parent.height - 2
                            spacing: 6
                            readonly property real nameW: Math.max(80, width - 24 - 136 - 62 - 66 - 26 - 5 * 6)
                            Text { width: 24; anchors.verticalCenter: parent.verticalCenter
                                   text: (stem.index < 9 ? "0" : "") + (stem.index + 1)
                                   color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 12; font.weight: 500 }
                            Row {
                                width: parent.nameW; spacing: 4; anchors.verticalCenter: parent.verticalCenter
                                Text { id: nm; width: Math.min(implicitWidth, parent.width - (conv.visible ? conv.width + 4 : 0))
                                       text: stem.modelData.name; elide: Text.ElideRight
                                       color: "#f3e7c4"; font.family: Theme.font; font.pixelSize: 12; font.weight: 700 }
                                Rectangle { id: conv; visible: !!stem.modelData.note; width: ct.implicitWidth + 8; height: 12
                                            anchors.verticalCenter: parent.verticalCenter; color: "#ffb000"
                                            Text { id: ct; anchors.centerIn: parent; text: "conv."; color: "#000"
                                                   font.family: Theme.font; font.pixelSize: 9; font.weight: 700 } }
                            }
                            Select {
                                width: 136; anchors.verticalCenter: parent.verticalCenter
                                options: root.mixer.data.types; current: stem.modelData.kind
                                fontSize: 11; fontWeight: 700; padX: 4; padY: 2
                                fill: "#16130e"; ink: "#f3e7c4"
                                onPicked: function (v) { root.mixer.setItemKind(stem.index, v) }
                            }
                            Select {
                                width: 62; anchors.verticalCenter: parent.verticalCenter
                                options: MD.ROLES; current: stem.modelData.role || "—"
                                fontSize: 11; fontWeight: 700; padX: 4; padY: 2
                                fill: "#16130e"; ink: "#f3e7c4"; tip: MD.roleTip()
                                onPicked: function (v) { root.mixer.setItemRole(stem.index, v) }
                            }
                            Text { width: 66; anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignRight
                                   text: stem.modelData.trackId >= 0 ? "▸ pista " + (root.trackNumber(stem.modelData.trackId)) : "sin pista"
                                   color: "#bdb398"; font.family: Theme.font; font.pixelSize: 11; font.weight: 500 }
                            NeoButton { text: "✕"; fontSize: 11; padX: 5; padY: 0; shadow: 2; anchors.verticalCenter: parent.verticalCenter
                                        tip: "Quitar " + stem.modelData.name + " de la lista (no borra el archivo)"
                                        onClicked: root.mixer.removeItem(stem.index) }
                        }
                    }
                }
                DashedBox {
                    visible: root.mixer.items.length === 0
                    x: 8; width: list.width - 16; height: visible ? implicitHeight : 0
                    strokeColor: "#f3e7c4"; textColor: "#f3e7c4"; fill: "transparent"
                    text: "Sin audios todavía."
                }
                Item { width: 1; height: root.mixer.items.length === 0 ? 8 : 0 }
            }
        }
    }

    Text {                                      // .hint
        width: root.width; topPadding: 8 + 10
        wrapMode: Text.Wrap
        text: "Quitar un audio de esta lista no borra nada de tu disco. Si borras su pista, el audio sigue aquí y puedes volver a crearla."
        color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
    }

    property var studio
    function trackNumber(id) {
        for (var i = 0; i < studio.tracks.length; i++) if (studio.tracks[i].id === id) return i + 1
        return "?"
    }
}
