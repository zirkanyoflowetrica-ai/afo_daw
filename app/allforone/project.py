"""Proyecto de AllForOne (.afo): JSON con la sesión para guardarla y recuperarla.

La interfaz aporta lo que solo ella sabe (pistas con sus notas, patrones y ajustes, tempo, master);
aquí se añade lo que vive en el motor: la cadena de efectos de cada pista y del master con sus
valores, puenteo y automatización, y la ruta de cada audio. Los audios no se copian: se guarda su
ruta absoluta y la relativa al proyecto, para poder mover la carpeta entera.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

FORMAT = "allforone-project"
VERSION = 1
MASTER = 0                       # id del master en las cadenas de efectos del motor
AUDIO_TYPES = ("audio", "voz")


def chain_of(engine, catalog: list[dict], track_id: int) -> list[dict]:
    """Cadena de efectos de una pista tal como se guarda (valores por id de parámetro)."""
    out = []
    for e in engine.effects(track_id):
        desc = next((d for d in catalog if d["key"] == e["key"]), None)
        if desc is None:
            continue
        ids = [p["id"] for p in desc["params"]]
        auto = {pid: [[round(t, 6), v] for t, v in engine.effect_automation(e["id"], pid)] for pid in e.get("automated", [])}
        out.append({"key": e["key"], "enabled": bool(e["enabled"]), "values": dict(zip(ids, e["values"])),
                    "automation": {k: v for k, v in auto.items() if v}})
    return out


def restore_chain(engine, catalog: list[dict], track_id: int, chain: list[dict]) -> list[str]:
    """Sustituye la cadena de la pista por la guardada. Devuelve avisos (efectos que ya no existen…)."""
    warnings = []
    for e in engine.effects(track_id):
        engine.remove_effect(e["id"])
    for fx in chain or []:
        desc = next((d for d in catalog if d["key"] == fx.get("key")), None)
        if desc is None:
            warnings.append(f"Efecto desconocido «{fx.get('key')}»: se omite")
            continue
        eid = engine.add_effect(track_id, desc["key"], -1)["id"]
        params = {p["id"]: p for p in desc["params"]}
        for pid, v in (fx.get("values") or {}).items():
            if pid in params:
                engine.set_effect_param(eid, pid, min(max(float(v), params[pid]["min"]), params[pid]["max"]))
        for pid, pts in (fx.get("automation") or {}).items():
            if pid in params and pts:
                engine.set_effect_automation(eid, pid, sorted((float(t), float(v)) for t, v in pts))
        engine.set_effect_enabled(eid, bool(fx.get("enabled", True)))
    return warnings


def collect(doc: dict, engine, catalog: list[dict], sources: dict[int, str]) -> dict:
    """Completa el documento de la interfaz con lo que guarda el motor. `sources`: id → audio original."""
    out = dict(doc)
    out["format"] = FORMAT
    out["version"] = VERSION
    out["saved"] = datetime.now().isoformat(timespec="seconds")
    tracks = []
    for t in doc.get("tracks", []):
        t = dict(t)
        tid = int(t.get("id", -1))
        if tid >= 0:
            t["fx"] = chain_of(engine, catalog, tid)
            if t.get("type") in AUDIO_TYPES:
                t["path"] = sources.get(tid, "")
        tracks.append(t)
    out["tracks"] = tracks
    out["master_fx"] = chain_of(engine, catalog, MASTER)
    return out


def save(path: str | Path, doc: dict) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".afo":
        path = path.with_suffix(".afo")
    base = path.parent.resolve()
    for t in doc.get("tracks", []):
        if t.get("path"):
            try:
                t["rel"] = os.path.relpath(Path(t["path"]).resolve(), base)
            except ValueError:               # otra unidad en Windows: solo la ruta absoluta
                t.pop("rel", None)
    tmp = path.with_suffix(".afo.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)                    # nunca deja un proyecto a medio escribir
    return path


def load(path: str | Path) -> dict:
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT:
        raise ValueError("No es un proyecto de AllForOne")
    if int(doc.get("version", 0)) > VERSION:
        raise ValueError("El proyecto es de una versión más nueva de AllForOne")
    base = path.parent
    missing = []
    for t in doc.get("tracks", []):
        if t.get("type") not in AUDIO_TYPES or not (t.get("path") or t.get("rel")):
            continue
        cands = [Path(t["path"])] if t.get("path") else []
        if t.get("rel"):
            cands.insert(0, base / t["rel"])       # junto al proyecto primero (carpeta movida)
        found = next((c for c in cands if c.is_file()), None)
        t["path"] = str(found.resolve()) if found else ""
        if not found:
            missing.append(t.get("name", "?"))
    doc["missing"] = missing
    doc["file"] = str(path.resolve())
    return doc
