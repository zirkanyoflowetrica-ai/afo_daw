"""Descomposicion APROXIMADA de un stem de bateria usando mascaras TF complementarias.

No es separacion neuronal ni aislamiento limpio de cada instrumento.
Las cinco salidas suman aproximadamente la entrada sin procesar; la asignacion
se basa en bandas espectrales, transitorios y sostenimiento temporal.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft, istft

PARTS = ("Kick", "Snare", "Hi-hat", "Toms", "Overheads / Platillos")


def _soft_gauss(f, center, spread):
    return np.exp(-0.5 * (np.log2((f + 25) / (center + 25)) / spread) ** 2)


def split_drums(x: np.ndarray, sample_rate=44100) -> dict[str, np.ndarray]:
    """Separa kits de bateria en 5 sub-bandas solapadas sin inventar contenido.

    Input: canales x muestras, 1 o 2 canales. Preserva sincronizacion.
    Los filtros son mascaras normalizadas que vuelven a sumar 1, por lo que
    la reconstruccion sin efectos es casi identidad (salvo error STFT).
    """
    x = np.asarray(x, dtype=np.float32)
    if x.ndim != 2 or x.shape[0] not in (1, 2) or x.shape[1] < 2048:
        raise ValueError("Drums debe contener al menos 2048 muestras mono/estereo")
    n = x.shape[1]
    # Ventanas de tiempo acotadas para no cargar STFT de canciones completas.
    result = {part: np.zeros_like(x) for part in PARTS}
    chunk_n = 44100 * 12
    # Dividir sin fundidos: cada fragmento conserva su suma reconstructiva.
    for pos in range(0, n, chunk_n):
        end = min(pos + chunk_n, n)
        segment = x[:, pos:end]
        if segment.shape[1] < 2048:
            # El ultimo fragmento no llega a la resolucion minima.
            result["Overheads / Platillos"][:, pos:end] = segment
            continue
        freqs, _, zmono = stft(np.mean(segment, axis=0), sample_rate,
                               nperseg=2048, noverlap=1536, boundary="zeros")
        mag = np.abs(zmono).astype(np.float32)
        # Transientes en varias bandas. Se evita confundir hats con sustain de platos.
        diff = np.maximum(0, np.diff(mag, axis=1, prepend=mag[:, :1]))
        lowmask = (freqs >= 30) & (freqs < 180)
        highmask = (freqs > 4000) & (freqs < 14500)
        low_onset = np.sum(diff[lowmask], axis=0)
        high_onset = np.sum(diff[highmask], axis=0)
        low_onset = low_onset / (np.percentile(low_onset, 90) + 1e-7)
        high_onset = high_onset / (np.percentile(high_onset, 90) + 1e-7)
        low_onset = gaussian_filter1d(np.clip(low_onset, 0, 2), 1.2)
        high_onset = gaussian_filter1d(np.clip(high_onset, 0, 2), 1.2)
        f = freqs.astype(np.float32)[:, None]
        weights = np.stack([
            _soft_gauss(f, 65, 0.75) * (0.6 + 0.7 * low_onset[None, :]),
            (0.8 * _soft_gauss(f, 210, 0.85) + 0.55 * _soft_gauss(f, 2400, 1.3)) * (0.8 + 0.3 * high_onset[None, :]),
            _soft_gauss(f, 8900, 1.15) * (0.5 + 1.15 * high_onset[None, :]),
            _soft_gauss(f, 330, 1.0) * (0.8 + 0.2 * low_onset[None, :]),
            (0.18 + 1.2 * _soft_gauss(f, 5500, 1.45)) * (1.15 - 0.25 * np.minimum(high_onset[None, :], 1)),
        ], axis=0)
        weights = np.maximum(weights, 0.005)
        weights /= np.sum(weights, axis=0, keepdims=True)
        for ch in range(x.shape[0]):
            _, _, zs = stft(segment[ch], sample_rate, nperseg=2048,
                             noverlap=1536, boundary="zeros")
            for idx, part in enumerate(PARTS):
                _, out = istft(zs * weights[idx], sample_rate, nperseg=2048,
                               noverlap=1536, boundary=True)
                result[part][ch, pos:end] = out[:end - pos]
    return result
