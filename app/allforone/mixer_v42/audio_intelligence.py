"""Clasificacion DESDE LA SENAL sin modelos descargados.

Es un detector de caracteristicas: no identifica con fiabilidad voz, sintes ni
instrumentos complejos. Expone una confianza y deja 'Otro' ante ambiguedad.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np
from scipy.signal import welch
from spectral_tools import classification_excerpt


@dataclass
class Identification:
    kind: str
    confidence: float
    explanation: str
    kit: bool = False


def identify_audio(x: np.ndarray, sr=44100) -> Identification:
    if not x.size or not np.any(x):
        return Identification("Otro", 0., "Silencio")
    data = classification_excerpt(x, sr)
    fs = sr
    if data.size < 1024:
        return Identification("Otro", 0.0, "Audio insuficiente para clasificar")
    f, p = welch(data, fs=fs, nperseg=min(4096, data.size))
    total = p.sum() + 1e-12
    energy = lambda lo, hi: float(p[(f >= lo) & (f < hi)].sum() / total)
    sub = energy(25, 130)
    body = energy(130, 1400)
    highs = energy(3700, 15000)
    mean_freq = float(np.dot(p, f) / total)
    # Variacion de amplitud por ventanas de 20 ms para medir transitorios.
    frame = max(16, int(fs * .02))
    frames = data[:data.size // frame * frame].reshape(-1, frame)
    env = np.sqrt(np.mean(frames.astype(np.float64)**2, axis=1) + 1e-12)
    median = float(np.median(env)) + 1e-7
    onset_strength = float(np.percentile(env, 95) / median)
    active = float(np.mean(env > (np.max(env) * .20)))
    # Impulsos detectables pero robustos frente a clips normalizados.
    pulse = onset_strength > 2.5
    if pulse and sub > .16 and body > .045 and highs > .018 and active < .90:
        return Identification("Drums", .76, f"Golpes graves y agudos combinados; espectro sub {sub:.0%}, agudos {highs:.0%}", True)
    if sub > .58 and pulse and highs < .15:
        return Identification("Kick", .80, f"Subgrave {sub:.0%}, transitorios {onset_strength:.1f}x")
    if sub > .53 and not pulse:
        return Identification("Bajo", .72, f"Graves sostenidos {sub:.0%}")
    if highs > .65 and mean_freq > 4500 and pulse:
        return Identification("Hi-hat", .78, f"Agudos {highs:.0%}, transitorios {onset_strength:.1f}x")
    if highs > .53 and mean_freq > 3500:
        return Identification("Overheads / Platillos", .66, f"Contenido agudo {highs:.0%}")
    # En un kit entero coexisten energía grave, cuerpo y agudos en golpes.
    if pulse and sub > .10 and body > .14 and highs > .08 and active < .80:
        return Identification("Drums", .73, f"Percusion multibanda, transitorios {onset_strength:.1f}x", True)
    if pulse and body > .50 and .025 < sub < .35 and .06 < highs < .45:
        return Identification("Snare", .59, "Transitorios en medios (hipotesis)")
    return Identification("Otro", .25, "Timbre ambiguo: no se afirma instrumento")
