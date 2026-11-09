"""Mezcla y mastering automáticos EN VIVO: las decisiones del Mezclador V4.2 como efectos reales.

El V4.2 (mixer_v42/, sin cambios) analiza cada stem y decide ganancia, paneo, EQ, compresión,
procesos de voz, espacio y master; luego renderiza WAVs. Aquí se reutilizan sus mismas mediciones
y criterios (analyze, TYPES, _adaptive_chain, perfiles de espacio vocal, MASTERS…) pero el
resultado es un PLAN: por pista, fader, paneo y una cadena de efectos de la Biblioteca nativa con
sus valores; el motor C++ los procesa en tiempo real y la consola los muestra. No se escribe audio.

Lo que el V4.2 hace con audio variable en el tiempo y que una cadena de efectos no reproduce tal
cual (nivelado de frases, ducking del bajo con el bombo, enmascaramiento dinámico, balance por
secciones, EQ dinámica de cuerpo y dureza) se informa en `skipped`, no se finge.

Este módulo corre en el hilo del mezclador (solo numpy/scipy). El master se decide en el hilo
principal con medidas reales del motor: ver `MasterAuto` (bridge.py).
"""
from __future__ import annotations

import math
from pathlib import Path

ROLE_POSITION = {"L": "Izquierda", "R": "Derecha", "B_L": "50% izquierda", "B_R": "50% derecha", "B": "Original / centro"}
POSITION_PAN = {"Izquierda": -1.0, "Derecha": 1.0, "50% izquierda": -0.5, "50% derecha": 0.5}
SPACE_ROLE = {"Voz principal": "principal", "Voz doble": "dobles", "Coros": "coros",
              "Voz de apoyo (_B)": "apoyo", "Voz lateral (_L/_R)": "laterales"}
NOT_LIVE = ("nivelado de frases de la voz", "ducking del bajo con el bombo", "enmascaramiento dinámico de guitarras y teclados",
            "balance por secciones", "EQ dinámica de cuerpo y dureza de la voz", "compresión paralela por bus")


def _fx(key, label, **values):
    return {"key": key, "label": label, "values": {k: float(v) for k, v in values.items()}}


def _db(x):
    return 20 * math.log10(max(float(x), 1e-9))


def _eq_from_plugins(plugins, extra=None):
    """Los filtros de pedalboard que decide _adaptive_chain, como valores del EQ paramétrico."""
    from pedalboard import HighpassFilter, LowShelfFilter, PeakFilter
    v, notes, mids = {}, [], 0
    for p in plugins:
        if isinstance(p, HighpassFilter):
            v["hpf"] = p.cutoff_frequency_hz
            notes.append(f"paso alto {p.cutoff_frequency_hz:.0f} Hz")
        elif isinstance(p, PeakFilter) and mids < 2:
            mids += 1
            v[f"mid{mids}Freq"], v[f"mid{mids}Gain"], v[f"mid{mids}Q"] = p.cutoff_frequency_hz, p.gain_db, p.q
            notes.append(f"{p.gain_db:+.1f} dB a {p.cutoff_frequency_hz:.0f} Hz")
        elif isinstance(p, LowShelfFilter):
            v["lowFreq"], v["lowGain"] = p.cutoff_frequency_hz, p.gain_db
            notes.append(f"graves {p.gain_db:+.1f} dB")
    for k, val in (extra or {}).items():
        v[k] = val
    return v, notes


def _compressor(plugins):
    from pedalboard import Compressor
    for p in plugins:
        if isinstance(p, Compressor):
            return _fx("compressor", "Compresión (V4.2)", threshold=p.threshold_db, ratio=p.ratio, attack=p.attack_ms,
                       release=p.release_ms, knee=0, detector=0, makeup=0, mix=100)
    return None


