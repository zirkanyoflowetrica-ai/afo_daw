"""Reverb y delay auxiliares POR FUNCION vocal, posteriores a afinacion y escalon.

La voz seca nunca pasa por estos efectos: cada envio es 100% wet, con EQ propia,
predelay, profundidad y ducking. Salidas (canales=2, muestras=N). Sin servicios ni IA.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import lfilter
from pedalboard import Pedalboard, Reverb, HighpassFilter, LowpassFilter

@dataclass(frozen=True)
class SpaceProfile:
    room: float
    pre_ms: int
    hp: int
    lp: int
    verb: float
    delay: float
    duck_db: float
    taps: tuple

# Referencias de partida, NO tiempos de decay medidos: room es la escala 0..1 del plugin.
# Los envios y filtrados se adaptan al papel de cada voz, sin boosts en la senal seca.
PROFILES = {
    'principal': SpaceProfile(.30, 62, 330, 7200, .060, .035, 3.0, ('slap','eighth')),
    'laterales': SpaceProfile(.43, 20, 420, 5400, .090, .040, 1.2, ('eighth','quarter')),
    'apoyo': SpaceProfile(.39, 25, 375, 6100, .075, .028, 1.5, ('slap','eighth')),
    'dobles': SpaceProfile(.29, 38, 355, 6500, .053, .041, 2.2, ('slap','eighth')),
    'coros': SpaceProfile(.52, 18, 430, 5150, .102, .033, .7, ('eighth','quarter')),
}


def _as_stereo(x):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim != 2 or a.shape[0] not in (1, 2):
        raise ValueError('Los efectos vocales esperan audio de uno o dos canales.')
    if a.shape[0] == 1:
        return np.repeat(a * math.sqrt(.5), 2, axis=0)
    return a


def _filter(x, sr, low, high):
    if not np.any(x) or x.shape[-1] < 32:
        return x.copy()
    return np.asarray(Pedalboard([HighpassFilter(float(low)), LowpassFilter(float(min(high, sr*.45)))])(
        np.ascontiguousarray(x, dtype=np.float32), sr), dtype=np.float32)


def _duck(wet, dry, lead, sr, max_db):
    """Duck de FX con ataque/release suave, nunca del audio seco."""
    control = lead if lead is not None and np.any(lead) else dry
    power = np.mean(control.astype(np.float32)**2, axis=0)
    env = np.sqrt(np.maximum(uniform_filter1d(power, size=max(1,int(sr*.045))), 0))
    samples = env[env > 1e-5]
    if samples.size == 0:
        return wet
    ref = float(np.percentile(samples, 80))
    if ref < 1e-7:
        return wet
    active = np.clip(env / max(ref*.8, 1e-7), 0, 1)
    # 85 ms smoothing forward, plus 160 ms de salida: evitar bombeo de consonantes.
    alpha = math.exp(-1.0 / max(1, int(sr*.16)))
    active = lfilter([1-alpha], [1,-alpha], active).astype(np.float32)
    gain = 10 ** (-(max_db * active) / 20)
    return (wet*gain[None,:]).astype(np.float32)


def _delay_time(name, bpm):
    if bpm is not None and 55 <= bpm <= 230:
        q = 60.0 / float(bpm)
        return {'slap': .107, 'eighth':q/2, 'quarter':q}[name]
    return {'slap': .107, 'eighth': .235, 'quarter': .47}[name]


def _delay_send(dry, sr, profile, bpm):
    """Taps filtrados sin realimentacion infinita, con rebotes discretos estereo."""
    n = dry.shape[1]
    out = np.zeros_like(dry)
    for i, tap in enumerate(profile.taps):
        dt = _delay_time(tap, bpm)
        lag = int(round(dt*sr))
        if lag <= 0 or lag >= n:
            continue
        # La primera reflexion respeta el paneo; la segunda cruza suavemente
        # a la otra oreja y aporta anchura sin invertir canales ni crear Haas seco.
        scaled = (0.74 if i == 0 else .30)
        out[:, lag:] += dry[:, :n-lag] * scaled
        if i > 0:
            out[:, lag:] += dry[::-1, :n-lag] * .14
    return _filter(out, sr, max(profile.hp, 410), min(profile.lp, 5600))


def _reverb_send(dry, sr, profile):
    n = dry.shape[1]
    if n < 32:
        return np.zeros_like(dry)
    filtered = _filter(dry, sr, profile.hp, profile.lp)
    reverberated = np.asarray(Pedalboard([Reverb(room_size=profile.room,
        damping=.78, wet_level=1., dry_level=0., width=.88)])(
        np.ascontiguousarray(filtered, dtype=np.float32), sr), dtype=np.float32)
    # Retrasar el retorno wet, NO la voz limpia.
    lag = int(sr * profile.pre_ms / 1000)
    out = np.zeros_like(dry)
    if lag < n:
        out[:,lag:] = reverberated[:,:n-lag]
    return _filter(out, sr, profile.hp, profile.lp)


def render_space(groups, sr, amount=45., bpm=0., lead=None):
    """Devuelve (FX por rol, descripcion). 0=sin FX; 45=espacio moderado.

    Parameters:
      groups: dict[rol, audio_estereo] YA PROCESADO y con escalon definitivo.
      bpm=0: slap libre y dos ecos predeterminados; si 55..230, 1/8 y 1/4.
    """
    try:
        intensity = float(np.clip(float(amount), 0., 100.))
        tempo = float(bpm)
    except (ValueError, TypeError):
        raise ValueError('La profundidad y el BPM deben ser numericos.')
    if not math.isfinite(intensity) or not math.isfinite(tempo) or (tempo != 0 and not 55 <= tempo <= 230):
        raise ValueError('Profundidad: 0-100; BPM: 0 o 55-230.')
    if intensity <= 0:
        return {}, 'Espacio vocal desactivado: señal seca intacta.'
    # 45 = 1x; 100 = 1.65x, para mantener un efecto comedido.
    scale = min(1.65, intensity / 45.)
    outputs = {}
    descriptions = []
    for role, source in groups.items():
        if role not in PROFILES:
            raise ValueError(f'Rol vocal desconocido: {role}')
        dry = _as_stereo(source)
        if dry.shape[-1] < 32 or not np.any(dry):
            continue
        config = PROFILES[role]
        reverb = _reverb_send(dry, sr, config)
        delay = _delay_send(dry, sr, config, tempo)
        wet = (reverb * (config.verb*scale) + delay*(config.delay*scale)).astype(np.float32)
        wet = _duck(wet, dry, _as_stereo(lead) if lead is not None else None, sr, config.duck_db)
        # Cortafuegos: una resonancia inusual en la reverb nunca debe disparar el bus.
        dry_rms = float(np.sqrt(np.mean(dry.astype(np.float64)**2)))
        wet_rms = float(np.sqrt(np.mean(wet.astype(np.float64)**2)))
        if wet_rms > max(1e-9, dry_rms * .24):
            wet *= dry_rms * .24 / wet_rms
        wet = np.nan_to_num(wet, nan=0, posinf=0, neginf=0)
        outputs[role] = wet.astype(np.float32)
        descriptions.append(f'{role}: room {config.room:.2f}; predelay {config.pre_ms} ms; '
                            f'FX filtrados {config.hp}-{config.lp} Hz; '
                            f'reverb send {20*math.log10(config.verb*scale):.1f} dB; '
                            f'delay send {20*math.log10(config.delay*scale):.1f} dB; duck hasta {config.duck_db:.1f} dB')
    tempo_note = f'delay sincronizado a {tempo:.0f} BPM' if tempo else 'delay corto libre (sin BPM confirmado)'
    return outputs, f'Profundidad vocal {intensity:.0f}/100; {tempo_note}; retornos wet aislados. ' + '; '.join(descriptions)
