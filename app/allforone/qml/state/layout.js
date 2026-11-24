.pragma library
// Utilidades de formato compartidas (el lienzo de módulos se retiró el 24-11-2026: ver docs/DISENO_DAW.md).

// Segundos → «mm:ss»
function fmt(s) {
    s = Math.round(s)
    var m = Math.floor(s / 60), r = s % 60
    return (m < 10 ? "0" : "") + m + ":" + (r < 10 ? "0" : "") + r
}
