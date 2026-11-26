"""Presets de los efectos nativos: de fábrica (aquí) y del usuario (datos/presets/fx/<efecto>.json).

Un preset guarda solo valores de parámetros por su id; lo que no nombra vuelve a su valor por
defecto del motor. Los valores se recortan al rango que declara el catálogo del motor.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import paths

FACTORY: dict[str, dict[str, dict[str, float]]] = {
    "gain": {
        "Unidad": {},
        "Recorte −6 dB": {"input": -6},
        "Mono compatible": {"mono": 1},
        "Polaridad invertida": {"polarity": 1},
    },
    "strip": {
        "Voz limpia": {"hpf": 90, "gate": -60, "lowGain": -2, "midFreq": 3000, "midGain": 2, "highGain": 3,
                       "compThr": -20, "ratio": 3, "attack": 8, "release": 120},
        "Bombo": {"hpf": 30, "lowGain": 4, "midFreq": 400, "midGain": -4, "highGain": 2,
                  "compThr": -16, "ratio": 4, "attack": 20, "release": 90},
        "Caja": {"hpf": 80, "gate": -45, "midFreq": 900, "midGain": -2, "highGain": 3,
                 "compThr": -18, "ratio": 4, "attack": 5, "release": 100, "drive": 15},
        "Bajo": {"hpf": 35, "lowGain": 3, "midFreq": 700, "midGain": 2, "compThr": -20, "ratio": 5,
                 "attack": 15, "release": 150, "drive": 20},
    },
    "eq": {
        "Plano": {},
        "Voz: presencia": {"hpf": 90, "hpfSlope": 1, "mid1Freq": 300, "mid1Gain": -3, "mid1Q": 1.2,
                           "mid2Freq": 3500, "mid2Gain": 3, "mid2Q": 0.9, "highFreq": 10000, "highGain": 2},
        "Quitar barro": {"mid1Freq": 300, "mid1Gain": -5, "mid1Q": 1.4},
        "Bombo: golpe": {"hpf": 30, "lowFreq": 60, "lowGain": 4, "mid1Freq": 350, "mid1Gain": -5,
                         "mid2Freq": 3500, "mid2Gain": 4, "mid2Q": 1.5},
        "Master: limpiar y abrir": {"hpf": 25, "hpfSlope": 1, "mid1Freq": 300, "mid1Gain": -1.5, "mid1Q": 0.7,
                                    "highFreq": 12000, "highGain": 1.5},
        "Teléfono": {"hpf": 400, "hpfSlope": 1, "mid2Freq": 1500, "mid2Gain": 6, "lpf": 3500},
    },
    "compressor": {
        "Voz suave": {"threshold": -20, "ratio": 3, "attack": 10, "release": 150, "knee": 6, "detector": 1, "makeup": 3},
        "Batería paralela": {"threshold": -30, "ratio": 8, "attack": 1, "release": 80, "knee": 3, "makeup": 8, "mix": 40},
        "Bus: pegamento": {"threshold": -16, "ratio": 2, "attack": 30, "release": 200, "knee": 10, "detector": 1, "makeup": 2},
        "Master: pegamento suave": {"threshold": -14, "ratio": 1.5, "attack": 30, "release": 150, "knee": 12,
                                    "detector": 1, "makeup": 1},
        "Bajo firme": {"threshold": -22, "ratio": 5, "attack": 15, "release": 120, "makeup": 4},
    },
    "glue": {
        "Bus de batería": {"threshold": -18, "ratio": 1, "attack": 4, "release": 1, "sidechain": 20, "makeup": 3},
        "Master: pegar suave": {"threshold": -10, "ratio": 0, "attack": 5, "release": 4, "sidechain": 120, "makeup": 1},
        "Mezcla al tempo": {"threshold": -14, "ratio": 0, "attack": 3, "release": 2, "sidechain": 90, "makeup": 2},
        "Aplastar en paralelo": {"threshold": -30, "ratio": 2, "attack": 0, "release": 0, "makeup": 12, "mix": 35},
    },
    "transient": {
        "Batería con más golpe": {"attack": 60, "sustain": -10},
        "Batería seca": {"attack": 10, "sustain": -70},
        "Suavizar golpes": {"attack": -60},
        "Más sala": {"sustain": 60},
    },
    "limiter": {
        "Seguro (−1 dBFS)": {"ceiling": -1, "release": 150},
        "Streaming (−1 dBTP aprox.)": {"input": 3, "ceiling": -1.5, "release": 120},
        "Fuerte": {"input": 8, "ceiling": -0.3, "release": 60},
        "Transparente": {"input": 2, "ceiling": -1, "release": 400},
    },
    "gate": {
        "Voz: quitar ruido": {"threshold": -50, "range": -24, "attack": 1, "hold": 80, "release": 250},
        "Batería: cerrar": {"threshold": -30, "range": -60, "attack": 0.1, "hold": 30, "release": 80},
        "Suave": {"threshold": -45, "range": -12, "attack": 2, "hold": 100, "release": 400},
    },
    "deesser": {
        "Voz masculina": {"freq": 5500, "q": 1.5, "threshold": -32, "range": -6},
        "Voz femenina": {"freq": 7500, "q": 1.5, "threshold": -32, "range": -6},
        "Suave": {"freq": 6500, "q": 1.0, "threshold": -28, "range": -3},
        "Fuerte (ancha)": {"freq": 6500, "q": 1.2, "threshold": -36, "range": -10, "mode": 1},
    },
    "tune": {
        "Natural (balada)": {"speed": 90, "humanize": 45, "amount": 90, "range": 1},
        "Pop moderno": {"speed": 25, "humanize": 30, "amount": 100, "range": 1},
        "Robot (trap)": {"speed": 0, "humanize": 0, "amount": 100, "range": 1},
        "Voz aguda suave": {"speed": 60, "humanize": 40, "amount": 85, "range": 0},
        "Voz grave suave": {"speed": 60, "humanize": 40, "amount": 85, "range": 2},
    },
    "harmonizer": {
        "Terceras arriba": {"voice1": 1, "level1": -4, "pan1": 0, "voice2": 0},
        "Coro 3ª y 5ª": {"voice1": 1, "level1": -5, "pan1": -40, "voice2": 5, "level2": -7, "pan2": 40},
        "Octava abajo (grave)": {"voice1": 10, "level1": -6, "pan1": 0, "voice2": 0, "glide": 10},
        "Quintas paralelas": {"mode": 1, "voice1": 5, "level1": -6, "pan1": -25, "voice2": 6, "level2": -8, "pan2": 25},
        "Solo la armonía": {"voice1": 1, "level1": 0, "pan1": 0, "voice2": 0, "dry": 0},
    },
    "doubler": {
        "Doble natural": {"voices": 1, "separation": 22, "variation": 45, "detune": 6, "spread": 70, "mix": 55},
        "Estribillo ancho": {"voices": 2, "separation": 18, "variation": 50, "detune": 10, "spread": 100, "mix": 60},
        "Coro de cuatro": {"voices": 4, "separation": 25, "variation": 60, "detune": 14, "spread": 90, "mix": 55},
        "Sutil (verso)": {"voices": 2, "separation": 12, "variation": 30, "detune": 4, "spread": 50, "mix": 30},
    },
    "saturator": {
        "Tubo cálido": {"drive": 9, "character": 0, "tone": -10, "mix": 100},
        "Cinta": {"drive": 12, "character": 1, "tone": -20, "bias": 10, "mix": 100},
        "Recorte duro": {"drive": 24, "character": 2, "tone": 10, "mix": 100, "output": -6},
        "Master: cinta sutil": {"drive": 4, "character": 1, "tone": 0, "mix": 30},
        "Paralelo sutil": {"drive": 18, "character": 0, "mix": 30},
    },
    "delay": {
        "Corchea": {"sync": 4, "feedback": 30, "mix": 25},
        "Corchea con puntillo": {"sync": 3, "feedback": 40, "mix": 25},
        "Ping-pong": {"sync": 2, "feedback": 45, "pingpong": 1, "mix": 30},
        "Slapback": {"sync": 0, "time": 110, "feedback": 0, "mix": 30, "lp": 6000},
        "Voz con ducking": {"sync": 2, "feedback": 35, "ducking": 70, "mix": 35},
    },
    "space": {
        "Sala pequeña": {"mode": 0, "size": 30, "predelay": 10, "decay": 0.8, "mix": 20},
        "Hall grande": {"mode": 1, "size": 85, "predelay": 30, "decay": 3.5, "mix": 25},
        "Placa vocal": {"mode": 2, "size": 55, "predelay": 40, "decay": 1.8, "damping": 9000, "mix": 20},
        "Cámara": {"mode": 3, "size": 45, "predelay": 15, "decay": 1.2, "mix": 22},
        "Ambiente infinito": {"mode": 1, "size": 100, "predelay": 60, "decay": 12, "damping": 5000, "mix": 35},
    },
    "analyzer": {
        "Estándar": {},
        "Rosa (4,5 dB/oct)": {"slope": 2},
        "Lateral (Side)": {"channel": 4},
    },
    # «taps» es el índice de la lista 1…8 (3 = cuatro ecos)
    "multitap": {
        "Cuatro corcheas": {"sync": 3, "taps": 3, "shape": 0, "decay": 70, "spread": 60, "mix": 35},
        "Crecida hacia la caja": {"sync": 4, "taps": 7, "shape": 1, "decay": 75, "spread": 30, "mix": 40},
        "Ecos de estadio": {"sync": 1, "taps": 2, "decay": 60, "spread": 100, "feedback": 40, "lp": 5000, "mix": 30},
        "Ráfaga de semicorcheas": {"sync": 4, "taps": 5, "shape": 2, "spread": 80, "mix": 30},
        "Tresillos": {"sync": 5, "taps": 2, "decay": 65, "spread": 70, "mix": 30},
    },
    "trancegate": {
        "Trance clásico": {"pattern": 3, "rate": 1, "length": 60},
        "Corcheas suaves": {"pattern": 1, "rate": 1, "length": 80, "attack": 8, "release": 40, "depth": 80},
        "Galope": {"pattern": 4, "rate": 1, "length": 50},
        "Ping-pong": {"pattern": 0, "rate": 1, "length": 70, "stereo": 1},
        "Bombeo a negras": {"pattern": 2, "rate": 1, "length": 95, "attack": 30, "release": 120, "depth": 70},
    },
    "shimmer": {
        "Octava celestial": {"shift": 0, "amount": 50, "decay": 5, "size": 80, "mix": 35},
        "Quinta brillante": {"shift": 1, "amount": 40, "decay": 4, "mix": 30},
        "Catedral de cristal": {"shift": 3, "amount": 60, "decay": 9, "size": 100, "predelay": 60, "mix": 40},
        "Octava abajo (oscura)": {"shift": 4, "amount": 35, "decay": 5, "damping": 5000, "lowcut": 80, "mix": 30},
        "Pad vocal": {"shift": 0, "amount": 30, "decay": 3, "size": 60, "predelay": 40, "mix": 25},
    },
    "textureverb": {
        "Seda": {"texture": 0, "depth": 50, "rate": 0.5, "decay": 3, "mix": 30},
        "Coro en la cola": {"texture": 0, "depth": 90, "rate": 1.2, "decay": 4, "mix": 35},
        "Granos lentos": {"texture": 1, "density": 6, "decay": 5, "mix": 35},
        "Lluvia de granos": {"texture": 1, "density": 30, "decay": 3, "mix": 30},
        "Cinta gastada": {"texture": 2, "depth": 60, "rate": 0.4, "decay": 3, "damping": 6000, "mix": 30},
    },
    "infinity": {
        "Cola eterna": {"freeze": 0, "decay": 40, "size": 100, "mix": 40},
        "Congelado": {"freeze": 1, "mix": 50},
        "Colchón de ambiente": {"freeze": 0, "decay": 25, "size": 80, "damping": 4000, "lowcut": 200, "mix": 30},
        "Pad oscuro": {"freeze": 0, "decay": 30, "damping": 2500, "mix": 45},
    },
    "granular": {
        "Nube suave": {"size": 120, "density": 25, "distance": 150, "spray": 200, "spread": 80, "mix": 40},
        "Octava arriba": {"size": 80, "density": 30, "pitch": 12, "distance": 100, "spray": 40, "mix": 45},
        "Cristales": {"size": 25, "density": 60, "pitch": 12, "pitchRand": 7, "spray": 300, "spread": 100, "mix": 35},
        "Reversa": {"size": 250, "density": 8, "reverse": 100, "distance": 400, "spray": 100, "mix": 45},
        "Textura congelada": {"size": 200, "density": 30, "spray": 600, "freeze": 1, "mix": 60},
    },
    "spectral": {
        "Desenfoque suave": {"mode": 0, "amount": 60, "mix": 50},
        "Mancha larga": {"mode": 0, "amount": 95, "mix": 70},
        "Robot": {"mode": 1, "amount": 100, "mix": 100},
        "Susurro": {"mode": 2, "amount": 100, "mix": 100},
        "Limpiar ruido": {"mode": 3, "threshold": -60, "mix": 100},
        "Metálico": {"mode": 0, "amount": 0, "shift": 300, "mix": 60},
        "Congelar": {"mode": 4, "mix": 100},
    },
    "fxlab": {
        "Las dos ramas": {"cross": 50},
        "Solo rama A": {"cross": 0},
        "Solo rama B": {"cross": 100},
        "Paralelo con seco": {"cross": 50, "levelA": -6, "levelB": -6, "dry": 70},
        "Ramas abiertas": {"cross": 50, "panA": -60, "panB": 60, "levelA": -3, "levelB": -3},
    },
}


def user_dir() -> Path:
    p = paths.user_data_dir() / "presets" / "fx"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _user_file(key: str) -> Path:
    if not key.isidentifier():
        raise ValueError(f"Efecto desconocido: {key}")
    return user_dir() / f"{key}.json"


def user_presets(key: str) -> dict[str, dict[str, float]]:
    f = _user_file(key)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {str(n): {str(k): float(v) for k, v in vals.items()} for n, vals in data.items()}
    except Exception:
        return {}


def listing(key: str) -> list[dict]:
    out = [{"name": n, "factory": True} for n in FACTORY.get(key, {})]
    out += [{"name": n, "factory": False} for n in sorted(user_presets(key))]
    return out


def resolve(key: str, name: str, desc: dict) -> dict[str, float]:
    """Valores completos (todos los parámetros) del preset, recortados a su rango."""
    vals = user_presets(key).get(name)
    if vals is None:
        vals = FACTORY.get(key, {}).get(name)
    if vals is None:
        raise KeyError(f"No existe el preset «{name}»")
    out = {}
    for p in desc["params"]:
        v = float(vals.get(p["id"], p["def"]))
        out[p["id"]] = min(max(v, p["min"]), p["max"])
    return out


def save(key: str, name: str, values: dict[str, float]) -> None:
    name = name.strip()
    if not name:
        raise ValueError("El preset necesita un nombre")
    if name in FACTORY.get(key, {}):
        raise ValueError(f"«{name}» es un preset de fábrica: elige otro nombre")
    data = user_presets(key)
    data[name] = {k: float(v) for k, v in values.items()}
    _user_file(key).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def delete(key: str, name: str) -> bool:
    data = user_presets(key)
    if name not in data:
        return False
    del data[name]
    _user_file(key).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