def _vocal_space(role, amount, bpm):
    """Perfil de espacio vocal del V4.2 (vocal_space.PROFILES) como Space + Delay en la cadena."""
    import vocal_space as vs
    prof = vs.PROFILES[role]
    scale = min(1.65, max(0.0, amount) / 45.0)
    if scale <= 0:
        return []
    out = [_fx("space", f"Espacio vocal ({role})", mode=2, size=prof.room * 100, predelay=prof.pre_ms,
               decay=0.5 + 4.0 * prof.room, diffusion=70, damping=min(20000, prof.lp), lowcut=prof.hp, early=40,
               width=88, mix=min(100, prof.verb * scale * 100))]
    tap = prof.taps[1] if len(prof.taps) > 1 else prof.taps[0]
    synced = bpm and 55 <= bpm <= 230
    sync = {"eighth": 4, "quarter": 2}.get(tap, 0) if synced else 0
    out.append(_fx("delay", f"Eco vocal ({tap})", time=vs._delay_time(tap, bpm if synced else None) * 1000, sync=sync,
                   feedback=12, pingpong=0, hp=max(prof.hp, 410), lp=min(prof.lp, 5600),
                   ducking=min(100, prof.duck_db * 20), mix=min(100, prof.delay * scale * 74)))
    return out


