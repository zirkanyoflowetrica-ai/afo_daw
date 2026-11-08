"""Confirmación explícita del usuario antes de emplear tonalidad/BPM en la mezcla."""
import hashlib
import json
from pathlib import Path
from music_analysis import MusicResult
from scale_tuner import KEYS, SCALES


def signature(paths, music_file, values):
    items=[]
    for name in [*paths, *([music_file] if music_file else [])]:
        p=Path(name).resolve()
        if not p.is_file():raise ValueError(f'Archivo ausente: {p.name}')
        stat=p.stat()
        items.append([str(p), stat.st_size, stat.st_mtime_ns])
    obj={'files':items,'choices':values}
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def resolve_choice(analysis, mode, manual_key, manual_scale, manual_bpm, prefer_known):
    """No confundir automática (calcular propuestas) con autorización de afinarlas."""
    if mode not in ('Automático','Manual','Asistido'):raise ValueError('Modo musical inválido')
    if manual_key not in KEYS or manual_scale not in SCALES:
        raise ValueError('Selecciona una escala válida')
    try:bpm=float(manual_bpm)
    except (TypeError,ValueError):raise ValueError('BPM debe ser numérico')
    if not 50<=bpm<=230:raise ValueError('Selecciona BPM entre 50 y 230')
    analysis=analysis or {}
    if mode=='Manual' or prefer_known:
        source='Referencia musical confirmada por el usuario' if prefer_known else 'Selección manual'
        return dict(key=manual_key,scale=manual_scale,bpm=bpm,source=source,mode=mode,analysis=analysis)
    # Solo mayor/menor natural se pueden escoger por estimación; la fórmula
    # de acuerdo sirve como barrera heurística, NO probabilidad estadística.
    if not analysis.get('key') or analysis.get('key_confidence',0)<.60:
        raise ValueError('La tonalidad automática es ambigua. Marca «Priorizar referencia» y confirma la escala correcta.')
    if not analysis.get('bpm') or analysis.get('bpm_confidence',0)<.55:
        raise ValueError('El BPM automático es ambiguo. Marca «Priorizar referencia» y confirma el tempo correcto.')
    return dict(key=analysis['key'],scale=analysis['scale'],bpm=float(analysis['bpm']),
                source='Estimación automática aprobada por el usuario',mode=mode,analysis=analysis)
