"""V4.1: voto multifuente Librosa + Essentia + Beat This, siempre opcionales.

La fuerza de un detector NO es una probabilidad calibrada. Una canción sólo
se afina después de elegir una tonalidad y confirmar esa elección en la UI.
"""
from __future__ import annotations
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from music_analysis_legacy import (
    _key_estimate, _chroma, _read_samples, _tempo_estimate,
    _type_from_name, MusicResult as LegacyResult,
    TONAL_TYPES, RHYTHM_TYPES, ANALYSIS_SR, NOTES,
)


@dataclass
class MusicResult(LegacyResult):
    # Nuevos campos agregados al FINAL: retrocompatibilidad con V4.0.
    key_votes: tuple = ()
    bpm_votes: tuple = ()
    providers: tuple = ()
    key_candidates: tuple = ()

    def summary(self):
        key = f'{self.key} {self.scale}' if self.key and self.scale else 'sin conclusión fiable'
        bpm = f'{self.bpm:.1f}' if self.bpm else 'no determinado'
        detail = '\n'.join(f' • {entry}' for entry in self.key_votes[:8]) or ' • Sin datos armónicos suficientes'
        tempo = '\n'.join(f' • {entry}' for entry in self.bpm_votes[:6]) or ' • Sin datos rítmicos suficientes'
        return (f'Tonalidad candidata: {key} | {self.key_status}\n'
                f'Tempo candidato: {bpm} BPM | {self.bpm_status}\n'
                f'Tonalidad por fuente/método:\n{detail}\n'
                f'BPM por fuente/método:\n{tempo}\n'
                f'Motores: {"; ".join(self.providers) or "Librosa"}\n'
                f'Fuentes: {", ".join(self.source_names) or "ninguna"}\n'
                'NOTA: la fuerza/acuerdo son heurísticas, NO porcentajes de probabilidad.')


def backend_status():
    """Evita cargar torch/essentia al construir la interfaz."""
    native = importlib.util.find_spec('essentia') is not None
    beat = importlib.util.find_spec('beat_this') is not None
    return {'essentia_native':native, 'essentia_wsl':os.name == 'nt', 'beat_this':beat}


