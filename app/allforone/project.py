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
LAB_PARTS = ("fxlab", "fxlab_b", "fxlab_end")   # FX Lab (AF-62): inicio, «Rama B» y «Fin» en la cadena


def chain_of(engine, catalog: list[dict], track_id: int, labels: dict | None = None, auto=(),
             uid_of: dict | None = None) -> list[dict]:
    """Cadena de efectos de una pista tal como se guarda (valores por id de parámetro).
    `labels`/`auto`: nombre y marca de los efectos que puso la mezcla automática. `uid_of` (id → uid):
    la pista que escucha la cadena lateral se guarda por su uid (los id cambian al abrir)."""
    labels = labels or {}
    out, index_of, effects = [], {}, list(engine.effects(track_id))
    for e in effects:                         # posición en la cadena guardada (los que no se guardan, fuera)
        if e["key"] == "vst3" or any(d["key"] == e["key"] for d in catalog):
            index_of[e["id"]] = len(index_of)
    for e in effects:
        key_from = (uid_of or {}).get(int(e.get("sidechain") or 0), "")    # G4: la pista que escucha
        if e["key"] == "vst3":               # plugin externo: su id y su estado completo (base64)
            out.append({"key": "vst3", "plugin": e["plugin_id"], "name": e["name"], "enabled": bool(e["enabled"]),
                        "state": engine.effect_state(e["id"])})
            if key_from:
                out[-1]["keyFrom"] = key_from
            continue
        desc = next((d for d in catalog if d["key"] == e["key"]), None)
        if desc is None:
            continue
        ids = [p["id"] for p in desc["params"]]
        auto_pts = {pid: [[round(t, 6), v] for t, v in engine.effect_automation(e["id"], pid)] for pid in e.get("automated", [])}
        item = {"key": e["key"], "enabled": bool(e["enabled"]), "values": dict(zip(ids, e["values"])),
                "automation": {k: v for k, v in auto_pts.items() if v}}
        if labels.get(e["id"]):
            item["label"] = labels[e["id"]]
        if key_from:
            item["keyFrom"] = key_from
        if e["id"] in auto:
            item["auto"] = True
        if e["key"] == "fxlab" and hasattr(engine, "effect_macros"):
            # macros del FX Lab: el efecto destino por su posición en esta misma cadena guardada
            macros = [{"target": index_of[m["effect_id"]], "param": m["param"], "macro": int(m["macro"]),
                       "amount": round(float(m["amount"]), 4)}
                      for m in engine.effect_macros(e["id"]) if m["effect_id"] in index_of]
            if macros:
                item["macros"] = macros
        out.append(item)
    return out


def restore_chain(engine, catalog: list[dict], track_id: int, chain: list[dict], on_added=None,
                  ids_out: list | None = None) -> list[str]:
    """Sustituye la cadena de la pista por la guardada. Devuelve avisos (efectos que ya no existen…).
    `on_added(id, efecto guardado)` se llama por cada efecto recreado; `ids_out` recibe el id nuevo de
    cada efecto guardado (None si no se pudo crear), para la cadena lateral cuando estén todas las pistas."""
    warnings = []
    for e in engine.effects(track_id):
        engine.remove_effect(e["id"])
    ids: list[int | None] = []                # id nuevo de cada efecto guardado (None: no se pudo crear)
    for fx in chain or []:
        ids.append(None)
        if fx.get("key") == "vst3":
            try:
                eid = engine.add_plugin_effect(track_id, fx.get("plugin", ""), -1, fx.get("state", ""))["id"]
            except Exception as exc:          # plugin desinstalado o que no carga: se avisa y se sigue
                warnings.append(f"Plugin «{fx.get('name', '?')}» no disponible: {exc}")
                continue
            ids[-1] = eid
            engine.set_effect_enabled(eid, bool(fx.get("enabled", True)))
            if on_added:
                on_added(eid, {**fx, "label": fx.get("label") or fx.get("name", "")})
            continue
        desc = next((d for d in catalog if d["key"] == fx.get("key")), None)
        if desc is None:
            warnings.append(f"Efecto desconocido «{fx.get('key')}»: se omite")
            continue
        eid = engine.add_effect(track_id, desc["key"], -1)["id"]
        ids[-1] = eid
        params = {p["id"]: p for p in desc["params"]}
        for pid, v in (fx.get("values") or {}).items():
            if pid in params:
                engine.set_effect_param(eid, pid, min(max(float(v), params[pid]["min"]), params[pid]["max"]))
        for pid, pts in (fx.get("automation") or {}).items():
            if pid in params and pts:
                engine.set_effect_automation(eid, pid, sorted((float(t), float(v)) for t, v in pts))
        engine.set_effect_enabled(eid, bool(fx.get("enabled", True)))
        if on_added:
            on_added(eid, fx)
    for fx, eid in zip(chain or [], ids):     # macros del FX Lab, ya con todos los efectos creados
        if eid is None or fx.get("key") != "fxlab":
            continue
        for m in fx.get("macros") or []:
            t = int(m.get("target", -1))
            tgt = ids[t] if 0 <= t < len(ids) else None
            if tgt is None or not engine.set_effect_macro(eid, int(m.get("macro", 1)), tgt, str(m.get("param", "")),
                                                          float(m.get("amount", 0.0))):
                warnings.append(f"FX Lab: una macro apuntaba a un efecto o parámetro que ya no existe; se omite")
    if ids_out is not None:
        ids_out[:] = ids
    return warnings


