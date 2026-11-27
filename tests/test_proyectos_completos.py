"""Proyectos COMPLETOS de varios géneros y voces, de punta a punta como los usaría un productor:

stems de una canción entera (batería, bajo, armonía, voz principal, dobles, laterales o coros) →
análisis de tonalidad y tempo (Python / IA, solo con los instrumentos) → confirmación → Mezcla IA en
vivo que afina en vivo con el AF-60 y la tonalidad analizada → master IA
→ render → guardar y volver a abrir el proyecto. Cada paso se mide; nada se da por bueno sin medir.
"""
import json
import time

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import mixer_service, project
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
PLATAFORMAS = "Plataformas (-14 LUFS, -2 dBTP)"
RANGE = {"trap": 2, "balada": 0, "rock": 1, "regueton": 1}      # Voz: grave / aguda / media
STRENGTH = {"trap": 100, "balada": 80, "rock": 85, "regueton": 95}   # afinación según el género (trap = efecto)
BACKING = ("Voz doble", "Coros", "Voz lateral (_L/_R)", "Voz de apoyo (_B)")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication
    return QCoreApplication.instance() or QCoreApplication([])


def _relative(key: str, minor: bool) -> str:
    i = F.NOTES.index(key)
    return F.NOTES[(i + 3) % 12] if minor else F.NOTES[(i - 3) % 12]


def _wait(qapp, h, events, kinds, limit=240):
    t0 = time.monotonic()
    while not any(e["type"] in kinds for e in events) and time.monotonic() - t0 < limit:
        qapp.processEvents()
        h.pump()
        time.sleep(0.005)
    return next((e for e in events if e["type"] in kinds), None)


