import QtQuick
import QtQuick.Shapes
import "../theme"
import "../controls"
import "../state/mixdata.js" as MD

// Módulo Mezcla final (Master VU): aguja VU, fader master con medidores L/R del motor y exportación.
Column {
    id: root
    property var studio
    width: parent ? parent.width : 340
    spacing: 0

    // ---------------- .vu ----------------
    Item {
        width: Math.min(root.width, 260); height: vuBox.height + 16
        Rectangle { x: 5; y: 5; width: vuBox.width; height: vuBox.height; color: "#000" }
        Rectangle {
            id: vuBox
            width: parent.width; height: Math.round((width - 6) * 115 / 200) + 6
            color: Theme.dark ? "#231e12" : "#f4e3a3"
            border.width: 3; border.color: "#000"
            Rectangle { anchors.fill: parent; anchors.margins: 3; color: "transparent"; border.width: 3
                        border.color: Theme.dark ? "#4a3d1c" : "#d9c47a" }
            Item {
                x: 3; y: 3; width: 200; height: 115
                readonly property color ink: Theme.dark ? "#f4e3a3" : "#000"
                id: dial
                transform: Scale { xScale: (vuBox.width - 6) / 200; yScale: (vuBox.width - 6) / 200 }
                Shape {
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath { strokeColor: dial.ink; strokeWidth: 2; fillColor: "transparent"
                                PathSvg { path: "M38.7 53.6A80 80 0 0 1 161.3 53.6" } }
                    ShapePath { strokeColor: "#d0221a"; strokeWidth: 6; fillColor: "transparent"
                                PathSvg { path: "M133.8 32.5A80 80 0 0 1 161.3 53.6" } }
                }
                Repeater {
                    model: [-50, -37.5, -25, -12.5, 0, 12.5, 25, 37.5, 50]
                    Rectangle {                  // marcas: de y=20 (o 24) a y=30, giradas sobre (100,105)
                        required property real modelData
                        x: 99; y: modelData % 25 ? 24 : 20
                        width: 2; height: 30 - y
                        color: dial.ink
                        transform: Rotation { origin.x: 1; origin.y: 105 - (modelData % 25 ? 24 : 20); angle: modelData }
                    }
                }
                Text { x: 100 - width / 2; y: 88 - 15 * 0.8; text: "VU"; color: dial.ink
                       font.family: Theme.font; font.pixelSize: 15; font.weight: 700 }
                Rectangle {                      // aguja: VU del motor (RMS con balística de 300 ms)
                    x: 98.5; y: 28; width: 3; height: 77
                    color: Theme.dark ? "#ffb000" : "#000"
                    transform: Rotation { origin.x: 1.5; origin.y: 77; angle: -50 + root.studio.vu * 1.05
                                          Behavior on angle { NumberAnimation { duration: 100; easing.type: Easing.OutQuad } } }
                }
                Rectangle { x: 93; y: 98; width: 14; height: 14; radius: 7; color: dial.ink }
            }
        }
    }

    // ---------------- .mrow.big ----------------
    Row {
        spacing: 18
        Row {                                    // .fad (190 px), alineado abajo como en la plantilla
            spacing: 6
            anchors.bottom: parent.bottom
            Fader { height: 190; value: root.studio.masterPos; tip: "Volumen master (70 = 0 dB)"
                    onMoved: function (v) { root.studio.setMaster(v) } }
            Meter { width: 16; height: 190; level: root.studio.playing ? MD.dbToPct(root.studio.masterDb[0]) : 0 }
            Meter { width: 16; height: 190; level: root.studio.playing ? MD.dbToPct(root.studio.masterDb[1]) : 0 }
        }
        Column {                                 // .stack
            spacing: 10
            Lcd { text: Math.round(root.studio.masterPos); fontSize: 24; width: Math.max(implicitWidth, 138) }
            Row {
                spacing: 16
                Knob { label: "Saturación"; value: root.studio.masterDrive; tip: "Saturación suave del master (tanh)"
                       onMoved: function (v) { root.studio.setMasterProcessing(v, root.studio.masterTone, root.studio.limiter) } }
                Knob { label: "Tono"; value: root.studio.masterTone; tip: "EQ inclinada: 50 = plano; ±6 dB en graves y agudos"
                       onMoved: function (v) { root.studio.setMasterProcessing(root.studio.masterDrive, v, root.studio.limiter) } }
            }
            NeoButton {
                text: "Limitador: " + (root.studio.limiter ? "activo" : "apagado")
                tip: "Limitador de seguridad del master: techo −1 dBFS, o el del preset de Master IA (también al exportar)"
                onClicked: root.studio.setMasterProcessing(root.studio.masterDrive, root.studio.masterTone, !root.studio.limiter)
            }
            NeoButton { text: "Exportar mezcla"; onClicked: root.studio.exportMix() }
        }
    }
}
