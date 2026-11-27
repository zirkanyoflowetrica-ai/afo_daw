pragma Singleton
import QtQuick

// Tema de la interfaz. Los temas viven en la carpeta `templates/` del programa: cada carpeta con un
// `theme.json` es un tema (copiar la carpeta a otro AllForOne = compartirlo). `apply(json)` lo carga;
// lo que el tema no dice toma el valor de la familia (Oscuro).
QtObject {
    id: th

    // Familia de temas (docs/FLUJO_PROFESIONAL.md §6): Oscuro (de fábrica), Grafito y Claro comparten
    // matiz, acento ámbar, colores con significado, colores de pista, letra y forma; un theme.json solo
    // cambia la luz (superficies, texto, acento). Lo que no diga sale de aquí (Oscuro).
    readonly property var base: ({
        name: "Oscuro", dark: true, font: "Space Grotesk",
        colors: {
            // superficies 0 (fondo) · 1 (zona) · 2 (tarjeta) · 3 (control), texto y acento
            s0: "#181612", s1: "#201e1a", s2: "#282622", s3: "#32302c",
            inkDim: "#a7a49f", inkOnAccent: "#111111", inkOnColor: "#111111",
            bg: "#181612", pn2: "#3c3a35", ink: "#eae7e3", line: "#0d0c0a", button: "#32302c", header: "#201e1a",
            input: "#181612", dot: "#26241f", help: "#282622", mdl: "#32302c", grip: "#4a4842", accent: "#f0b135",
            focus: "#ffd27a", pressedBg: "#f0b135", pressedInk: "#111111",
            canvas: "#181612", panelHead: "#201e1a", panelHeadInk: "#eae7e3", panelBorder: "#0d0c0a", panelBody: "#201e1a",
            chip: "#282622", chipInk: "#a7a49f", shadow: "#000000",
            device: "#282622", deviceHead: "#32302c", deviceInk: "#eae7e3", deviceBorder: "#0d0c0a",
            knobArc: "#f0b135", knobTrack: "#181612", knobValue: "#eae7e3", chain: "#201e1a",
            lcd: "#f0b135", lcdSoft: "#f6d08a", lcdBg: "#141310",
            screen: "#141310", screenCard: "#282622", screenHover: "#32302c", screenLine: "#3e3b36",
            screenInk: "#eae7e3", screenDim: "#a7a49f",
            sidebar: "#201e1a", tipBg: "#32302c", tipInk: "#eae7e3",
            // colores con significado: iguales en todos los temas
            rec: "#e6443d", recInk: "#ff8a80", ai: "#b699eb", meterOk: "#6ed274", meterWarn: "#edcc48", meterPeak: "#f9423d",
            ledOff: "#4a1d1a",
            // teclado (piano roll y afinador) y perillas metálicas (temas de usuario con knob: "metal")
            keyWhite: "#f2efe9", keyWhite2: "#d9d5ce", keyBlack: "#16140f", keyBlackDown: "#55524c", keyLabel: "#55524c",
            metalDark: "#5a5a5a", metalLight: "#e6e6e6"
        },
        // 12 colores de pista: mismo brillo y croma (OKLCH L 0,72 C 0,11), solo cambia el matiz
        tracks: ["#e18881", "#da915f", "#c49f4d", "#a9ab54", "#77b779", "#4abba1",
                 "#35b9c0", "#57afe0", "#83a3ea", "#a996e2", "#c88ccb", "#d887ae"],
        style: { frame: 0, border: 1, shadow: 0, buttonShadow: 0, buttonBorder: 1, radius: 3, headHeight: 32,
                 titleSize: 13, upperTitles: false, bodyTint: 0.0, canvas: "grid", knob: "arc", gridStep: 24, accentStripe: 3 },
        // Colores de las zonas y funciones: sacados de los colores de pista (la IA, del color «IA»)
        modules: {
            piano: "#83a3ea", inst: "#e18881", drums: "#a9ab54", cinta: "#da915f", ia: "#b699eb",
            pistas: "#c49f4d", mezcla: "#4abba1", master: "#d887ae",
            audios: "#57afe0", afina: "#35b9c0", mastia: "#b699eb", antes: "#c88ccb", fx: "#a996e2", fxm: "#a996e2"
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
    readonly property color canvas: cl.canvas           // fondo de la ventana
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
    readonly property color lcd: cl.lcd                 // cifras de la pantalla LCD, aguja del VU y lecturas
    readonly property color lcdSoft: cl.lcdSoft
    readonly property color chain: cl.chain
    // Pantallas oscuras (pads, rejilla de pasos, lista de audios, rejilla de notas): fondo, tarjeta,
    // tarjeta con el ratón encima, borde interior, texto y texto secundario
    readonly property color screen: cl.screen
    readonly property color screenCard: cl.screenCard
    readonly property color screenHover: cl.screenHover
    readonly property color screenLine: cl.screenLine
    readonly property color screenInk: cl.screenInk
    readonly property color screenDim: cl.screenDim
    // familia (§6): superficies, texto secundario, texto sobre acento / sobre color, significados
    readonly property color s0: cl.s0
    readonly property color s1: cl.s1
    readonly property color s2: cl.s2
    readonly property color s3: cl.s3
    readonly property color panelBody: cl.panelBody     // cuerpo de los paneles (Navegador, Inicio, laboratorio)
    readonly property color inkDim: cl.inkDim
    readonly property color inkOnAccent: cl.inkOnAccent
    readonly property color inkOnColor: cl.inkOnColor
    readonly property color rec: cl.rec
    readonly property color recInk: cl.recInk
    readonly property color ai: cl.ai
    readonly property color meterOk: cl.meterOk
    readonly property color meterWarn: cl.meterWarn
    readonly property color meterPeak: cl.meterPeak
    readonly property color ledOff: cl.ledOff
    readonly property color lcdBg: cl.lcdBg
    readonly property color tipBg: cl.tipBg
    readonly property color tipInk: cl.tipInk
    readonly property color keyWhite: cl.keyWhite
    readonly property color keyWhite2: cl.keyWhite2
    readonly property color keyBlack: cl.keyBlack
    readonly property color keyBlackDown: cl.keyBlackDown
    readonly property color keyLabel: cl.keyLabel
    readonly property color metalDark: cl.metalDark
    readonly property color metalLight: cl.metalLight
    readonly property var tracks: spec.tracks
    function trackColor(i) { var n = tracks.length; return tracks[((i % n) + n) % n] }
    // «rgba(r,g,b,a)» para los Canvas (fillStyle / strokeStyle)
    function rgba(c, a) { var k = Qt.color(c); return "rgba(" + Math.round(k.r * 255) + "," + Math.round(k.g * 255) + "," + Math.round(k.b * 255) + "," + a + ")" }

    // Colores de módulo
    readonly property var pc: spec.modules

    // Título de un módulo en su cabecera: el color del módulo, o el que diga el tema
    function headInk(c) { return cl.panelHeadInk ? cl.panelHeadInk : c }
    // Cuerpo de un módulo: el color del tema con un poco del color del módulo. El Piano roll es oscuro.
    function panelColor(id, c) {
        if (id === "piano") return cl.screen
        var k = Qt.color(c)
        return Qt.tint(cl.panelBody, Qt.rgba(k.r, k.g, k.b, st.bodyTint))
    }
    // F10: con un fondo puesto, las superficies de las zonas dejan ver un poco (0–15 %) de la imagen.
    // Los controles, clips, tiras y textos no usan esto: siguen opacos.
    property real surfaceAlpha: 1
    function veil(c) { var k = Qt.color(c); return surfaceAlpha >= 1 ? k : Qt.rgba(k.r, k.g, k.b, surfaceAlpha) }
    function tint(c) { var k = Qt.color(c); return Qt.tint(cl.button, Qt.rgba(k.r, k.g, k.b, dark ? 0.35 : 0.45)) }
    // Color del módulo a partir de su id (las instancias extra «fx~2» usan el de su tipo)
    function pcOf(id) { return pc[String(id).split("~")[0]] || cl.accent }
    function panelShadow(c) {
        return dark ? Qt.tint(cl.shadow, Qt.rgba(Qt.color(c).r, Qt.color(c).g, Qt.color(c).b, 0.55)) : cl.shadow
    }
}
