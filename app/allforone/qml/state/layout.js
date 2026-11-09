.pragma library
// Geometría del lienzo: misma matemática que PLANTILLA_DAW.html (anchor, cableShape, nearestPin, fit).

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)) }

// Versión del lienzo: sube cuando cambian los módulos o su colocación de fábrica (el diseño guardado
// de otra versión no se aplica)
var VERSION = 3

// Módulos: [id, nombre, modelo, [x, y, ancho], alto por defecto]. De izquierda a derecha sigue el
// camino del sonido: fuentes → Pistas → Mezcla → efectos y master. Al abrir, nada se solapa (Main.settleAll).
var PANELS = [
    ["piano", "Piano roll", "Teclas S-61", [0, 0, 780], 645],
    ["inst", "Instrumentos", "Banco VST-1", [880, 0, 440], 560],
    ["drums", "Batería", "Ritmos R-16", [880, 680, 780], 640],
    ["cinta", "Grabador de cintas", "Cinta RX-2", [420, 760, 420], 471],
    ["ia", "Pistas con IA", "Cerebro AI-1", [0, 760, 380], 511],
    ["pistas", "Pistas", "Mesa MT-8", [1760, 0, 900], 441],
    ["mezcla", "Mezcla", "Consola 6C", [2760, 0, 780], 748],
    ["master", "Mezcla final", "Master VU", [4500, 0, 400], 463],
    ["audios", "Audios", "Carga A-30", [1760, 640, 760], 369],
    ["afina", "Afinador", "PSOLA AT-1", [2760, 880, 520], 701],
    ["mastia", "Master IA", "Master M-4", [4500, 560, 440], 563],
    ["antes", "Antes / Después", "A/B Comp", [3620, 920, 420], 316],
    ["fx", "Efectos", "Rack FX-96", [3620, 0, 800], 760],
    ["fxm", "Efectos master", "Rack FX-M", [5000, 0, 780], 640]
]

// Cables fijos entre módulos (orden de la interfaz web: plantilla + afo_panels.js)
var LINKS = [["piano", "inst"], ["pistas", "mezcla"], ["mezcla", "master"], ["audios", "pistas"],
             ["mezcla", "mastia"], ["mezcla", "antes"], ["mastia", "master"], ["mezcla", "fx"], ["master", "fxm"]]

function links(hidden) {
    var out = []
    for (var i = 0; i < LINKS.length; i++) {
        var f = LINKS[i][0], t = LINKS[i][1]
        if (!hidden[f] && !hidden[t]) out.push({ key: f + "-" + t, f: f, t: t })
    }
    return out
}

function defaultPin(l, end) { return end === "from" ? { side: "right", u: .21 } : { side: "left", u: .21 } }

// g = {x, y, w, h}; p = {side, u}
function anchor(g, p) {
    var u = clamp(p.u, .03, .97), px = 0, py = 0, nx = 0, ny = 0
    if (p.side === "left") { py = g.h * u; nx = -1 }
    else if (p.side === "right") { px = g.w; py = g.h * u; nx = 1 }
    else if (p.side === "top") { px = g.w * u; ny = -1 }
    else { px = g.w * u; py = g.h; ny = 1 }
    return { x: g.x + px, y: g.y + py, px: px, py: py, nx: nx, ny: ny, side: p.side, u: u }
}

function cableShape(a, b, m) {
    var d1 = Math.hypot(m.x - a.x, m.y - a.y), d2 = Math.hypot(b.x - m.x, b.y - m.y), dl = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y))
    var tx = (b.x - a.x) / dl, ty = (b.y - a.y) / dl
    var aa = clamp(d1 * .38, 18, 210), bb = clamp(d2 * .38, 18, 210)
    var c1 = { x: a.x + a.nx * aa, y: a.y + a.ny * aa }
    var c2 = { x: m.x - tx * clamp(d1 * .22, 12, 90), y: m.y - ty * clamp(d1 * .22, 12, 90) }
    var c3 = { x: m.x + tx * clamp(d2 * .22, 12, 90), y: m.y + ty * clamp(d2 * .22, 12, 90) }
    var c4 = { x: b.x + b.nx * bb, y: b.y + b.ny * bb }
    return "M" + a.x + " " + a.y + " C" + c1.x + " " + c1.y + " " + c2.x + " " + c2.y + " " + m.x + " " + m.y +
           " C" + c3.x + " " + c3.y + " " + c4.x + " " + c4.y + " " + b.x + " " + b.y
}

function nearestPin(g, x, y) {
    var rx = x - g.x, ry = y - g.y
    var opts = [{ side: "left", d: Math.abs(rx), u: ry / g.h }, { side: "right", d: Math.abs(rx - g.w), u: ry / g.h },
                { side: "top", d: Math.abs(ry), u: rx / g.w }, { side: "bottom", d: Math.abs(ry - g.h), u: rx / g.w }]
    opts.sort(function (p, q) { return p.d - q.d })
    return { side: opts[0].side, u: clamp(opts[0].u, .03, .97) }
}

// Vista que encuadra los rectángulos rs en un visor de vw x vh
function fit(rs, vw, vh) {
    var a = 1e9, b = 1e9, c = -1e9, d = -1e9
    for (var i = 0; i < rs.length; i++) {
        var r = rs[i]
        a = Math.min(a, r.x); b = Math.min(b, r.y); c = Math.max(c, r.x + r.w); d = Math.max(d, r.y + r.h)
    }
    var z = Math.max(.2, Math.min(1, vw / (c - a + 160), vh / (d - b + 160)))
    return { z: z, tx: (vw - (c - a) * z) / 2 - a * z, ty: (vh - (d - b) * z) / 2 - b * z }
}

function fmt(s) {
    s = Math.round(s)
    var m = Math.floor(s / 60), r = s % 60
    return (m < 10 ? "0" : "") + m + ":" + (r < 10 ? "0" : "") + r
}
