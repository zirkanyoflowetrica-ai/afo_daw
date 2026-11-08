"""Clasificador CLAP opcional (pesos locales; sin descargas silenciosas).

Para habilitarlo, instalar el paquete extra y ejecutar instalar_modelo_ia.py.
No es infalible: confianza calculada como semejanza relativa, no probabilidad.
"""
from __future__ import annotations
from functools import lru_cache
import numpy as np

MODEL_ID = 'laion/clap-htsat-unfused'
LABELS = [
    ('Drums', 'A full drum kit playing a drum beat with kick snare and cymbals.'),
    ('Kick', 'A single kick drum making repeated low bass drum hits.'),
    ('Snare', 'A snare drum making snappy backbeat hits.'),
    ('Hi-hat', 'Closed and open hi hat cymbal percussion only.'),
    ('Overheads / Platillos', 'Crash and ride cymbals ringing.'),
    ('Toms', 'Tom tom drums playing a drum fill.'),
    ('Percusion', 'Hand percussion, congas, bongos, claps and shakers.'),
    ('Bajo', 'A bass guitar or sub bass synth playing a bassline.'),
    ('Voz principal', 'A person singing or rapping an isolated vocal track.'),
    ('Coros', 'A choir or multiple singers singing background vocals.'),
    ('Guitarra ritmica', 'An isolated electric rhythm guitar strumming chords.'),
    ('Guitarra acustica', 'An acoustic guitar strumming music.'),
    ('Guitarra lead / solo', 'An electric guitar playing a melodic solo.'),
    ('Piano', 'A piano playing notes and chords.'),
    ('Teclados / Synth', 'An electronic synthesizer playing music.'),
    ('Pad / Cuerdas', 'Orchestral strings or a sustained ambient synth pad.'),
    ('FX', 'A sound effect whoosh rise or impact.'),
]


@lru_cache(maxsize=1)
def _model():
    import torch
    from transformers import ClapModel, ClapProcessor
    # Se exige descarga voluntaria previa para no sorprender al usuario.
    processor = ClapProcessor.from_pretrained(MODEL_ID, local_files_only=True)
    model = ClapModel.from_pretrained(MODEL_ID, local_files_only=True)
    model.eval()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)
    return processor, model, device


def recognize(x, sr=44100):
    """Returns (etiqueta, margen 0..1) o None si IA no disponible.

    Solo el audio, no su nombre. Evita confundir pistas con silencio.
    """
    try:
        import torch
        from scipy.signal import resample_poly
        from math import gcd
        proc, model, device = _model()
    except (ImportError, OSError, RuntimeError, ValueError):
        return None
    mono = np.mean(x, axis=0).astype(np.float32)
    if mono.size < sr or np.max(np.abs(mono)) < 1e-5:
        return None
    # Elegir una ventana de actividad entre 3 ventanas repartidas por el clip.
    cut = min(sr * 10, mono.size)
    positions = [0, max(0, (mono.size-cut)//2), max(0, mono.size-cut)]
    seg = max((mono[p:p+cut] for p in positions), key=lambda y: np.mean(y*y))
    target = 48000
    g = gcd(sr, target)
    seg = resample_poly(seg, target//g, sr//g).astype(np.float32) if sr != target else seg
    inp = proc(text=[txt for _, txt in LABELS], audios=seg, sampling_rate=target,
               return_tensors='pt', padding=True)
    inp = {key: val.to(device) for key, val in inp.items()}
    with torch.no_grad():
        logits = model(**inp).logits_per_audio[0]
        similarities = torch.softmax(logits, dim=0).cpu().numpy()
    ranked = np.argsort(similarities)[::-1]
    best = float(similarities[ranked[0]])
    runner = float(similarities[ranked[1]])
    # Confianza de decision conservadora, no probabilidad real de acierto.
    margin = best - runner
    if best < 0.19 or margin < 0.055:
        return None
    return LABELS[ranked[0]][0], float(np.clip(.56 + 2*margin, .55, .90))
