"""Mezcla y mastering automáticos EN VIVO: las decisiones de la mezcla automática como efectos reales.

La mezcla automática (mixer_v42/, sin cambios) analiza cada stem y decide ganancia, paneo, EQ, compresión,
procesos de voz, espacio y master; luego renderiza WAVs. Aquí se reutilizan sus mismas mediciones
y criterios (analyze, TYPES, _adaptive_chain, perfiles de espacio vocal, MASTERS…) pero el
resultado es un PLAN: por pista, fader, paneo y una cadena de efectos de la Biblioteca nativa con
sus valores; el motor C++ los procesa en tiempo real y la consola los muestra. No se escribe audio.

Lo que cambia con el tiempo se escribe como AUTOMATIZACIÓN de esos efectos (curvas de Tracktion que
el motor sigue al reproducir y que las perillas muestran moviéndose): rides de la voz principal
frase a frase, ecos y reverbs lanzados al final de las frases, ducking de la música mientras canta
la voz y barridos de filtro antes de que entre la voz (`automate`). Lo demás que la mezcla automática hace con
audio variable (ducking del bajo con el bombo, enmascaramiento dinámico, balance por secciones, EQ
dinámica de cuerpo y dureza) se informa en `skipped`, no se finge.

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
NOT_LIVE = ("ducking del bajo con el bombo", "enmascaramiento dinámico de guitarras y teclados",
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
            return _fx("compressor", "Compresión (auto)", threshold=p.threshold_db, ratio=p.ratio, attack=p.attack_ms,
                       release=p.release_ms, knee=0, detector=0, makeup=0, mix=100)
    return None


def _vocal_space(role, amount, bpm):
    """Perfil de espacio vocal de la mezcla automática (vocal_space.PROFILES) como Space + Delay en la cadena."""
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
    """Decisiones de la mezcla automática para un stem, como fader, paneo y cadena de efectos."""
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
        chain.append(_fx("eq", "EQ (auto)", **eqv))
        notes += eqn
    if kind in VOCALS:
        # De-esser: la banda 4,5–10 kHz que vigila dynamic_cut, con umbral relativo al nivel de la voz
        full = envelope(x, eng.SR)
        loud = full[full > 1e-5]
        ref_db = _db(np.percentile(loud, 80)) if loud.size else -30.0
        sib = envelope(band(x, eng.SR, 4500, 10000), eng.SR)
        strength = float(np.percentile(sib[full > 1e-5] / np.maximum(full[full > 1e-5], 1e-8), 95)) if loud.size else 0.0
        chain.append(_fx("deesser", "De-Esser (auto)", freq=6700, q=1.2, threshold=ref_db + _db(.35),
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
            chain.append(_fx("compressor", "Compresión paralela (auto)", threshold=float(np.clip(rms_db + 3, -36, -10)), ratio=3,
                             attack=18, release=100, knee=0, detector=0, makeup=3, mix=wet * 100))
        chain.append(_fx("saturator", "Saturación (auto)", drive=6, character=1, tone=0, bias=0,
                         mix=(8 if kind == "Voz principal" else 4.5), output=0))
        if kind in SPACE_ROLE:
            chain += _vocal_space(SPACE_ROLE[kind], opts.get("space", 45.0), opts.get("bpm", 0.0))
    elif spec["send"] is not None:
        mix = 60 * 10 ** (spec["send"] / 20)
        chain.append(_fx("space", "Reverb de instrumentos (auto)", mode=0, size=38, predelay=10, decay=1.2, diffusion=70,
                         damping=8500, lowcut=250, early=40, width=100, mix=mix))
        notes.append(f"reverb {spec['send']} dB")
    return {"path": path, "name": name, "kind": kind, "role": role, "position": position,
            "pan": POSITION_PAN.get(position, 0.0), "gain_db": round(delta, 2), "chain": chain, "notes": notes,
            "lufs": level, "lufs_after": level + delta, "presence": a.bands.get("presence", 0.0),
            "power": 10 ** ((level + delta) / 10), "bands": a.bands, "crest_db": a.crest_db}


def plan(m, stems: list[dict], opts: dict, progress=None) -> dict:
    """Plan de toda la mezcla. La voz principal se decide primero: los acompañamientos se escalonan con ella."""
    from vocal_dsp import VOCALS  # noqa: F401  (comprueba que la mezcla automática está cargada)
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
    buses = shared_reverbs(tracks) if opts.get("shared_reverb", True) else {}
    auto = automate(m, tracks, opts) if opts.get("automation", True) else {}
    # Bandas de la mezcla (para el master): suma de potencias de cada pista tras su ganancia
    total = sum(t["power"] for t in tracks) or 1.0
    bands = {}
    for t in tracks:
        for k, v in t["bands"].items():
            bands[k] = bands.get(k, 0.0) + v * t["power"] / total
    return {"tracks": out, "mix_bands": bands, "skipped": list(NOT_LIVE), "automation": auto, "buses": buses}


# Reverbs compartidas por envío, como en una consola: una sala para los instrumentos (el «send» en dB
# de la mezcla automática) y una reverb para dobles y coros. La voz principal conserva la suya en la cadena porque
# lleva «reverb lanzada» automatizada al final de frase (el motor aún no automatiza envíos).
BUSES = {"sala": ("Sala instrumentos (IA)", "Reverb de instrumentos"),
         "voces": ("Reverb voces (IA)", "Espacio vocal")}


def shared_reverbs(tracks: list[dict]) -> dict:
    """Saca de cada cadena la reverb que se puede compartir y la cambia por un envío al bus.

    La Space mezcla en lineal (wet × mix), así que un envío de 20·log10(mix) dB a un bus con la misma
    reverb al 100 % deja la misma cantidad de reverb que el efecto en la pista. Devuelve los buses usados:
    {clave: {name, chain}}; en cada pista deja t["sends"] = {clave: dB}.
    """
    buses = {}
    for t in tracks:
        t["sends"] = {}
        if t.get("kind") == "Voz principal":
            continue
        for key, (bus, prefix) in BUSES.items():
            fx = next((f for f in t["chain"] if f["key"] == "space" and f["label"].startswith(prefix)), None)
            if fx is None:
                continue
            t["chain"].remove(fx)
            mix = fx["values"].get("mix", 0.0) / 100.0
            if mix <= 0:
                continue
            t["sends"][key] = round(20 * math.log10(mix), 2)
            if key not in buses:          # la reverb del bus: la primera que aparece, toda húmeda
                buses[key] = {"name": bus, "chain": [{"key": "space", "label": f"{fx['label']} · bus",
                                                      "values": dict(fx["values"], mix=100.0)}]}
            t["notes"].append(f"reverb por envío a «{bus}» ({t['sends'][key]:+.1f} dB)")
    return buses


# ----------------------------------------------------------------------------------------
# Automatización: lo que cambia durante la canción
MUSIC_KINDS = ("Guitarra acustica", "Guitarra lead / solo", "Guitarra ritmica", "Piano", "Pad / Cuerdas",
               "Teclados / Synth", "FX", "Otro")
HOP = 0.05                       # resolución del análisis (s)


def vocal_activity(x, sr: int):
    """Nivel de la voz cada HOP s (RMS de 400 ms, en dB) y tramos en que canta [(inicio, fin), …]."""
    import numpy as np
    from vocal_dsp import envelope
    env = envelope(x, sr, 0.4)[:: max(1, int(sr * HOP))]
    lv = 20 * np.log10(np.maximum(env, 1e-9))
    top = float(np.percentile(lv, 95)) if lv.size else -100.0
    on = lv > max(top - 22.0, -60.0)
    segs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append([start * HOP, i * HOP])
            start = None
    if start is not None:
        segs.append([start * HOP, len(on) * HOP])
    merged = []                                   # huecos de menos de 0,25 s no cortan la frase
    for a, b in segs:
        if merged and a - merged[-1][1] < 0.25:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return lv, [(a, b) for a, b in merged if b - a >= 0.3]


def _thin(pts: list, tol: float) -> list:
    """Quita los puntos que una recta entre sus vecinos ya explica (curvas ligeras de editar)."""
    if len(pts) <= 2:
        return pts
    keep, stack = {0, len(pts) - 1}, [(0, len(pts) - 1)]       # Ramer–Douglas–Peucker en el valor
    while stack:
        i, j = stack.pop()
        (t0, v0), (t2, v2) = pts[i], pts[j]
        worst, at = 0.0, -1
        for k in range(i + 1, j):
            t1, v1 = pts[k]
            err = abs(v1 - (v0 + (v2 - v0) * (t1 - t0) / max(t2 - t0, 1e-9)))
            if err > worst:
                worst, at = err, k
        if worst > tol:
            keep.add(at)
            stack += [(i, at), (at, j)]
    return [pts[k] for k in sorted(keep)]


def ride_curve(lv, segs, depth: float = 4.0) -> list:
    """Ride de la voz: acerca cada frase al nivel típico de la voz (±depth dB), suave como una mano en
    el fader y sin moverse en los silencios (mantiene el último valor)."""
    import numpy as np
    from scipy.ndimage import uniform_filter1d
    active = np.zeros(lv.size, bool)
    for a, b in segs:
        active[int(a / HOP):int(b / HOP)] = True
    if not active.any():
        return []
    sung = lv[active]
    lo, hi = np.percentile(sung, [10, 90])
    target = float(np.mean(np.clip(sung, lo, hi)))          # nivel típico de la voz (media recortada)
    # nivel de cada frase suavizado (1 s, solo con lo cantado) para seguir frases, no sílabas
    w = max(1, int(1.0 / HOP))
    smooth = uniform_filter1d(np.where(active, lv, 0.0), w) / np.maximum(uniform_filter1d(active.astype(float), w), 1e-6)
    want = np.clip((target - smooth) * 0.7, -depth, depth)
    g, last = np.zeros(lv.size), 0.0
    for i in range(lv.size):
        if active[i]:
            last = want[i]
        g[i] = last
    g = uniform_filter1d(g, max(1, int(0.6 / HOP)))
    pts = [(round(i * HOP, 3), round(float(v), 2)) for i, v in enumerate(g) if i % 2 == 0]
    return _thin(pts, 0.35)


def throw_points(segs, base: float, peak: float, min_gap: float, hold: float, every: float, length: float) -> list:
    """Lanzamientos: al acabar una frase seguida de un hueco ≥ min_gap, la mezcla del efecto sube a
    `peak` durante `hold` s y vuelve a `base`. Como mucho uno cada `every` s."""
    pts, last = [(0.0, base)], -1e9
    for i, (a, b) in enumerate(segs):
        nxt = segs[i + 1][0] if i + 1 < len(segs) else length
        if nxt - b < min_gap or b - a < 0.8 or b - last < every:
            continue
        up = max(b - 0.08, pts[-1][0] + 0.01)
        down = b + min(hold, nxt - b - 0.1)
        back = min(down + 0.35, max(nxt - 0.05, down + 0.05))
        pts += [(round(up, 3), base), (round(up + 0.06, 3), peak), (round(down, 3), peak), (round(back, 3), base)]
        last = b
    return pts if len(pts) > 1 else []


def duck_points(segs, depth: float, length: float) -> list:
    """Ducking de la música mientras canta la voz (−depth dB); las frases cercanas se unen para no bombear."""
    groups = []
    for a, b in segs:
        if groups and a - groups[-1][1] < 0.8:
            groups[-1][1] = b
        else:
            groups.append([a, b])
    pts = [(0.0, 0.0)]
    for a, b in groups:
        a0 = max(a - 0.15, pts[-1][0] + 0.01)
        pts += [(round(a0, 3), 0.0), (round(a0 + 0.15, 3), -depth), (round(b, 3), -depth),
                (round(min(b + 0.4, length), 3), 0.0)]
    return pts if len(pts) > 1 else []


def sweep_points(segs, bpm: float, top_hz: float = 650.0) -> list:
    """Barrido de paso alto en la música antes de cada entrada de la voz tras ≥ 6 s sin ella (la intro
    o un puente): sube de 20 Hz a `top_hz` en dos compases y se abre de golpe cuando entra la voz."""
    bar = 240.0 / bpm if bpm and 55 <= bpm <= 230 else 2.0
    dur = min(max(2 * bar, 2.0), 6.0)
    pts, prev_end, n = [(0.0, 20.0)], 0.0, 0
    for a, b in segs:
        if n < 4 and a - prev_end >= 6.0 and a - dur > pts[-1][0] + 0.1:
            t0 = a - dur
            pts.append((round(t0, 3), 20.0))
            for k in range(1, 7):                  # curva exponencial: el oído oye octavas
                pts.append((round(t0 + dur * k / 6 - (0.02 if k == 6 else 0.0), 3),
                            round(20.0 * (top_hz / 20.0) ** (k / 6), 1)))
            pts.append((round(a + 0.01, 3), 20.0))
            n += 1
        prev_end = b
    return pts if n else []


def automate(m, tracks: list[dict], opts: dict) -> dict:
    """Escribe en las cadenas del plan las curvas de automatización a partir de la voz principal.
    Cada efecto automatizado lleva `auto = {parámetro: [(segundos, valor), …]}` en tiempo del audio."""
    lead = next((t for t in tracks if t.get("kind") == "Voz principal"), None)
    if lead is None:
        return {"note": "sin voz principal: no hay rides, lanzamientos ni ducking que escribir"}
    eng = m.eng
    x = eng.load_stem(lead["path"])
    length = x.shape[-1] / eng.SR
    lv, segs = vocal_activity(x, eng.SR)
    if not segs:
        return {"note": "la voz principal no tiene frases claras"}
    bpm = float(opts.get("bpm") or 0.0)
    summary = {"phrases": len(segs)}
    # 1) Ride de la voz, justo después del de-esser (antes de comprimir, como el técnico en el fader)
    ride = ride_curve(lv, segs)
    if len(ride) > 2 and max(abs(v) for _, v in ride) >= 0.5:
        at = next((i + 1 for i, fx in enumerate(lead["chain"]) if fx["key"] == "deesser"), 0)
        fx = _fx("gain", "Ride de voz (automático)", input=0, output=0)
        fx["auto"] = {"input": ride}
        lead["chain"].insert(at, fx)
        span = max(abs(v) for _, v in ride)
        lead["notes"].append(f"ride de voz frase a frase (hasta ±{span:.1f} dB, {len(ride)} puntos)")
        summary["ride_points"] = len(ride)
    # 2) Ecos y reverb lanzados al final de las frases
    beat = 60.0 / bpm if bpm and 55 <= bpm <= 230 else 0.5
    for fx in lead["chain"]:
        base = fx["values"].get("mix", 0.0)
        if fx["key"] == "delay":
            pts = throw_points(segs, base, min(100.0, max(base * 3, base + 28)), 0.6, 2 * beat, 6.0, length)
            if pts:
                fx["auto"] = {"mix": pts}
                n = (len(pts) - 1) // 4
                lead["notes"].append(f"{n} eco(s) lanzado(s) al final de frase")
                summary["delay_throws"] = n
        elif fx["key"] == "space":
            pts = throw_points(segs, base, min(100.0, base + 22), 1.8, 1.2, 8.0, length)
            if pts:
                fx["auto"] = {"mix": pts}
                n = (len(pts) - 1) // 4
                lead["notes"].append(f"{n} reverb(s) lanzada(s) antes de los huecos largos")
                summary["reverb_throws"] = n
    # 3) La música deja sitio a la voz (ducking) y se abre con un barrido antes de cada entrada
    music = [t for t in tracks if t.get("kind") in MUSIC_KINDS and t is not lead]
    sweep = sweep_points(segs, bpm)
    for t in music:
        depth = 2.0 if t["kind"] == "Otro" else 1.5
        duck = duck_points(segs, depth, length)
        if duck:
            fx = _fx("gain", "Ducking bajo la voz (automático)", input=0, output=0)
            fx["auto"] = {"input": duck}
            t["chain"].append(fx)
            t["notes"].append(f"ducking de {depth:.1f} dB mientras canta la voz")
        if sweep:
            fx = _fx("eq", "Barrido de filtro (automático)", hpf=20)
            fx["auto"] = {"hpf": sweep}
            t["chain"].insert(0, fx)
            t["notes"].append("barrido de paso alto antes de la entrada de la voz")
    summary["ducked"] = len(music)
    summary["sweeps"] = sum(1 for _, v in sweep if v >= 600)
    return summary


def master_chain(m, preset: str, bands: dict, crest_db: float, pre_gain_db: float) -> list[dict]:
    """La cadena de master() de la mezcla automática como efectos: entrada a −18 LUFS, EQ, compresión, color, nivel final
    y el limitador (AFO Limiter, con el techo del preset: su reducción se ve en la tarjeta)."""
    p = m.eng.MASTERS[preset]
    eq = {"hpf": 24}
    if bands.get("mud", 0.0) > .27:
        eq.update(mid1Freq=330, mid1Gain=-1.0, mid1Q=.8)
    if bands.get("air", 1.0) < .01:
        eq.update(highFreq=9500, highGain=.5)
    chain = [_fx("gain", "Entrada del master (−18 LUFS)", input=pre_gain_db, output=0),
             _fx("eq", "EQ del master (auto)", **eq)]
    if crest_db > 13:
        chain.append(_fx("compressor", "Compresión del master (auto)", threshold=-15, ratio=p["ratio"], attack=35, release=175,
                         knee=0, detector=0, makeup=0, mix=100))
    chain.append(_fx("saturator", "Color del master (auto)", drive=4, character=1, tone=0, bias=0, mix=2.5, output=0))
    chain.append(_fx("gain", "Nivel final del master", input=0, output=0))
    chain.append(_fx("limiter", "Limitador del master", input=0, ceiling=float(p["tp"]), release=120))
    return chain


# ----------------------------------------------------------------------------------------
# Aplicación en el motor (hilo principal)
def apply_chain(eng, track_id: int, chain: list[dict], old_ids: list[int], at: int = -1, start: float = 0.0) -> list[int]:
    """Sustituye los efectos automáticos anteriores de la pista por la cadena nueva. Las curvas de
    automatización (`auto`, en tiempo del audio) se colocan desde `start`, donde empieza la pista."""
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
        for k, pts in (fx.get("auto") or {}).items():
            eng.set_effect_automation(eid, k, [(float(t) + start, float(v)) for t, v in pts])
        ids.append(eid)
    return ids


def _measure(eng):
    r = eng.measure_mix()
    if not r["ok"]:
        raise RuntimeError("La sesión no suena: no hay nada que medir")
    return r


def apply_master(eng, m, preset: str, bands: dict, old_ids: list[int], target_lufs: float | None = None):
    """master() de la mezcla automática en vivo: mide la mezcla en el motor (en memoria) y ajusta la cadena del master
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
    final = ids[-2]                                  # «Nivel final», justo antes del limitador
    eng.effect_meters(final)                         # vacía el pico de salida antes de medir
    m1 = _measure(eng)["master"]
    peak_pre = eng.effect_meters(final)[1]           # pico antes del limitador
    budget = p["tp"] - peak_pre + p["max_gr"]
    gain = min(float(np.clip(p["lufs"] - m1["lufs_i"], -18, 18)), budget)
    eng.set_effect_param(final, "output", float(np.clip(gain, -36, 36)))
    chain[-2]["values"]["output"] = gain
    m2 = _measure(eng)["master"]
    if m2["lufs_i"] < p["lufs"] - .5 and gain < budget:   # una corrección: el limitador baja la media
        gain = min(gain + (p["lufs"] - m2["lufs_i"]), budget)
        eng.set_effect_param(final, "output", float(np.clip(gain, -36, 36)))
        chain[-2]["values"]["output"] = gain
        m2 = _measure(eng)["master"]
    stats = {"preset": preset, "target_lufs": p["lufs"], "ceiling_db": p["tp"], "lufs_i": round(m2["lufs_i"], 2),
             "max_peak_db": round(m2["max_peak_db"], 2), "input_lufs": round(l0, 2), "pre_gain_db": round(pre, 2),
             "final_gain_db": round(gain, 2), "limit_budget_db": round(budget, 2), "compressed": crest > 13,
             "note": ("Objetivo aproximado logrado." if abs(m2["lufs_i"] - p["lufs"]) < .5
                      else "Se conserva dinámica y presupuesto de limitación; objetivo LUFS orientativo.")}
    return ids, stats, chain
