import QtQuick
import "../theme"
import "../controls"

// Pie de «Efectos master»: master automático del V4.2 en vivo. El motor mide la sesión en memoria y
// pone en este rack una cadena real (EQ, compresión si hace falta, color y nivel final) hasta el
// objetivo del preset. Cada resultado queda como versión en «Rebobinado».
Column {
    id: root
    property var mixer
    width: parent ? parent.width : 600
    spacing: 8
    topPadding: 14

    Rectangle { width: root.width; height: 3; color: Theme.ink }
    Text { text: "MASTERIZAR AUTOMÁTICAMENTE"; color: Theme.ink
           font.family: Theme.font; font.pixelSize: 13; font.weight: 700; font.letterSpacing: 0.52 }
    Row {
        width: root.width; spacing: 8
        Select {
            id: preset
            width: root.width - 8 - go.width
            options: root.mixer.masterNames.map(function (n, i) { return [String(i), n] })
            current: String(root.mixer.masterSel)
            onPicked: function (v) { root.mixer.masterSel = +v }
        }
        NeoButton {
            id: go
            text: root.mixer.mastering ? "Masterizando…" : "MASTERIZAR"
            fontSize: 14; fontWeight: 700; padY: 8; shadow: 4
            color: root.mixer.mastering ? "#e0c0a0" : "#ff9f45"; textColor: "#000"
            tip: "Mide la sesión en el motor y pone la cadena del master en este rack (queda en Rebobinado)"
            onClicked: if (!root.mixer.mastering && !root.mixer.busy) root.mixer.masterAuto(root.mixer.masterSel)
        }
    }
    Text {
        width: root.width; wrapMode: Text.Wrap
        text: root.mixer.masterStats ? "Último: " + root.mixer.masterStats.preset + " · " + root.mixer.masterStats.lufs_i.toFixed(1) + " LUFS · pico " +
                                       root.mixer.masterStats.max_peak_db.toFixed(1) + " dB"
                                     : "Presets: " + root.mixer.masterNames.join(" · ") + ". «Según referencia» usa la canción de referencia de Mezcla IA."
        color: Theme.ink; opacity: 0.8; font.family: Theme.font; font.pixelSize: 11; font.weight: 500
    }
}
