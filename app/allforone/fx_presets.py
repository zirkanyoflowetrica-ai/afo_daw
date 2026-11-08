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
        "Teléfono": {"hpf": 400, "hpfSlope": 1, "mid2Freq": 1500, "mid2Gain": 6, "lpf": 3500},
    },
    "compressor": {
        "Voz suave": {"threshold": -20, "ratio": 3, "attack": 10, "release": 150, "knee": 6, "detector": 1, "makeup": 3},
        "Batería paralela": {"threshold": -30, "ratio": 8, "attack": 1, "release": 80, "knee": 3, "makeup": 8, "mix": 40},
        "Bus: pegamento": {"threshold": -16, "ratio": 2, "attack": 30, "release": 200, "knee": 10, "detector": 1, "makeup": 2},
        "Bajo firme": {"threshold": -22, "ratio": 5, "attack": 15, "release": 120, "makeup": 4},
    },
    "gate": {
        "Voz: quitar ruido": {"threshold": -50, "range": -24, "attack": 1, "hold": 80, "release": 250},
        "Batería: cerrar": {"threshold": -30, "range": -60, "attack": 0.1, "hold": 30, "release": 80},
        "Suave": {"threshold": -45, "range": -12, "attack": 2, "hold": 100, "release": 400},
    },
    "saturator": {
        "Tubo cálido": {"drive": 9, "character": 0, "tone": -10, "mix": 100},
        "Cinta": {"drive": 12, "character": 1, "tone": -20, "bias": 10, "mix": 100},
        "Recorte duro": {"drive": 24, "character": 2, "tone": 10, "mix": 100, "output": -6},
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
