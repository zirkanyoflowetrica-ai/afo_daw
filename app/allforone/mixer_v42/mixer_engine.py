"""Motor de mezcla automatica de stems, sin servicios externos.

Es DSP adaptativo basado en mediciones (NO un modelo de IA). Los nombres _L/_R
imponen panorama; voces _B al centro o _B_L/_B_R al 50%.
Las tomas vocales _L/_R quedan detras de la voz principal, con EQ sustractiva.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from math import gcd
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from pedalboard import (Compressor, HighpassFilter, HighShelfFilter, Limiter,
                        LowpassFilter, LowShelfFilter, PeakFilter, Pedalboard, Reverb)
from scipy.ndimage import uniform_filter1d, maximum_filter1d
from scipy.signal import resample_poly, welch, lfilter
from vocal_dsp import band, envelope, VOCALS, process_vocal, dynamic_cut, phase_notes, compare_phase
from vocal_space import render_space
from spectral_tools import spectrum
from track_tools import resonance_eq, section_balance
from mastering_tools import limit_linked, dynamics_summary, true_peak_db
from sonic_tools import enhance_vocal, enhance_master, enhance_bus
from audio_intelligence import identify_audio
from drum_split import split_drums
from neural_drums import try_separate
from mix_templates import DEFAULT_TEMPLATE, GUIDE_ONLY, inventory, style_trims, PROFILES

SR = 44100
MAX_TRACKS = 30
EPS = 1e-9
BACKING_STEP_DEFAULT_DB = 7.0  # Escalon de -7 dB para el bus vocal L/R

# Criterios de partida, ajustados de manera conservadora a cada stem.
# El LUFS objetivo es una REFERENCIA de balance, no una normalizacion absoluta
# que borre la dinamica original o fuerce cada pista a un mismo nivel.
TYPES = {
    "Voz de apoyo (_B)": dict(bus="Voces apoyo", lufs=-27, hp=125, send=-26, kw=[]),
    "Voz lateral (_L/_R)": dict(bus="Voces laterales", lufs=-27, hp=125, send=-26, kw=[]),
    "Coros": dict(bus="Voces", lufs=-27, hp=120, send=-21, kw=["coro", "chorus", "backing", "bv", "harmon"]),
    "Voz doble": dict(bus="Voces", lufs=-28, hp=120, send=-24, kw=["double", "dbl", "doble"]),
    "Drums": dict(bus="Bateria", lufs=-22, hp=25, send=None, kw=["drums", "drumkit", "drum kit", "bateria", "batería", "kit", "beat"]),
    "Kick": dict(bus="Bateria", lufs=-21, hp=27, send=None, kw=["kick", "bombo", "bd_"]),
    "Snare": dict(bus="Bateria", lufs=-23, hp=65, send=-27, kw=["snare", "redoblante", "caja"]),
    "Hi-hat": dict(bus="Bateria", lufs=-32, hp=260, send=None, kw=["hihat", "hi-hat", "hat", "charles"]),
    "Overheads / Platillos": dict(bus="Bateria", lufs=-30, hp=130, send=None, kw=["overhead", "cymbal", "platillo", "crash", "ride"]),
    "Toms": dict(bus="Bateria", lufs=-27, hp=45, send=None, kw=["tom"]),
    "Percusion": dict(bus="Bateria", lufs=-29, hp=130, send=-28, kw=["perc", "shaker", "pandereta", "conga", "clap"]),
    "Bajo": dict(bus="Bajo", lufs=-22, hp=27, send=None, kw=["bass", "bajo", "sub", "808"]),
    "Guitarra acustica": dict(bus="Guitarras", lufs=-28, hp=75, send=-26, kw=["acust", "acoustic"]),
    "Guitarra lead / solo": dict(bus="Guitarras", lufs=-25, hp=85, send=-25, kw=["gtr lead", "guitar lead", "guitarra lead", "gtr solo", "guitar solo"]),
    "Guitarra ritmica": dict(bus="Guitarras", lufs=-27, hp=80, send=-29, kw=["guit", "gtr"]),
    "Piano": dict(bus="Teclados", lufs=-27, hp=55, send=-27, kw=["piano", "pno", "rhodes"]),
    "Pad / Cuerdas": dict(bus="Teclados", lufs=-31, hp=85, send=-25, kw=["pad", "string", "cuerda", "violin", "cello"]),
    "Teclados / Synth": dict(bus="Teclados", lufs=-28, hp=70, send=-27, kw=["synth", "sinte", "teclado", "organ", "organo", "keys"]),
    "FX": dict(bus="Otros", lufs=-33, hp=50, send=None, kw=["fx", "riser", "sfx", "efecto", "impact"]),
    "Voz principal": dict(bus="Voces", lufs=-19, hp=75, send=-23, kw=["lead", "voz", "vocal", "vox", "main", "rap", "acapella"]),
    "Otro": dict(bus="Otros", lufs=-29, hp=30, send=None, kw=[]),
}

MASTERS = {
    "Dinamico (-14 LUFS)": dict(lufs=-14.0, tp=-1.0, ratio=1.35, max_gr=4.),
    "Comercial (-11 LUFS)": dict(lufs=-11.0, tp=-1.0, ratio=1.6, max_gr=6.),
    "Fuerte (-8.5 LUFS)": dict(lufs=-8.5, tp=-1.0, ratio=1.9, max_gr=8.),
    "Plataformas (-14 LUFS, -2 dBTP)": dict(lufs=-14., tp=-2., ratio=1.25, max_gr=3.),
}


@dataclass
class Analysis:
    lufs: float
    peak: float
    rms: float
    crest_db: float
    centroid_hz: float
    bands: dict[str, float]
    silent: bool


def _normal(text):
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def is_backing_voice(filename):
    """La marca _B es un token del nombre (no _BASS ni _BATERIA).

    Se admite Voz_B.wav y Voz_B_02.wav, incluyendo _B_L/_B_R; la
    posicion de _B es centro; _B_L/_B_R van al 50% de su lado.
    Se trata de una etiqueta EXPLICITA de voz, no de inferencia timbrica.
    """
    return re.search(r"_B(?=_|$)", Path(filename).stem, flags=re.IGNORECASE) is not None


def is_lateral_voice(filename, kind):
    """_L/_R en una voz identificada: acompañamiento. Nunca en instrumentos.

    _B_L/_B_R tambien pertenecen al grupo L/R, pero conservan su tipo _B
    y su paneo a 50%. No se deduce que un instrumento sea voz por su sufijo.
    """
    return pan_from_filename(filename) in ("Izquierda", "Derecha") and kind in VOCALS


def guess_type(filename):
    if is_backing_voice(filename):
        return "Voz de apoyo (_B)"
    name = _normal(Path(filename).stem)
    name = re.sub(r"(?:_L|_R)$", "", name, flags=re.I)
    name = re.sub(r"[_\-]+", " ", name)
    for typ, spec in TYPES.items():
        if any((lambda key: bool(re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", name))
                if len(key) <= 3 else key in name)(re.sub(r"[_\-]+", " ", kw))
               for kw in spec["kw"]):
            return typ
    return "Otro"


def pan_from_filename(filename):
    """Solo reconoce _L/_R AL FINAL DEL STEM, antes de la extension."""
    stem = Path(filename).stem
    m = re.search(r"_([LR])$", stem, flags=re.IGNORECASE)
    if not m:
        return "Original / centro"
    return "Izquierda" if m.group(1).upper() == "L" else "Derecha"


def load_stem(path, start=0., dur=0.):
    info = sf.info(path)
    if info.channels < 1:
        raise ValueError(f"Archivo sin canales: {Path(path).name}")
    if info.samplerate < 8000:
        raise ValueError(f"Frecuencia no compatible: {Path(path).name}")
    first = max(0, int(start * info.samplerate))
    frames = max(0, int(dur * info.samplerate)) if dur > 0 else -1
    data, sr = sf.read(path, start=first, frames=frames, always_2d=True, dtype="float32")
    x = np.nan_to_num(data.T, nan=0., posinf=0., neginf=0.)
    if x.shape[0] > 2:
        # Mezcla a estereo razonable en lugar de eliminar los canales extra.
        left, right = x[::2].mean(axis=0), x[1::2].mean(axis=0)
        x = np.stack([left, right]) if len(x[1::2]) else x[:1]
    if x.shape[0] == 2 and x.shape[1] and np.allclose(x[0], x[1], rtol=0, atol=1e-5):
        x = x[:1]
    if sr != SR and x.shape[1]:
        g = gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g, axis=1).astype(np.float32)
    return np.ascontiguousarray(x, dtype=np.float32)


def stereo(x, position):
    """Monos al centro (-3 dB por canal). Stereo original no se toca.

    Si _L/_R: convertir ese stem en mono y colocarlo SOLO en ese canal.
    """
    if position == "Original / centro":
        if x.shape[0] == 1:
            return np.repeat(x * math.sqrt(0.5), 2, axis=0)
        return x
    mono = x.mean(axis=0) if x.shape[0] == 2 else x[0]
    if position in ("50% izquierda", "50% derecha"):
        angle = np.pi/8 if position == "50% izquierda" else 3*np.pi/8
        return np.stack([mono*np.cos(angle), mono*np.sin(angle)])
    zeros = np.zeros_like(mono)
    return np.stack((mono, zeros) if position == "Izquierda" else (zeros, mono))


def _run(chain, x):
    return np.asarray(Pedalboard(chain)(np.ascontiguousarray(x, dtype=np.float32), SR), dtype=np.float32) if chain else x


def _lufs(x, meter):
    if x.shape[1] < int(0.45 * SR) or not np.any(x):
        return -math.inf
    try:
        result = float(meter.integrated_loudness(x[0] if x.shape[0] == 1 else x.T))
        return result if math.isfinite(result) else -math.inf
    except (ValueError, FloatingPointError):
        return -math.inf


def _peak(x):
    return float(np.max(np.abs(x))) if x.size else 0.


def _true_peak_db(x):
    return true_peak_db(x, SR)


def analyze(x, meter):
    mono = x.mean(axis=0)
    rms = float(np.sqrt(np.einsum("ij,ij->",x,x,dtype=np.float64)/max(1,x.size))) if x.size else 0.
    peak = _peak(x)
    if peak < 1e-6:
        return Analysis(-math.inf, peak, rms, 0., 0., {}, True)
    lufs = _lufs(x, meter)
    crest = 20 * math.log10(max(peak, EPS) / max(rms, EPS))
    f, power = spectrum(x, SR)
    total = float(power.sum()) + EPS
    centroid = float(np.sum(f * power) / total)
    bands = {}
    for name, lo, hi in (("sub", 20, 90), ("low", 90, 250), ("mud", 250, 600),
                         ("mid", 600, 2500), ("presence", 2500, 6000), ("air", 6000, 18000)):
        bands[name] = float(power[(f >= lo) & (f < hi)].sum() / total)
    return Analysis(lufs, peak, rms, crest, centroid, bands, False)


def _backing_eq(backing, lead, meter):
    """EQ conservadora para que la voz principal tenga prioridad.

    No usa una curva fija de brillo: un recorte selectivo y suave de presencia
    cuando el contenido de ambas voces coincide. Sin voz principal hace solo
    una ligera limpieza de medios-bajos cuando es necesaria.
    """
    b = analyze(backing, meter)
    main = analyze(lead, meter) if lead is not None else None
    chain = []
    notes = []
    if b.bands.get("mud", 0.) > .19:
        cut = float(np.clip((b.bands["mud"] - .19) * 8.0, 0., 1.5))
        if cut >= .15:
            chain.append(PeakFilter(330, -cut, .85))
            notes.append(f"menos medios-bajos {cut:.1f} dB")
    if main is not None and not main.silent:
        b_pres = b.bands.get("presence", 0.)
        m_pres = main.bands.get("presence", 0.)
        # Siempre deja un pequeno hueco si ambas tienen presencia apreciable.
        if b_pres > .015 and m_pres > .015:
            cut = float(np.clip(.65 + min(b_pres, m_pres) * 5., .65, 1.8))
            chain.append(PeakFilter(3200, -cut, .85))
            notes.append(f"espacio para voz principal {cut:.1f} dB a 3.2 kHz")
    return (_run(chain, backing) if chain else backing), (", ".join(notes) or "sin cortes adicionales")


def _blend_backing(buses, lead, meter, report, step_db=BACKING_STEP_DEFAULT_DB, fx_groups=None):
    """Aplica el escalon DESPUES de EQ, compresion y procesos de cada pista.

    Controla por separado apoyo central (_B) y voces laterales (_L/_R,
    incluyendo _B_L/_B_R), para que una toma _B central muy fuerte no
    obligue a silenciar innecesariamente el par de acompanamientos laterales.
    Los L/R se controlan como PAR/GRUPO, no por pista: la suma tambien queda
    detras de la voz principal. No normaliza un acompanamiento ruidoso.
    """
    step_db = float(np.clip(step_db, 5.0, 10.0))
    m_lufs = _lufs(lead, meter) if lead is not None else -math.inf
    results = []
    for bus_name, label, offset in (
        ("Voces apoyo", "Voces _B centro", 6.0),
        ("Voces laterales", "Voces L/R (grupo)", step_db),
    ):
        backing = buses.pop(bus_name, None)
        if backing is None:
            continue
        backing, eq_msg = _backing_eq(backing, lead, meter)
        b_lufs = _lufs(backing, meter)
        target = m_lufs - offset if math.isfinite(m_lufs) else -26.0
        if math.isfinite(b_lufs):
            reduction = max(0.0, b_lufs - target)
            # Un acompanamiento demasiado bajo no se sube excesivamente:
            # hasta +2 dB si existe principal y la pista tiene nivel util.
            lift = min(2.0, max(0.0, target - b_lufs - 1.0)) if math.isfinite(m_lufs) and b_lufs > -45 else 0.0
            backing *= 10 ** ((lift - reduction) / 20.0)
        else:
            reduction = lift = 0.0
        if lead is not None and np.any(lead):
            e = np.mean(lead.astype(np.float32)**2, axis=0)
            e = np.sqrt(np.maximum(uniform_filter1d(e, size=int(SR*.040)+1), 0.))
            moving = e[e > 1e-5]
            ref = float(np.percentile(moving, 80)) if moving.size else 0.0
            if ref > EPS:
                fraction = np.clip(e / max(.7*ref, EPS), 0.0, 1.0)
                fraction = uniform_filter1d(fraction, size=int(SR*.045)+1)
                duck = 1.0 * np.clip(fraction, 0.0, 1.0)
                backing *= (10 ** (-duck / 20.0))[None, :]
                duck_msg = "ducking hasta 1 dB sobre frases principales"
            else:
                duck_msg = "sin ducking"
        else:
            duck_msg = "sin voz principal detectada"
        results.append(backing)
        if fx_groups is not None:
            fx_groups["apoyo" if bus_name == "Voces apoyo" else "laterales"] = backing.copy()
        report.append(f"{label}: EQ {eq_msg}; escalon objetivo {offset:.1f} dB bajo principal (medido por grupo en LUFS); "
                      f"ajuste {lift-reduction:+.1f} dB; {duck_msg}."
                      + (" Sin principal: techo -26 LUFS." if not math.isfinite(m_lufs) else ""))
    if not results:
        return None
    all_backing = sum(results)
    buses.setdefault("Voces", np.zeros_like(all_backing))
    buses["Voces"] += all_backing
    return all_backing


def _adaptive_chain(typ, a):
    spec = TYPES[typ]
    plugins = [] if typ in VOCALS else [HighpassFilter(spec["hp"])]
    b = a.bands
    # EQ sustractiva en respuesta al contenido medido; nunca boosts fijos.
    if b.get("mud", 0) > 0.23 and typ not in (*VOCALS, "Kick", "Bajo"):
        cut = min(3.0, (b["mud"] - 0.23) * 10)
        plugins.append(PeakFilter(350, -cut, 0.85))
    if b.get("presence", 0) > 0.31 and typ in ("Hi-hat", "Overheads / Platillos"):
        plugins.append(PeakFilter(4200, -min(2.5, (b["presence"] - 0.31) * 9), 1.1))
    if b.get("sub", 0) > 0.55 and typ not in (*VOCALS, "Kick", "Bajo"):
        plugins.append(LowShelfFilter(90, -2.0))
    # Solo comprimir cuando existe rango transitorio razonable. Evita
    # aplastar stems ya limitados o silenciosos.
    if a.crest_db > 11 and a.rms > 0.0005 and typ not in ("FX", "Overheads / Platillos", "Pad / Cuerdas"):
        rms_db = 20 * math.log10(a.rms)
        threshold = float(np.clip(rms_db + 8, -34, -6))
        ratio = 2.4 if typ in ("Voz principal", "Bajo", "Kick") else 1.7
        plugins.append(Compressor(threshold_db=threshold, ratio=ratio,
                                  attack_ms=12 if typ in ("Kick", "Snare") else 22,
                                  release_ms=110))
    return plugins


def _apply_masking(buses, meter):
    """Mitigacion dinamica de presencia, guiada por actividad vocal."""
    details = []
    if "Voces" in buses:
        vocal = analyze(buses["Voces"], meter)
        for name in ("Guitarras", "Teclados"):
            if name not in buses:
                continue
            comp = analyze(buses[name], meter)
            overlap = min(comp.bands.get("presence", 0), vocal.bands.get("presence", 0))
            if overlap > 0.09:
                cut = min(1.8, 0.5 + overlap * 4)
                buses[name], actual = dynamic_cut(buses[name], SR, 2200, 4500, cut, buses["Voces"])
                details.append(f"Enmascaramiento: {name}, EQ dinamica de hasta {cut:.1f} dB en 2.2-4.5 kHz para abrir espacio a voces.")
    if "Kick" in buses and "Bajo" in buses:
        pass  # Los kicks comparten bus Bateria; evitar detecciones ficticias.
    return details


def _apply_reference_tone(mix, reference, meter, return_chain=False):
    """Igualacion timbrica SUAVE de banda ancha; no imita efectos ni plugins."""
    ref = analyze(reference, meter)
    src = analyze(mix, meter)
    if ref.silent or src.silent:
        return (mix, "Referencia silenciosa, se ignora su tono.", []) if return_chain else (mix, "Referencia silenciosa, se ignora su tono.")
    # Espectro relativo en dB normalizado al promedio para no copiar volumen.
    tags = ("low", "mud", "presence", "air")
    a = np.asarray([max(src.bands.get(t, 0.), 1e-5) for t in tags])
    b = np.asarray([max(ref.bands.get(t, 0.), 1e-5) for t in tags])
    delta = 10 * np.log10(b / a)
    delta -= float(np.mean(delta))
    delta = np.clip(delta * .28, -1.5, 1.5)
    chain = [LowShelfFilter(130, float(delta[0])),
             PeakFilter(380, float(delta[1]), .9),
             PeakFilter(3400, float(delta[2]), .8),
             HighShelfFilter(8500, float(delta[3]))]
    out = _run(chain, mix)
    msg = ("Referencia: correccion tonal conservadora "
           f"graves {delta[0]:+.1f} dB, medios-bajos {delta[1]:+.1f} dB, "
           f"presencia {delta[2]:+.1f} dB, aire {delta[3]:+.1f} dB.")
    return (out, msg, chain) if return_chain else (out, msg)


def _kick_duck_bass(buses, kick, report):
    """Ducking solo de graves coincidentes, release según anchura de golpe."""
    if "Bajo" not in buses or kick is None or not np.any(kick):
        return
    from scipy.signal import find_peaks, peak_widths
    f,p = spectrum(kick, SR)
    mask=(f>=25)&(f<=140)
    center=float(f[mask][np.argmax(p[mask])]) if np.any(mask) else 65.
    high=float(np.clip(center*2.5,90,220))
    bass_low=band(buses["Bajo"],SR,25,high)
    if np.mean(bass_low.astype(float)**2)<np.mean(buses["Bajo"].astype(float)**2)*.08:
        report.append("Kick/bajo: sin ducking (poco solapamiento grave).")
        return
    e=envelope(band(kick,SR,25,high),SR,.012)
    hop=max(1,SR//200)
    frames=e[::hop]
    peaks,_=find_peaks(frames,height=float(frames.max())*.3,distance=20)
    widths=peak_widths(frames,peaks,rel_height=.7)[0]/200 if len(peaks) else np.array([.09])
    release=float(np.clip(np.median(widths)*.8,.04,.15))
    e=maximum_filter1d(e,size=int(SR*.015)+1)
    alpha=np.exp(-1/(SR*release))
    e=lfilter([1-alpha],[1,-alpha],e)
    moving=e[e>1e-6]
    ref=float(np.percentile(moving,90)) if moving.size else 0.
    if ref<=EPS:
        return
    reduction=2.*np.clip(e/ref,0,1)
    buses["Bajo"]=(buses["Bajo"]+bass_low*(10**(-reduction/20)-1)[None,:]).astype('float32')
    report.append(f"Kick/bajo: ducking grave 25-{high:.0f} Hz, hasta 2 dB; release adaptativo {release*1000:.0f} ms.")


def _should_tune_vocal(tuning, typ, lateral, pos):
    """Selecciona afinación por rol/posición sin afectar limpieza ni FX.

    Los apoyos _B_L/_B_R se evalúan por posición antes que por tipo.
    Los diccionarios V3.7 sin opciones separadas conservan su comportamiento.
    """
    if not isinstance(tuning, dict) or tuning.get('strength', 0) <= 0:
        return False
    legacy_backings = bool(tuning.get('include_backings', False))
    if lateral and pos in ('Izquierda', '50% izquierda'):
        return bool(tuning.get('tune_left', legacy_backings))
    if lateral and pos in ('Derecha', '50% derecha'):
        return bool(tuning.get('tune_right', legacy_backings))
    if typ == 'Voz principal':
        return bool(tuning.get('tune_lead', True))
    return bool(tuning.get('tune_center_backings', legacy_backings))


def render_mix(tracks, reverb_amount=None, start=0., dur=0., progress=None,
               reference_path=None, return_details=False, tuning=False,
               backing_step_db=BACKING_STEP_DEFAULT_DB, vocal_space_amount=45.,
               vocal_space_bpm=0., auto_music_bpm=False, music_source_path=None, music_plan=None,
               mix_template=DEFAULT_TEMPLATE, template_mode=GUIDE_ONLY):
    """Mezcla automatica. Con return_details=True devuelve tambien stems derivados.

    No se cambia el paneo salvo sufijo _L/_R; un stem stereo conserva su ancho.
    """
    tracks = [t for t in tracks if t.get("path")][:MAX_TRACKS]
    if mix_template not in PROFILES:
        raise ValueError('Plantilla de mezcla no reconocida.')
    if template_mode not in (GUIDE_ONLY, 'Guía + balance muy sutil'):
        raise ValueError('Modo de guía de mezcla no reconocido.')
    template_inventory = inventory([Path(t['path']).name for t in tracks])
    if not tracks:
        raise ValueError("No hay stems para mezclar.")
    if start < 0 or dur < 0:
        raise ValueError("El inicio y la duracion deben ser positivos.")
    n = 0
    for t in tracks:
        info = sf.info(t["path"])
        frames = max(0, info.frames - int(start * info.samplerate))
        if dur > 0:
            frames = min(frames, int(dur * info.samplerate))
        n = max(n, int(math.ceil(frames * SR / info.samplerate)))
    if n == 0:
        raise ValueError("Los stems estan vacios.")
    meter = pyln.Meter(SR)
    buses = {}
    send = np.zeros((2, n), dtype=np.float32)
    role_sources = {}  # Auxiliares independientes para principal, dobles y coros
    processed_tracks = []
    kick_signal = np.zeros((2, n), dtype=np.float32)
    lead_monitor = np.zeros((2, n), dtype=np.float32)
    derived = {}
    report = ["MEZCLA AUTOMATICA V4.2 | Plantillas orientativas + afinacion individual", "",
              f"GUIA ELEGIDA: {PROFILES[mix_template]['name']} | {template_mode}",
              "Los criterios estilisticos no sustituyen la escucha ni aplican EQ o compresores fijos.", "",
              "Paneo: SOLO _L/_R; excepcion _B: centro o _B_L/_B_R al 50%; voces laterales a nivel secundario.",
              "Clasificacion: nombre explicitamente reconocido + analisis de audio; CLAP opcional.",
              "ATENCION: separar un kit en piezas con DSP no da stems aislados limpios.", ""]
    # Preanálisis de instrumentos SIN procesar; las voces se afinan luego,
    # una por una, antes de enviarse a cualquier bus.
    music_result = None
    auto_key_requested = isinstance(tuning,dict) and bool(tuning.get('auto_key')) and float(tuning.get('strength',0))>0
    if music_plan is not None:
        # La vista previa autorizada contiene la decisión musical; no se recalcula
        # en secreto ni se sobreescribe con una predicción distinta.
        if not music_plan.get('confirmed'):
            raise ValueError('La tonalidad y el BPM deben confirmarse antes de la mezcla.')
        music_result = music_plan.get('analysis') or {}
        if isinstance(tuning,dict):
            tuning = dict(tuning, key=music_plan['key'], scale=music_plan['scale'], auto_key=False)
        vocal_space_bpm = float(music_plan['bpm'])
        auto_key_requested = False
        report.append('AJUSTE MUSICAL CONFIRMADO: '
                      +f"{music_plan['key']} {music_plan['scale']}, {vocal_space_bpm:.1f} BPM; "
                      +music_plan.get('source','usuario'))
        report.append('Los detectores solo aportan sugerencias; no reconfiguran la afinacion sin confirmacion.')
    elif auto_key_requested or (auto_music_bpm and not vocal_space_bpm):
        from music_analysis import analyze_music
        music_result = analyze_music(tracks, instrumental_source=music_source_path)
        report.append('PREANALISIS INSTRUMENTAL (sin voces):\n'+music_result.summary())
        if auto_key_requested:
            # Una predicción dudosa nunca decide qué notas modificar.
            if (music_result.key and music_result.scale and music_result.key_confidence >= .50):
                tuning = dict(tuning, key=music_result.key,scale=music_result.scale)
                report.append(f'Afinacion por tonalidad detectada: {music_result.key} {music_result.scale}. Cada stem vocal se procesa independientemente.')
            else:
                tuning = dict(tuning,strength=0)
                report.append('PROTECCION: tonalidad incierta. Afinacion automatica omitida. Selecciona manualmente la escala para corregir las voces.')
        if auto_music_bpm and not vocal_space_bpm:
            if music_result.bpm and music_result.bpm_confidence >= .30:
                vocal_space_bpm = music_result.bpm
                report.append(f'Delay vocal sincronizado a BPM detectado: {vocal_space_bpm:.1f}.')
            else:
                report.append('BPM no fiable; delay libre sin sincronizar. Puedes introducirlo manualmente.')
    phase_history = []
    active = 0
    for i, t in enumerate(tracks):
        name = Path(t["path"]).name
        if progress:
            progress((i, len(tracks)), desc=f"Escuchando y analizando {name}")
        x = load_stem(t["path"], start, dur)
        if not x.shape[1]:
            report.append(f"{name}: archivo vacio; omitido")
            continue
        a = analyze(x, meter)
        if a.silent:
            report.append(f"{name}: silencioso; omitido")
            continue
        report.extend(phase_notes(x, name))
        report.extend(compare_phase(x, name, phase_history, SR))
        active += 1
        name_typ = guess_type(name)
        audio_guess = identify_audio(x, SR)
        typ = name_typ
        origin = "nombre"
        # Solo usar heuristica si se distingue lo suficiente; no inventar voces.
        if typ == "Otro" and audio_guess.confidence >= .65:
            typ, origin = audio_guess.kind, f"audio ({audio_guess.confidence:.0%})"
        # La IA opcional aporta reconocimiento genuinamente aprendido de audio.
        ai_res = None
        try:
            from ai_classifier import recognize
            ai_res = recognize(x, SR)
        except (ImportError, OSError, RuntimeError, ValueError, TypeError):
            pass
        if ai_res and (typ == "Otro" or (name_typ == "Otro" and ai_res[1] >= audio_guess.confidence)):
            typ, origin = ai_res[0], f"IA CLAP ({ai_res[1]:.0%} relativo)"
        # La etiqueta _B es intencional: tiene prioridad frente a nombre,
        # heuristica e IA; _B_L y _B_R van al 50% de su lado.
        if is_backing_voice(name):
            typ, origin = "Voz de apoyo (_B)", "marcador explicito _B"
        pos = backing_position(name) if typ == "Voz de apoyo (_B)" else pan_from_filename(name)
        # _L/_R de una pista VOCAL identificada => acompanamiento, no lead.
        # _B_L/_B_R conserva su tipo _B y su paneo de 50%.
        lateral = is_lateral_voice(name, typ)
        if lateral and typ != "Voz de apoyo (_B)":
            typ, origin = "Voz lateral (_L/_R)", f"{origin} + sufijo lateral vocal"
        if typ not in TYPES:
            typ = "Otro"
        if typ == "Drums":
            # Un stem de bateria combinado, separado automatico en sub-stems.
            try:
                drum_parts, neural_msg = try_separate(x, SR)
                if drum_parts is None:
                    drum_parts = split_drums(x, SR)
                report.append(f"{name}: {neural_msg}")
            except ValueError:
                drum_parts = None
            if drum_parts:
                report.append(f"{name}: bateria completa [{origin}], separada en 5 sub-stems; calidad depende del separador.")
                dry_kit = np.zeros((2, n), dtype=np.float32)
                for part, audio in drum_parts.items():
                    # Conservar para descargar tal cual; no se entregan como
                    # aislamientos profesionales ni se multiplica su LUFS.
                    derived[f"{Path(name).stem}__{part}"] = audio
                    if not np.any(audio):
                        continue
                    asub = analyze(audio, meter)
                    # Ganancias moderadas sin normalizar cada banda artificial.
                    chain = _adaptive_chain(part, asub)
                    processed = _run(chain, audio)
                    # EQ en grupos sin boosts de volumen exagerados.
                    y = stereo(processed, pos)
                    if "Bateria" not in buses:
                        buses["Bateria"] = np.zeros((2, n), dtype=np.float32)
                    buses["Bateria"][:, :y.shape[1]] += y
                    dry_kit[:, :y.shape[1]] += y
                    if part == "Kick":
                        kick_signal[:, :y.shape[1]] += y
                processed_tracks.append(dict(name=name, path=str(t["path"]), kind=typ, position=pos, audio=dry_kit, note="Kit procesado; sub-stems DSP exportados aparte"))
                continue
            report.append(f"{name}: bateria demasiado corta; procesada como kit entero.")
        spec = TYPES[typ]
        level = a.lufs if math.isfinite(a.lufs) else 20 * math.log10(max(a.rms, EPS))
        delta = float(np.clip(spec["lufs"] - level, -7, 7))
        template_trim = 0.
        if template_mode != GUIDE_ONLY:
            from mix_templates import GROUPS, role_for
            guide_item = dict(template_inventory[i], kind=typ,
                              role=role_for(name,typ))
            # Si la clasificación acústica cambió respecto del nombre, no se
            # fuerza la cantidad de capas ni los trims de otro instrumento.
            guide_item['group'] = GROUPS[guide_item['role']]
            if guide_item['group'] != template_inventory[i]['group']:
                guide_item['layer_count'] = 1
            template_trim = style_trims(mix_template, guide_item, a)
            delta = float(np.clip(delta + template_trim, -7., 7.))
        if a.rms < .00015:
            delta = min(delta, 0.)
        chain = _adaptive_chain(typ, a)
        prepared = x
        vocal_note = ""
        if typ in VOCALS:
            tune_this = _should_tune_vocal(tuning, typ, lateral, pos)
            prepared, vocal_note = process_vocal(prepared, SR, tuning if tune_this else False, kind=typ)
            if not tune_this and isinstance(tuning, dict) and tuning.get('strength', 0) > 0:
                vocal_note += '; afinacion omitida por configuracion de esa voz'
            report.append(f"{name}: {vocal_note}")
        processed = _run(chain, prepared * (10 ** (delta / 20)))
        processed, resonance_note = resonance_eq(processed, SR, typ)
        report.append(f"{name}: {resonance_note}")
        if typ in VOCALS:
            processed,finish_note=enhance_vocal(processed,SR,typ)
            vocal_note+="; "+finish_note
            report.append(f"{name}: {finish_note}")
        # La voz _B parte de mono antes del paneo especificado, aunque traiga
        # panorama o extension de canales. Esto no afecta los demas stems.
        if typ in ("Voz de apoyo (_B)", "Voz lateral (_L/_R)"):
            processed = processed.mean(axis=0, keepdims=True)
        y = stereo(processed, pos)
        processed_tracks.append(dict(name=name, path=str(t["path"]), kind=typ, position=pos, audio=y,
                                     note=vocal_note+"; "+resonance_note+
                                     (f"; sesgo de guía {template_trim:+.2f} dB" if template_trim else "")))
        length = min(y.shape[1], n)
        # Las _B_L/_B_R van al MISMO bus lateral que las voces _L/_R.
        # Las _B del centro mantienen su balance propio.
        bus_name = "Voces laterales" if lateral else spec["bus"]
        buses.setdefault(bus_name, np.zeros((2, n), dtype=np.float32))
        buses[bus_name][:, :length] += y[:, :length]
        if typ == "Kick":
            kick_signal[:, :length] += y[:, :length]
        if typ == "Voz principal":
            lead_monitor[:, :length] += y[:, :length]
        # Fuente de espacio por tipo, despues de afinacion, EQ y paneo.
        # _B y L/R se añaden DESPUES del escalon global, no aqui.
        if typ in VOCALS and not lateral and typ != "Voz de apoyo (_B)":
            role = {"Voz principal":"principal", "Voz doble":"dobles", "Coros":"coros"}.get(typ)
            if role:
                role_sources.setdefault(role, np.zeros((2,n),dtype=np.float32))
                role_sources[role][:,:length] += y[:,:length]
        elif spec["send"] is not None and typ not in VOCALS:
            send[:,:length] += y[:,:length] * 10 ** (spec["send"] / 20)
        if template_trim:
            report.append(f"{name}: orientación estilística muy sutil {template_trim:+.2f} dB "+
                          "(no modifica EQ ni afinación; máximo 1 dB por stem).")
        report.append(f"{name}: {typ} ({origin}); lectura audio: {audio_guess.kind} "
                      f"({audio_guess.confidence:.0%}); {pos}; ganancia {delta:+.1f} dB; "
                      f"EQ adaptativa, compresion {'si' if any(isinstance(z, Compressor) for z in chain) else 'no'}")
    if not active:
        raise ValueError("No hay audio util.")
    report.append(f"Fase: revisados L/R y pares de {len(phase_history)} stems (pares: primeros 30 s, sin buscar desfases temporales). Solo se avisan correlaciones negativas fuertes.")
    backing_groups = {}
    backing = _blend_backing(buses, lead_monitor if np.any(lead_monitor) else None,
                             meter, report, backing_step_db, fx_groups=backing_groups)
    context_gain, context_note = section_balance(buses, lead_monitor, SR)
    report.append(context_note)
    # Las nuevas fuentes de FX _B/L/R heredan el balance FINAL, no envios previos.
    for role, signal in backing_groups.items():
        role_sources[role] = (signal * context_gain[None,:] if context_gain is not None else signal)
    if context_gain is not None:
        for role in ('principal', 'dobles', 'coros'):
            if role in role_sources:
                role_sources[role] *= context_gain[None,:]
    fx_by_role, space_report = render_space(role_sources, SR, amount=vocal_space_amount,
        bpm=vocal_space_bpm, lead=lead_monitor if np.any(lead_monitor) else None)
    report.append(space_report)
    _kick_duck_bass(buses, kick_signal, report)
    report.extend(_apply_masking(buses, meter))
    mix = np.zeros((2, n), dtype=np.float32)
    final_buses = {}
    for bus, y in buses.items():
        if bus in ('Bateria','Guitarras','Teclados'):
            y,parallel_amount=enhance_bus(y,SR)
            report.append(f"{bus}: compresion paralela discreta {parallel_amount:.0%}, omitida si ya esta denso.")
        if bus == "Voces" and analyze(y, meter).crest_db > 13:
            y = _run([Compressor(threshold_db=-18, ratio=1.5,
                                 attack_ms=25, release_ms=140)], y)
        mix += y
        final_buses[bus] = y
    for role, wet in fx_by_role.items():
        if np.any(wet):
            mix += wet
            final_buses[f"FX vocales - {role}"] = wet
    if np.any(send):
        wet = _run([HighpassFilter(250), Reverb(room_size=.38, damping=.72,
                     wet_level=1., dry_level=0., width=1.), LowpassFilter(8500)], send)
        mix += wet * .6
        final_buses["FX instrumentos"] = wet * .6
    ref = None
    if reference_path:
        ref = load_stem(reference_path)
        if not ref.shape[1] or analyze(ref, meter).silent:
            report.append("Referencia vacia o silenciosa: ignorada.")
            ref = None
        else:
            mix, detail, reference_chain = _apply_reference_tone(mix, ref, meter, return_chain=True)
            report.append(detail)
            for bus in final_buses:
                final_buses[bus] = _run(reference_chain, final_buses[bus])
            # La suma de las instancias de filtros puede diferir unos LSB del
            # filtrado del total. Usar la suma exportada como mezcla canónica.
            mix = np.zeros((2, n), dtype=np.float32)
            for signal in final_buses.values():
                mix += signal
            report.append("La referencia NO se mezcla con los stems y NO copia el procesamiento interno de la cancion.")
    mix_lufs = _lufs(mix, meter)
    mix_gain = 1.
    if math.isfinite(mix_lufs):
        mix_gain = 10 ** (float(np.clip(-18 - mix_lufs, -9, 9)) / 20)
        mix *= mix_gain
    peak = _peak(mix)
    if peak > .88:
        mix_gain *= .88 / peak
        mix *= (.88 / peak)
        report.append("Mezcla atenuada para evitar clipping.")
    report.append(f"Stems procesados: {active}. Buses: {', '.join(buses)}.")
    report.append(f"Mezcla: {_lufs(mix, meter):.1f} LUFS; {_true_peak_db(mix):.1f} dBTP estimado.")
    report.append("El reconocimiento es probabilistico y no garantiza una mezcla profesional sin escucha critica.")
    for bus in final_buses:
        final_buses[bus] = final_buses[bus] * mix_gain
    details = {"derived": derived, "reference_lufs": _lufs(ref, meter) if ref is not None else None,
               "tracks": processed_tracks, "buses": final_buses, "mix_gain": mix_gain,
               "dynamics": dynamics_summary(mix, SR),
               "mix_template":mix_template, "template_mode":template_mode,
               "music_analysis": (music_result.as_dict() if hasattr(music_result,"as_dict") else music_result) if music_result else None}
    if return_details:
        return mix, "\n".join(report), details
    return mix, "\n".join(report)

def master(mix, preset, target_lufs=None):
    """Master adaptativo con prioridad en evitar clipping y exceso de limitacion.

    El objetivo LUFS es orientativo: si el limitador impide alcanzarlo, no
    se incrementa el nivel indefinidamente. Se informa el resultado real.
    """
    if preset not in MASTERS:
        raise ValueError(f"Master no reconocido: {preset}")
    p = dict(MASTERS[preset])
    if target_lufs is not None and math.isfinite(float(target_lufs)):
        p["lufs"] = float(np.clip(target_lufs, -16., -9.))
    meter = pyln.Meter(SR)
    if _peak(mix) <= EPS:
        return mix.copy(), {"lufs": -math.inf, "true_peak": -120., "note": "Silencio"}
    a = analyze(mix, meter)
    chain = [HighpassFilter(24)]
    # Solo reducir acumulaciones espectrales muy claras.
    if a.bands.get("mud", 0.) > 0.27:
        chain.append(PeakFilter(330, -1.0, 0.8))
    if a.bands.get("air", 0.) < 0.01 and a.centroid_hz < 1600:
        chain.append(HighShelfFilter(9500, 0.5))
    if a.crest_db > 13:
        chain.append(Compressor(threshold_db=-15, ratio=p["ratio"], attack_ms=35, release_ms=175))
    pre = _run(chain, mix)
    pre, color_note = enhance_master(pre, SR)
    pre_l = _lufs(pre, meter)
    if not math.isfinite(pre_l):
        out, stats = limit_linked(pre, SR, p["tp"], p["max_gr"])
        tp = _true_peak_db(out)
        if tp > p["tp"]-.05:
            out *= 10**((p["tp"]-.05-tp)/20)
        return out, {"lufs": pre_l, "true_peak": _true_peak_db(out), "note": "Audio demasiado corto para LUFS; techo de picos protegido", **stats, **dynamics_summary(out, SR)}
    desired = float(np.clip(p["lufs"] - pre_l, -18., 18.))
    desired = min(desired, p["tp"] - _true_peak_db(pre) + p["max_gr"])
    out, limit_stats = limit_linked(pre * 10**(desired/20), SR, p["tp"], p["max_gr"])
    tp = _true_peak_db(out)
    if tp > p["tp"] - .05:
        out *= 10**((p["tp"]-.05-tp)/20)
    final_lufs = _lufs(out, meter)
    # Si la curva de release ha bajado el promedio, no perseguir LUFS con más drive.
    note = ("Objetivo aproximado logrado." if abs(final_lufs-p["lufs"])<.5
            else "Se conserva dinamica y presupuesto de limitacion; objetivo LUFS orientativo.")
    return out, {"lufs": final_lufs, "true_peak": _true_peak_db(out), "note": note+" "+color_note,
                 "target_lufs":p["lufs"], "ceiling_db":p["tp"], **limit_stats, **dynamics_summary(out, SR)}


def save_wav(path, audio, subtype="PCM_24"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = audio.T if subtype == "FLOAT" else np.clip(audio.T, -1, 1)
    sf.write(str(path), samples, SR, subtype=subtype)
    return str(path.resolve())


def backing_position(filename):
    raw = pan_from_filename(filename)
    return {"Izquierda": "50% izquierda", "Derecha": "50% derecha"}.get(raw, "Original / centro")



