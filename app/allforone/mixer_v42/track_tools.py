"""Edición automática acotada, con avisos y comparaciones no destructivas."""
import numpy as np
from scipy.ndimage import median_filter, uniform_filter1d, label
from scipy.signal import find_peaks
from pedalboard import Pedalboard, PeakFilter
from spectral_tools import spectrum
from vocal_dsp import band, envelope

def level_phrases(x, sr):
    if x.shape[-1] < sr//2:
        return x, 'nivelacion omitida (toma corta)'
    hop = max(1, sr//100)
    e = envelope(x, sr, .22)[::hop]
    active = e > max(float(e.max())*.12, 1e-4)
    if np.count_nonzero(active)<10:
        return x, 'nivelacion omitida (sin frases fiables)'
    target = float(np.percentile(e[active], 65))
    db = np.clip(20*np.log10(target/np.maximum(e, 1e-9)), -3., 1.5)
    db[~active] = 0.
    # Curva suave de 200 ms; no normaliza cada sílaba ni levanta silencios.
    db = uniform_filter1d(db, 21, mode='nearest')
    gain = np.interp(np.arange(x.shape[-1]), np.arange(len(db))*hop, db)
    gain[envelope(x, sr, .03)<max(float(e.max())*.025, 1e-5)] = 0.
    gain = uniform_filter1d(gain, max(1,int(sr*.025)))
    return (x*10**(gain[None,:]/20)).astype('float32'), f'nivelacion por frases {gain.min():+.1f}/{gain.max():+.1f} dB (limites -3/+1.5 dB)'

def repair_vocal(x, sr):
    y = x.copy()
    fixes = 0
    if x.shape[-1]>5:
        # Solo impulsos de una muestra muy aislados. Si abundan, no se toca.
        for c in range(x.shape[0]):
            z=x[c]
            residual=z[1:-1]-(z[:-2]+z[2:])*.5
            local=np.sqrt(np.maximum(uniform_filter1d(residual.astype(float)**2,max(3,int(sr*.01))),0))
            candidates=np.flatnonzero((np.abs(residual)>.08)&(np.abs(residual)>8*local))+1
            if len(candidates)<=max(2,int(x.shape[-1]/sr*3)):
                for i in candidates:
                    if abs(z[i-1]-z[i+1])<.04:
                        y[c,i]=(z[i-1]+z[i+1])*.5
                        fixes+=1
    low=band(y,sr,25,120)
    body=envelope(y,sr,.015)
    rumble=envelope(low,sr,.015)
    baseline=np.maximum(uniform_filter1d(rumble,max(1,int(sr*.35))),1e-5)
    fraction=np.clip((rumble/baseline-1.6)/2.,0,1)*np.clip((rumble/np.maximum(body,1e-8)-.55)/.35,0,1)
    fraction=uniform_filter1d(fraction,max(1,int(sr*.015)))
    reduction=3*fraction
    y=(y+low*(10**(-reduction/20)-1)[None,:]).astype('float32')
    # Ruido/clipping se diagnostican, no se reconstruyen ni eliminan consonantes.
    clipped=float(np.mean(np.max(np.abs(x),axis=0)>=.999))
    note=f'limpieza: {fixes} clics aislados; golpes graves hasta {reduction.max():.1f} dB'
    if clipped>.0001:
        note+=f'; AVISO {clipped:.2%} muestras cerca del techo: revisar grabacion'
    if y.shape[-1]>=sr:
        air=envelope(band(y,sr,3000,10000),sr,.03)
        ref=float(np.percentile(body[body>1e-5],80)) if np.any(body>1e-5) else 1.
        mask=(air/np.maximum(body,1e-9)>.65)&(body<ref*.45)&(body>ref*.06)
        regions,count=label(mask[::max(1,sr//100)])
        lengths=np.bincount(regions)[1:]/100
        candidates=int(np.count_nonzero((lengths>=.06)&(lengths<=.45)))
        note+=f'; {candidates} intervalos de aire/respiracion candidatos (solo aviso, pueden ser consonantes)'
    return y,note

def resonance_eq(x,sr,typ):
    """Una resonancia estrecha como máximo; nunca en kick/bajo/platillos."""
    allowed=('Voz principal','Coros','Voz doble','Voz de apoyo (_B)', 'Guitarra acustica','Guitarra ritmica','Guitarra lead / solo','Piano','Teclados / Synth')
    if typ not in allowed or x.shape[-1]<sr//2:
        return x,'sin EQ de resonancia adicional'
    f,p=spectrum(x,sr)
    db=10*np.log10(np.maximum(p,1e-15))
    baseline=median_filter(db, size=31, mode='nearest')
    contrast=db-baseline
    peaks,_=find_peaks(contrast,height=10, prominence=6)
    peaks=[i for i in peaks if 500<f[i]<6500 and db[i]>db.max()-18]
    if not peaks:
        return x,'sin resonancia dominante'
    i=max(peaks,key=lambda k:contrast[k])
    # Evita recortar líneas tonales puras o instrumentos con pocas armónicas.
    audible=np.count_nonzero(db>db.max()-25)
    if audible<35:
        return x,'resonancia omitida: contenido muy tonal'
    cut=min(1.2,(contrast[i]-8)*.12)
    y=np.asarray(Pedalboard([PeakFilter(float(f[i]),-float(cut),3.)])(x,sr))
    return y,f'resonancia candidata {f[i]:.0f} Hz: -{cut:.1f} dB (una banda, maximo 1.2 dB)'

def level_match_pair(original,processed,meter):
    """A/B al menor LUFS de ambas, con margen común; exportaciones separadas."""
    def loud(x):
        if x.shape[-1]<meter.rate*.45 or not np.any(x):
            return -np.inf
        return float(meter.integrated_loudness(x.T))
    a,b=loud(original),loud(processed)
    if not (np.isfinite(a) and np.isfinite(b)):
        return original.copy(),processed.copy(),'A/B sin igualacion LUFS (silencio/toma corta)'
    target=min(a,b,-18.)
    left=original*10**((target-a)/20)
    right=processed*10**((target-b)/20)
    peak=max(float(np.max(np.abs(left))),float(np.max(np.abs(right))),1e-9)
    guard=min(1.,.89/peak)
    return left*guard,right*guard,f'A/B igualado a {target+20*np.log10(guard):.1f} LUFS; solo escucha, no cambia stems exportados'

def section_balance(buses,lead,sr):
    """Ride contextual lento de hasta 0.8 dB, solo con principal identificada."""
    if lead is None or 'Voces' not in buses or not np.any(lead):
        return None,'balance por secciones omitido (sin principal)'
    music=[v for k,v in buses.items() if k!='Voces']
    if not music:
        return None,'balance por secciones omitido (solo voces)'
    hop=max(1,sr//100)
    voice=envelope(lead,sr,.6)[::hop]
    bed=np.sqrt(sum(envelope(v,sr,.6)[::hop]**2 for v in music))
    valid=(voice>max(float(voice.max())*.12,1e-5))&(bed>1e-5)
    if np.count_nonzero(valid)<30:
        return None,'balance por secciones omitido (poca coincidencia)'
    ratio=bed/np.maximum(voice,1e-8)
    baseline=float(np.median(ratio[valid]))
    db=np.clip(20*np.log10(np.maximum(ratio,1e-8)/max(baseline,1e-8))*.3,-.8,.8)
    db[~valid]=0.
    db=uniform_filter1d(db,101,mode='nearest')
    curve=10**(np.interp(np.arange(lead.shape[-1]),np.arange(len(db))*hop,db)/20)
    buses['Voces']*=curve[None,:]
    return curve,f'balance vocal contextual lento {db.min():+.1f}/{db.max():+.1f} dB; limite +/-0.8 dB, sin mover paneo'
