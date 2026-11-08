"""Procesamiento conservador; señales (canales, muestras), sin modelos externos."""
import numpy as np
from scipy.signal import butter, sosfiltfilt, correlate, resample_poly
from scipy.ndimage import uniform_filter1d
from pedalboard import Pedalboard, HighpassFilter, PitchShift

VOCALS = ('Voz principal', 'Voz de apoyo (_B)', 'Voz lateral (_L/_R)', 'Coros', 'Voz doble')

def envelope(x, sr, seconds=.03):
    power=np.zeros(x.shape[-1],dtype='float32')
    for channel in x: power+=channel*channel/max(1,x.shape[0])
    return np.sqrt(np.maximum(uniform_filter1d(power,max(1,int(sr*seconds))),0))

def band(x, sr, low, high):
    if x.shape[-1] == 0:
        return x.copy()
    return sosfiltfilt(butter(2, [low, min(high, sr*.47)], fs=sr, btype='bandpass', output='sos'), x, axis=-1, padlen=min(15, x.shape[-1]-1))

def dynamic_cut(x, sr, low, high, maximum=2., sidechain=None):
    """Reducción solo de banda; detector relativo, alisado 40 ms, máximo en dB."""
    b = band(x, sr, low, high)
    full = envelope(x, sr)
    strength = envelope(b, sr) / np.maximum(full, 1e-8)
    amount = np.clip((strength-.35)/.45, 0, 1)
    if sidechain is not None:
        control = envelope(sidechain, sr)
        ref = np.percentile(control, 85)
        amount *= np.clip(control/max(ref*.6, 1e-8), 0, 1)
    amount *= full > 1e-5
    amount = uniform_filter1d(amount, max(1, int(sr*.04)))
    gain = 10**(-maximum*amount/20)
    return (x + b*(gain-1)[None, :]).astype('float32'), float(maximum*np.max(amount))

def pitch_profile(x, sr):
    """Autocorrelación normalizada a 11.025 kHz; no infiere sexo ni tesitura clásica."""
    mono = resample_poly(x.mean(axis=0), 1, 4)
    rate = sr/4
    size, hop = 2048, 1024
    found = []
    total = 0
    # Muestreo distribuido para limitar el análisis a unas 1200 ventanas.
    starts = np.arange(0, max(0, len(mono)-size+1), hop)
    if len(starts)>1200:
        starts = starts[np.linspace(0, len(starts)-1, 1200).astype(int)]
    for start in starts:
        z = mono[start:start+size].astype(float)
        total += 1
        z -= z.mean()
        if np.sqrt(np.mean(z*z)) < 1e-4:
            continue
        c = correlate(z, z, mode='full', method='fft')[size-1:]
        lo, hi = int(rate/700), int(rate/65)
        # Corrige sesgo de ventana y elige el primer máximo fuerte para evitar suboctavas.
        c /= np.maximum(np.arange(size, 0, -1), 1)
        c /= max(c[0], 1e-12)
        peaks = np.where((c[lo:hi]>c[lo-1:hi-1]) & (c[lo:hi]>c[lo+1:hi+1]))[0]+lo
        if not len(peaks):
            continue
        best = max(c[peaks])
        good = peaks[c[peaks] >= max(.75, best*.94)]
        if len(good):
            lag = good[0]
            d = .5*(c[lag-1]-c[lag+1])/max(1e-9, 2*c[lag]-c[lag-1]-c[lag+1])
            found.append(rate/(lag-d))
    if not found:
        return None
    f = np.array(found)
    return dict(median=float(np.median(f)), low=float(np.percentile(f, 10)), high=float(np.percentile(f, 90)), voiced=len(f)/max(total, 1))

