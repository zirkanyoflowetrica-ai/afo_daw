"""Muestreo temporal a frecuencia original: conserva agudos y canales."""
import numpy as np
from scipy.signal import welch

def excerpts(x, sr, seconds=40., windows=8):
    n = x.shape[-1]
    if not n or n <= sr*seconds:
        return [x]
    width = max(1, int(sr*seconds/windows))
    return [x[..., i:i+width] for i in np.linspace(0, n-width, windows).astype(int)]

def spectrum(x, sr):
    parts = excerpts(x, sr)
    powers = []
    for part in parts:
        f, p = welch(part, fs=sr, nperseg=min(4096, part.shape[-1]), axis=-1)
        powers.append(p.mean(axis=0))
    return f, np.mean(powers, axis=0)

def classification_excerpt(x, sr):
    # Canal con mayor energía; un estéreo en oposición no desaparece al analizar.
    channel = int(np.argmax(np.mean(x.astype(float)**2, axis=-1)))
    return np.concatenate(excerpts(x[channel], sr, seconds=25., windows=5))
