"""Adaptador del Mezclador Automático V4.2 para los paneles de AllForOne.

Los algoritmos (mixer_engine, scale_tuner, vocal_dsp, vocal_space, mastering_tools,
mix_templates, music_analysis…) se usan SIN modificar desde allforone/mixer_v42.
Este módulo solo sustituye la interfaz Gradio original (app.py): reproduce su
orquestación de `process()` / `preview_hybrid()` / `confirm_hybrid()` y la expone a
los paneles Mezcla IA, Afinador, Master IA y Antes/Después.

Reglas:
  * El trabajo pesado corre en un hilo aparte: nunca en el hilo de la interfaz ni en el de audio.
  * Los originales del usuario no se modifican. Si el usuario corrige el tipo o el rol de un
    stem, se usa una COPIA con un nombre que el mezclador entiende (él clasifica por nombre).
  * Cada mezcla se guarda en su propia carpeta (historial; REMEZCLAR no borra la anterior).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import sys
import threading
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.mixer")

MIXER_DIR = Path(__file__).resolve().parent / "mixer_v42"
VERSION = "4.2"
PLATFORM = "Plataformas (-14 LUFS, -2 dBTP)"
REF_LABEL = "Según referencia"
ROLE_SUFFIX = {"—": "", "P": "", "B": "_B", "L": "_L", "R": "_R", "B_L": "_B_L", "B_R": "_B_R"}
AUDIO_EXT = {".wav", ".aif", ".aiff", ".flac", ".ogg", ".mp3"}

_loaded = None
_load_error = None


def load():
    """Importa los módulos del mezclador (una vez). Devuelve un namespace o lanza el error."""
    global _loaded, _load_error
    if _loaded is not None:
        return _loaded
    data = paths.user_data_dir() / "mezclador"
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MEZCLADOR_DATA_DIR", str(data))
    if str(MIXER_DIR) not in sys.path:
        sys.path.insert(0, str(MIXER_DIR))
    try:
        import numpy as np
        import pyloudnorm as pyln
        import mixer_engine as eng
        import mix_templates as tpl
        import scale_tuner
        import track_tools
        import music_confirmation
        _loaded = type("Mixer", (), dict(np=np, pyln=pyln, eng=eng, tpl=tpl, tuner=scale_tuner,
                                         tracks=track_tools, confirm=music_confirmation))
        return _loaded
    except Exception as exc:  # dependencias que falten se informan, no se simulan
        _load_error = f"{type(exc).__name__}: {exc}"
        log.exception("No se pudo cargar el Mezclador V4.2")
        raise


def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(name).stem)[:55].strip("_") or "pista"


#: Posiciones que usa `mixer_engine.stereo()` traducidas al paneo -1..+1 de la consola.
PAN_VALUE = {"Original / centro": 0.0, "Izquierda": -1.0, "Derecha": 1.0,
             "50% izquierda": -0.5, "50% derecha": 0.5}


def _rms_db(np, x) -> float:
    """Nivel RMS en dBFS de un bloque de audio (−100 si es silencio)."""
    if x is None or not getattr(x, "size", 0):
        return -100.0
    v = float(np.sqrt(np.mean(np.square(np.asarray(x, dtype="float64")))))
    return 20.0 * math.log10(v) if v > 1e-9 else -100.0


def _peak_db(np, x) -> float:
    if x is None or not getattr(x, "size", 0):
        return -100.0
    v = float(np.max(np.abs(x)))
    return 20.0 * math.log10(v) if v > 1e-9 else -100.0


# ----------------------------------------------------------------------------------------
# Clasificación (lo mismo que hace el mezclador con el nombre) y correcciones del usuario
# ----------------------------------------------------------------------------------------
def predicted_role(m, filename: str, kind: str) -> str:
    eng = m.eng
    if eng.is_backing_voice(filename):
        pos = eng.backing_position(filename)
        return "B_L" if "Izq" in pos else "B_R" if "Der" in pos else "B"
    pan = eng.pan_from_filename(filename)
    if kind in eng.VOCALS or kind == "Voz lateral (_L/_R)":
        return "L" if pan == "Izquierda" else "R" if pan == "Derecha" else "P"
    return "—"


def describe(m, path: str) -> dict:
    eng = m.eng
    p = Path(path)
    kind = eng.guess_type(p.name)
    if eng.is_lateral_voice(p.name, kind) and kind != "Voz de apoyo (_B)":
        kind = "Voz lateral (_L/_R)"
    return {"path": str(p), "name": p.stem, "kind": kind, "role": predicted_role(m, p.name, kind),
            "auto_kind": kind, "auto_role": predicted_role(m, p.name, kind)}


def _kind_token(m, kind: str) -> str:
    kw = m.eng.TYPES.get(kind, {}).get("kw") or []
    return re.sub(r"\s+", "_", kw[0]) if kw else ""


def staged_filename(m, stem: dict, index: int) -> str | None:
    """Nombre que hace que el mezclador clasifique el stem como pidió el usuario.

    Devuelve None si el nombre original ya produce ese resultado (se usa el original).
    """
    eng = m.eng
    kind, role = stem.get("kind") or stem.get("auto_kind"), stem.get("role") or "—"
    original = Path(stem["path"])
    if kind == stem.get("auto_kind") and role == stem.get("auto_role"):
        return None
    base_kind = "Voz principal" if kind in ("Voz lateral (_L/_R)", "Voz de apoyo (_B)") else kind
    if kind == "Voz lateral (_L/_R)" and role not in ("L", "R"):
        role = "L"
    if kind == "Voz de apoyo (_B)" and role not in ("B", "B_L", "B_R"):
        role = "B"
    token = _kind_token(m, base_kind)
    suffix = ROLE_SUFFIX.get(role, "")
    clean = re.sub(r"(_B(_[LR])?|_[LR])$", "", safe_name(original.name), flags=re.I)
    candidates = [f"{token}_{clean}{suffix}", f"{index:02d}_{token}{suffix}", f"{index:02d}_otro{suffix}"]
    for cand in candidates:
        name = cand + original.suffix.lower()
        got = describe(m, name)
        if got["kind"] == kind and got["role"] == role:
            return name
    return candidates[1] + original.suffix.lower()


# ----------------------------------------------------------------------------------------
class MixerService:
    """Una instancia por aplicación. `emit(dict)` envía eventos al panel (hilo cualquiera)."""

    def __init__(self, emit):
        self.emit = emit
        self.runs: list[dict] = []
        self.analysis: dict | None = None
        self.analysis_signature: str | None = None
        self.approval: dict | None = None
        self.busy = False
        self._lock = threading.Lock()

    # --- información para los paneles -----------------------------------------------
    def info(self) -> dict:
        try:
            m = load()
        except Exception:
            return {"ok": False, "error": f"Mezclador V4.2 no disponible: {_load_error}"}
        return {"ok": True, "version": VERSION,
                "profiles": [[k, v["name"], v.get("tag", "")] for k, v in m.tpl.PROFILES.items()],
                "modes": list(m.tpl.GUIDE_MODES), "keys": list(m.tuner.KEYS), "scales": list(m.tuner.SCALES),
                "masters": list(m.eng.MASTERS), "types": list(m.eng.TYPES), "max_tracks": m.eng.MAX_TRACKS,
                "step_default": m.eng.BACKING_STEP_DEFAULT_DB}

    def describe_paths(self, files: list[str]) -> list[dict]:
        m = load()
        return [describe(m, f) for f in files if Path(f).suffix.lower() in AUDIO_EXT and Path(f).is_file()]

    # --- análisis musical (Afinador) -------------------------------------------------
    def _music_paths(self, payload):
        return [s["path"] for s in payload.get("stems", [])]

    def analyze_async(self, payload: dict) -> dict:
        if not payload.get("stems"):
            return {"ok": False, "error": "Carga stems instrumentales en Mezcla IA antes de analizar."}
        return self._start("analysis", self._analyze, payload)

    def _analyze(self, payload):
        m = load()
        from music_analysis import analyze_music
        paths_ = self._music_paths(payload)
        flags = {"essentia": False, "beat_this": True}
        self.emit({"type": "progress", "panel": "afina", "p": 20, "desc": "Analizando instrumentos (las voces no participan)…"})
        result = analyze_music(paths_, use_essentia=False, use_beat_this=True)
        data = result.as_dict()
        data["source_signature"] = m.confirm.signature(paths_, None, flags)
        self.analysis = data
        self.approval = None
        self.emit({"type": "analysis", "summary": result.summary(), "key": data.get("key"), "scale": data.get("scale"),
                   "bpm": data.get("bpm"), "key_confidence": data.get("key_confidence"), "bpm_confidence": data.get("bpm_confidence")})

    def confirm(self, payload: dict) -> dict:
        """Igual que confirm_hybrid() del original: autoriza una combinación concreta."""
        m = load()
        t = payload.get("tune", {})
        mode = t.get("mode", "Automático")
        paths_ = self._music_paths(payload)
        try:
            if mode != "Manual":
                expected = m.confirm.signature(paths_, None, {"essentia": False, "beat_this": True})
                if not self.analysis or self.analysis.get("source_signature") != expected:
                    raise ValueError("Primero pulsa «Analizar música» con estos stems.")
            choice = m.confirm.resolve_choice(self.analysis or {}, mode, t.get("key", "F"), t.get("scale", "Menor natural"),
                                              float(t.get("bpm", 91)), bool(t.get("prefer", True)))
            choice["signature"] = m.confirm.signature(paths_, None, {"mode": mode, "key": t.get("key"), "scale": t.get("scale"),
                                                                     "bpm": float(t.get("bpm", 91))})
            choice["confirmed"] = True
            self.approval = choice
            msg = (f'CONFIRMADO: {choice["key"]} {choice["scale"]}, {choice["bpm"]:.1f} BPM. '
                   f'{choice["source"]}. Afinación permitida por canales separados.')
            return {"ok": True, "confirmed": {"key": choice["key"], "scale": choice["scale"], "bpm": choice["bpm"]}, "status": msg}
        except (ValueError, OSError) as exc:
            self.approval = None
            return {"ok": False, "error": f"Sin confirmar: {exc}"}

    # --- mezcla --------------------------------------------------------------------------
    def mix_async(self, payload: dict) -> dict:
        stems = payload.get("stems", [])
        if not stems:
            return {"ok": False, "error": "Arrastra o añade stems en Mezcla IA."}
        strength = float(payload.get("tune", {}).get("strength", 0))
        if strength > 0 and not self.approval:
            return {"ok": False, "error": "Para afinar, confirma la tonalidad y el BPM en el panel Afinador (o deja la intensidad en 0 %)."}
        return self._start("mix", self._mix, payload)

    def _start(self, kind, fn, payload):
        with self._lock:
            if self.busy:
                return {"ok": False, "error": "El mezclador ya está trabajando; espera a que termine."}
            self.busy = True

        def run():
            try:
                fn(payload)
            except MemoryError:
                self.emit({"type": "error", "panel": kind, "error": "Falta memoria: prueba menos stems o una sección más corta."})
            except Exception as exc:
                log.exception("Fallo en %s", kind)
                self.emit({"type": "error", "panel": kind, "error": f"{exc}", "trace": traceback.format_exc()[-1500:]})
            finally:
                self.busy = False
                self.emit({"type": "idle"})

        threading.Thread(target=run, name=f"afo-mixer-{kind}", daemon=True).start()
        return {"ok": True, "started": kind}

    def make_zip(self, run: dict, progress=None) -> str:
        """Arma el ZIP de la sesión (bajo demanda; ver _mix). Devuelve su ruta."""
        dest = Path(run["folder"])
        archive = Path(run["zip"])
        if archive.is_file() and archive.stat().st_size > 1000:
            return str(archive)
        files = [f for f in dest.rglob("*") if f.is_file() and f != archive]
        tmp = archive.with_suffix(".parcial")
        try:
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as z:
                for i, f in enumerate(files, 1):
                    if progress and i % 5 == 0:
                        progress(i, len(files))
                    z.write(f, f.relative_to(dest).as_posix())
            tmp.replace(archive)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return str(archive)

    def _stage(self, m, stems, dest):
        """Rutas a mezclar: el original, o una copia renombrada si el usuario corrigió tipo/rol."""
        staged, notes = [], []
        for i, s in enumerate(stems, 1):
            name = staged_filename(m, s, i)
            if name is None:
                staged.append(s["path"])
                continue
            target = dest / "entrada_reclasificada" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s["path"], target)
            staged.append(str(target))
            notes.append(f"{Path(s['path']).name} → {name} ({s.get('kind')}, rol {s.get('role')})")
        return staged, notes

    def _mix(self, payload):
        m = load()
        eng, np, pyln, tpl = m.eng, m.np, m.pyln, m.tpl
        t0 = time.monotonic()
        stems = payload["stems"][: eng.MAX_TRACKS]
        profile = payload.get("profile") or tpl.DEFAULT_TEMPLATE
        mode = payload.get("mode") or tpl.GUIDE_ONLY
        step_db = float(payload.get("step_db", eng.BACKING_STEP_DEFAULT_DB))
        space = float(payload.get("space", 45.0))
        tune = payload.get("tune", {})
        strength = float(tune.get("strength", 0))
        reference = (payload.get("reference") or {}).get("path")
        label = payload.get("label") or tpl.PROFILES[profile]["name"]

        out_root = paths.user_data_dir() / "mezclas"
        dest = out_root / f"{safe_name(stems[0]['path'])}_{datetime.now():%Y%m%d_%H%M%S}"
        dest.mkdir(parents=True, exist_ok=True)
        from runtime_setup import check_space
        check_space([s["path"] for s in stems], dest)
        staged, restage_notes = self._stage(m, stems, dest)

        def progress(frac, desc=""):
            try:
                i, n = frac
                p = 5 + 70 * (i / max(1, n))
            except Exception:
                i, p = None, 50
            self.emit({"type": "progress", "panel": "mezcla", "p": round(p, 1), "desc": desc})
            if i is not None:
                # La consola marca qué tira está procesando el mezclador en este momento.
                self.emit({"type": "strip", "i": int(i), "phase": "work", "desc": desc})

        music_plan = None
        vocal_bpm = 0.0
        if self.approval:
            music_plan = dict(self.approval)
            music_plan.setdefault("analysis", self.analysis or {})
            vocal_bpm = float(music_plan["bpm"])
        tuning = dict(key=(music_plan or {}).get("key", tune.get("key", "F")), scale=(music_plan or {}).get("scale", tune.get("scale", "Menor natural")),
                      strength=strength, auto_key=False,
                      tune_lead=bool(tune.get("voices", {}).get("lead", True)), tune_left=bool(tune.get("voices", {}).get("l", False)),
                      tune_right=bool(tune.get("voices", {}).get("r", False)), tune_center_backings=bool(tune.get("voices", {}).get("b", False))
                      ) if strength > 0 else False

        self.emit({"type": "progress", "panel": "mezcla", "p": 3, "desc": f"Preparando {len(staged)} stems…"})
        mix, report, details = eng.render_mix([{"path": p} for p in staged], reference_path=reference, return_details=True,
                                              progress=progress, tuning=tuning, backing_step_db=step_db,
                                              vocal_space_amount=space, vocal_space_bpm=vocal_bpm, auto_music_bpm=False,
                                              music_source_path=None, music_plan=music_plan, mix_template=profile, template_mode=mode)
        if restage_notes:
            report = "RECLASIFICACIÓN MANUAL EN ALLFORONE (copias, originales intactos):\n" + "\n".join(restage_notes) + "\n\n" + report
        if not music_plan:
            report += "\nTonalidad/BPM sin confirmar: delays vocales sin sincronizar y sin afinación."

        files = {"mix": eng.save_wav(dest / "mezcla_sin_master.wav", mix)}
        masters = {}
        platform_audio = None
        for k, preset in enumerate(eng.MASTERS):
            self.emit({"type": "progress", "panel": "mastia", "p": 75 + 4 * k, "desc": f"Masterizando: {preset}"})
            audio, stats = eng.master(mix, preset)
            fn = "master_plataformas.wav" if preset == PLATFORM else "master_" + re.sub(r"[^a-zA-Z0-9]+", "_", preset).strip("_") + ".wav"
            path = eng.save_wav(dest / fn, audio)
            masters[preset] = dict(stats, file=path)
            if preset == PLATFORM:
                platform_audio = audio
            report += (f"\n{preset}: {stats['lufs']:.1f} LUFS; {stats['true_peak']:.2f} dBTP estimado; "
                       f"limitador max. {stats.get('max_reduction_db', 0):.1f} dB, P95 {stats.get('p95_reduction_db', 0):.1f} dB; "
                       f"crest {stats.get('crest_db', 0):.1f} dB; variacion RMS entre ventanas 3 s {stats.get('window_range_db', 0):.1f} dB; {stats['note']}")
        if details["reference_lufs"] is not None:
            target = float(np.clip(details["reference_lufs"], -16., -9.))
            audio, stats = eng.master(mix, "Comercial (-11 LUFS)", target_lufs=target)
            masters[REF_LABEL] = dict(stats, file=eng.save_wav(dest / "master_segun_referencia.wav", audio))
            report += f"\nMaster de referencia: objetivo {target:.1f}; resultado {stats['lufs']:.1f} LUFS y {stats['true_peak']:.2f} dBTP estimado."

        meter = pyln.Meter(eng.SR)
        review, manifest_tracks = [], []
        n = len(details["tracks"])
        for i, item in enumerate(details["tracks"], 1):
            self.emit({"type": "progress", "panel": "antes", "p": 92 + 6 * i / max(1, n), "desc": f"Preparando A/B: {item['name']}"})
            stem = f"{i:02d}_{safe_name(item['name'])}"
            processed = eng.save_wav(dest / "pistas_procesadas_pre_bus" / f"{stem}.wav", item["audio"], subtype="FLOAT")
            original = eng.stereo(eng.load_stem(item["path"]), "Original / centro")
            a, b, note = m.tracks.level_match_pair(original, item["audio"], meter)
            a_path = eng.save_wav(dest / "comparacion" / f"{stem}_A_original.wav", a)
            b_path = eng.save_wav(dest / "comparacion" / f"{stem}_B_procesada.wav", b)
            review.append(dict(label=f"{i:02d} · {item['name']}", a=a_path, b=b_path, processed=processed,
                               note=f"{item['kind']} · {item['position']}\n{item['note']}\n{note}. Pista seca antes de buses y efectos compartidos."))
            manifest_tracks.append(dict(name=item["name"], kind=item["kind"], position=item["position"],
                                        file=f"pistas_procesadas_pre_bus/{stem}.wav", decisions=item["note"]))
            # Lo que la consola muestra en su tira: medido sobre el audio real, no estimado.
            before, after = _rms_db(np, original), _rms_db(np, item["audio"])
            self.emit({"type": "strip", "i": i - 1, "phase": "done", "name": item["name"],
                       "kind": item["kind"], "position": item["position"],
                       "pan": PAN_VALUE.get(item["position"], 0.0),
                       "gain_db": round(after - before, 2) if before > -100 else 0.0,
                       "rms_db": round(after, 2), "peak_db": round(_peak_db(np, item["audio"]), 2),
                       "note": item["note"]})
        for i, (name, audio) in enumerate(details["buses"].items(), 1):
            eng.save_wav(dest / "buses_finales" / f"{i:02d}_{safe_name(name)}.wav", audio, subtype="FLOAT")
        for i, (lab, audio) in enumerate(details["derived"].items(), 1):
            eng.save_wav(dest / "drums_separados_aproximados" / f"{i:02d}_{safe_name(lab)}.wav", audio, subtype="FLOAT")
        if reference and details["reference_lufs"] is not None and platform_audio is not None:
            ref_audio = eng.stereo(eng.load_stem(reference), "Original / centro")
            a, b, note = m.tracks.level_match_pair(ref_audio, platform_audio, meter)
            review.append(dict(label="Referencia / master plataformas", a=eng.save_wav(dest / "comparacion" / "referencia_A.wav", a),
                               b=eng.save_wav(dest / "comparacion" / "master_plataformas_B.wav", b),
                               note=note + ". A = referencia; B = tu master. No se alinean arreglos ni tempos."))
        guide_md, guide_json = tpl.export_guide(dest, profile, details["tracks"])
        report += f"\n\nPLANTILLA DE GUÍA: {tpl.PROFILES[profile]['name']} ({mode}). Revisa guia_mezcla_por_stems.md."
        report += "\n\nMaster plataformas: -14 LUFS orientativos; techo -2 dBTP estimado; hasta 3 dB de limitacion. No garantiza una sonoridad identica en todos los servicios."
        report += "\nPistas individuales: secas antes de buses, FLOAT 32 bits. Buses finales: suman la mezcla sin master. Masters: PCM 24 bits / 44.1 kHz."
        report += "\nComparaciones A/B: copias al mismo volumen para escuchar; no son los stems de produccion."
        report += f"\nCarpeta: {dest.resolve()}"
        (dest / "informe.txt").write_text(report, encoding="utf-8")

        def clean(v):
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items()}
            if isinstance(v, list):
                return [clean(x) for x in v]
            if isinstance(v, float) and not np.isfinite(v):
                return None
            return v
        manifest = dict(version=VERSION, app="AllForOne", samplerate=eng.SR, tracks=manifest_tracks,
                        masters={k: {kk: vv for kk, vv in s.items() if kk != "file"} for k, s in masters.items()},
                        dynamics=details["dynamics"], mix_template=dict(key=profile, name=tpl.PROFILES[profile]["name"], mode=mode),
                        music_analysis=details.get("music_analysis"),
                        music_selection=({k: music_plan.get(k) for k in ("key", "scale", "bpm", "mode", "source", "confirmed")} if music_plan else None),
                        tuning=(tuning or None), step_db=step_db, vocal_space=space,
                        stems=[{k: s.get(k) for k in ("path", "kind", "role")} for s in stems])
        (dest / "sesion.json").write_text(json.dumps(clean(manifest), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        # El ZIP se arma solo cuando lo pides (Master IA → «Exportar sesión ZIP»): para una
        # canción de 3-4 minutos duplicaría la carpeta (2,5 GB) y añadiría ~40 s a cada mezcla.
        archive = dest / "sesion_completa.zip"

        run = dict(id=len(self.runs), label=f"{label} · {datetime.now():%H:%M}", folder=str(dest), zip=str(archive), report=report,
                   mix=files["mix"], masters={k: {kk: (float(vv) if isinstance(vv, (int, float)) else vv) for kk, vv in s.items()} for k, s in masters.items()},
                   review=review, seconds=round(time.monotonic() - t0, 1), stems=len(staged),
                   tuned=bool(tuning), confirmed=(music_plan or {}).get("key") and f"{music_plan['key']} {music_plan['scale']} {music_plan['bpm']:.1f} BPM")
        self.runs.append(run)
        log.info("Mezcla terminada en %.1fs: %s", run["seconds"], dest)
        self.emit({"type": "done", "run": run})
