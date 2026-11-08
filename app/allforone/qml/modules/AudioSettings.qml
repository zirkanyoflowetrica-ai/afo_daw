import QtQuick
import "../theme"
import "../controls"

// Configuración de audio del motor (JUCE/Tracktion): driver (Windows Audio, DirectSound, ASIO…),
// dispositivo de salida y de entrada, frecuencia y búfer. Con ASIO (ASIO4ALL, FL Studio ASIO, los
// de cada interfaz) la entrada y la salida son el mismo driver y su panel propio se abre desde aquí.
Item {
    id: root
    property var studio
    property bool open: false
    property var device: ({})                  // dispositivo abierto ahora (device_info)
    property var types: []
    property string type: ""
    property var opts: ({ outputs: [], inputs: [], sample_rates: [], buffer_sizes: [], separate_io: true })
    property string output: ""
    property string input: ""
    property real rate: 0
    property int buffer: 0
    property string status: ""
    property bool failed: false
    readonly property bool asio: type === "ASIO"
    anchors.fill: parent
    visible: open
    z: 8

    function show() { load(""); status = ""; failed = false; open = true }
    function load(t) {
        var r = studio.call("audioOptions", t)
        if (!r.ok) { status = r.error; failed = true; return }
        device = r.device; types = r.types; opts = r.options; type = r.options.type
        var same = type === device.type
        output = same && opts.outputs.indexOf(device.output) >= 0 ? device.output : (opts.outputs[0] || "")
        input = same && opts.inputs.indexOf(device.input) >= 0 ? device.input : (opts.inputs[0] || "")
        rate = same ? device.sample_rate : (opts.sample_rates.indexOf(48000) >= 0 ? 48000 : (opts.sample_rates[0] || 0))
        buffer = same ? device.buffer_size : 0
    }
    function apply() {
        var r = studio.call("setAudioDevice", JSON.stringify({ type: type, output: output, input: opts.separate_io ? input : "",
                                                               sampleRate: rate, bufferSize: buffer }))
        failed = !r.ok
        device = r.device || device
        status = r.ok ? "Abierto: " + device.type + " · " + device.output + " · " + device.sample_rate + " Hz · búfer " + device.buffer_size
                      : r.error
        if (r.ok) load(type)
        studio.audioDeviceChanged()
    }
    function ms(b) { return rate > 0 ? " (" + (b / rate * 1000).toFixed(1) + " ms)" : "" }

    MouseArea { anchors.fill: parent; onClicked: root.open = false }              // fuera del cuadro: cerrar
    Rectangle { anchors.fill: parent; color: "#000"; opacity: 0.35 }

    Rectangle {
        id: box
        width: Math.min(560, root.width - 40)
        height: col.height + 28
        anchors.centerIn: parent
        color: Theme.dark ? "#24262c" : "#c9ccd2"
        border.width: 3; border.color: "#000"
        Rectangle { x: 6; y: 6; z: -1; width: parent.width; height: parent.height; color: "#000" }
        MouseArea { anchors.fill: parent }                                         // no cerrar al pulsar dentro

        Column {
            id: col
            x: 14; y: 14; width: box.width - 28
            spacing: 8
            Row {
                width: col.width
                Text { width: col.width - closeBtn.width; text: "Configuración de audio"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 18; font.weight: 700; anchors.verticalCenter: parent.verticalCenter }
                NeoButton { id: closeBtn; text: "✕"; padX: 8; padY: 2; tip: "Cerrar"; onClicked: root.open = false }
            }
            Text {
                width: col.width; wrapMode: Text.Wrap
                text: "Ahora: " + (root.device.open ? root.device.type + " · " + root.device.output + " · " + root.device.sample_rate
                      + " Hz · búfer " + root.device.buffer_size + " · " + root.device.input_channels + " entradas"
                      : "ningún dispositivo abierto")
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 600
            }

            Grid {
                columns: 2; columnSpacing: 10; rowSpacing: 8
                width: col.width
                readonly property real lw: 92
                readonly property real fw: col.width - lw - 10
                Text { width: parent.lw; height: 30; verticalAlignment: Text.AlignVCenter; text: "Driver"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Select { width: parent.fw; options: root.types; current: root.type; onPicked: function (v) { root.load(v) } }

                Text { width: parent.lw; height: 30; verticalAlignment: Text.AlignVCenter; text: root.asio ? "Driver ASIO" : "Salida"
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Select { width: parent.fw; options: root.opts.outputs.length ? root.opts.outputs : [["", "No hay dispositivos de este tipo"]]
                         current: root.output; onPicked: function (v) { root.output = v } }

                Text { visible: root.opts.separate_io; width: parent.lw; height: 30; verticalAlignment: Text.AlignVCenter; text: "Entrada"
                       color: Theme.ink; font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Select { visible: root.opts.separate_io; width: parent.fw
                         options: [["", "Ninguna (solo reproducir)"]].concat(root.opts.inputs)
                         current: root.input; onPicked: function (v) { root.input = v } }

                Text { width: parent.lw; height: 30; verticalAlignment: Text.AlignVCenter; text: "Frecuencia"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Select { width: parent.fw; options: root.opts.sample_rates.map(function (r) { return [String(r), r + " Hz"] })
                         current: String(root.rate); onPicked: function (v) { root.rate = Number(v) } }

                Text { width: parent.lw; height: 30; verticalAlignment: Text.AlignVCenter; text: "Búfer"; color: Theme.ink
                       font.family: Theme.font; font.pixelSize: 13; font.weight: 700 }
                Select { width: parent.fw
                         options: [["0", "Por defecto del driver"]].concat(root.opts.buffer_sizes.map(function (b) { return [String(b), b + " muestras" + root.ms(b)] }))
                         current: String(root.buffer); onPicked: function (v) { root.buffer = Number(v) } }
            }
            Text {
                visible: root.type === root.device.type && (root.opts.input_latency_ms > 0 || root.opts.output_latency_ms > 0)
                width: col.width; wrapMode: Text.Wrap
                text: "Latencia que informa el driver: entrada " + Number(root.opts.input_latency_ms || 0).toFixed(1)
                      + " ms · salida " + Number(root.opts.output_latency_ms || 0).toFixed(1) + " ms"
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 500
            }
            Flow {
                width: col.width; spacing: 6
                NeoButton { text: "Aplicar"; color: "#5ee0b0"; textColor: "#000"; onClicked: root.apply() }
                NeoButton {
                    visible: root.asio && root.type === root.device.type
                    text: "Panel del driver"; tip: "Panel propio del driver ASIO (en ASIO4ALL: qué entradas y salidas usa)"
                    onClicked: { var r = root.studio.call("audioControlPanel"); if (!r.ok) root.studio.toast(r.error); else root.load(root.type) }
                }
                NeoButton { text: "Releer"; tip: "Volver a buscar dispositivos (tras conectar una interfaz)"; onClicked: root.load(root.type) }
            }
            Text {
                visible: root.status.length > 0
                width: col.width; wrapMode: Text.Wrap
                text: root.status
                color: root.failed ? "#b3261e" : Theme.ink; font.family: Theme.font; font.pixelSize: 12; font.weight: 700
            }
            Text {
                width: col.width; wrapMode: Text.Wrap
                text: root.types.indexOf("ASIO") >= 0
                      ? "ASIO: AllForOne usa cualquier driver ASIO instalado (ASIO4ALL 2.x, el de tu interfaz, FL Studio ASIO…). Con ASIO la entrada y la salida van por el mismo driver; los canales se eligen en su panel."
                      : "Esta compilación no tiene ASIO."
                color: Theme.ink; font.family: Theme.font; font.pixelSize: 11; font.weight: 500; opacity: 0.85
            }
        }
    }
}