@pytest.mark.parametrize("genre", list(F.GENRES))
def test_proyecto_completo(genre, qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    song = F.write_song(genre, tmp_path / "stems")
    g = song["genre"]
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.mixerEvent.connect(lambda s: events.append(json.loads(s)))
    try:
        m = mixer_service.load()
        stems = []
        for p in song["paths"]:
            d = mixer_service.describe(m, p)
            d["trackId"] = h.add_audio(p)["id"]
            stems.append(d)
        kinds = {s["name"].split("_", 1)[1]: s["kind"] for s in stems}
        lead = next(s for s in stems if s["kind"] == "Voz principal")
        backs = [s for s in stems if s["kind"] in BACKING]
        assert lead["name"].endswith("Voz_Lead") and len(backs) == len(g.voices) - 1, kinds

        # 1. Análisis musical (solo instrumentos): tonalidad y tempo de la canción
        b.mixsvc._analyze({"stems": stems})
        a = b.mixsvc.analysis
        bpm = float(a.get("bpm") or 0)
        assert any(abs(bpm * k - g.bpm) / g.bpm < 0.04 for k in (0.5, 1, 2)), (genre, a.get("bpm"), g.bpm)
        assert a.get("key") in (g.key, _relative(g.key, g.minor)), (genre, a.get("key"), a.get("scale"), g.key, g.scale)

        # 2. Confirmar (automático) y 3. Mezcla IA en vivo con la voz principal afinada sin conexión
        c = b.mixsvc.confirm({"stems": stems, "tune": {"mode": "Automático"}})
        if not c["ok"]:                # el automático solo confirma con acuerdo alto; si no, el productor
            assert a.get("key_confidence", 0) < 0.60 or a.get("bpm_confidence", 0) < 0.55, (c, a)   # confirma a mano
            c = b.mixsvc.confirm({"stems": stems, "tune": {"mode": "Manual", "key": a["key"], "scale": a["scale"], "bpm": a["bpm"]}})
        assert c["ok"], c
        r = json.loads(b.mixer("mix", json.dumps({"stems": stems, "space": 45,
                                                  "tune": {"strength": STRENGTH[genre], "voices": {"lead": True}, "method": "live"}})))
        assert r["ok"], r
        done = _wait(qapp, h, events, ("done", "error"))
        assert done and done["type"] == "done" and done["applied"] == len(stems), done
        eng = h.engine
        chains = {s["name"]: [e["key"] for e in eng.effects(s["trackId"])] for s in stems}
        assert all(chains.values()), chains
        assert {"eq", "deesser"} <= set(chains[lead["name"]]), chains[lead["name"]]

        # Mezcla coherente: la voz principal manda sobre dobles, coros y laterales
        lv = eng.measure_mix()["tracks"]
        for s in backs:
            assert lv[lead["trackId"]]["lufs_i"] > lv[s["trackId"]]["lufs_i"] + 2.0, (s["name"], lv[lead["trackId"]], lv[s["trackId"]])

        # Reverbs compartidas como en una consola: dobles y coros por envío a un bus «Reverb voces»,
        # los instrumentos con reverb a «Sala instrumentos»; la voz principal conserva la suya
        aux = {v["name"]: k for k, v in h.tracks.items() if v.get("name") in ("Reverb voces (IA)", "Sala instrumentos (IA)")}
        assert "Reverb voces (IA)" in aux, (genre, aux)
        for name, a in aux.items():
            assert [e["key"] for e in eng.effects(a)] == ["space"], (name, eng.effects(a))
        vb = aux["Reverb voces (IA)"]
        for s in backs:
            sends = {x["aux"]: x["db"] for x in eng.sends(s["trackId"])}
            assert -40 < sends.get(vb, -100) < 0, (s["name"], sends)
            assert "space" not in chains[s["name"]], (s["name"], chains[s["name"]])
        assert "space" in chains[lead["name"]] and not [x for x in eng.sends(lead["trackId"]) if x["db"] > -99]
        print(genre, "buses:", sorted(aux), {s["name"]: [round(x["db"], 1) for x in eng.sends(s["trackId"]) if x["db"] > -99] for s in stems})

        # 4. La Mezcla IA afina EN VIVO: AF-60 el primero de la cadena de la voz, con la tonalidad
        #    confirmada y el rango medido de esa voz (grave / media / aguda), sin tocar el audio
        conf = c["confirmed"]
        assert h.tracks[lead["trackId"]]["source_path"] == lead["path"], "la afinación no sustituye el audio"
        ch = json.loads(b.fxList(lead["trackId"]))["chain"]
        assert ch[0]["key"] == "tune" and ch[0]["auto"], [e["key"] for e in ch]
        tid = ch[0]["id"]
        scale = {"Mayor": 1, "Menor natural": 2}.get(conf["scale"], 0)
        vals = ch[0]["values"]
        assert (round(vals[0]), round(vals[1]), round(vals[5])) == (F.NOTES.index(conf["key"]), scale, RANGE[genre]), (genre, vals)
        assert abs(vals[4] - STRENGTH[genre]) < 0.5, "intensidad = la elegida"

        # 5. Master IA medido sobre la sesión en vivo
        mr = json.loads(b.mixer("master", json.dumps({"preset": PLATAFORMAS})))
        assert mr["ok"], mr
        st = mr["stats"]
        assert abs(st["lufs_i"] + 14) < 1.0 and st["max_peak_db"] <= -1.9, st

        # 6. Render de la canción: completo, sin NaN ni recortes
        out = tmp_path / f"{genre}_master.wav"
        assert eng.render_to_wav(str(out))
        y, sr = sf.read(str(out))
        assert np.isfinite(y).all() and len(y) >= (g.seconds - 0.5) * sr
        assert 20 * np.log10(np.max(np.abs(y)) + 1e-12) <= -1.0

        # La voz que sale afinada: solo la voz, con el afinador y puenteado
        eng.set_track_solo(lead["trackId"], True)
        wet = [e["id"] for e in eng.effects(lead["trackId"]) if e["key"] in ("space", "delay") and e["enabled"]]
        for i in wet:                      # reverb y eco aparte: se mide la nota, no la cola de la sala
            b.fxEnable(i, False)
        def voice_err(name):
            p = tmp_path / name
            assert eng.render_to_wav(str(p))
            v, vsr = sf.read(str(p))
            return F.pitch_error_cents(v, g, vsr)
        tuned = voice_err("voz_afinada.wav")
        b.fxEnable(tid, False)
        offline_only = voice_err("voz_sin_afinador.wav")      # la toma original, intacta
        b.fxEnable(tid, True)
        for i in wet:
            b.fxEnable(i, True)
        eng.set_track_solo(lead["trackId"], False)
        assert offline_only > 20.0 and tuned < offline_only * (1.0 - 0.6 * STRENGTH[genre] / 100), (genre, tuned, offline_only)
        # Comparativa con la afinación PSOLA de la mezcla automática (la que se usaba antes, sin conexión): misma voz y
        # misma intensidad. Por eso «Precisa» (PSOLA) sigue siendo la opción por defecto de la Mezcla IA
        # y el AF-60 en vivo es la alternativa editable: las dos tienen que afinar de verdad.
        m = mixer_service.load()
        raw = m.eng.load_stem(lead["path"])
        psola, _ = m.tuner.tune_to_scale(raw, m.eng.SR, conf["key"], conf["scale"], STRENGTH[genre])
        psola_err = F.pitch_error_cents(np.asarray(psola).T, g, m.eng.SR)    # mezcla automática: (canales, muestras)
        print(f"{genre}: sin afinar {offline_only:.1f} c · PSOLA {psola_err:.1f} c · AF-60 {tuned:.1f} c")
        assert psola_err < offline_only * 0.5 and psola_err <= tuned + 1.0, (genre, tuned, psola_err)

        # 7. Guardar y reabrir el proyecto: el afinador y su tonalidad siguen en la voz
        doc = project.collect({"tracks": [{"id": lead["trackId"], "type": "audio"}]}, eng, h.effect_catalog(), {},
                              b._fx_labels, b._auto)
        saved = doc["tracks"][0]["fx"]
        assert saved[0]["key"] == "tune", [f["key"] for f in saved]
        rr = json.loads(b.fxRestore(lead["trackId"], json.dumps(saved)))
        assert rr["ok"] and rr["chain"][0]["key"] == "tune"
        assert round(rr["chain"][0]["values"][0]) == F.NOTES.index(conf["key"])
    finally:
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None
