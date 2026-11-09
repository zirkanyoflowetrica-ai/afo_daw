.pragma library
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
    if (key === "eq") return response(ctx, w, h, eqFilters(fx, d), 18, "#ffcf9e")
    if (key === "strip") return response(ctx, w, h, stripFilters(fx, d), 18, "#ffcf9e")
    if (key === "deesser") {
        var depth = v(fx, d, "range"), bp = biquad("bp", v(fx, d, "freq"), v(fx, d, "q"), 0)
        // Banda vigilada y la reducción máxima que puede aplicar (range) sobre ella
        return response(ctx, w, h, [function (f) { var g = Math.pow(10, bp(f) / 20); return 20 * Math.log(1 + (Math.pow(10, depth / 20) - 1) * g) / Math.LN10 }], 18, "#ff9f45")
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
        ctx.strokeStyle = "#ff9f45"; ctx.lineWidth = 2; ctx.stroke()
        return
    }
    if (key === "delay") {
        // Repeticiones en 2 s: el tiempo real lo informa el motor (medidor «tiempo ms», sigue al tempo)
        var ms = live && live.length > 2 && live[2] > 0 ? live[2] : v(fx, d, "time"), fb = v(fx, d, "feedback") / 100, wet = v(fx, d, "mix") / 100
        frame(ctx, w, h, [], [h - 2])
        var a = wet, n = 0
        for (var tt = ms; tt < 2000 && a > 0.01 && n < 40; tt += ms, n++) {
            var bx = w * tt / 2000, bh = (h - 6) * a
            ctx.fillStyle = v(fx, d, "pingpong") > 0.5 && n % 2 ? "#ffcf9e" : "#ffb000"
            ctx.fillRect(bx - 2, h - 2 - bh, 4, bh)
            a *= fb
        }
        ctx.fillStyle = "#5ee0b0"; ctx.fillRect(0, 2, 4, h - 4)
        return
    }
    if (key === "space") {
        var pre = v(fx, d, "predelay"), dec = Math.max(0.1, v(fx, d, "decay")), wetS = v(fx, d, "mix") / 100, span = Math.max(1, dec * 1.3)
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
    ctx.fillStyle = "#ffb000"
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
