"""Separador neuronal DrumSep OPCIONAL. Nunca descarga pesos durante mezcla sin opt-in.

Los pesos ajenos tienen terminos comerciales no aclarados; se activa solo
mediante archivo de confirmacion creado por el instalador experimental.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import numpy as np

ENABLED = Path(__file__).resolve().parent / '.modelo_drumsep_activado'


@lru_cache(maxsize=1)
def _separator():
    from mdxnet_infer import MDXNetSeparator
    return MDXNetSeparator(model_name='drumsep-6stem', device='auto')


def try_separate(x, sr=44100):
    """(dict[kind -> channels x frames], message) or (None, explanation)."""
    if not ENABLED.exists():
        return None, 'Separador neuronal de bateria no activado; usando DSP.'
    try:
        # Interfaz acepta audio tiempo x canales, segun README oficial.
        stereo = x if x.shape[0] == 2 else np.repeat(x, 2, axis=0)
        outputs = _separator().separate(np.ascontiguousarray(stereo.T, dtype=np.float32), sample_rate=sr)
        alias = {'kick':'Kick','snare':'Snare','toms':'Toms','hh':'Hi-hat',
                 'hihat':'Hi-hat','ride':'Overheads / Platillos','crash':'Overheads / Platillos',
                 'cymbals':'Overheads / Platillos'}
        parts = {}
        for name, data in outputs.items():
            kind = alias.get(name.lower())
            if not kind:
                continue
            y = np.asarray(data, dtype=np.float32)
            if y.ndim != 2:
                raise ValueError('El modelo devolvio datos no estereo')
            if y.shape[0] not in (1, 2) and y.shape[1] in (1, 2):
                y = y.T
            if y.shape[0] not in (1, 2):
                raise ValueError('El modelo devolvio canales inesperados')
            if y.shape[0] == 1 and x.shape[0] == 2:
                y = np.repeat(y,2,axis=0)
            if x.shape[0] == 1:
                y = y.mean(axis=0, keepdims=True)
            fixed = np.zeros_like(x)
            m = min(x.shape[1], y.shape[1])
            fixed[:, :m] = y[:, :m]
            if kind in parts:
                parts[kind] += fixed
            else:
                parts[kind] = fixed
        if not all(key in parts for key in ('Kick','Snare','Toms','Hi-hat')):
            raise ValueError('El modelo no devolvio las fuentes esperadas')
        parts.setdefault('Overheads / Platillos', np.zeros_like(x))
        # Residuo leve de reconstruccion: preserva nivel total y sincronizacion.
        total = np.sum(np.stack(list(parts.values()), axis=0), axis=0)
        residual = x - total
        parts['Overheads / Platillos'] += residual
        return parts, 'DrumSep neuronal MDX23C (experimental); puede haber filtraciones y artefactos.'
    except Exception as exc:
        return None, f'DrumSep neuronal no pudo ejecutarse ({type(exc).__name__}: {str(exc)[:120]}); usando DSP.'
