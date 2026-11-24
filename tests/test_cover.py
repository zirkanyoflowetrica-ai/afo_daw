"""«Versión con IA» (ACE-Step «cover», C13) sobre PROYECTOS COMPLETOS.

Sin tarjeta gráfica: la petición se valida (≥ 2 s, ≤ el máximo del perfil, modo conocido), y con una
canción de song_factory en una pista se comprueba que el slot recorta justo el trozo del clip, que
«Parecida» va como `cover-nofsq` con el mismo audio de referencia y «Libre» como `cover`, y que el
resultado lleva dónde ponerlo (pista nueva; el original no se toca).

En la tarjeta gráfica (una sola vez, corta, por el cuidado de la GPU): 8 s de un reguetón se versionan
«Parecida» y se mide que el resultado dura lo mismo que el trozo y suena."""
import json
import time

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import ai_music
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 44100


def _mix(genre: str, folder) -> tuple[str, float]:
    song = F.write_song(genre, folder / "stems")
    x = sum(sf.read(p, dtype="float32", always_2d=True)[0] for p in song["paths"])
    x = x / max(1e-6, float(np.abs(x).max())) * 0.8
    out = folder / f"{genre}_mezcla.wav"
    sf.write(out, x, SR, subtype="PCM_16")
    return str(out), len(x) / SR


def test_peticion_cover():
    p = ai_music.build_cover_request({"mode": "Parecida", "likeness": 1, "style": "Jazz", "bpm": 96, "seed": 2}, 10.0)
    assert p["task_type"] == "cover-nofsq" and p["synth_model"] == ai_music.SYNTH_MODEL
    assert p["audio_cover_strength"] == 0.5 and p["duration"] == 10 and p["bpm"] == 96 and "jazz" in p["caption"]
    q = ai_music.build_cover_request({"mode": "Libre", "likeness": 0}, 10.0)
    assert q["task_type"] == "cover" and q["audio_cover_strength"] == 0.3 and "same" in q["caption"]
    for opts, secs in (({}, 1.5), ({"mode": "Otra"}, 10.0), ({}, ai_music.max_seconds() + 5)):
        with pytest.raises(ValueError):
            ai_music.build_cover_request(opts, secs)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    yield h, b
    h.engine = None


@pytest.mark.parametrize("genre,mode", [("balada", "Parecida"), ("trap", "Libre")])
def test_recorta_el_clip_y_pide_el_modo(genre, mode, bridge, tmp_path, monkeypatch):
    """Sin IA: el motor de ACE-Step se sustituye por una captura; se mira lo que le llegaría."""
    h, b = bridge
    path, secs = _mix(genre, tmp_path)
    tid = h.add_audio(path)["id"]
    eng = tmp_path / "motor"; eng.mkdir()
    mdl = tmp_path / "modelos"; mdl.mkdir(); (mdl / ai_music.SYNTH_MODEL).write_bytes(b"x")
    monkeypatch.setattr(ai_music, "engine_dir", lambda: eng)
    monkeypatch.setattr(ai_music, "models_dir", lambda: mdl)
    got = {}

    def fake_part(eng_, req, src, name, meta, extra=None):
        got.update(req=req, src=src, meta=meta, extra=extra or [],
                   cut=sf.read(str(src), dtype="float32", always_2d=True)[0])
    monkeypatch.setattr(b.ai, "_part", fake_part)

    a, z = round(secs / 2 - 3, 3), round(secs / 2 + 3, 3)
    r = json.loads(b.aiCover(tid, json.dumps({"start": a, "end": z, "at": 4.0, "mode": mode, "style": "Lo-fi"})))
    assert r["ok"], r
    b.ai._gen.join(5)
    x = sf.read(path, dtype="float32", always_2d=True)[0]
    cut = got["cut"]
    assert abs(len(cut) / SR - (z - a)) < 0.01, "el trozo dura lo que el clip"
    assert np.abs(cut - x[int(a * SR):int(a * SR) + len(cut)]).max() < 1e-3, "es justo ese trozo de la canción"
    want = "cover-nofsq" if mode == "Parecida" else "cover"
    assert got["req"]["task_type"] == want
    assert got["extra"] == (["--ref-audio", str(got["src"])] if mode == "Parecida" else [])
    assert got["meta"]["cover"] == {"trackId": tid, "at": 4.0, "start": a, "end": z, "mode": mode}
    assert h.tracks[tid]["originalPath"] == path, "el original no se toca"
    assert not json.loads(b.aiCover(9999, "{}"))["ok"]                       # sin pista de audio
    print(f"{genre} ({secs:.1f} s): trozo {a}–{z} s → {want}, fuerza {got['req']['audio_cover_strength']}")


@pytest.mark.skipif(ai_music.engine_dir() is None or not (ai_music.models_dir() / ai_music.SYNTH_MODEL).is_file(),
                    reason="sin motor ACE-Step o sin el sintetizador")
def test_version_de_un_regueton_en_la_gpu(bridge, tmp_path):
    from PySide6.QtCore import QCoreApplication
    h, b = bridge
    path, secs = _mix("regueton", tmp_path)
    tid = h.add_audio(path)["id"]
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    a, z = 2.0, 10.0
    r = json.loads(b.aiCover(tid, json.dumps({"start": a, "end": z, "at": a, "mode": "Parecida", "bpm": 100, "seed": 5})))
    assert r["ok"], r
    t0 = time.monotonic()
    while not any(e.get("phase") == "done" for e in events) and time.monotonic() - t0 < 600:
        QCoreApplication.processEvents()
        h.pump()
        time.sleep(0.02)
    done = next(e for e in events if e.get("phase") == "done")
    took = time.monotonic() - t0
    assert done["ok"], done
    assert done["cover"]["trackId"] == tid and done["cover"]["mode"] == "Parecida"
    y, sr = sf.read(done["path"], dtype="float32", always_2d=True)
    lvl = 20 * np.log10(float(np.sqrt(np.mean(y ** 2))) + 1e-12)
    print(f"reguetón: versión parecida de {z - a:.0f} s en {took:.0f} s; largo {len(y) / sr:.2f} s, nivel {lvl:.1f} dBFS")
    assert abs(len(y) / sr - (z - a)) < 0.6, "la versión dura lo que el trozo"
    assert lvl > -40, "la versión suena"
    nt = h.add_audio(done["path"])["id"]                                   # como la interfaz: pista nueva
    assert nt != tid and h.tracks[tid]["originalPath"] == path
