.pragma library
// Datos y reglas del Mezclador V4.2 en la interfaz (mismos que afo_panels.js). Los valores reales
// (plantillas, tipos, masters) llegan de Python con mixer('info'); estos son los de arranque.

var D = {
    profiles: [["trap_oscuro", "Trap oscuro · contundente"], ["trap_melodico", "Trap melódico · atmosférico"], ["trap_latino", "Trap latino · urbano"],
               ["rage_hypertrap", "Rage / hypertrap · energético"], ["drill", "Drill · tenso y rítmico"], ["rap_moderno", "Rap moderno · voz dominante"],
               ["boom_bap", "Boom bap · orgánico"], ["guitar_trap", "Guitar trap · emo rap"], ["minimal_trap", "Trap minimalista · espacio y silencio"]],
    modes: ["Solo guía (audio sin cambios)", "Guía + balance muy sutil"],
    masters: ["Dinamico (-14 LUFS)", "Comercial (-11 LUFS)", "Fuerte (-8.5 LUFS)", "Plataformas (-14 LUFS, -2 dBTP)"],
    types: ["Voz principal", "Voz doble", "Voz lateral (_L/_R)", "Voz de apoyo (_B)", "Coros", "Drums", "Kick", "Snare", "Hi-hat", "Overheads / Platillos", "Toms", "Percusion",
            "Bajo", "Guitarra acustica", "Guitarra lead / solo", "Guitarra ritmica", "Piano", "Pad / Cuerdas", "Teclados / Synth", "FX", "Otro"]
}
var ROLES = ["—", "P", "B", "L", "R", "B_L", "B_R"]
var ROLE_NAME = { "—": "sin rol vocal", P: "voz principal (centro)", B: "voz de apoyo (centro)", L: "voz lateral izquierda",
                  R: "voz lateral derecha", B_L: "apoyo 50 % izquierda", B_R: "apoyo 50 % derecha" }
var VOCAL_KINDS = ["Voz principal", "Voz doble", "Voz lateral (_L/_R)", "Voz de apoyo (_B)", "Coros"]
var KIND_FOR_ROLE = { P: "Voz principal", B: "Voz de apoyo (_B)", L: "Voz lateral (_L/_R)", R: "Voz lateral (_L/_R)",
                      B_L: "Voz de apoyo (_B)", B_R: "Voz de apoyo (_B)" }

function roleTip() { return "Rol vocal: " + ROLES.map(function (r) { return r + " = " + ROLE_NAME[r] }).join(" · ") }

function kindColor(k) {
    k = String(k || "")
    if (/Voz|Coros/.test(k)) return "#ffc233"
    if (/Drum|Kick|Snare|Hi-hat|Overhead|Toms|Percu/.test(k)) return "#d4f26a"
    if (/Bajo/.test(k)) return "#ff7a70"
    if (/Guitarra|Piano|Pad|Teclado/.test(k)) return "#b79bff"
    return "#c9ccd2"
}
function kindShort(k) {
    return String(k || "").replace("Voz principal", "Voz P").replace("Voz lateral (_L/_R)", "Voz L/R")
        .replace("Voz de apoyo (_B)", "Voz _B").replace("Overheads / Platillos", "OH").replace("Guitarra ", "Gtr ")
        .replace("Teclados / Synth", "Synth").replace("Pad / Cuerdas", "Pad")
}

// Medidores: dBFS → 0..100 en escala -60..0 dB
function dbToPct(db) { return Math.max(0, Math.min(100, (db + 60) / 60 * 100)) }
// Ley de fader de la plantilla (70 = 0 dB): posición que corresponde a una ganancia en dB
// Posición del fader (70 = 0 dB) → dB, y su texto («−∞ dB» abajo del todo)
function faderToDb(v) { return v <= 0 ? -100 : 40 * Math.log(v / 70) / Math.LN10 }
function faderDbText(v) { var d = faderToDb(v); return d <= -99 ? "−∞ dB" : (d > 0.05 ? "+" : "") + d.toFixed(1) + " dB" }
function dbToFader(db) { return Math.max(0, Math.min(100, 70 * Math.pow(10, Math.max(-24, Math.min(6, db)) / 40))) }