def collect(doc: dict, engine, catalog: list[dict], sources: dict[int, str], labels: dict | None = None,
            auto: dict | None = None, modes: dict | None = None) -> dict:
    """Completa el documento de la interfaz con lo que guarda el motor. `sources`: id → audio original.
    `labels` (efecto → nombre) y `auto` (pista → efectos) vienen de la mezcla automática."""
    auto = auto or {}
    out = dict(doc)
    out["format"] = FORMAT
    out["version"] = VERSION
    out["saved"] = datetime.now().isoformat(timespec="seconds")
    tracks = []
    uid_of = {int(t.get("id", -1)): t.get("uid", "") for t in doc.get("tracks", [])}
    for t in doc.get("tracks", []):
        t = dict(t)
        tid = int(t.get("id", -1))
        if tid >= 0:
            t["fx"] = chain_of(engine, catalog, tid, labels, auto.get(tid, ()), uid_of)
            try:                             # envíos a buses Aux: el bus se guarda por su uid (los id cambian al abrir)
                sends = [{"to": uid_of.get(int(s["aux"]), ""), "db": round(float(s["db"]), 2), "pre": bool(s["pre"])}
                         for s in engine.sends(tid)]
                if sends:
                    t["sends"] = [s for s in sends if s["to"]]
            except Exception:                # motor sin buses Aux
                pass
            try:                             # curvas del fader y del paneo de la pista
                ta = {p: [[round(x, 4), round(v, 4)] for x, v in engine.track_automation(tid, p)] for p in ("volume", "pan")}
                ta = {p: v for p, v in ta.items() if v}
                if ta:
                    t["trackAuto"] = ta
            except Exception:
                pass
            if modes and modes.get(tid, "read") != "read":
                t["autoMode"] = modes[tid]
            if t.get("type") == "inst" and (t.get("cfg") or {}).get("plugin"):
                try:                         # estado del instrumento VST3 (sonido elegido en su ventana)
                    t["cfg"] = {**t["cfg"], "pluginState": engine.track_instrument_state(tid)}
                except Exception:
                    pass
            if t.get("type") in AUDIO_TYPES:
                t["path"] = sources.get(tid, "")
                try:                         # cortes, posiciones, volumen y fundidos de cada clip
                    t["aclips"] = [{k: c[k] for k in ("start", "length", "offset", "gain_db", "fade_in", "fade_out")}
                                  for c in engine.clips(tid)]
                except Exception:            # motor sin edición de clips
                    pass
        tracks.append(t)
    out["tracks"] = tracks
    out["master_fx"] = chain_of(engine, catalog, MASTER, labels, auto.get(MASTER, ()), uid_of)
    out["master_ceiling"] = round(engine.master_ceiling(), 2)
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
