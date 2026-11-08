"""Afinación monofónica por escala: detector YIN, curva suave y Rubber Band.

100 = corrección rápida y completa de tramas fiables, no emulación del plugin
comercial Auto-Tune. Los fragmentos no tonales se conservan sin corregir.
"""
import numpy as np
from scipy.signal import correlate,resample_poly
from scipy.ndimage import median_filter,uniform_filter1d
from pedalboard import time_stretch

KEYS=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
SCALES={'Cromatica':list(range(12)),'Mayor':[0,2,4,5,7,9,11],
        'Menor natural':[0,2,3,5,7,8,10],'Menor armonica':[0,2,3,5,7,8,11],
        'Pentatonica mayor':[0,2,4,7,9],'Pentatonica menor':[0,3,5,7,10]}

def allowed_notes(key,scale):
    if key not in KEYS or scale not in SCALES:
        raise ValueError('Tonica o escala no reconocida')
    pcs={(KEYS.index(key)+i)%12 for i in SCALES[scale]}
    return np.array([i for i in range(24,109) if i%12 in pcs],dtype=float)

def track_pitch(x,sr):
    channel=int(np.argmax(np.einsum('ij,ij->i',x,x,dtype=np.float64)))
    mono=resample_poly(x[channel],1,4).astype('float32')
    rate=sr/4
    hop=256
    size=1024
    padded=np.pad(mono,(size//2,size//2),mode='constant')
    centers=np.arange(0,len(mono),hop)
    frequencies=np.full(len(centers),np.nan)
    confidence=np.zeros(len(centers))
    lo,hi=int(rate/900),min(int(rate/65),size//2)
    # Umbral relativo de actividad, calculado sin copiar la toma completa.
    rmsref=float(np.sqrt(np.mean(mono.astype(float)**2)))
    for index,start in enumerate(centers):
        z=padded[start:start+size].astype(float)
        z-=z.mean()
        if np.sqrt(np.mean(z*z))<max(1e-4,rmsref*.045):continue
        corr=correlate(z,z,mode='full',method='fft')[size-1:]
        energy=np.r_[0.,np.cumsum(z*z)]
        tau=np.arange(1,hi+1)
        diff=np.maximum(energy[size-tau]+energy[size]-energy[tau]-2*corr[tau],0.)
        cmnd=np.r_[1.,diff*tau/np.maximum(np.cumsum(diff),1e-12)]
        candidates=np.flatnonzero((cmnd[lo:hi]<.18)&(cmnd[lo:hi]<=cmnd[lo-1:hi-1])&(cmnd[lo:hi]<cmnd[lo+1:hi+1]))+lo
        if not len(candidates):continue
        lag=int(candidates[0])
        a,b,c=cmnd[lag-1:lag+2]
        offset=.5*(a-c)/(a-2*b+c) if abs(a-2*b+c)>1e-12 else 0.
        f=rate/(lag+np.clip(offset,-.5,.5))
        if 65<=f<=900:
            frequencies[index]=f
            confidence[index]=1-float(b)
    return centers*4,frequencies,confidence

def _stable_regions(voiced, hop, sr):
    """Une huecos consonánticos breves, pero no procesa tramas aisladas."""
    from scipy.ndimage import binary_closing, label
    min_frames = max(2, int(np.ceil(.055 * sr / hop)))
    closed = binary_closing(voiced, structure=np.ones(max(2, int(.14*sr/hop))), border_value=0)
    # La primera y la última trama no deben desaparecer por el cierre.
    if voiced[0]: closed[:np.flatnonzero(~voiced)[0] if np.any(~voiced) else len(voiced)] = True
    if voiced[-1]:
        inds = np.flatnonzero(~voiced)
        closed[(inds[-1]+1) if len(inds) else 0:] = True
    labels, count = label(closed)
    for region in range(1, count+1):
        indices = np.flatnonzero(labels == region)
        if np.count_nonzero(voiced[indices]) < min_frames:
            continue
        yield int(indices[0]), int(indices[-1])+1


def _legacy_rubberband_tune(x, sr, key='C', scale='Cromatica', strength=0):
    """Afina regiones vocales con un solo render por frase y transiciones suaves.

    No re-renderiza bloques arbitrarios de ~6 s ni mezcla señal original con
    señal afinada dentro de una nota sostenida. Mantiene intactos los intervalos
    no tonales; los fundidos se realizan fuera del núcleo vocal identificado.
    """
    amount=float(strength)
    if not np.isfinite(amount) or not 0<=amount<=100:
        raise ValueError('La intensidad de afinacion debe estar entre 0 y 100')
    notes=allowed_notes(key,scale)
    x=np.ascontiguousarray(x,dtype='float32')
    if amount==0 or x.shape[-1]<sr*.12:
        return x.copy(),'afinacion por escala desactivada (0%)'
    positions,f0,confidence=track_pitch(x,sr)
    hop=int(positions[1]-positions[0]) if len(positions)>1 else max(1,sr//40)
    voiced=np.isfinite(f0)&(confidence>.82)
    # Ignora falsos armónicos/octavas aislados que pueden romper consonantes.
    midi=np.full(len(f0),np.nan,dtype=np.float64)
    midi[voiced]=69+12*np.log2(f0[voiced]/440.)
    if np.count_nonzero(voiced)<3:
        return x.copy(),'afinacion omitida: sin suficientes notas vocales fiables'
    for i in np.flatnonzero(voiced):
        neighbours=midi[max(0,i-2):min(len(midi),i+3)]
        good=neighbours[np.isfinite(neighbours)]
        if len(good)>=3 and abs(midi[i]-np.median(good))>1.3:
            voiced[i]=False
    if np.count_nonzero(voiced)<3:
        return x.copy(),'afinacion omitida: contorno vocal inestable'
    # Relleno únicamente para estimar objetivos y evitar saltos espurios.
    indices=np.flatnonzero(voiced)
    contour=np.interp(np.arange(len(midi)),indices,midi[indices])
    targets=notes[np.argmin(abs(contour[:,None]-notes[None,:]),axis=1)]
    # Confirmación de nota: cambios que duran menos de ~70 ms no cambian objetivo.
    targets=median_filter(targets,size=3,mode='nearest')
    raw=np.clip(targets-contour,-2.,2.)*(amount/100.)
    raw[~voiced]=0.
    if np.max(np.abs(raw))<.004:
        return x.copy(),f'afinacion {key} {scale} {amount:.0f}%: ya dentro de margen'
    n=x.shape[-1]
    output=x.copy()
    regions=0
    # ~140 ms a cada lado para dar contexto al algoritmo de estiramiento.
    # Las zonas de cruce (30 ms) quedan en la parte NO tonal de la toma.
    context=int(sr*.15)
    fade=int(sr*.03)
    for first,last in _stable_regions(voiced,hop,sr):
        core_first=max(0, first*hop)
        core_last=min(n,last*hop)
        # Asegurar al menos alguna trama tonal de duración suficiente.
        if core_last-core_first<max(sr*.05,hop*2):
            continue
        outer_first=max(0,core_first-fade)
        outer_last=min(n,core_last+fade)
        left=max(0,outer_first-context)
        right=min(n,outer_last+context)
        # El control cambia cada 1024 muestras y se suaviza a ~70 ms.
        curve=raw.copy()
        # Conserva variaciones de la melodía, sin jitter entre tramas.
        smooth_frames=max(3,int(round(.065*sr/hop))|1)
        curve=uniform_filter1d(curve,size=smooth_frames,mode='nearest')
        # Nunca se afina fuera de la región detectada; los fundidos están en el margen.
        steps=left+((np.arange(right-left)//1024)*1024)
        control=np.interp(steps,positions,curve,left=0.,right=0.).astype('float64')
        if np.max(np.abs(control))<.004:
            continue
        # UNA pasada por frase para mantener la fase continua entre notas.
        shifted=time_stretch(np.ascontiguousarray(x[:,left:right]),sr,
            stretch_factor=1.,pitch_shift_in_semitones=control,
            preserve_formants=True,high_quality=True,
            transient_mode='mixed',transient_detector='soft',
            retain_phase_continuity=True,use_time_domain_smoothing=False)
        length=right-left
        if shifted.shape[-1]<length:
            shifted=np.pad(shifted,((0,0),(0,length-shifted.shape[-1])))
        shifted=shifted[:,:length]
        start=outer_first-left
        end=outer_last-left
        weight=np.ones(end-start,dtype=np.float32)
        if outer_first<core_first:
            fw=core_first-outer_first
            weight[:fw]=np.linspace(0,1,fw,dtype=np.float32)
        if outer_last>core_last:
            fw=outer_last-core_last
            weight[-fw:]=np.linspace(1,0,fw,dtype=np.float32)
        # No usar fundidos entre renderizados distintos sobre vocales sostenidas.
        output[:,outer_first:outer_last]=(x[:,outer_first:outer_last]*(1-weight[None,:])+
            shifted[:,start:end]*weight[None,:])
        regions+=1
    if regions==0:
        return x.copy(),'afinacion omitida: regiones vocales demasiado breves'
    return output.astype('float32'),(f'afinacion por escala {key} {scale}, intensidad {amount:.0f}%; '
        f'{np.mean(voiced):.0%} tramas fiables; {regions} frases continuas; '
        'formantes preservados, fundidos fuera de notas, una pasada por frase')


# V3.7 - backend recomendado para VOZ: TD-PSOLA de Praat.
# El antiguo procesado Rubber Band permanece disponible como función privada
# para reproducibilidad, pero NO es respaldo automático: si PSOLA falla,
# se conserva la voz original y se muestra el motivo.
def tune_to_scale(x, sr, key='C', scale='Cromatica', strength=0):
    """Corrige voces monofónicas por escala antes de EQ/compresión/FX.

    Praat sintetiza pulsos glotales en vez de estirar el espectro por bloques.
    Mantiene intervalos sordos y consonantes y no hace mezclas seco/húmedo
    por nota. Ante voz estéreo no coherente o detección dudosa, omite afinación.
    """
    from scipy.ndimage import gaussian_filter1d
    amount=float(strength)
    if not np.isfinite(amount) or not (0 <= amount <= 100):
        raise ValueError('La intensidad de afinacion debe estar entre 0 y 100')
    notes=allowed_notes(key,scale)
    x=np.ascontiguousarray(x,dtype=np.float32)
    if amount==0 or x.shape[-1]<int(sr*.12):
        return x.copy(),'afinacion desactivada (0%)'
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return x.copy(),'afinacion omitida: falta instalar praat-parselmouth (no se utiliza el algoritmo anterior con artefactos)'

    # Aceptar mono, dual mono y estéreo con canales casi idénticos.
    # No modificar estéreo real con PSOLA mono para evitar colapso y desfase.
    if x.shape[0]==1:
        source=x[0].copy()
        gains=np.array([1.],dtype=float)
    elif x.shape[0]==2:
        energies=np.mean(x.astype(np.float64)**2,axis=1)
        if max(energies)<1e-10:
            return x.copy(),'afinacion omitida: pista silenciosa'
        ref=int(np.argmax(energies))
        source=x[ref].copy()
        denom=max(float(np.dot(source.astype('float64'),source.astype('float64'))),1e-12)
        gains=np.array([float(np.dot(channel.astype('float64'),source.astype('float64'))/denom) for channel in x])
        residual=np.mean((x-gains[:,None]*source[None,:])**2,axis=1)
        coherence=np.max(residual/np.maximum(energies,1e-12))
        # Si el segundo canal tiene nivel casi nulo, es un stem ya paneado.
        coherence=max((float(r) if e/max(energies)>1e-4 else 0.) for r,e in zip(residual/np.maximum(energies,1e-12),energies))
        if coherence>.003:
            return x.copy(),'afinacion omitida: voz estereo con diferencias reales entre canales; se preserva su imagen y fase'
    else:
        return x.copy(),'afinacion omitida: numero de canales no compatible'

    try:
        snd=parselmouth.Sound(np.ascontiguousarray(source,dtype='float64'),sampling_frequency=float(sr))
        manipulation=call(snd,'To Manipulation',0.01,65,850)
        tier=call(manipulation,'Extract pitch tier')
        count=int(call(tier,'Get number of points'))
        if count<8:
            return x.copy(),'afinacion omitida: notas tonales insuficientes o deteccion no fiable'
        times=np.array([call(tier,'Get time from index',i) for i in range(1,count+1)],dtype=float)
        hz=np.array([call(tier,'Get value at index',i) for i in range(1,count+1)],dtype=float)
        if np.any(~np.isfinite(hz)) or np.any(hz<=0):
            return x.copy(),'afinacion omitida: F0 no fiable'
        midis=69+12*np.log2(hz/440.)
        output_midis=midis.copy()
        valid_count=0
        corrected_regions=[]
        # Frases tonales independientes. No conectar silencios de 80 ms o más.
        chunks=np.split(np.arange(count),np.where(np.diff(times)>.075)[0]+1)
        for ids in chunks:
            if len(ids)<8 or times[ids[-1]]-times[ids[0]]<.075:
                continue
            pitch=midis[ids]
            # Eliminar saltos aislados de octava/contorno sospechosos.
            stable=median_filter(pitch,size=5,mode='nearest')
            reliable=np.abs(pitch-stable)<.65
            targets=notes[np.argmin(np.abs(stable[:,None]-notes[None,:]),axis=1)]
            targets=median_filter(targets,size=7,mode='nearest')
            deviation=targets-pitch
            # Correcciones mayores de un semitono (100 cents) suelen indicar
            # una nota equivoca o una deteccion incierta; no forzarlas.
            reliable&=np.abs(deviation)<=1.0
            if np.sum(reliable)<7: continue
            delta=np.where(reliable,deviation*amount/100.,0.)
            # Curva suave sin cortar ni fundir el audio original a cada nota.
            delta=gaussian_filter1d(delta,sigma=2.,mode='nearest')
            # Cerca de una pausa reducir la magnitud de correccion.
            fade_n=min(3,len(ids)//4)
            if fade_n:
                delta[:fade_n]*=np.linspace(.25,1.,fade_n)
                delta[-fade_n:]*=np.linspace(1.,.25,fade_n)
            output_midis[ids]=pitch+delta
            if np.any(np.abs(delta)>.015):
                corrected_regions.append((times[ids[0]],times[ids[-1]]))
            valid_count+=int(np.sum(reliable & (np.abs(delta)>.015)))
        if valid_count<5 or np.max(np.abs(output_midis-midis))<.015:
            return x.copy(),'afinacion omitida: notas ya afinadas o demasiado inciertas para corregir sin riesgos'

        newtier=call('Create PitchTier','Voz afinada',snd.xmin,snd.xmax)
        for when,midi in zip(times,output_midis):
            call(newtier,'Add point',float(when),float(440*2**((midi-69)/12)))
        call([newtier,manipulation],'Replace pitch tier')
        rendered=call(manipulation,'Get resynthesis (overlap-add)').values[0]
        # Praat a veces redondea una muestra al resintetizar.
        n=x.shape[-1]
        if len(rendered)<n:rendered=np.pad(rendered,(0,n-len(rendered)))
        rendered=np.asarray(rendered[:n],dtype='float32')
        if not np.isfinite(rendered).all():
            return x.copy(),'afinacion omitida: salida no finita de PSOLA'
        # Mantener EXACTAMENTE intactos los segmentos externos a las notas.
        # Crossfade únicamente antes y después de cada frase, fuera del
        # núcleo tonal; en el interior no se mezcla seco/afinado.
        weight=np.zeros(n,dtype='float32')
        fade=max(8,int(sr*.025))
        for first,last in corrected_regions:
            a=max(0,int(first*sr)-fade)
            b=min(n,int(last*sr)+fade)
            if b<=a:continue
            f=min(fade,(b-a)//3)
            weight[a:b]=1.
            if f:
                weight[a:a+f]=np.maximum(weight[a:a+f]*np.linspace(0,1,f,dtype='float32'),0.)
                weight[b-f:b]=np.maximum(weight[b-f:b]*np.linspace(1,0,f,dtype='float32'),0.)
        pitched=np.stack([rendered*g for g in gains]).astype('float32')
        output=x*(1-weight[None,:])+pitched*weight[None,:]
        # Falla cerrada si genera picos inesperados.
        input_peak=float(np.max(np.abs(x)))
        output_peak=float(np.max(np.abs(output)))
        if output_peak>max(1.,input_peak*2.5):
            return x.copy(),'afinacion omitida: resintesis produjo picos anormales'
        return output,(f'afinacion vocal PSOLA {key} {scale} {amount:.0f}%; '
                       f'{valid_count} tramas fiables modificadas; '
                       'consonantes conservadas; sin mezclas seco/humedo por nota')
    except Exception as exc:
        return x.copy(),f'afinacion PSOLA omitida por error del analizador ({type(exc).__name__}: {str(exc)[:110]}); voz original conservada'
