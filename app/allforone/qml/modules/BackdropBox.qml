import QtQuick
import QtQuick.Controls.Basic as B
import "../theme"
import "../controls"

// Ver › Fondo… (F10, FLUJO_PROFESIONAL §7): Ninguno (de fábrica), Imagen o Parallax. La imagen la pone
// el usuario; se copia preparada a datos/fondos. Los clips, el editor, las tiras y los textos siguen
// sobre su superficie: el contraste no depende de la imagen (el selftest lo mide con el fondo puesto).
B.Popup {
    id: root
    property var studio
    readonly property var bd: studio ? studio.backdrop : ({})

    modal: false
    focus: true
    width: Math.min(560, (parent ? parent.width : 900) - 40)
    x: ((parent ? parent.width : 900) - width) / 2
    y: 80
    padding: 14
    closePolicy: B.Popup.CloseOnEscape | B.Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.s2; border.width: 1; border.color: Theme.line; radius: Theme.radius }

    readonly property var modes: [["none", "Ninguno", "Sin imagen: el fondo liso del tema (de fábrica)"],
                                  ["image", "Imagen", "Una imagen tuya detrás de la ventana"],
                                  ["parallax", "Parallax", "Una carpeta con capas PNG: 1.png el fondo … n.png la de delante"]]

    contentItem: Column {
        spacing: 10
        Text { text: "Fondo de la ventana"; color: Theme.ink; font.family: Theme.font; font.pixelSize: 16; font.weight: 800 }
        Text {
            width: root.availableWidth; wrapMode: Text.Wrap
            text: "Se ve detrás de las zonas, bajo las pistas del Arreglo y en el Inicio. Las capas se mueven con el scroll y el zoom del Arreglo. "
                  + "El programa no trae imágenes: elige las tuyas (se copian a datos/fondos)."
            color: Theme.inkDim; font.family: Theme.font; font.pixelSize: 12
        }
        Row {
            spacing: 8
            Repeater {
                model: root.modes
                NeoButton {
                    required property var modelData
                    objectName: "backdropMode_" + modelData[0]
                    text: modelData[1]; tip: modelData[2]
                    pressedState: root.bd.mode === modelData[0]
                    onClicked: root.studio.chooseBackdrop(modelData[0])
                }
            }
        }
        Text {
            width: root.availableWidth; wrapMode: Text.Wrap
            text: root.bd.mode === "none" ? "Sin fondo." : "En uso: «" + root.bd.name + "» (" + root.bd.layers.length
                  + (root.bd.layers.length === 1 ? " capa)" : " capas)")
            color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
        }
        Row {
            spacing: 24
            Knob { objectName: "backdropIntensity"; label: "Movimiento"; value: root.bd.intensity
                   tip: "Cuánto se desplazan las capas con el scroll del Arreglo (0 = quieto)"
                   onMoved: function (v) { root.studio.setBackdrop({ intensity: Math.round(v) }) } }
            Knob { label: "Atenuar"; value: root.bd.atten / 0.8
                   tip: "Mezcla la imagen con el fondo del tema (0–80 %)"
                   onMoved: function (v) { root.studio.setBackdrop({ atten: Math.round(v * 0.8) }) } }
            Knob { label: "Zonas"; value: root.bd.zoneAlpha / 0.15
                   tip: "Transparencia de las zonas sobre la imagen (0–15 %)"
                   onMoved: function (v) { root.studio.setBackdrop({ zoneAlpha: Math.round(v * 0.15) }) } }
            Text {
                anchors.verticalCenter: parent.verticalCenter; textFormat: Text.StyledText
                width: Math.max(140, root.availableWidth - 3 * 80 - 3 * 24); wrapMode: Text.Wrap
                text: "movimiento <b>" + root.bd.intensity + "</b><br>atenuar <b>" + root.bd.atten + " %</b><br>zonas <b>"
                      + root.studio.backdropZoneAlpha + " %</b>" + (root.bd.mode !== "none" && root.studio.backdropZoneAlpha < root.bd.zoneAlpha
                      ? " (de " + root.bd.zoneAlpha + " %: más no deja leer bien el texto con esta imagen)" : "")
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 12
            }
        }
        Row {
            spacing: 8
            NeoButton { text: "Reducir movimiento"; pressedState: !!root.bd.reduce
                        tip: "Las capas se quedan quietas (también se paran con la ventana en segundo plano)"
                        onClicked: root.studio.setBackdrop({ reduce: !root.bd.reduce }) }
            NeoButton { text: "Cerrar"; tip: "Esc"; onClicked: root.close() }
        }
    }
}