def plan_track(m, stem: dict, opts: dict, lead: dict | None = None) -> dict:
    """Decisiones del V4.2 para un stem, como fader, paneo y cadena de efectos."""
    import numpy as np
    eng = m.eng
    from vocal_dsp import VOCALS, band, envelope, pitch_profile
    from spectral_tools import excerpts, spectrum

    path, name = stem["path"], Path(stem["path"]).name
    x = eng.load_stem(path)
    meter = m.pyln.Meter(eng.SR)
    a = eng.analyze(x, meter)
    if a.silent:
        return {"path": path, "name": name, "skip": "silencioso"}
    role = stem.get("role") or "—"
    kind = stem.get("kind") if stem.get("kind") in eng.TYPES else eng.guess_type(name)
    if role in ("B", "B_L", "B_R"):
        kind = "Voz de apoyo (_B)"
    elif role in ("L", "R") and kind in VOCALS:
        kind = "Voz lateral (_L/_R)"
    position = ROLE_POSITION.get(role) or (eng.backing_position(name) if kind == "Voz de apoyo (_B)" else eng.pan_from_filename(name))
    spec = eng.TYPES[kind]
    level = a.lufs if math.isfinite(a.lufs) else _db(a.rms)
    delta = float(np.clip(spec["lufs"] - level, -7, 7))
    notes = []
    if opts.get("template_mode") and opts["template_mode"] != m.tpl.GUIDE_ONLY:
        item = dict(m.tpl.inventory([name])[0], kind=kind, role=m.tpl.role_for(name, kind))
        item["group"] = m.tpl.GROUPS[item["role"]]
        trim = m.tpl.style_trims(opts["profile"], item, a)
        if trim:
            delta = float(np.clip(delta + trim, -7, 7))
            notes.append(f"guía de estilo {trim:+.2f} dB")
    # Escalón de los acompañamientos respecto de la voz principal (mismo criterio que _blend_backing)
    if kind in ("Voz de apoyo (_B)", "Voz lateral (_L/_R)") and lead is not None:
        offset = 6.0 if kind == "Voz de apoyo (_B)" else float(np.clip(opts.get("step_db", eng.BACKING_STEP_DEFAULT_DB), 5, 10))
        target = lead["lufs_after"] - offset
        after = level + delta
        delta += float(np.clip(target - after, -12, 2))
        notes.append(f"escalón {offset:.1f} dB bajo la voz principal")
    if a.rms < .00015:
        delta = min(delta, 0.0)

    plugins = eng._adaptive_chain(kind, a)
    chain, extra = [], {}
    if kind in VOCALS:
        prof = pitch_profile(x, eng.SR)
        hp = float(np.clip(prof["low"] * .48, 55, 110)) if prof else (75.0 if kind == "Voz principal" else 90.0)
        extra["hpf"] = hp
        notes.append(f"paso alto adaptativo {hp:.0f} Hz" + (f" (F0 {prof['median']:.0f} Hz)" if prof else ""))
        if kind in ("Voz de apoyo (_B)", "Voz lateral (_L/_R)"):
            if a.bands.get("mud", 0) > .19:
                cut = float(np.clip((a.bands["mud"] - .19) * 8.0, 0, 1.5))
                if cut >= .15:
                    extra.update(mid1Freq=330, mid1Gain=-cut, mid1Q=.85)
            if lead is not None and a.bands.get("presence", 0) > .015 and lead["presence"] > .015:
                cut = float(np.clip(.65 + min(a.bands["presence"], lead["presence"]) * 5., .65, 1.8))
                extra.update(mid2Freq=3200, mid2Gain=-cut, mid2Q=.85)
                notes.append(f"hueco de {cut:.1f} dB a 3,2 kHz para la principal")
        # Aire y recorte agudo de enhance_vocal (sonic_tools)
        f, p = spectrum(x, eng.SR)
        total = float(p.sum()) + 1e-12
        air = float(p[(f >= 8000) & (f < 16000)].sum() / total)
        top = float(p[f >= 17500].sum() / total)
        samples = np.concatenate(excerpts(x, eng.SR, seconds=12, windows=4), axis=-1)
        frame = max(1, eng.SR // 10)
        lv = [float(np.sqrt(np.mean(samples[:, i:i + frame] ** 2))) for i in range(0, samples.shape[-1], frame)]
        floor = float(np.percentile(lv, 10) / max(np.percentile(lv, 80), 1e-8)) if lv else 1.0
        if .001 < air < .085 and floor < .65:
            g = float(np.clip((.065 - air) * 22, 0, 1.4 if kind == "Voz principal" else .8))
            if g > .05:
                extra.update(highFreq=10000, highGain=g)
                notes.append(f"aire +{g:.1f} dB a 10 kHz")
        if top > .025:
            extra["lpf"] = 18500
    eqv, eqn = _eq_from_plugins(plugins, extra)
    if eqv:
        chain.append(_fx("eq", "EQ (V4.2)", **eqv))
        notes += eqn
    if kind in VOCALS:
        # De-esser: la banda 4,5–10 kHz que vigila dynamic_cut, con umbral relativo al nivel de la voz
        full = envelope(x, eng.SR)
        loud = full[full > 1e-5]
        ref_db = _db(np.percentile(loud, 80)) if loud.size else -30.0
        sib = envelope(band(x, eng.SR, 4500, 10000), eng.SR)
        strength = float(np.percentile(sib[full > 1e-5] / np.maximum(full[full > 1e-5], 1e-8), 95)) if loud.size else 0.0
        chain.append(_fx("deesser", "De-Esser (V4.2)", freq=6700, q=1.2, threshold=ref_db + _db(.35),
                         range=-4.0, mode=0, listen=0))
        notes.append(f"de-esser 4,5–10 kHz hasta 4 dB (sibilancia relativa {strength:.2f})")
    comp = _compressor(plugins)
    if comp:
        chain.append(comp)
        notes.append(f"compresión {comp['values']['ratio']:.1f}:1 desde {comp['values']['threshold']:.0f} dB")
    if kind in VOCALS:
        wet = .10 if kind == "Voz principal" else .06
        rms_db = _db(a.rms)
        if a.crest_db >= 9:
            chain.append(_fx("compressor", "Compresión paralela (V4.2)", threshold=float(np.clip(rms_db + 3, -36, -10)), ratio=3,
                             attack=18, release=100, knee=0, detector=0, makeup=3, mix=wet * 100))
        chain.append(_fx("saturator", "Saturación (V4.2)", drive=6, character=1, tone=0, bias=0,
                         mix=(8 if kind == "Voz principal" else 4.5), output=0))
        if kind in SPACE_ROLE:
            chain += _vocal_space(SPACE_ROLE[kind], opts.get("space", 45.0), opts.get("bpm", 0.0))
    elif spec["send"] is not None:
        mix = 60 * 10 ** (spec["send"] / 20)
        chain.append(_fx("space", "Reverb de instrumentos (V4.2)", mode=0, size=38, predelay=10, decay=1.2, diffusion=70,
                         damping=8500, lowcut=250, early=40, width=100, mix=mix))
        notes.append(f"reverb {spec['send']} dB")
    return {"path": path, "name": name, "kind": kind, "role": role, "position": position,
            "pan": POSITION_PAN.get(position, 0.0), "gain_db": round(delta, 2), "chain": chain, "notes": notes,
            "lufs": level, "lufs_after": level + delta, "presence": a.bands.get("presence", 0.0),
            "power": 10 ** ((level + delta) / 10), "bands": a.bands, "crest_db": a.crest_db}


def plan(m, stems: list[dict], opts: dict, progress=None) -> dict:
    """Plan de toda la mezcla. La voz principal se decide primero: los acompañamientos se escalonan con ella."""
    from vocal_dsp import VOCALS  # noqa: F401  (comprueba que el V4.2 está cargado)
    order = sorted(range(len(stems)), key=lambda i: 0 if (stems[i].get("role") == "P" or stems[i].get("kind") == "Voz principal") else 1)
    out, lead = [None] * len(stems), None
    for n, i in enumerate(order):
        if progress:
            progress(n, len(stems), stems[i])
        t = plan_track(m, stems[i], opts, lead)
        out[i] = t
        if lead is None and t.get("kind") == "Voz principal":
            lead = t
    tracks = [t for t in out if t and not t.get("skip")]
    # Bandas de la mezcla (para el master): suma de potencias de cada pista tras su ganancia
    total = sum(t["power"] for t in tracks) or 1.0
    bands = {}
    for t in tracks:
        for k, v in t["bands"].items():
            bands[k] = bands.get(k, 0.0) + v * t["power"] / total
    return {"tracks": out, "mix_bands": bands, "skipped": list(NOT_LIVE)}


def master_chain(m, preset: str, bands: dict, crest_db: float, pre_gain_db: float) -> list[dict]:
    """La cadena de master() del V4.2 como efectos: entrada a −18 LUFS, EQ, compresión, color y nivel final."""
    p = m.eng.MASTERS[preset]
    eq = {"hpf": 24}
    if bands.get("mud", 0.0) > .27:
        eq.update(mid1Freq=330, mid1Gain=-1.0, mid1Q=.8)
    if bands.get("air", 1.0) < .01:
        eq.update(highFreq=9500, highGain=.5)
    chain = [_fx("gain", "Entrada del master (−18 LUFS)", input=pre_gain_db, output=0),
             _fx("eq", "EQ del master (V4.2)", **eq)]
    if crest_db > 13:
        chain.append(_fx("compressor", "Compresión del master (V4.2)", threshold=-15, ratio=p["ratio"], attack=35, release=175,
                         knee=0, detector=0, makeup=0, mix=100))
    chain.append(_fx("saturator", "Color del master (V4.2)", drive=4, character=1, tone=0, bias=0, mix=2.5, output=0))
    chain.append(_fx("gain", "Nivel final del master", input=0, output=0))
    return chain


# ----------------------------------------------------------------------------------------
# Aplicación en el motor (hilo principal)
def apply_chain(eng, track_id: int, chain: list[dict], old_ids: list[int], at: int = -1) -> list[int]:
    """Sustituye los efectos automáticos anteriores de la pista por la cadena nueva."""
    for i in old_ids:
        try:
            eng.remove_effect(i)
        except Exception:
            pass                                 # el usuario ya lo quitó
    ids = []
    for n, fx in enumerate(chain):
        eid = eng.add_effect(track_id, fx["key"], -1)["id"]
        if at >= 0:
            eng.move_effect(eid, at + n)
        for k, v in fx["values"].items():
            eng.set_effect_param(eid, k, v)
        ids.append(eid)
    return ids


def _measure(eng):
    r = eng.measure_mix()
    if not r["ok"]:
        raise RuntimeError("La sesión no suena: no hay nada que medir")
    return r


def apply_master(eng, m, preset: str, bands: dict, old_ids: list[int], target_lufs: float | None = None):
    """master() del V4.2 en vivo: mide la mezcla en el motor (en memoria) y ajusta la cadena del master
    hasta el objetivo de LUFS sin pasar del presupuesto de limitación ni del techo.
    Devuelve (ids de los efectos, estadísticas, cadena)."""
    import numpy as np
    p = dict(m.eng.MASTERS[preset])
    if target_lufs is not None:
        p["lufs"] = float(target_lufs)
    apply_chain(eng, 0, [], old_ids)
    eng.set_master_ceiling(p["tp"])
    # 1) Medir la mezcla tal cual sin que el limitador actúe: la cadena entra a −24 dB (el EQ es lineal
    #    y el color apenas suma), y el pico real se lee a la entrada del primer efecto.
    probe = -24.0
    chain = master_chain(m, preset, bands, 0.0, probe)
    ids = apply_chain(eng, 0, chain, [], at=0)
    eng.effect_meters(ids[0])
    ma = _measure(eng)["master"]
    p0 = eng.effect_meters(ids[0])[0]                # pico de la mezcla antes del master
    l0 = ma["lufs_i"] - probe if ma["lufs_i"] > -70 else -100.0
    # 2) Como render_mix + master(): la mezcla no pasa de 0,88 de pico y entra al master a −18 LUFS
    norm = min(0.0, _db(.88) - p0)
    pre = norm + (float(np.clip(-18.0 - (l0 + norm), -9, 9)) if l0 > -70 else 0.0)
    crest = p0 - l0 if l0 > -70 else 0.0
    if crest > 13:                                   # la compresión del master depende de la dinámica
        apply_chain(eng, 0, [], ids)
        chain = master_chain(m, preset, bands, crest, pre)
        ids = apply_chain(eng, 0, chain, [], at=0)
    else:
        eng.set_effect_param(ids[0], "input", float(np.clip(pre, -36, 36)))
        chain[0]["values"]["input"] = pre
    final = ids[-1]
    eng.effect_meters(final)                         # vacía el pico de salida antes de medir
    m1 = _measure(eng)["master"]
    peak_pre = eng.effect_meters(final)[1]           # pico antes del limitador
    budget = p["tp"] - peak_pre + p["max_gr"]
    gain = min(float(np.clip(p["lufs"] - m1["lufs_i"], -18, 18)), budget)
    eng.set_effect_param(final, "output", float(np.clip(gain, -36, 36)))
    chain[-1]["values"]["output"] = gain
    m2 = _measure(eng)["master"]
    if m2["lufs_i"] < p["lufs"] - .5 and gain < budget:   # una corrección: el limitador baja la media
        gain = min(gain + (p["lufs"] - m2["lufs_i"]), budget)
        eng.set_effect_param(final, "output", float(np.clip(gain, -36, 36)))
        chain[-1]["values"]["output"] = gain
        m2 = _measure(eng)["master"]
    stats = {"preset": preset, "target_lufs": p["lufs"], "ceiling_db": p["tp"], "lufs_i": round(m2["lufs_i"], 2),
             "max_peak_db": round(m2["max_peak_db"], 2), "input_lufs": round(l0, 2), "pre_gain_db": round(pre, 2),
             "final_gain_db": round(gain, 2), "limit_budget_db": round(budget, 2), "compressed": crest > 13,
             "note": ("Objetivo aproximado logrado." if abs(m2["lufs_i"] - p["lufs"]) < .5
                      else "Se conserva dinámica y presupuesto de limitación; objetivo LUFS orientativo.")}
    return ids, stats, chain
