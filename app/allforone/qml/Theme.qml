pragma Singleton
import QtQuick

// Colores y medidas de PLANTILLA_DAW.html (tema claro) y de afo_theme_dark.css (tema oscuro).
QtObject {
    property bool dark: false

    readonly property string font: "Space Grotesk"
    readonly property color bg: dark ? "#121017" : "#fff1c9"
    readonly property color pn2: dark ? "#3a3346" : "#ffe48a"          // botón con el ratón encima
    readonly property color ink: dark ? "#efe9ff" : "#000000"          // texto general
    readonly property color line: "#000000"                            // bordes y sombras duras
    readonly property color button: dark ? "#2a2533" : "#ffffff"
    readonly property color header: dark ? "#17141d" : "#fff1c9"
    readonly property color input: dark ? "#1b1822" : "#ffffff"
    readonly property color dot: dark ? Qt.rgba(1, 1, 1, 0.18) : "#000000"
    readonly property color help: dark ? "#1d1a24" : "#ffffff"
    readonly property color mdl: dark ? "#2a2533" : "#e4e4e4"
    readonly property color grip: dark ? "#3a3446" : "#ffffff"
    readonly property color accent: "#ffc233"
    readonly property color focus: "#2a6bff"

    // Colores de módulo (PC en la plantilla y en afo_panels.js)
    readonly property var pc: ({
        piano: "#b79bff", inst: "#ff7a70", drums: "#d4f26a", cinta: "#c9ccd2", ia: "#6ab8ff",
        pistas: "#ffc233", mezcla: "#5ee0b0", master: "#ff9ee0",
        audios: "#ff9f45", afina: "#7ae7ff", mastia: "#ff6b9a", antes: "#e6d3a3"
    })

    // Superficie de un módulo: su color en claro; en oscuro, 17 % de su color sobre #1b1822
    function panelColor(id, c) {
        if (id === "piano") return dark ? "#141419" : "#1b1c22"
        if (id === "cinta") return dark ? "#24262c" : "#c9ccd2"
        return dark ? Qt.tint("#1b1822", Qt.rgba(Qt.color(c).r, Qt.color(c).g, Qt.color(c).b, 0.17)) : c
    }
    function panelShadow(c) {
        return dark ? Qt.tint("#000000", Qt.rgba(Qt.color(c).r, Qt.color(c).g, Qt.color(c).b, 0.55)) : "#000000"
    }
}
