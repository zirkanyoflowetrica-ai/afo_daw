"""Análisis musical de un trozo de audio (F11, base de F7): tempo y tonalidad.

Solo lee el archivo (nunca toca el sonido: estirar y transponer lo hace el motor C++ con SoundTouch).
Tempo: pulso de los ataques (librosa) afinado con una recta sobre los tiempos encontrados, para dar
décimas de BPM. Tonalidad: cromagrama de la parte armónica comparado con los perfiles de
Krumhansl–Kessler (24 tonalidades).
"""
from __future__ import annotations

import math

import numpy as np
import soundfile as sf

NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
NAMES_ES = ("Do", "Do#", "Re", "Re#", "Mi", "Fa", "Fa#", "Sol", "Sol#", "La", "La#", "Si")
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SR = 22050
HOP = 512


def read_mono(path: str, start: float = 0.0, length: float = 0.0, max_seconds: float = 90.0) -> np.ndarray:
    """El trozo [start, start + length) del archivo en mono a 22,05 kHz (length 0 = hasta el final)."""
    info = sf.info(path)
    a = max(0, int(start * info.samplerate))
    n = int((length if length > 0 else info.duration) * info.samplerate)
    n = min(n, int(max_seconds * info.samplerate), max(0, info.frames - a))
    if n <= 0:
        return np.zeros(0, np.float32)
    x, sr = sf.read(path, start=a, frames=n, always_2d=True, dtype="float32")
    y = x.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = math.gcd(SR, int(sr))
        y = resample_poly(y, SR // g, int(sr) // g).astype(np.float32)
    return y


def _fold(bpm: float, near: float) -> float:
    """Medio o doble tiempo: el pulso que más se acerca al tempo de referencia (60–200)."""
    cands = [b for b in (bpm / 2, bpm, bpm * 2) if 60 <= b <= 200] or [bpm]
    if near and near > 0:
        return min(cands, key=lambda b: abs(math.log(b / near)))
    return min(cands, key=lambda b: abs(math.log(b / 120)))


def detect_tempo(y: np.ndarray, near: float = 0.0) -> dict:
    """{bpm, raw, confidence}: bpm ya plegado (medio o doble tiempo) hacia `near`, el tempo del proyecto.

    Tempograma de Fourier sobre la fuerza de los ataques: para cada tempo de 50 a 220 BPM (cada 0,02)
    mide cuánto se repiten los ataques a ese pulso y a sus múltiplos; el máximo da el tempo con
    centésimas, sin depender de dónde cae el primer tiempo.
    """
    import librosa
    if y.size < SR * 3:
        return {"bpm": 0.0, "raw": 0.0, "confidence": 0.0}
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP).astype(np.float64)
    env -= env.mean()
    if not np.any(env):
        return {"bpm": 0.0, "raw": 0.0, "confidence": 0.0}
    fr = SR / HOP
    n = np.arange(len(env))
    grid = np.arange(50.0, 220.0, 0.02)
    score = np.zeros(len(grid))
    for h, w in ((1, 1.0), (2, 0.5), (4, 0.25), (0.5, 0.5)):
        for i in range(0, len(grid), 400):
            f = grid[i:i + 400, None] / 60.0 * h
            score[i:i + 400] += w * np.abs(np.exp(-2j * np.pi * f * n[None] / fr) @ env)
    score /= len(env)
    k = int(np.argmax(score))
    raw = float(grid[k])
    # Confianza: cuánto destaca el pico sobre la mediana de la curva
    conf = float(np.clip((score[k] / (np.median(score) + 1e-12) - 1.5) / 4.0, 0, 1))
    bpm = _fold(raw, near)
    if abs(bpm - round(bpm)) < 0.1:          # el tempo de una canción suele ser entero
        bpm = float(round(bpm))
    return {"bpm": round(bpm, 2), "raw": round(raw, 2), "confidence": round(conf, 2)}


