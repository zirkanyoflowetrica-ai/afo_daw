"""Análisis de tonalidad/BPM ANTES de afinar. Solo lee stems originales.

No es transcripción de acordes ni separación de voces: ofrece estimaciones
con confianza y omite la afinación automática si la escala es incierta.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd

# Se importa solo cuando se solicita el análisis; no ralentiza la interfaz.
ANALYSIS_SR=11025
NOTES=('C','C#','D','D#','E','F','F#','G','G#','A','A#','B')
MAJOR=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],float)
MINOR=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17],float)
TONAL_TYPES={'Piano','Guitarra acustica','Guitarra lead / solo','Guitarra ritmica','Teclados / Synth','Pad / Cuerdas','Bajo'}
RHYTHM_TYPES={'Drums','Kick','Snare','Hi-hat','Overheads / Platillos','Toms','Percusion'}

@dataclass
class MusicResult:
    key: str|None=None
    scale: str|None=None
    key_confidence: float=0.
    key_status: str='Sin análisis'
    bpm: float|None=None
    bpm_confidence: float=0.
    bpm_status: str='Sin análisis'
    source_names: tuple[str,...]=()

    def summary(self):
        tonal=f'{self.key} {self.scale}' if self.key and self.scale else 'no fiable'
        beat=f'{self.bpm:.1f} BPM (posible medio/doble tiempo)' if self.bpm else 'no fiable'
        return (f'Tonalidad: {tonal} | confianza {self.key_confidence:.0%} | {self.key_status}\n'
                f'Tempo: {beat} | confianza {self.bpm_confidence:.0%} | {self.bpm_status}\n'
                f'Fuentes examinadas: {", ".join(self.source_names) or "ninguna"}')

    def as_dict(self):
        return asdict(self)


def _type_from_name(name):
    # Importación diferida para evitar circularidad.
    from mixer_engine import guess_type, is_backing_voice
    if is_backing_voice(name): return 'Voz de apoyo (_B)'
    return guess_type(name)


def _read_samples(path, seconds=16.):
    """Dos fragmentos repartidos por la pieza, sin cargar WAV completo."""
    info=sf.info(path)
    if not info.frames or info.samplerate<8000: return np.zeros(0,'float32')
    clip_frames=int(seconds*.5*info.samplerate)
    if clip_frames<1: return np.zeros(0,'float32')
    # Evitar silencios del principio, tomar segmentos interior y mitad.
    starts=[max(0,int(info.frames*.13)),max(0,int(info.frames*.57))]
    chunks=[]
    for start in starts:
        start=min(start,max(0,info.frames-clip_frames))
        audio,rate=sf.read(path,start=start,frames=clip_frames,always_2d=True,dtype='float32')
        if not len(audio):continue
        mono=np.mean(audio,axis=1)
        g=gcd(ANALYSIS_SR,rate)
        mono=resample_poly(mono,ANALYSIS_SR//g,rate//g).astype('float32') if rate!=ANALYSIS_SR else mono
        if np.sqrt(np.mean(mono.astype(float)**2))>3e-5:
            chunks.append(mono)
    return np.concatenate(chunks) if chunks else np.zeros(0,dtype='float32')


def _chroma(y, librosa):
    """Chroma sobre componente armónica; la batería pesa mucho menos."""
    y=np.asarray(y,dtype='float32')
    if y.size<ANALYSIS_SR*2:return None
    rms=float(np.sqrt(np.mean(y.astype('float64')**2)))
    if rms<3e-5:return None
    y=y/max(rms,1e-7)
    stft=librosa.stft(y,n_fft=4096,hop_length=512)
    s=np.abs(stft)
    harmonic,_=librosa.decompose.hpss(s,margin=(1.5,2.0))
    chroma=librosa.feature.chroma_stft(S=harmonic**2,sr=ANALYSIS_SR,n_fft=4096,hop_length=512)
    power=np.sum(harmonic**2,axis=0)
    mask=power>max(float(np.percentile(power,40)),1e-6)
    if np.count_nonzero(mask)<8:return None
    # Se normalizan los frames, evitando que un instante muy fuerte domine.
    frames=chroma[:,mask]
    v=np.mean(frames/(np.sum(frames,axis=0,keepdims=True)+1e-8),axis=1)
    return v/(np.sum(v)+1e-9)


def _key_estimate(chromas):
    if not chromas:return None,None,0.,'No hay suficientes instrumentos tonales'
    chroma=np.average([c for c,_ in chromas],axis=0,weights=[w for _,w in chromas])
    flat=float(np.std(chroma)/(np.mean(chroma)+1e-9))
    scores=[]
    for name,base in [('Mayor',MAJOR),('Menor natural',MINOR)]:
        for pitch in range(12):
            tmpl=np.roll(base,pitch)
            corr=np.corrcoef(chroma,tmpl)[0,1]
            scores.append((float(corr),NOTES[pitch],name))
    scores.sort(reverse=True)
    best,second=scores[:2]
    margin=best[0]-second[0]
    # Correlación positiva por sí sola es insuficiente (relativo mayor/menor).
    confidence=float(np.clip((best[0]-.35)/.55,0,1)*np.clip(margin/.115,0,1)*np.clip(flat/.24,0,1))
    if best[0]<.48 or margin<.035 or flat<.12:
        return None,None,confidence,(f'Ambigua: {best[1]} {best[2]} / {second[1]} {second[2]}. Elegir manualmente')
    if confidence<.50:
        return best[1],best[2],confidence,('Estimación orientativa; no se aplicará al afinador automáticamente')
    return best[1],best[2],confidence,('Estimación suficientemente consistente para sugerir afinación')


def _tempo_estimate(chunks,librosa):
    if not chunks:return None,0.,'No hay instrumentos rítmicos detectables'
    candidates=[]
    for y,weight in chunks:
        if len(y)<ANALYSIS_SR*3:continue
        # La normalización hace la detección menos dependiente del volumen del stem.
        z=y/max(float(np.sqrt(np.mean(y.astype('float64')**2))),1e-7)
        hop=256
        onset=librosa.onset.onset_strength(y=z,sr=ANALYSIS_SR,hop_length=hop)
        if np.percentile(onset,95)<.03:continue
        tempo,beats=librosa.beat.beat_track(onset_envelope=onset,sr=ANALYSIS_SR,hop_length=hop,trim=False)
        value=float(np.ravel(tempo)[0])
        if not 50<=value<=230 or len(beats)<4:continue
        intervals=np.diff(np.asarray(beats,dtype=float))*hop/ANALYSIS_SR
        intervals=intervals[intervals>0]
        if len(intervals)<3:continue
        med=float(np.median(intervals))
        regularity=float(np.mean(np.abs(intervals-med)/(med+1e-7)<.22))
        conf=float(np.clip((regularity-.30)/.65,0,1))*min(1.,len(intervals)/12.)
        candidates.append((value,conf*weight,weight))
    if not candidates:return None,0.,'Pulso no fiable; usar BPM manual o delay libre'
    # Mejor fuente rítmica; no promediar ritmos incompatibles.
    candidates.sort(key=lambda a:a[1],reverse=True)
    bpm,c,_=candidates[0]
    for other,score,_ in candidates[1:]:
        # 70/140 o 80/160 suelen ser dos lecturas válidas del mismo pulso.
        ratio=max(bpm,other)/min(bpm,other)
        if (abs(bpm-other)/max(bpm,other)>.12 and abs(ratio-2.)>.14 and score>c*.7):
            c*=.65
            break
    return round(bpm,1),round(float(np.clip(c,0,1)),3),('Estimación; verificar medio/doble tiempo en trap')


def analyze_music(tracks, *, limit_files=12, instrumental_source=None):
    """Admite rutas o dicts {path}; no toca las señales originales."""
    try:
        import librosa
    except ImportError:
        return MusicResult(key_status='Falta instalar librosa',bpm_status='Falta instalar librosa')
    tonal=[]; rhythmic=[]; sources=[]
    paths=[]
    if instrumental_source and Path(str(instrumental_source)).is_file():
        # Stem musical de referencia SOLO para detectar; nunca se mezcla ni masteriza.
        paths.append((str(instrumental_source),'Otro',False,True,True))
    for t in tracks:
        path=str(t.get('path') if isinstance(t,dict) else t)
        if not path or not Path(path).is_file():continue
        typ=_type_from_name(Path(path).name)
        if typ.startswith('Voz') or typ in {'Coros','Voz doble'}: continue
        candidate=typ in TONAL_TYPES
        broad=typ=='Otro' and any(word in Path(path).stem.lower() for word in ('instrumental','melodia','melody','beat','music','loop'))
        # Los beats completos pueden tener música, pero nunca asumir tonalidad de un kit de percusión puro.
        if typ=='Drums' and 'beat' in Path(path).stem.lower(): broad=True
        rhythm=typ in RHYTHM_TYPES or candidate or broad
        if candidate or broad or rhythm:paths.append((path,typ,candidate,broad,rhythm))
    # Tonales primero, incluyendo un beat completo como respaldo.
    paths.sort(key=lambda t:(not t[2] and not t[3],not t[3],not (t[1] in RHYTHM_TYPES)))
    for path,typ,tonal_ok,broad,rhythm in paths[:limit_files]:
        try:y=_read_samples(path)
        except (OSError,RuntimeError,ValueError):continue
        if len(y)<ANALYSIS_SR*2:continue
        sources.append(Path(path).name)
        if tonal_ok or broad:
            try: c=_chroma(y,librosa)
            except (ValueError,RuntimeError,MemoryError):c=None
            if c is not None:
                weight=.65 if typ=='Bajo' else (.8 if broad else 1.)
                tonal.append((c,weight))
        if rhythm:
            weight=1. if typ in RHYTHM_TYPES else (.9 if broad else .6)
            rhythmic.append((y,weight))
    key,scale,k_conf,k_info=_key_estimate(tonal)
    bpm,b_conf,b_info=_tempo_estimate(rhythmic,librosa)
    return MusicResult(key,scale,k_conf,k_info,bpm,b_conf,b_info,tuple(sources))
