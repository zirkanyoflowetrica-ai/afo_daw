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
    // botón pulsado de pestañas y A/B: negro en claro, claro con texto negro en oscuro
    readonly property color pressedBg: dark ? "#efe9ff" : "#000000"
    readonly property color pressedInk: dark ? "#000000" : "#ffffff"

    // Colores de módulo (PC en la plantilla y en afo_panels.js)
    readonly property var pc: ({
        piano: "#b79bff", inst: "#ff7a70", drums: "#d4f26a", cinta: "#c9ccd2", ia: "#6ab8ff",
        pistas: "#ffc233", mezcla: "#5ee0b0", master: "#ff9ee0",
        audios: "#ff9f45", afina: "#7ae7ff", mastia: "#ff6b9a", antes: "#e6d3a3", fx: "#ffcf9e", fxm: "#ffb07a"
    })

    // Cuerpo de un módulo (dentro del marco de su color): crema con un 14 % de su color en claro;
    // en oscuro, 17 % de su color sobre #1b1822. El Piano roll es oscuro en los dos temas.
    function panelColor(id, c) {
        if (id === "piano") return dark ? "#141419" : "#1b1c22"
        var k = Qt.color(c)
        return dark ? Qt.tint("#1b1822", Qt.rgba(k.r, k.g, k.b, 0.17)) : Qt.tint("#fffaf0", Qt.rgba(k.r, k.g, k.b, 0.14))
    }
    // Color del módulo a partir de su id (las instancias extra «fx~2» usan el de su tipo)
    function tint(c) { var k = Qt.color(c); return Qt.tint(dark ? "#2a2533" : "#ffffff", Qt.rgba(k.r, k.g, k.b, dark ? 0.35 : 0.45)) }
    function pcOf(id) { return pc[String(id).split("~")[0]] || "#ffffff" }
    function panelShadow(c) {
        return dark ? Qt.tint("#000000", Qt.rgba(Qt.color(c).r, Qt.color(c).g, Qt.color(c).b, 0.55)) : "#000000"
    }
}
