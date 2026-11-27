import QtQuick
import "../theme"

// F10 (FLUJO_PROFESIONAL §7): fondo opcional detrás de la ventana, apagado de fábrica. Una imagen o
// capas de parallax ya preparadas en Python (backdrop.py: reducidas y con la de atrás desenfocada).
// Aquí solo se trasladan: la de atrás se mueve un 5 % y la de delante un 30 % del recorrido del
// scroll del Arreglo (el zoom cambia ese recorrido). Nada se anima con la ventana en segundo plano
// ni con «Reducir movimiento». Encima, «Atenuar» mezcla la imagen con el fondo del tema.
Item {
    id: root
    property string mode: "none"             // none | image | parallax
    property var layers: []                  // rutas de las capas (1 = la de atrás)
    property real intensity: 50              // 0 = quieto … 100
    property real atten: 50                  // 0–80 %: cuánto se mezcla con el fondo del tema
    property bool reduce: false              // «Reducir movimiento»
    property bool active: true               // la ventana está delante
    property real progress: 0                // 0..1: dónde está el scroll del Arreglo
    readonly property bool on: mode !== "none" && layers.length > 0

    visible: on
    clip: true

    // El scroll solo se sigue con la ventana delante: en segundo plano no hay trabajo
    property real p: 0
    Binding on p { value: root.progress; when: root.active && !root.reduce }

    function depth(i) { return root.layers.length <= 1 ? 0.1 : 0.05 + 0.25 * i / (root.layers.length - 1) }

    Rectangle { anchors.fill: parent; color: Theme.bg }   // debajo de capas con transparencia
    Repeater {
        model: root.on ? root.layers : []
        Image {
            required property var modelData
            required property int index
            readonly property real d: root.depth(index)
            readonly property real travel: root.width * d * root.intensity / 100
            width: root.width + travel; height: root.height
            x: -travel * root.p
            source: "file:///" + String(modelData).replace(/\\/g, "/")
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            smooth: true
            Behavior on x { enabled: root.active && !root.reduce; NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        }
    }
    Rectangle { anchors.fill: parent; color: Theme.bg; opacity: root.atten / 100 }
}