def _as_mono_22050(y, sample_rate=ANALYSIS_SR):
    y = np.asarray(y, dtype='float32')
    if sample_rate == 22050:return y
    from math import gcd
    d = gcd(sample_rate,22050)
    return resample_poly(y,22050//d,sample_rate//d).astype('float32')


def _essentia_available_path(path, mode):
    """Ejecuta una implementación de Essentia real en local, o WSL en Windows.

    WSL no se instala ni se invoca con shell=True. Los paths se traducen de manera
    individual. Si no hay Essentia, el motor devuelve un error controlado.
    """
    helper = Path(__file__).with_name('essentia_helper.py').resolve()
    target = Path(path).resolve()
    if importlib.util.find_spec('essentia') is not None:
        cmd = [sys.executable, str(helper), mode, str(target)]
    elif os.name == 'nt':
        def to_wsl(p):
            ans=subprocess.run(['wsl.exe','-e','wslpath','-a',str(p)],capture_output=True,text=True,timeout=12)
            if ans.returncode or not ans.stdout.strip():raise RuntimeError('WSL sin ruta disponible')
            return ans.stdout.strip()
        cmd = ['wsl.exe','-e','bash','-lc',
               'if [ -x "$HOME/.venvs/mezclador-essentia/bin/python" ]; then exec "$HOME/.venvs/mezclador-essentia/bin/python" "$1" "$2" "$3"; else exec python3 "$1" "$2" "$3"; fi',
               'mezclador-essentia',to_wsl(helper),mode,to_wsl(target)]
    else:
        raise RuntimeError('Essentia no está instalado (requiere Linux o WSL)')
    out = subprocess.run(cmd, capture_output=True,text=True,timeout=110)
    if out.returncode:
        raise RuntimeError((out.stderr or out.stdout).strip()[-250:])
    # Bibliotecas C++ pueden escribir mensajes en stdout antes del JSON.
    lines = [line.strip() for line in out.stdout.splitlines() if line.strip().startswith('{')]
    if not lines:raise RuntimeError('Essentia no devolvió JSON')
    data = json.loads(lines[-1])
    if data.get('error'):raise RuntimeError(str(data['error']))
    return data


def _beat_this_tempo(path):
    # No importar ni descargar un modelo al arrancar la interfaz.
    from beat_this.inference import File2Beats
    import torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tracker = File2Beats(checkpoint_path='final0', device=device, dbn=False)
    beats, _downbeats = tracker(str(path))
    return _bpm_from_beats(beats)


def _bpm_from_beats(beats):
    beats = np.asarray(beats,dtype=float).reshape(-1)
    delta = np.diff(beats)
    delta = delta[np.isfinite(delta) & (delta > .18) & (delta < 1.5)]
    if len(delta)<6:return None
    center=float(np.median(delta))
    # Consistencia robusta de los intervalos; no es certeza estadística.
    kept = delta[np.abs(delta/center-1)<.25]
    if len(kept)<6:return None
    bpm=60/float(np.median(kept))
    if not 45<=bpm<=225:return None
    agreement=float(np.mean(np.abs(kept/np.median(kept)-1)<.08))
    return (round(bpm,2), agreement)


def _role(path):
    name=Path(path).name
    t=_type_from_name(name)
    if t.startswith('Voz') or t in ('Coros','Voz doble'): return 'vocal', t
    if t in TONAL_TYPES:return 'tonal',t
    if t in RHYTHM_TYPES:return 'rhythm',t
    if any(part in Path(path).stem.lower() for part in ('beat','music','instrumental','melody','melodia','loop')):
        return 'full',t
    return 'ignore',t


def _normalize_key(pitch, mode):
    k=str(pitch).strip().upper().replace('♭','B')
    flat_to_sharp={'DB':'C#','EB':'D#','GB':'F#','AB':'G#','BB':'A#'}
    k=flat_to_sharp.get(k,k)
    m=str(mode).lower()
    if m in ('minor','menor','menor natural'):m='Menor natural'
    elif m in ('major','mayor'):m='Mayor'
    else:return None
    return (k,m) if k in NOTES else None


def _ensemble_keys(votes):
    if not votes:return None,None,0.,'No hay instrumentos tonales suficientes',()
    totals=defaultdict(float)
    for key,scale,weight,source in votes:
        totals[(key,scale)]+=max(0.,weight)
    ordered=sorted(totals.items(),key=lambda kv:kv[1],reverse=True)
    (key,scale),first=ordered[0]
    second=ordered[1][1] if len(ordered)>1 else 0
    total=sum(totals.values())
    # Acuerdo de estimaciones, nunca probabilidad de que la tonalidad sea correcta.
    ratio=first/max(total,1e-6)
    conf=float(np.clip(ratio*((first-second)/max(first,1e-6)),0,1))
    if conf < .50 or (len(votes)<2 and first<1):
        return None,None,conf,'Acuerdo bajo: comprobar tonalidad manualmente',tuple(f'{k} {s}' for (k,s),_ in ordered[:3])
    return key,scale,conf,'Acuerdo '+('alto' if conf>=.73 else 'moderado')+' entre métodos (no es probabilidad)',tuple(f'{k} {s}' for (k,s),_ in ordered[:3])


def _ensemble_tempo(votes):
    if not votes:return None,0.,'No se encontraron pulsos fiables'
    groups=[]
    for bpm,weight,source in sorted(votes,key=lambda x:-x[1]):
        best=None
        for cluster in groups:
            ref=cluster[0][0]
            ratio=max(ref,bpm)/min(ref,bpm)
            # Asociar sólo valores de igual pulso. Los 91 y 182 se informan
            # como variantes, no se promedian porque la división es musical.
            if abs(bpm-ref)/max(ref,bpm)<.055: best=cluster;break
        if best is None:groups.append([(bpm,weight,source)])
        else:best.append((bpm,weight,source))
    groups.sort(key=lambda c:-sum(x[1] for x in c))
    winning=groups[0]
    w=np.asarray([x[1] for x in winning]); v=np.asarray([x[0] for x in winning])
    bpm=float(np.average(v,weights=w))
    ratio=float(np.sum(w)/max(sum(z[1] for z in votes),1e-6))
    status='Acuerdo '+('alto' if ratio>.75 else 'moderado' if ratio>.52 else 'bajo')
    options=[round(float(np.average([x[0] for x in cl],weights=[x[1] for x in cl])),1) for cl in groups[:3]]
    if any(abs(bpm-o)/max(bpm,o)>.08 for o in options[1:]):status+='; hay estimaciones alternativas'
    status+='; comprobar medio/doble tiempo (no es probabilidad)'
    return round(bpm,1),round(ratio,3),status


def analyze_music(tracks, *, limit_files=12, instrumental_source=None, use_essentia=True, use_beat_this=True):
    """Observa instrumentos individuales; cada motor es realmente invocado si está instalado.

    Los archivos de voz NUNCA participan en la estimación tonal/rítmica.
    Ni una escala estimada ni la clave 'key_confidence' autorizan afinar por sí solas.
    """
    try:
        import librosa
    except ImportError:
        return MusicResult(key_status='Falta Librosa', bpm_status='Falta Librosa')
    paths=[]
    if instrumental_source and Path(str(instrumental_source)).is_file():
        paths.append((str(instrumental_source),'full','Referencia'))
    for t in tracks:
        p=str(t.get('path') if isinstance(t,dict) else t)
        if not p or not Path(p).is_file():continue
        role,kind=_role(p)
        if role not in ('ignore','vocal') and all(p!=entry[0] for entry in paths):
            paths.append((p,role,kind))
    paths.sort(key=lambda z:({'full':0,'tonal':1,'rhythm':2}[z[1]],z[0]))
    paths=paths[:limit_files]
    sources=[]; key_votes=[]; tempo_votes=[]; key_summary=[]; bpm_summary=[]
    provider=['Librosa: disponible']
    rhythm_audio=[]; readable=[]
    for path,role,kind in paths:
        try:y=_read_samples(path,seconds=24)
        except (OSError,ValueError,RuntimeError):continue
        if len(y)<ANALYSIS_SR*2:continue
        sources.append(Path(path).name)
        readable.append((path,role,kind,y))
        if role in ('tonal','full'):
            try:
                chroma=_chroma(y,librosa)
                k,s,c,status=_key_estimate([(chroma,1.)]) if chroma is not None else (None,None,0.,'sin notas')
                if k and s:
                    weight=1.0 if role=='tonal' else .65
                    weight*=max(.35,min(1.,c))
                    key_votes.append((k,s,weight,Path(path).name+' / Librosa'))
                    key_summary.append(f'{Path(path).name}: {k} {s} (Librosa, indicador {c:.2f})')
                else:
                    key_summary.append(f'{Path(path).name}: ambiguo (Librosa)')
            except (RuntimeError,ValueError,MemoryError):pass
        if role in ('rhythm','full'):
            rhythm_audio.append((y,1.0 if role=='rhythm' else .8))
    # Agregar la estimación global de Librosa como voto independiente de perfil,
    # sin dar a ese voto un peso aplastante.
    legacy = None
    try:legacy = __import__('music_analysis_legacy').analyze_music(tracks,limit_files=limit_files,instrumental_source=instrumental_source)
    except (RuntimeError,ValueError,MemoryError):pass
    if legacy and legacy.key and legacy.scale:
        key_votes.append((legacy.key,legacy.scale,.85,'Librosa agregado'))
        key_summary.append(f'Conjunto armónico: {legacy.key} {legacy.scale} (Librosa)')
    if legacy and legacy.bpm:
        tempo_votes.append((legacy.bpm,.75,'Librosa'))
        bpm_summary.append(f'Librosa: {legacy.bpm:.1f} BPM')
    # Essentia: máximo 2 fuentes tonales + un ritmo para evitar 12 arranques WSL.
    if use_essentia:
        targets=[p for p,r,k,y in readable if r in ('tonal','full')][:2]
        done=False
        for path in targets:
            try:
                output=_essentia_available_path(path,'clave')
                done=True
                for item in output.get('keys',[]):
                    candidate=_normalize_key(item.get('key'),item.get('scale'))
                    if not candidate:continue
                    # Strength es fuerza de correlación, NO probabilidad.
                    strength=float(item.get('strength',0))
                    weight=(.65 if item['profile']=='krumhansl' else .55)*max(.35,min(1.,abs(strength)))
                    key_votes.append((*candidate,weight, f'Essentia/{item.get("profile", "perfil")}'))
                    key_summary.append(f'{Path(path).name}: {candidate[0]} {candidate[1]} (Essentia/{item.get("profile")})')
            except (OSError,RuntimeError,subprocess.SubprocessError,ValueError,ImportError):
                break
        provider.append('Essentia: '+('ejecutado' if done else 'no disponible (Windows: instalar en WSL)'))
        rhythm=next((p for p,r,k,y in readable if r in ('rhythm','full')),None)
        if rhythm:
            try:
                result=_essentia_available_path(rhythm,'ritmo')
                done=True
                beats=_bpm_from_beats(result.get('beats',[]))
                # Tempo informado por BeatTracker, contrastado con intervalos.
                v=float(result.get('bpm',0.))
                if 45<=v<=225:
                    tempo_votes.append((v,.8,'Essentia'))
                    bpm_summary.append(f'Essentia: {v:.1f} BPM')
                if beats and abs(beats[0]-v)<v*.06:tempo_votes.append((beats[0],.35,'Essentia pulsos'))
            except (OSError,RuntimeError,subprocess.SubprocessError,ValueError,ImportError):pass
        provider[-1]='Essentia: '+('ejecutado' if done else 'no disponible (Windows: instalar en WSL)')
    else:provider.append('Essentia: desactivado')
    if use_beat_this:
        rhythm=next(((p,y) for p,r,k,y in readable if r in ('full','rhythm')),None)
        if importlib.util.find_spec('beat_this') is None:
            provider.append('Beat This!: no instalado (opcional)')
        elif rhythm is None:
            provider.append('Beat This!: sin audio rítmico')
        else:
            try:
                temp_dir=Path(__file__).parent/'temporales';temp_dir.mkdir(exist_ok=True)
                with tempfile.TemporaryDirectory(dir=str(temp_dir)) as td:
                    path=Path(td)/'beat_this_entrada.wav'
                    sf.write(path,_as_mono_22050(rhythm[1]),22050)
                    estimate=_beat_this_tempo(path)
                if estimate:
                    tempo_votes.append((estimate[0],1.3*max(.35,estimate[1]),'Beat This!'))
                    bpm_summary.append(f'Beat This!: {estimate[0]:.1f} BPM (regularidad de pulsos {estimate[1]:.2f})')
                    provider.append('Beat This!: ejecutado')
                else:provider.append('Beat This!: pulso ambiguo')
            except Exception as exc:
                provider.append(f'Beat This!: no se pudo ejecutar ({type(exc).__name__})')
    else:provider.append('Beat This!: desactivado')
    k,s,kc,ks,alternatives=_ensemble_keys(key_votes)
    bpm,bc,bs=_ensemble_tempo(tempo_votes)
    return MusicResult(k,s,kc,ks,bpm,bc,bs,tuple(sources),tuple(key_summary),tuple(bpm_summary),tuple(provider),alternatives)
