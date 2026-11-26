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
