"""Air, saturación y compresión paralela de aporte moderado, sin normalizar peaks."""
import numpy as np
from scipy.signal import resample_poly
from pedalboard import Pedalboard,HighShelfFilter,LowpassFilter,HighpassFilter,Compressor
from spectral_tools import spectrum,excerpts
from vocal_dsp import dynamic_cut

def rms(x):
    return float(np.sqrt(np.einsum('ij,ij->',x,x,dtype=np.float64)/max(1,x.size)))

def saturation(x,sr,wet=.08):
    if not x.size or rms(x)<1e-5:return x.copy(),0.
    sample=np.concatenate(excerpts(x,sr,seconds=12,windows=4),axis=-1)
    reference=max(.04,float(np.percentile(abs(sample),98)))
    out=np.empty_like(x)
    block=sr*4
    for i in range(0,x.shape[-1],block):
        left=max(0,i-64);right=min(x.shape[-1],i+block+64)
        up=resample_poly(x[:,left:right],2,1,axis=-1)
        shaped=np.tanh(up*(1.15/reference))*reference
        down=resample_poly(shaped,1,2,axis=-1)
        lo=i-left;length=min(block,x.shape[-1]-i)
        out[:,i:i+length]=down[:,lo:lo+length]
    gain=min(1.8,rms(x)/max(rms(out),1e-9))
    return (x*(1-wet)+out*(gain*wet)).astype('float32'),wet

def parallel_compression(x,sr,wet=.10,voice=False):
    level=rms(x)
    if level<1e-5:return x.copy(),0.
    peak=float(np.max(abs(x)))
    crest=20*np.log10(max(peak,1e-8)/level)
    if crest<9:return x.copy(),0.
    threshold=float(np.clip(20*np.log10(level)+3,-36,-10))
    chain=[]
    if voice:chain=[HighpassFilter(120),LowpassFilter(9000)]
    chain.append(Compressor(threshold_db=threshold,ratio=3.,attack_ms=18.,release_ms=100.))
    compressed=np.asarray(Pedalboard(chain)(x,sr))
    makeup=min(10**(3/20),level/max(rms(compressed),1e-9))
    return (x*(1-wet)+compressed*(makeup*wet)).astype('float32'),wet

def enhance_vocal(x,sr,kind):
    f,p=spectrum(x,sr);total=float(p.sum())+1e-12
    air=float(p[(f>=8000)&(f<16000)].sum()/total)
    top=float(p[f>=17500].sum()/total)
    # No aumentar ruido de fondo si la energía alta sigue en ventanas suaves.
    samples=np.concatenate(excerpts(x,sr,seconds=12,windows=4),axis=-1)
    frame=max(1,sr//10)
    levels=[rms(samples[:,i:i+frame]) for i in range(0,samples.shape[-1],frame)]
    floor_ratio=float(np.percentile(levels,10)/max(np.percentile(levels,80),1e-8)) if levels else 1.
    gain=0.
    if .001<air<.085 and floor_ratio<.65:
        gain=float(np.clip((.065-air)*22,0,1.4 if kind=='Voz principal' else .8))
    chain=[]
    if top>.025:
        chain.append(LowpassFilter(18500))
    if gain>.05:chain.append(HighShelfFilter(10000,gain))
    out=np.asarray(Pedalboard(chain)(x,sr)) if chain else x
    out,sat=saturation(out,sr,.08 if kind=='Voz principal' else .045)
    out,parallel=parallel_compression(out,sr,.10 if kind=='Voz principal' else .06,voice=True)
    out,ess=dynamic_cut(out,sr,5000,10000,1.)
    return out,(f'air adaptativo +{gain:.1f} dB a 10 kHz (se omite si brillante, sin aire o ruido persistente); '
        f'recorte agudo {"18.5 kHz" if top>.025 else "no necesario"}; saturacion paralela {sat:.0%}; '
        f'compresion paralela {parallel:.0%}; control final de eses {ess:.1f} dB')

def enhance_bus(x,sr):
    return parallel_compression(x,sr,.06,voice=False)

def enhance_master(x,sr):
    f,p=spectrum(x,sr)
    ultrahigh=float(p[f>=19000].sum()/max(float(p.sum()),1e-12))
    if ultrahigh>.04:
        x=np.asarray(Pedalboard([LowpassFilter(20000)])(x,sr))
    out,sat=saturation(x,sr,.025)
    out,parallel=parallel_compression(out,sr,.025,voice=False)
    return out,f'saturacion master {sat:.1%}, compresion paralela {parallel:.1%}; recorte extremo agudo {"20 kHz" if ultrahigh>.04 else "no necesario"} (aportes moderados)'
