.pragma library

// Colores de las lecturas (los pone el tema: Theme.lcd / Theme.lcdSoft antes de dibujar)
var pal = { lcd: "#a3acea", soft: "#c6cbef" }
function setPalette(lcd, soft) { pal = { lcd: String(lcd), soft: String(soft) } }
// Mini gráficas de las tarjetas del rack: se calculan con los MISMOS valores y fórmulas que usa el
// motor (biquads RBJ de native/src/fx/FxDsp.h, curvas del Saturator, ley del compresor). No miden
// audio: muestran lo que el efecto hará con esos parámetros.

var SR = 48000

function v(fx, desc, id) {
    for (var i = 0; i < desc.params.length; i++) if (desc.params[i].id === id) return fx.values[i] !== undefined ? fx.values[i] : desc.params[i].def
    return 0
}

// Coeficientes RBJ como FxDsp.h → magnitud en dB a la frecuencia f
function biquad(type, freq, q, gainDb) {
    freq = Math.min(Math.max(freq, 5), SR * 0.49); q = Math.max(0.025, q)
    var A = Math.pow(10, gainDb / 40), w = 2 * Math.PI * freq / SR, c = Math.cos(w), s = Math.sin(w), al = s / (2 * q)
    var n0, n1, n2, d0, d1, d2, sq
    if (type === "lp") { n0 = (1 - c) / 2; n1 = 1 - c; n2 = n0; d0 = 1 + al; d1 = -2 * c; d2 = 1 - al }
    else if (type === "hp") { n0 = (1 + c) / 2; n1 = -(1 + c); n2 = n0; d0 = 1 + al; d1 = -2 * c; d2 = 1 - al }
    else if (type === "bp") { n0 = al; n1 = 0; n2 = -al; d0 = 1 + al; d1 = -2 * c; d2 = 1 - al }
    else if (type === "bell") { n0 = 1 + al * A; n1 = -2 * c; n2 = 1 - al * A; d0 = 1 + al / A; d1 = -2 * c; d2 = 1 - al / A }
    else if (type === "ls") {
        sq = 2 * Math.sqrt(A) * al
        n0 = A * ((A + 1) - (A - 1) * c + sq); n1 = 2 * A * ((A - 1) - (A + 1) * c); n2 = A * ((A + 1) - (A - 1) * c - sq)
        d0 = (A + 1) + (A - 1) * c + sq; d1 = -2 * ((A - 1) + (A + 1) * c); d2 = (A + 1) + (A - 1) * c - sq
    } else {
        sq = 2 * Math.sqrt(A) * al
        n0 = A * ((A + 1) + (A - 1) * c + sq); n1 = -2 * A * ((A - 1) + (A + 1) * c); n2 = A * ((A + 1) + (A - 1) * c - sq)
        d0 = (A + 1) - (A - 1) * c + sq; d1 = 2 * ((A - 1) - (A + 1) * c); d2 = (A + 1) - (A - 1) * c - sq
    }
    return function (f) {
        var ww = 2 * Math.PI * f / SR, c1 = Math.cos(ww), s1 = Math.sin(ww), c2 = Math.cos(2 * ww), s2 = Math.sin(2 * ww)
        var nr = n0 + n1 * c1 + n2 * c2, ni = -(n1 * s1 + n2 * s2), dr = d0 + d1 * c1 + d2 * c2, di = -(d1 * s1 + d2 * s2)
        return 10 * Math.log((nr * nr + ni * ni) / (dr * dr + di * di)) / Math.LN10
    }
}

