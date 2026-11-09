pragma Singleton
import QtQuick

// Tema de la interfaz. Los temas viven en la carpeta `templates/` del programa: cada carpeta con un
// `theme.json` es un tema (copiar la carpeta a otro AllForOne = compartirlo). `apply(json)` lo carga;
// lo que el tema no dice toma el valor de AllForOne (PLANTILLA_DAW.html, tema claro).
QtObject {
    id: th

    // Valores de AllForOne (claro): los de la plantilla
    readonly property var base: ({
        name: "AllForOne", dark: false, font: "Space Grotesk",
        colors: {
            bg: "#fff1c9", pn2: "#ffe48a", ink: "#000000", line: "#000000", button: "#ffffff", header: "#fff1c9",
            input: "#ffffff", dot: "#000000", help: "#ffffff", mdl: "#e4e4e4", grip: "#ffffff", accent: "#ffc233",
            focus: "#2a6bff", pressedBg: "#000000", pressedInk: "#ffffff",
            canvas: "#fff1c9", panelHead: "#000000", panelHeadInk: "", panelBorder: "#000000", panelBody: "#fffaf0",
            chip: "#ffffff", chipInk: "#000000", shadow: "#000000",
            device: "#f6f1e4", deviceHead: "#e3dac4", deviceInk: "#1b1b1b", deviceBorder: "#000000",
            knobArc: "#ff8a1f", knobTrack: "#c9bfa6", knobValue: "#1b1b1b", chain: "#ece4cf",
            sidebar: "#fff1c9"
        },
        style: { frame: 9, border: 3, shadow: 7, buttonShadow: 3, buttonBorder: 2, radius: 0, headHeight: 44,
                 titleSize: 19, upperTitles: true, bodyTint: 0.14, canvas: "dots", knob: "metal", gridStep: 26, accentStripe: 0 },
        modules: {
            piano: "#b79bff", inst: "#ff7a70", drums: "#d4f26a", cinta: "#c9ccd2", ia: "#6ab8ff",
            pistas: "#ffc233", mezcla: "#5ee0b0", master: "#ff9ee0",
            audios: "#ff9f45", afina: "#7ae7ff", mastia: "#ff6b9a", antes: "#e6d3a3", fx: "#ffcf9e", fxm: "#ffb07a"
        }
    })
    property var spec: base                    // tema cargado (con lo que falte tomado de `base`)
    property string name: spec.name
    property bool dark: !!spec.dark

    function merge(a, b) {
        var o = {}
        for (var k in a) o[k] = a[k]
        for (var j in b) o[j] = (b[j] && typeof b[j] === "object" && !Array.isArray(b[j]) && a[j] && typeof a[j] === "object") ? merge(a[j], b[j]) : b[j]
        return o
    }
    function apply(t) { spec = merge(base, t || {}) }

    readonly property var cl: spec.colors
    readonly property var st: spec.style

    readonly property string font: spec.font
    readonly property color bg: cl.bg
    readonly property color pn2: cl.pn2                 // botón con el ratón encima
    readonly property color ink: cl.ink                 // texto general
    readonly property color line: cl.line               // bordes
    readonly property color button: cl.button
    readonly property color header: cl.header
    readonly property color input: cl.input
    readonly property color dot: cl.dot
    readonly property color help: cl.help
    readonly property color mdl: cl.mdl
    readonly property color grip: cl.grip
    readonly property color accent: cl.accent
    readonly property color focus: cl.focus
    readonly property color pressedBg: cl.pressedBg     // botón pulsado de pestañas y A/B
    readonly property color pressedInk: cl.pressedInk
    readonly property color canvas: cl.canvas           // fondo del lienzo
    readonly property color shadowColor: cl.shadow
    readonly property color sidebar: cl.sidebar
    // módulos
    readonly property color panelHead: cl.panelHead
    readonly property color panelBorder: cl.panelBorder
    readonly property color chip: cl.chip
    readonly property color chipInk: cl.chipInk
    readonly property int frame: st.frame
    readonly property int border: st.border
    readonly property int panelShadowSize: st.shadow
    readonly property int buttonShadow: st.buttonShadow
    readonly property int buttonBorder: st.buttonBorder
    readonly property int radius: st.radius
    readonly property int headHeight: st.headHeight
    readonly property int titleSize: st.titleSize
    readonly property bool upperTitles: st.upperTitles
    readonly property string canvasStyle: st.canvas     // "dots" | "grid"
    readonly property string knobStyle: st.knob         // "metal" | "arc"
    readonly property int gridStep: st.gridStep
    readonly property int accentStripe: st.accentStripe      // franja del color del módulo (temas sin marco)
    // dispositivos del rack de efectos (como los de un DAW: cara clara, cabecera, perillas de arco)
    readonly property color device: cl.device
    readonly property color deviceHead: cl.deviceHead
    readonly property color deviceInk: cl.deviceInk
    readonly property color deviceBorder: cl.deviceBorder
    readonly property color knobArc: cl.knobArc
    readonly property color knobTrack: cl.knobTrack
    readonly property color knobValue: cl.knobValue
    readonly property color chain: cl.chain

    // Colores de módulo
    readonly property var pc: spec.modules

    // Título de un módulo en su cabecera: el color del módulo, o el que diga el tema
    function headInk(c) { return cl.panelHeadInk ? cl.panelHeadInk : c }
    // Cuerpo de un módulo: el color del tema con un poco del color del módulo. El Piano roll es oscuro.
    function panelColor(id, c) {
        if (id === "piano") return dark ? "#141419" : "#1b1c22"
        var k = Qt.color(c)
        return Qt.tint(cl.panelBody, Qt.rgba(k.r, k.g, k.b, st.bodyTint))
    }
    function tint(c) { var k = Qt.color(c); return Qt.tint(cl.button, Qt.rgba(k.r, k.g, k.b, dark ? 0.35 : 0.45)) }
    // Color del módulo a partir de su id (las instancias extra «fx~2» usan el de su tipo)
    function pcOf(id) { return pc[String(id).split("~")[0]] || "#ffffff" }
    function panelShadow(c) {
        return dark ? Qt.tint(cl.shadow, Qt.rgba(Qt.color(c).r, Qt.color(c).g, Qt.color(c).b, 0.55)) : cl.shadow
    }
}