def process_vocal(x, sr, tuning=False, kind='Voz principal'):
    from track_tools import repair_vocal, level_phrases
    # Afinación PRIMERO sobre la toma cruda: los demás procesos siguen intactos.
    notes = []
    if isinstance(tuning,dict):
        from scale_tuner import tune_to_scale
        x,tune_note=tune_to_scale(x,sr,tuning.get('key','C'),tuning.get('scale','Cromatica'),tuning.get('strength',0))
        notes.append(tune_note)
    x, cleanup_note = repair_vocal(x, sr)
    notes.append(cleanup_note)
    profile = pitch_profile(x, sr)
    if profile:
        f = profile['median']
        hp = float(np.clip(profile['low']*.48, 55, 110))
        x = np.asarray(Pedalboard([HighpassFilter(hp)])(x, sr))
        notes.append(f"F0 mediana {f:.1f} Hz; rango P10-P90 {profile['low']:.1f}-{profile['high']:.1f} Hz; tramas tonales {profile['voiced']:.0%}; HP adaptativo {hp:.0f} Hz")
        if tuning and not isinstance(tuning,dict):
            # Solo tomas casi monótonas y fiables. No altera melodías ni adivina tonalidad.
            spread = 12*np.log2(profile['high']/profile['low'])
            midi = 69+12*np.log2(f/440)
            cents = (round(midi)-midi)*100
            if spread < .35 and profile['voiced']>.8 and 5<abs(cents)<35:
                shift = float(np.clip(cents*.5, -15, 15)/100)
                x = np.asarray(Pedalboard([PitchShift(semitones=shift)])(x, sr))
                notes.append(f"afinacion cromatica global prudente {shift*100:+.1f} cents")
            else:
                notes.append('afinacion omitida: melodia variable, poca confianza o desviacion fuera de margen')
    else:
        hp = 75. if kind == 'Voz principal' else 90.
        x = np.asarray(Pedalboard([HighpassFilter(hp)])(x, sr))
        notes.append(f'F0 no fiable: un solo HP de respaldo {hp:.0f} Hz; sin afinacion')
    x, level_note = level_phrases(x, sr)
    notes.append(level_note)
    x, de = dynamic_cut(x, sr, 4500, 10000, 4.)
    x, mud = dynamic_cut(x, sr, 180, 500, 1.8)
    x, harsh = dynamic_cut(x, sr, 2400, 4500, 1.5)
    notes.append(f'de-esser hasta {de:.1f} dB; EQ dinamica cuerpo {mud:.1f} dB, dureza {harsh:.1f} dB')
    return x, '; '.join(notes)

def phase_notes(x, name):
    if x.shape[0]!=2 or not np.any(x):
        return []
    l, r = x.astype(float)
    corr = float(np.dot(l,r)/max(np.linalg.norm(l)*np.linalg.norm(r), 1e-12))
    if corr < -.3:
        return [f'FASE {name}: correlacion L/R {corr:.2f}; posible cancelacion en mono. Revisar origen; sin invertir automaticamente.']
    return []

def compare_phase(x, name, previous, sr):
    """Comparación de primeros 30 s; solo alertas de duplicados casi invertidos."""
    z = resample_poly(x[..., :sr*30].mean(axis=0), 1, 16)
    notes = []
    for other, ref in previous:
        n = min(len(z), len(ref))
        if not n:
            continue
        corr = float(np.dot(z[:n], ref[:n])/max(np.linalg.norm(z[:n])*np.linalg.norm(ref[:n]), 1e-12))
        if corr < -.85:
            notes.append(f'FASE {name} / {other}: correlacion {corr:.2f}, posible duplicado con polaridad invertida (primeros 30 s); revisar manualmente.')
    previous.append((name, z))
    return notes

def vocal_effects(x, sr, style='principal'):
    """Eco filtrado con ducking y perfil por función; conserva duración."""
    wet = np.zeros_like(x)
    taps = ((.115, .045), (.23, .018)) if style == 'principal' else ((.16, .035), (.32, .015))
    for seconds, gain in taps:
        lag = int(sr*seconds)
        if x.shape[1]>lag:
            wet[:, lag:] += x[:, :-lag]*gain
    wet = band(wet, sr, 400, 5500 if style == 'principal' else 4500)
    e = envelope(x, sr, .07)
    moving=e[e>1e-5]
    ref = float(np.percentile(moving, 80)) if moving.size else 1.
    duck = 1-.6*np.clip(e/max(ref, 1e-8), 0, 1)
    return (x+wet*duck[None, :]).astype('float32')