function eqFilters(fx, d) {
    var f = [], hp = v(fx, d, "hpf"), lp = v(fx, d, "lpf")
    if (hp > 20.5) { f.push(biquad("hp", hp, 0.7071, 0)); if (v(fx, d, "hpfSlope") > 0.5) f.push(biquad("hp", hp, 0.7071, 0)) }
    f.push(biquad("ls", v(fx, d, "lowFreq"), 0.7071, v(fx, d, "lowGain")))
    f.push(biquad("bell", v(fx, d, "mid1Freq"), v(fx, d, "mid1Q"), v(fx, d, "mid1Gain")))
    f.push(biquad("bell", v(fx, d, "mid2Freq"), v(fx, d, "mid2Q"), v(fx, d, "mid2Gain")))
    f.push(biquad("hs", v(fx, d, "highFreq"), 0.7071, v(fx, d, "highGain")))
    if (lp < 19900) f.push(biquad("lp", lp, 0.7071, 0))
    return f
}

function stripFilters(fx, d) {
    var f = []
    if (v(fx, d, "hpf") > 20.5) f.push(biquad("hp", v(fx, d, "hpf"), 0.7071, 0))
    f.push(biquad("ls", 100, 0.7071, v(fx, d, "lowGain")))
    f.push(biquad("bell", v(fx, d, "midFreq"), 1, v(fx, d, "midGain")))
    f.push(biquad("hs", 8000, 0.7071, v(fx, d, "highGain")))
    return f
}

// Fondo con rejilla; devuelve los colores
function frame(ctx, w, h, vlines, hlines) {
    ctx.reset()
    ctx.fillStyle = "#0c0a07"; ctx.fillRect(0, 0, w, h)
    ctx.strokeStyle = "rgba(255,255,255,0.09)"; ctx.lineWidth = 1
    for (var i = 0; i < vlines.length; i++) { ctx.beginPath(); ctx.moveTo(vlines[i], 0); ctx.lineTo(vlines[i], h); ctx.stroke() }
    for (var j = 0; j < hlines.length; j++) { ctx.beginPath(); ctx.moveTo(0, hlines[j]); ctx.lineTo(w, hlines[j]); ctx.stroke() }
}

function logX(f, w) { return w * Math.log(f / 20) / Math.log(1000) }