def detect_key(y: np.ndarray) -> dict:
    """{key, scale, name, confidence}: key en inglés (C … B), scale «Mayor» o «Menor natural»."""
    import librosa
    if y.size < SR * 2 or float(np.sqrt(np.mean(y ** 2))) < 1e-4:
        return {"key": "", "scale": "", "name": "", "confidence": 0.0}
    harm = librosa.effects.harmonic(y, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=harm, sr=SR, hop_length=HOP)
    energy = chroma.sum(axis=0)
    keep = energy > np.percentile(energy, 30)
    v = (chroma[:, keep] / (chroma[:, keep].sum(axis=0, keepdims=True) + 1e-9)).mean(axis=1)
    scores = []
    for scale, prof in (("Mayor", MAJOR), ("Menor natural", MINOR)):
        for pc in range(12):
            scores.append((float(np.corrcoef(v, np.roll(prof, pc))[0, 1]), pc, scale))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    conf = float(np.clip((best[0] - 0.4) / 0.5, 0, 1) * np.clip((best[0] - second[0]) / 0.1, 0.2, 1))
    pc, scale = best[1], best[2]
    return {"key": NOTES[pc], "scale": scale, "name": key_name(NOTES[pc], scale), "confidence": round(conf, 2)}


def key_name(key: str, scale: str) -> str:
    if key not in NOTES:
        return ""
    return NAMES_ES[NOTES.index(key)] + (" menor" if scale.startswith("Menor") else " mayor")


def semitones_between(from_key: str, from_scale: str, to_key: str, to_scale: str) -> int:
    """Semitonos que hay que mover lo que está en `from` para que quede en `to` (−6…+5).

    Mayor y menor se comparan por su relativo mayor (La menor = Do mayor): pasar de La menor a Do
    mayor no mueve nada; de La menor a Re menor, +5.
    """
    def tonic(k, s):
        pc = NOTES.index(k)
        return (pc + 3) % 12 if s.startswith("Menor") else pc
    d = (tonic(to_key, to_scale) - tonic(from_key, from_scale)) % 12
    return d - 12 if d > 5 else d


def analyze_file(path: str, start: float = 0.0, length: float = 0.0, near_bpm: float = 0.0) -> dict:
    y = read_mono(path, start, length)
    return {"tempo": detect_tempo(y, near_bpm), "key": detect_key(y), "seconds": round(y.size / SR, 2)}


# ---------------- F7: acordes y secciones de todo el proyecto ----------------
MAJ_STEPS = (0, 2, 4, 5, 7, 9, 11)
MIN_STEPS = (0, 2, 3, 5, 7, 8, 10)


def _templates() -> tuple[np.ndarray, list[tuple[int, str]]]:
    """24 tríadas (12 mayores, 12 menores): plantilla de croma con la fundamental reforzada."""
    rows, labels = [], []
    for q, third in (("maj", 4), ("min", 3)):
        for r in range(12):
            t = np.zeros(12)
            t[r] = 1.0
            t[(r + third) % 12] = 0.8
            t[(r + 7) % 12] = 0.8
            rows.append(t / np.linalg.norm(t))
            labels.append((r, q))
    return np.array(rows), labels


def chord_name(root: int, quality: str, es: bool = False) -> str:
    """Am / Lam; F / Fa."""
    return (NAMES_ES if es else NOTES)[root] + ("m" if quality == "min" else "")


def _diatonic(key: str, scale: str) -> set[tuple[int, str]]:
    """Tríadas mayores y menores de la tonalidad (sin la disminuida)."""
    if key not in NOTES:
        return set()
    t = NOTES.index(key)
    steps = MIN_STEPS if scale.startswith("Menor") else MAJ_STEPS
    out = set()
    for d in range(7):
        a, b, c = steps[d], steps[(d + 2) % 7], steps[(d + 4) % 7]
        third, fifth = (b - a) % 12, (c - a) % 12
        if fifth == 7:
            out.add(((t + a) % 12, "maj" if third == 4 else "min"))
    return out


def beat_grid(y: np.ndarray, bpm: float) -> np.ndarray:
    """Tiempos de los pulsos (s): rejilla al tempo con la fase que mejor cae sobre los ataques."""
    import librosa
    dur = y.size / SR
    if bpm <= 0 or dur <= 0:
        return np.zeros(0)
    beat = 60.0 / bpm
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    fr = SR / HOP
    best, phase = -1.0, 0.0
    for ph in np.arange(0.0, beat, 0.01):
        idx = np.round(np.arange(ph, dur, beat) * fr).astype(int)
        idx = idx[idx < len(env)]
        s = float(env[idx].sum()) if idx.size else 0.0
        if s > best:
            best, phase = s, ph
    return np.arange(phase, dur, beat)


