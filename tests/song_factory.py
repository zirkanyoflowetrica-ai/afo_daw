"""Canciones COMPLETAS sintéticas para las pruebas: batería, bajo, armonía y voces (principal, dobles,
laterales y coros) de varios géneros, con la desafinación de una toma real.

Todo se genera con numpy (sin descargas ni archivos externos) y es reproducible (semilla fija). Las voces
tienen formantes de vocal, vibrato, ataques, respiraciones entre frases y cada nota desafinada al azar
entre 15 y 45 cents, para que el afinador tenga trabajo de verdad.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]
# Formantes (frecuencia, ancho de banda) de las vocales «a» y «o»
VOWELS = {"a": [(800, 80), (1200, 90), (2500, 120)], "o": [(450, 70), (800, 80), (2830, 120)]}


@dataclass
class Voice:
    name: str            # nombre del stem (decide el tipo en el mezclador: Voz_Lead, Voz_Doble, Voz_L, Coros…)
    low: int             # nota MIDI más grave de su registro
    high: int
    level: float = 0.25
    interval: int = 0    # grados de la escala por encima de la melodía principal (armonías)
    seed: int = 0
    vowel: str = "a"
    late_ms: float = 0.0  # retraso humano (dobles)


@dataclass
class Genre:
    key: str             # tónica (C … B, como el analizador)
    minor: bool
    bpm: float
    voices: list[Voice]
    parts: list[str]     # instrumentos: kick, snare, clap, hats, drums, 808, bass, piano, pad, synth, gtr, gtrlead
    progression: list[int] = field(default_factory=lambda: [0, 5, 2, 6])   # grados (0 = I)
    seconds: float = 16.0

    @property
    def scale(self) -> str:
        return "Menor natural" if self.minor else "Mayor"

    @property
    def tonic(self) -> int:
        return NOTES.index(self.key)

    @property
    def steps(self) -> list[int]:
        return MINOR if self.minor else MAJOR


GENRES = {
    # Trap: 808 largo, charles en semicorcheas, voz grave de barítono y su doble
    "trap": Genre("F", True, 140.0, [Voice("Voz_Lead", 41, 55, 0.28, seed=1, vowel="o"),
                                      Voice("Voz_Doble", 41, 55, 0.16, seed=2, vowel="o", late_ms=18)],
                  ["kick", "clap", "hats", "808", "pad"], [0, 5, 3, 6]),
    # Balada pop: piano y cuerdas, voz aguda de soprano con vibrato marcado y coros a una tercera
    "balada": Genre("C", False, 72.0, [Voice("Voz_Lead", 62, 77, 0.24, seed=3),
                                        Voice("Coros", 62, 79, 0.12, interval=2, seed=4, vowel="o")],
                    ["drums", "bass", "piano", "pad"], [0, 4, 5, 3]),
    # Rock: guitarras con distorsión, batería completa, voz de tenor y armonías a izquierda y derecha
    "rock": Genre("E", True, 120.0, [Voice("Voz_Lead", 52, 67, 0.27, seed=5),
                                      Voice("Voz_L", 52, 69, 0.12, interval=2, seed=6),
                                      Voice("Voz_R", 52, 69, 0.12, interval=4, seed=7)],
                  ["drums", "bass", "gtr", "gtrlead"], [0, 5, 2, 6]),
    # Reguetón: dembow (bombo en negras, caja desplazada), bajo, sintetizador, voz media y voz _B
    "regueton": Genre("A", True, 95.0, [Voice("Voz_Lead", 55, 69, 0.26, seed=8),
                                         Voice("Voz_B", 55, 69, 0.13, interval=0, seed=9, late_ms=12)],
                      ["kick", "snare", "hats", "bass", "synth"], [0, 5, 2, 6]),
}

# Más géneros (laboratorio de instrumentales y pruebas que no recorren GENRES enteros)
MAS_GENEROS = {
    # Hip hop boom bap: batería completa a 90, bajo y piano, voz media
    "hiphop": Genre("D", True, 90.0, [Voice("Voz_Lead", 48, 62, 0.26, seed=12)],
                    ["drums", "bass", "piano"], [0, 3, 5, 4]),
    # Lo-fi: tempo lento, piano y pad, bajo suave, voz susurrada
    "lofi": Genre("F", False, 75.0, [Voice("Voz_Lead", 57, 69, 0.18, seed=13, vowel="o")],
                  ["drums", "bass", "piano", "pad"], [0, 5, 3, 4]),
    # House: bombo a negras, clap, charles, bajo y sintetizador
    "house": Genre("G", True, 124.0, [Voice("Voz_Lead", 55, 69, 0.24, seed=14)],
                   ["kick", "clap", "hats", "bass", "synth"], [0, 5, 2, 6]),
    # Cinematográfica: pad de cuerdas, piano, bajo y batería, coros graves
    "cinematico": Genre("D", True, 80.0, [Voice("Coros", 50, 65, 0.15, seed=15, vowel="o")],
                        ["drums", "pad", "piano", "bass"], [0, 5, 3, 4]),
}
TODOS = {**GENRES, **MAS_GENEROS}


def hz(m):
    return 440.0 * 2 ** ((np.asarray(m, dtype=float) - 69) / 12)


def _env(n, a=0.01, r=0.08):
    e = np.ones(n)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na: e[:na] = np.linspace(0, 1, na)
    if nr: e[-nr:] *= np.linspace(1, 0, nr)
    return e


def _place(buf, x, at):
    i = int(at * SR)
    if i >= len(buf): return
    x = x[: len(buf) - i]
    buf[i:i + len(x)] += x


def _chord(g: Genre, degree: int, octave: int) -> list[int]:
    s = g.steps
    base = 12 * (octave + 1) + g.tonic
    return [base + s[(degree + k) % 7] + 12 * ((degree + k) // 7) for k in (0, 2, 4)]


def _resonate(x, formants):
    """Filtro de formantes (resonadores de dos polos en paralelo)."""
    from scipy.signal import lfilter
    y = np.zeros_like(x)
    for f, bw in formants:
        r = np.exp(-np.pi * bw / SR)
        th = 2 * np.pi * f / SR
        y += lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)
    return y


def _sing(freq, formants, rng):
    """Voz: pulsos glotales (diente de sierra limitado en banda) por formantes, con un poco de aliento."""
    ph = 2 * np.pi * np.cumsum(freq) / SR
    nh = int(min(40, SR / 2 / max(60.0, float(np.max(freq)))))
    src = sum(np.sin(k * ph) / k ** 1.2 for k in range(1, nh))
    return _resonate(src + 0.02 * rng.standard_normal(len(freq)), formants)


def melody(g: Genre, v: Voice, beats: float):
    """Frases de la voz: notas de la escala dentro del registro, siguiendo los acordes; silencios para respirar."""
    rng = np.random.default_rng(100 + 7 * list(TODOS.values()).index(g))     # misma melodía para todas las voces
    beat = 60.0 / g.bpm
    notes, t = [], 0.5 * beat
    bar = 0
    while t < g.seconds - 1.0:
        chord = _chord(g, g.progression[bar % len(g.progression)], 4)
        phrase_end = t + 3 * beat * 4 / 4
        while t < phrase_end and t < g.seconds - 1.0:
            dur = beat * rng.choice([0.5, 1.0, 1.0, 1.5, 2.0])
            pc = rng.choice(chord + [chord[0] + g.steps[1]])
            notes.append([t, dur, int(pc)])
            t += dur
        t += beat * rng.choice([0.5, 1.0])       # respiración
        bar += 1
    # al registro de la voz
    out = []
    for t0, d, m in notes:
        while m < v.low: m += 12
        while m > v.high: m -= 12
        out.append([t0, d, m])
    return out


def _harmonise(g: Genre, m: int, degrees: int) -> int:
    if not degrees: return m
    rel = (m - g.tonic) % 12
    idx = min(range(7), key=lambda i: abs(g.steps[i] - rel))
    up = idx + degrees
    return m - g.steps[idx] + g.steps[up % 7] + 12 * (up // 7)


def voice_track(g: Genre, v: Voice, n: int):
    rng = np.random.default_rng(1000 + v.seed)
    lead = melody(g, v, 0)
    x = np.zeros(n)
    truth = []          # (inicio, fin, nota de la escala, desafinación en cents)
    for t0, d, m in lead:
        m = _harmonise(g, m, v.interval)
        while m < v.low: m += 12
        while m > v.high: m -= 12
        cents = rng.choice([-1, 1]) * rng.uniform(15, 45)
        t0 += v.late_ms / 1000 + rng.uniform(-0.01, 0.01)
        k = int(d * SR * 0.92)
        tt = np.arange(k) / SR
        vib = 0.25 * np.clip(tt / 0.35 - 0.3, 0, 1) * np.sin(2 * np.pi * 5.6 * tt)       # vibrato que entra tarde
        scoop = -0.6 * np.exp(-tt / 0.04)                                                  # entrada desde abajo
        f = hz(m + cents / 100 + vib + scoop)
        y = _sing(f, VOWELS[v.vowel], rng) * _env(k, 0.03, 0.06)
        _place(x, y, t0)
        truth.append((t0, t0 + d * 0.92, m, cents))
    x *= v.level / (np.max(np.abs(x)) + 1e-9)
    return x, truth


def drums(g: Genre, n: int, parts: set):
    beat = 60.0 / g.bpm
    out = {}
    nb = int(g.seconds / beat)
    def kick():
        k = int(0.35 * SR); t = np.arange(k) / SR
        return 0.9 * np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
    def snare():
        k = int(0.25 * SR); t = np.arange(k) / SR; rng = np.random.default_rng(5)
        return 0.5 * (0.6 * rng.standard_normal(k) * np.exp(-t * 18) + 0.4 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25))
    def hat():
        k = int(0.06 * SR); t = np.arange(k) / SR; rng = np.random.default_rng(6)
        from scipy.signal import lfilter
        return 0.25 * lfilter([1, -1], [1], rng.standard_normal(k)) * np.exp(-t * 70)
    K, S, H = kick(), snare(), hat()
    if "drums" in parts:          # kit completo en un stem
        x = np.zeros(n)
        for b in range(nb):
            if b % 2 == 0: _place(x, K, b * beat)
            else: _place(x, S, b * beat)
            _place(x, 0.7 * H, b * beat); _place(x, 0.5 * H, (b + 0.5) * beat)
        out["Drums"] = x
    if "kick" in parts:
        x = np.zeros(n)
        for b in range(nb):
            if g.bpm >= 130:     # trap: bombo sincopado
                if b % 4 in (0,) or (b % 8 == 2): _place(x, K, b * beat)
                if b % 8 == 5: _place(x, K, (b + 0.5) * beat)
            else:
                _place(x, K, b * beat)
        out["Kick"] = x
    if "snare" in parts:          # dembow: 3+3+2 en semicorcheas
        x = np.zeros(n)
        for b in range(nb):
            _place(x, S, (b + 0.75) * beat)
            if b % 2 == 1: _place(x, S, (b + 0.5) * beat)
        out["Snare"] = x
    if "clap" in parts:
        x = np.zeros(n)
        for b in range(nb):
            if b % 4 == 2: _place(x, S * 1.1, b * beat)
        out["Clap"] = x
    if "hats" in parts:
        x = np.zeros(n)
        sub = 4 if g.bpm >= 130 else 2
        for i in range(nb * sub):
            _place(x, H * (0.9 if i % sub == 0 else 0.6), i * beat / sub)
        out["HiHat"] = x
    return out


def tonal(g: Genre, n: int, parts: set):
    beat = 60.0 / g.bpm
    bar = 4 * beat
    out = {}
    def synth(freqs, k, kind):
        t = np.arange(k) / SR
        y = np.zeros(k)
        for f in freqs:
            if kind == "piano":
                y += sum(np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.5 + h)) / h for h in range(1, 7))
            elif kind == "pad":
                y += sum(np.sin(2 * np.pi * f * (1 + dt) * t) for dt in (-0.003, 0, 0.003))
            elif kind == "synth":
                y += sum(np.sign(np.sin(2 * np.pi * f * h * t)) / h ** 2 for h in (1, 2))
            elif kind == "gtr":
                y += np.tanh(4 * sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, 8)))
        return y
    nbars = int(np.ceil(g.seconds / bar))
    for part, kind, octv in (("piano", "piano", 4), ("pad", "pad", 3), ("synth", "synth", 4), ("gtr", "gtr", 3)):
        if part not in parts: continue
        x = np.zeros(n)
        for b in range(nbars):
            ch = _chord(g, g.progression[b % len(g.progression)], octv)
            if part == "gtr": ch = [ch[0], ch[0] + 7, ch[0] + 12]        # quintas (power chord)
            if part in ("piano", "synth", "gtr"):
                for q in range(4 if part != "gtr" else 8):
                    step = beat if part != "gtr" else beat / 2
                    k = int(step * SR * 0.95)
                    _place(x, synth(hz(ch), k, kind) * _env(k, 0.005, 0.03), b * bar + q * step)
            else:
                k = int(bar * SR)
                _place(x, synth(hz(ch), k, kind) * _env(k, 0.3, 0.3), b * bar)
        name = {"piano": "Piano", "pad": "Pad_Cuerdas", "synth": "Synth", "gtr": "Guitarra_Ritmica"}[part]
        out[name] = 0.3 * x / (np.max(np.abs(x)) + 1e-9)
    if "gtrlead" in parts:
        rng = np.random.default_rng(11)
        x = np.zeros(n)
        for b in range(nbars):
            ch = _chord(g, g.progression[b % len(g.progression)], 5)
            for q in range(4):
                k = int(beat * SR * 0.9); f = hz(int(rng.choice(ch)))
                t = np.arange(k) / SR
                _place(x, np.tanh(3 * np.sin(2 * np.pi * f * t * (1 + 0.004 * np.sin(2 * np.pi * 6 * t)))) * _env(k, 0.01, 0.05), b * bar + q * beat)
        out["Guitarra_Lead"] = 0.2 * x / (np.max(np.abs(x)) + 1e-9)
    if "bass" in parts or "808" in parts:
        x = np.zeros(n)
        for b in range(nbars):
            root = _chord(g, g.progression[b % len(g.progression)], 1)[0]
            if "808" in parts:
                k = int(bar * SR * 0.9); t = np.arange(k) / SR
                _place(x, np.tanh(2 * np.sin(2 * np.pi * hz(root) * t)) * np.exp(-t * 0.8), b * bar)
            else:
                for q in range(4):
                    k = int(beat * SR * 0.9); t = np.arange(k) / SR
                    _place(x, (np.sin(2 * np.pi * hz(root) * t) + 0.3 * np.sin(4 * np.pi * hz(root) * t)) * _env(k, 0.005, 0.05),
                           b * bar + q * beat)
        out["808" if "808" in parts else "Bajo"] = 0.45 * x / (np.max(np.abs(x)) + 1e-9)
    return out


def write_song(genre: str, folder: Path) -> dict:
    """Escribe los stems de un género en `folder`. Devuelve {paths, genre, truth (por voz)}."""
    g = TODOS[genre]
    folder.mkdir(parents=True, exist_ok=True)
    n = int(g.seconds * SR)
    stems = {}
    stems.update(drums(g, n, set(g.parts)))
    stems.update(tonal(g, n, set(g.parts)))
    truth = {}
    for v in g.voices:
        x, tr = voice_track(g, v, n)
        stems[v.name] = x
        truth[v.name] = tr
    paths = []
    for name, x in stems.items():
        p = folder / f"{genre.capitalize()}_{name}.wav"
        sf.write(str(p), np.stack([x, x], 1).astype("float32"), SR)
        paths.append(str(p))
    return {"paths": paths, "genre": g, "truth": truth}


def pitch_error_cents(y, g: Genre, sr: int = SR, fmin=70.0, fmax=1000.0) -> float:
    """Desviación media (cents) de la voz respecto a la nota de la escala más cercana, en tramos con voz."""
    import librosa
    y = np.asarray(y, dtype=float)
    if y.ndim > 1: y = y.mean(axis=1)
    f0, voiced, prob = librosa.pyin(y.astype(np.float32), fmin=fmin, fmax=fmax, sr=sr, frame_length=2048, hop_length=512)
    ok = voiced & np.isfinite(f0) & (prob > 0.5)
    if ok.sum() < 20: return float("nan")
    m = 69 + 12 * np.log2(f0[ok] / 440.0)
    allowed = np.array([g.tonic + s + 12 * o for o in range(0, 11) for s in g.steps])
    d = np.abs(m[:, None] - allowed[None, :]).min(axis=1) * 100
    return float(np.median(d))