function response(ctx, w, h, filters, range, color) {
    frame(ctx, w, h, [100, 1000, 10000].map(function (f) { return logX(f, w) }), [h / 2])
    ctx.beginPath()
    for (var x = 0; x <= w; x += 2) {
        var f = 20 * Math.pow(1000, x / w), db = 0
        for (var i = 0; i < filters.length; i++) db += filters[i](f)
        var y = h / 2 - (h / 2 - 3) * Math.max(-1, Math.min(1, db / range))
        if (x) ctx.lineTo(x, y); else ctx.moveTo(x, y)
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke()
}

// Curva de transferencia entrada → salida (dB, de −60 a 0)
function transfer(ctx, w, h, fn, color) {
    var lines = [], k
    for (k = 1; k < 4; k++) lines.push(w * k / 4)
    frame(ctx, w, h, lines, lines.map(function (x) { return h * x / w }))
    ctx.strokeStyle = "rgba(255,255,255,0.18)"; ctx.beginPath(); ctx.moveTo(0, h); ctx.lineTo(w, 0); ctx.stroke()
    ctx.beginPath()
    for (var x = 0; x <= w; x += 2) {
        var inDb = -60 + 60 * x / w, out = fn(inDb)
        var y = h - h * Math.max(0, Math.min(1, (out + 60) / 60))
        if (x) ctx.lineTo(x, y); else ctx.moveTo(x, y)
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke()
}

function compCurve(thr, ratio, knee, makeup) {
    return function (x) {
        var over = x - thr, y
        if (knee > 0 && Math.abs(over) <= knee / 2) y = x + (1 / ratio - 1) * Math.pow(over + knee / 2, 2) / (2 * knee)
        else y = over > 0 ? thr + over / ratio : x
        return y + makeup
    }
}

function draw(ctx, w, h, fx, d, live) {
    var key = fx.key
    if (key === "eq") return response(ctx, w, h, eqFilters(fx, d), 18, pal.soft)
    if (key === "strip") return response(ctx, w, h, stripFilters(fx, d), 18, pal.soft)
    if (key === "deesser") {
        var depth = v(fx, d, "range"), bp = biquad("bp", v(fx, d, "freq"), v(fx, d, "q"), 0)
        // Banda vigilada y la reducción máxima que puede aplicar (range) sobre ella
        return response(ctx, w, h, [function (f) { var g = Math.pow(10, bp(f) / 20); return 20 * Math.log(1 + (Math.pow(10, depth / 20) - 1) * g) / Math.LN10 }], 18, pal.soft)
    }
    if (key === "compressor")
        return transfer(ctx, w, h, compCurve(v(fx, d, "threshold"), v(fx, d, "ratio"), v(fx, d, "knee"), v(fx, d, "makeup")), "#5ee0b0")
    if (key === "gate") {
        var thr = v(fx, d, "threshold"), range = v(fx, d, "range")
        return transfer(ctx, w, h, function (x) { return x < thr ? x + range : x }, "#5ee0b0")
    }
    if (key === "saturator") {
        var c = Math.round(v(fx, d, "character")), g = Math.pow(10, v(fx, d, "drive") / 20), mix = v(fx, d, "mix") / 100
        frame(ctx, w, h, [w / 2], [h / 2])
        ctx.beginPath()
        for (var x = 0; x <= w; x += 2) {
            var t = -1.5 + 3 * x / w, s = g * t
            var y0 = c === 0 ? Math.tanh(s) : c === 1 ? s / Math.sqrt(1 + s * s) : Math.max(-1, Math.min(1, s))
            var y = (1 - mix) * Math.max(-1, Math.min(1, t)) + mix * y0
            if (x) ctx.lineTo(x, h / 2 - (h / 2 - 3) * y); else ctx.moveTo(x, h / 2 - (h / 2 - 3) * y)
        }
        ctx.strokeStyle = pal.soft; ctx.lineWidth = 2; ctx.stroke()
        return
    }
    if (key === "delay") {
        // Repeticiones en 2 s: el tiempo real lo informa el motor (medidor «tiempo ms», sigue al tempo)
        var ms = live && live.length > 2 && live[2] > 0 ? live[2] : v(fx, d, "time"), fb = v(fx, d, "feedback") / 100, wet = v(fx, d, "mix") / 100
        frame(ctx, w, h, [], [h - 2])
        var a = wet, n = 0
        for (var tt = ms; tt < 2000 && a > 0.01 && n < 40; tt += ms, n++) {
            var bx = w * tt / 2000, bh = (h - 6) * a
            ctx.fillStyle = v(fx, d, "pingpong") > 0.5 && n % 2 ? pal.soft : pal.lcd
            ctx.fillRect(bx - 2, h - 2 - bh, 4, bh)
            a *= fb
        }
        ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, 2, 4, h - 4)
        return
    }
    if (key === "multitap") {
        // Los ecos en 2 s con el nivel de la forma elegida; los de la derecha en el otro tono
        var gap = live && live.length > 2 && live[2] > 0 ? live[2] : v(fx, d, "time"), taps = Math.round(v(fx, d, "taps")) + 1
        var shape = Math.round(v(fx, d, "shape")), dec = v(fx, d, "decay") / 100, wetM = v(fx, d, "mix") / 100, spr = v(fx, d, "spread")
        frame(ctx, w, h, [], [h - 2])
        for (var k = 0; k < taps; k++) {
            var e = shape === 0 ? k : shape === 1 ? taps - 1 - k : 0, gx = w * gap * (k + 1) / 2000
            if (gx > w) break
            var gh = (h - 6) * wetM * Math.pow(dec, e)
            ctx.fillStyle = spr > 0 && k % 2 ? pal.soft : pal.lcd
            ctx.fillRect(gx - 2, h - 2 - gh, 4, gh)
        }
        ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, 2, 4, h - 4)
        return
    }
    if (key === "trancegate") {
        // Los 16 pasos del patrón: la parte abierta de cada uno y, al sonar, el paso actual (lo dice el motor)
        var pats = ["1111111111111111", "1010101010101010", "1000100010001000", "1011011010110110",
                    "1011101110111011", "0010001000100010", "1001001010010010", "0110011001100110"]
        var pat = pats[Math.max(0, Math.min(7, Math.round(v(fx, d, "pattern"))))], len = v(fx, d, "length") / 100
        var depthT = v(fx, d, "depth") / 100, alt = v(fx, d, "stereo") > 0.5, cur = live && live.length > 2 ? live[2] - 1 : -1
        var sw = w / 16
        frame(ctx, w, h, [w / 4, w / 2, w * 3 / 4], [])
        for (var s = 0; s < 16; s++) {
            if (s === cur) { ctx.fillStyle = "rgba(94,224,176,0.25)"; ctx.fillRect(s * sw, 0, sw, h) }
            var floorH = (h - 4) * (1 - depthT)
            ctx.fillStyle = pal.soft; ctx.fillRect(s * sw + 1, h - 2 - floorH, sw - 2, floorH)
            if (pat[s] !== "1") continue
            ctx.fillStyle = alt && s % 2 ? pal.soft : pal.lcd
            ctx.fillRect(s * sw + 1, 3, Math.max(2, (sw - 2) * len), h - 5)
        }
        return
    }
    if (key === "granular") {
        // De dónde salen los granos (2 s hacia atrás desde «ahora», a la izquierda): la franja
        // distancia…distancia+dispersión, y la forma de un grano (Hann) de su tamaño; la parte
        // que suena al revés en el otro tono. Con el motor sonando, cuántos granos hay a la vez
        var dist = v(fx, d, "distance"), spray = v(fx, d, "spray"), size = v(fx, d, "size"), rev = v(fx, d, "reverse") / 100
        frame(ctx, w, h, [w * 0.25, w * 0.5, w * 0.75], [h - 2])
        var x0 = w * Math.min(1, dist / 2000), x1 = w * Math.min(1, (dist + spray + size) / 2000)
        ctx.fillStyle = "rgba(94,224,176,0.25)"; ctx.fillRect(x0, 2, Math.max(2, x1 - x0), h - 4)
        var gw = Math.max(4, w * size / 2000), live2 = live && live.length > 2 ? live[2] : 0
        ctx.beginPath()
        for (var gi = 0; gi <= 40; gi++) {
            var gs = Math.sin(Math.PI * gi / 40)
            var gpx = x0 + gw * gi / 40, gpy = h - 2 - (h - 8) * gs * gs
            if (gi) ctx.lineTo(gpx, gpy); else ctx.moveTo(gpx, gpy)
        }
        ctx.strokeStyle = pal.lcd; ctx.lineWidth = 2; ctx.stroke()
        if (rev > 0) { ctx.fillStyle = pal.soft; ctx.fillRect(x0, h - 6, gw * rev, 4) }
        if (v(fx, d, "freeze") > 0.5) { ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, 2, 4, h - 4) }
        if (live2 > 0) { ctx.fillStyle = pal.lcd; for (var gk = 0; gk < live2; gk++) ctx.fillRect(w - 6 - gk * 5, 4, 3, 8) }
        return
    }
    if (key === "spectral") {
        // Lo que hace el modo sobre un ejemplo (armónicos de 220 Hz, -6 dB por armónico) en escala
        // logarítmica; Puerta dibuja su umbral y Desplazar mueve todas las rayas los mismos Hz
        var mode = Math.round(v(fx, d, "mode")), amt = v(fx, d, "amount") / 100, sh = v(fx, d, "shift"), thrS = v(fx, d, "threshold")
        frame(ctx, w, h, [100, 1000, 10000].map(function (f) { return logX(f, w) }), [])
        for (var hk = 1; hk <= 40; hk++) {
            var f0 = mode === 1 ? 93.75 * Math.round(220 * hk / 93.75) : 220 * hk
            var fs = f0 + sh
            if (fs < 20 || fs > 20000) continue
            var lvl = -6 * Math.log(hk) / Math.LN2 - 6, sx = logX(fs, w)
            if (mode === 3 && lvl < thrS) continue
            var bh2 = (h - 4) * Math.max(0, 1 + lvl / 90), bwid = mode === 0 ? 2 + 6 * amt : 2
            ctx.fillStyle = mode === 2 ? pal.soft : pal.lcd
            ctx.fillRect(sx - bwid / 2, h - 2 - bh2, bwid, bh2)
        }
        if (mode === 3) { ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, h - 2 - (h - 4) * (1 + thrS / 90), w, 2) }
        if (mode === 4) { ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, 2, 4, h - 4) }
        return
    }
    if (key === "space" || key === "shimmer" || key === "textureverb" || key === "infinity") {
        // Curva de caída (RT60). Infinity congelada no cae: línea plana
        var pre = v(fx, d, "predelay"), dec = key === "infinity" && v(fx, d, "freeze") > 0.5 ? 1e6 : Math.max(0.1, v(fx, d, "decay")), wetS = v(fx, d, "mix") / 100, span = Math.max(1, dec * 1.3)
        frame(ctx, w, h, [w * 0.25, w * 0.5, w * 0.75], [])
        ctx.beginPath(); ctx.moveTo(0, h)
        for (var x2 = 0; x2 <= w; x2 += 2) {
            var ts = span * x2 / w, env = ts < pre / 1000 ? 0 : Math.pow(10, -3 * (ts - pre / 1000) / dec)
            ctx.lineTo(x2, h - (h - 4) * env * Math.max(0.15, wetS))
        }
        ctx.lineTo(w, h); ctx.closePath()
        ctx.fillStyle = "rgba(94,224,176,0.35)"; ctx.fill()
        ctx.strokeStyle = "#5ee0b0"; ctx.lineWidth = 2; ctx.stroke()
        return
    }
    if (key === "harmonizer") {
        // Dónde suena cada voz respecto a la nota cantada (raya central), ±12 semitonos. En la escala, con
        // la voz sonando, usa la nota real que elige el motor; si no, el intervalo nominal (3ª = 4 st)
        var semis = [0, 4, -4, 5, -5, 7, -7, 9, -9, 12, -12]
        frame(ctx, w, h, [], [h / 2])
        var det = live && live.length > 4 ? live[2] : 0
        ctx.font = "11px sans-serif"
        for (var hv = 0; hv < 2; hv++) {
            var ivx = Math.round(v(fx, d, hv ? "voice2" : "voice1"))
            if (!ivx) continue
            var tg = live && live.length > 4 ? live[3 + hv] : 0
            var st = det > 0 && tg > 0 ? tg - det : semis[ivx]
            var hy = h / 2 - (h / 2 - 6) * Math.max(-1, Math.min(1, st / 12))
            var lvlH = Math.pow(10, v(fx, d, hv ? "level2" : "level1") / 20)
            var hx = w / 2 + (w / 2 - 30) * v(fx, d, hv ? "pan2" : "pan1") / 100
            ctx.fillStyle = hv ? pal.soft : pal.lcd
            ctx.fillRect(hx - 14, hy - 3, 28 * Math.min(1.5, lvlH) + 2, 6)
            ctx.fillText(String(hv + 1), hx - 24, hy + 4)
        }
        ctx.fillStyle = pal.lcd; ctx.globalAlpha = v(fx, d, "dry") / 100 * 0.8 + 0.2
        ctx.fillRect(w / 2 - 14, h / 2 - 1, 28, 3); ctx.globalAlpha = 1
        return
    }
    if (key === "doubler") {
        // Retardo de cada copia (0–120 ms) con el margen que recorre por la variación; a la altura de su lado
        var nvD = Math.round(v(fx, d, "voices")), sep = v(fx, d, "separation"), varD = v(fx, d, "variation") / 100
        var spr = v(fx, d, "spread") / 100
        frame(ctx, w, h, [w * 25 / 120, w * 50 / 120, w * 75 / 120, w * 100 / 120], [h / 2])
        ctx.fillStyle = pal.lcd; ctx.fillRect(0, h / 2 - 2, 3, 4)
        for (var dk = 0; dk < nvD; dk++) {
            var base = sep * (1 + 0.45 * dk), span2 = (base - 10) * 0.35 * varD
            var side = (dk % 2 ? 1 : -1) * (1 - 0.35 * Math.floor(dk / 2)) * spr
            var dy = h / 2 + side * (h / 2 - 8)
            ctx.fillStyle = pal.soft; ctx.fillRect(w * (base - span2) / 120, dy - 3, Math.max(2, w * 2 * span2 / 120), 6)
            ctx.fillStyle = pal.lcd; ctx.fillRect(w * base / 120 - 1, dy - 5, 3, 10)
        }
        return
    }
    if (key === "fxlab") {
        // Cuánto suena cada rama (cruce A↔B por igual potencia, nivel) y el seco, en barras
        var c = v(fx, d, "cross") / 100
        var gA = Math.min(1, Math.SQRT2 * Math.cos(c * Math.PI / 2)) * Math.pow(10, v(fx, d, "levelA") / 20)
        var gB = Math.min(1, Math.SQRT2 * Math.sin(c * Math.PI / 2)) * Math.pow(10, v(fx, d, "levelB") / 20)
        var bars = [["A", gA], ["B", gB], ["seco", v(fx, d, "dry") / 100]]
        frame(ctx, w, h, [], [h / 2])
        ctx.font = "11px sans-serif"
        for (var bi = 0; bi < 3; bi++) {
            var bw = (w - 16) / 3, bx = 4 + bi * (bw + 4), bhh = (h - 18) * Math.min(2, bars[bi][1]) / 2
            ctx.fillStyle = bi === 2 ? pal.soft : pal.lcd
            ctx.fillRect(bx, h - 14 - Math.min(h - 18, bhh), bw, Math.min(h - 18, bhh))
            ctx.fillStyle = pal.lcd; ctx.fillText(bars[bi][0], bx + 2, h - 3)
        }
        return
    }
    if (key === "fxlab_b" || key === "fxlab_end") {         // separadores del FX Lab: sin pantalla propia
        frame(ctx, w, h, [], [])
        ctx.fillStyle = pal.lcd; ctx.font = "11px sans-serif"
        ctx.fillText(key === "fxlab_b" ? "← rama A · rama B →" : "mezcla A + B + seco", 6, h / 2 + 4)
        return
    }
    if (key === "analyzer" && live && live.length > 1) {
        frame(ctx, w, h, [100, 1000, 10000].map(function (f) { return logX(f, w) }), [])
        ctx.beginPath()
        for (var i = 0; i < live.length; i++) {
            var lx = w * i / (live.length - 1), ly = h * Math.min(1, Math.max(0, -live[i] / 90))
            if (i) ctx.lineTo(lx, ly); else ctx.moveTo(lx, ly)
        }
        ctx.strokeStyle = "#5ee0b0"; ctx.lineWidth = 2; ctx.stroke()
        return
    }
    // Ganancia y el resto: nivel de entrada y salida
    var total = v(fx, d, "input") + v(fx, d, "output")
    frame(ctx, w, h, [w / 2], [])
    ctx.fillStyle = pal.lcd
    ctx.fillRect(w / 2, h / 2 - 5, (w / 2 - 2) * Math.max(-1, Math.min(1, total / 24)), 10)
}

// Espectro de las pantallas Antes / Después (bandas en dBFS)
function spectrum(ctx, w, h, bands, color, fill, lo) {
    lo = lo || -90
    frame(ctx, w, h, [100, 1000, 10000].map(function (f) { return logX(f, w) }), [h / 3, 2 * h / 3])
    if (!bands || bands.length < 2) return
    ctx.beginPath(); ctx.moveTo(0, h)
    for (var i = 0; i < bands.length; i++) {
        var x = w * i / (bands.length - 1), y = h * Math.min(1, Math.max(0, bands[i] / lo))
        ctx.lineTo(x, y)
    }
    ctx.lineTo(w, h); ctx.closePath()
    ctx.fillStyle = fill; ctx.fill()
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke()
}