def detect_chords(y: np.ndarray, bpm: float, key: str = "", scale: str = "", beats: np.ndarray | None = None) -> list[dict]:
    """Acordes por pulso: croma de la parte armónica contra 24 tríadas, suavizado con Viterbi (cambiar
    de acorde cuesta) y con un empujón a los acordes de la tonalidad. Tramos
    [{start, end, root, quality, name, name_es}]."""
    import librosa
    if y.size < SR * 2 or bpm <= 0:
        return []
    beats = beat_grid(y, bpm) if beats is None else beats
    if beats.size < 2:
        return []
    harm = librosa.effects.harmonic(y, margin=2.0)
    chroma = librosa.feature.chroma_cqt(y=harm, sr=SR, hop_length=HOP)
    fr = SR / HOP
    edges = np.append(beats, y.size / SR)
    T, labels = _templates()
    dia = _diatonic(key, scale)
    prior = np.array([0.08 if lab in dia else 0.0 for lab in labels])
    obs, keep = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        i = min(int(a * fr), chroma.shape[1] - 1)
        j = min(max(i + 1, int(b * fr)), chroma.shape[1])
        v = chroma[:, i:j].mean(axis=1)
        nv = float(np.linalg.norm(v))
        keep.append(nv > 1e-6)
        obs.append(T @ (v / nv) + prior if nv > 1e-6 else np.full(len(labels), -1.0))
    S = np.array(obs)                               # pulsos x 24
    # Primer tiempo del compás: el pulso (de cada 4) donde más cambia el croma. Cambiar de acorde
    # cuesta poco ahí, algo más a mitad de compás y bastante en los otros pulsos.
    V = np.array([v / (np.linalg.norm(v) + 1e-9) for v in (S - prior)])
    nov = np.r_[0.0, 1 - np.sum(V[1:] * V[:-1], axis=1)]
    down = int(np.argmax([nov[o::4].mean() if nov[o::4].size else 0 for o in range(4)]))
    n, k = S.shape
    score = S[0].copy()
    back = np.zeros((n, k), int)
    for t in range(1, n):
        pos = (t - down) % 4
        switch = 0.1 if pos == 0 else 0.25 if pos == 2 else 0.45
        best = int(np.argmax(score))
        move = score[best] - switch
        back[t] = np.where(score >= move, np.arange(k), best)
        score = np.maximum(score, move) + S[t]
    path = [int(np.argmax(score))]
    for t in range(n - 1, 0, -1):
        path.append(int(back[t][path[-1]]))
    path.reverse()
    out: list[dict] = []
    for t, c in enumerate(path):
        if not keep[t]:
            continue
        a, b = float(edges[t]), float(edges[t + 1])
        r, q = labels[c]
        if out and out[-1]["root"] == r and out[-1]["quality"] == q and abs(out[-1]["end"] - round(a, 3)) < 2e-3:
            out[-1]["end"] = round(b, 3)
        else:
            out.append({"start": round(a, 3), "end": round(b, 3), "root": r, "quality": q,
                        "name": chord_name(r, q), "name_es": chord_name(r, q, True)})
    return out


def detect_sections(y: np.ndarray, bpm: float, beats: np.ndarray | None = None, min_bars: int = 2) -> list[dict]:
    """Secciones por compases: rasgos de cada compás (croma, timbre y energía), novedad sobre la matriz
    de parecido (núcleo en damero) y sus picos como fronteras. Las que se parecen comparten letra
    (A, B, A…): no se inventan nombres como estrofa o estribillo. [{start, end, label}]"""
    import librosa
    beats = beat_grid(y, bpm) if beats is None else beats
    dur = y.size / SR
    if beats.size < 8:
        return [{"start": 0.0, "end": round(dur, 3), "label": "A"}] if dur > 0 else []
    bars = np.append(beats[::4], dur)
    if bars[0] > 0.05:
        bars = np.insert(bars, 0, 0.0)
    fr = SR / HOP
    chroma = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=SR, hop_length=HOP, n_mfcc=13)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    onset = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    m = min(chroma.shape[1], mfcc.shape[1], len(rms), len(onset))
    feats = []
    for a, b in zip(bars[:-1], bars[1:]):
        i = min(int(a * fr), m - 1)
        j = min(max(i + 1, int(b * fr)), m)
        feats.append(np.concatenate([chroma[:, i:j].mean(axis=1), mfcc[1:, i:j].mean(axis=1),
                                     [10 * np.log10(rms[i:j].mean() + 1e-9), onset[i:j].mean()]]))
    F = np.array(feats)
    F = (F - F.mean(axis=0)) / (F.std(axis=0) + 1e-6)
    nb = len(F)
    D = np.linalg.norm(F[:, None] - F[None], axis=2)
    spread = float(np.median(D[np.triu_indices(nb, 1)])) if nb > 1 else 1.0
    Ssim = np.exp(-D / (spread + 1e-9))
    w = min(4, max(1, nb // 4))
    nov = np.zeros(nb)
    for i in range(1, nb):
        lo, hi = max(0, i - w), min(nb, i + w)
        a, b, c = Ssim[lo:i, lo:i], Ssim[i:hi, i:hi], Ssim[lo:i, i:hi]
        nov[i] = (a.mean() + b.mean()) / 2 - c.mean()
    cuts = [0]
    thr = max(0.12, float(np.mean(nov[1:]) + np.std(nov[1:])))
    for i in range(min_bars, nb - min_bars + 1):
        if nov[i] >= thr and nov[i] >= nov[max(1, i - min_bars):i + min_bars].max() - 1e-9 and i - cuts[-1] >= min_bars:
            cuts.append(i)
    cuts.append(nb)
    segs = [(cuts[k], cuts[k + 1]) for k in range(len(cuts) - 1)]
    means = [F[a:b].mean(axis=0) for a, b in segs]
    letters: list[str] = []
    out = []
    for s, mu in enumerate(means):
        lab = next((letters[p] for p in range(s) if np.linalg.norm(mu - means[p]) < 0.5 * spread), None)
        if lab is None:
            lab = "ABCDEFGHIJ"[len(set(letters)) % 10]
        letters.append(lab)
        a, b = segs[s]
        out.append({"start": round(float(bars[a]), 3), "end": round(float(bars[b]), 3), "label": lab})
    return out


def analyze_mix(y: np.ndarray, near_bpm: float = 0.0) -> dict:
    """Todo el proyecto (F7): tempo, tonalidad, acordes y secciones de una mezcla mono a 22,05 kHz."""
    tempo = detect_tempo(y, near_bpm)
    key = detect_key(y)
    bpm = tempo["bpm"] or near_bpm
    beats = beat_grid(y, bpm) if bpm else np.zeros(0)
    chords = detect_chords(y, bpm, key["key"], key["scale"], beats) if bpm else []
    sections = detect_sections(y, bpm, beats) if bpm else []
    return {"tempo": tempo, "key": key, "chords": chords, "sections": sections, "seconds": round(y.size / SR, 2),
            "first_beat": round(float(beats[0]), 3) if beats.size else 0.0}


def mix_clips(parts: list[tuple], max_seconds: float = 600.0) -> np.ndarray:
    """Suma en mono (22,05 kHz) los clips de audio en su sitio: (archivo, inicio en la línea de
    tiempo, desplazamiento en el archivo, largo en el archivo, largo en la línea de tiempo, ganancia
    en dB). Sin efectos ni fader: es para analizar, no para escuchar."""
    if not parts:
        return np.zeros(0, np.float32)
    end = min(max_seconds, max(p[1] + p[4] for p in parts))
    out = np.zeros(int(end * SR) + 1, np.float32)
    for src, start, off, flen, tlen, gain in parts:
        if start >= end or tlen <= 0:
            continue
        y = read_mono(src, off, flen, max_seconds=max_seconds)
        if y.size == 0:
            continue
        if abs(flen - tlen) > 1e-3:              # clip estirado: se lleva a su largo en la línea de tiempo
            y = np.interp(np.linspace(0, y.size - 1, max(1, int(tlen * SR))), np.arange(y.size), y).astype(np.float32)
        i = int(start * SR)
        y = y[: min(y.size, out.size - i)] * np.float32(10 ** (gain / 20))
        out[i:i + y.size] += y
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    return out / peak if peak > 0 else out
