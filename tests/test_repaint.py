"""«Rehacer con IA» (ACE-Step «repaint», C12) sobre PROYECTOS COMPLETOS.

Sin tarjeta gráfica: la petición se valida (zona dentro del audio, ≥ 1 s, ≤ el máximo del perfil) y la
pista cambia de archivo sin perder sus clips; «Deshacer» (clipEdit «set» con `source`) vuelve al original.

En la tarjeta gráfica (una sola vez, corta, por el cuidado de la GPU): se mezcla un rock de song_factory
en una pista, se rehacen 4 s del centro y se mide que fuera de la zona sigue la canción, que dentro hay
algo distinto que suena, y que el archivo dura lo mismo."""
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


def test_peticion_repaint():
    r = ai_music.build_repaint_request({"start": 4, "end": 8, "style": "Rock", "bpm": 120, "seed": 3}, 20.0)
    assert r["task_type"] == "repaint" and r["synth_model"] == ai_music.SYNTH_MODEL
    assert (r["repainting_start"], r["repainting_end"], r["duration"], r["bpm"]) == (4, 8, 20, 120)
    assert r["caption"] and r["lyrics"] == "[Instrumental]"
    assert "same" in ai_music.build_repaint_request({"start": 0, "end": 2}, 5)["caption"]
    for bad in ({"start": 4, "end": 4.5}, {"start": -1, "end": 3}, {"start": 18, "end": 25}):
        with pytest.raises(ValueError):
            ai_music.build_repaint_request(bad, 20.0)
    with pytest.raises(ValueError):                         # más de lo que el perfil del equipo deja seguido
        ai_music.build_repaint_request({"start": 0, "end": ai_music.max_seconds() + 5}, ai_music.max_seconds() + 30)


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


@pytest.mark.parametrize("genre", ["balada", "trap"])
def test_cambiar_archivo_conserva_clips_y_deshacer(genre, bridge, tmp_path):
    """Sin IA: otro archivo del mismo largo (la mezcla al revés) entra en la pista con sus clips; el
    deshacer de la interfaz (clipEdit «set» con source) devuelve el archivo y los clips de antes."""
    h, b = bridge
    path, secs = _mix(genre, tmp_path)
    tid = h.add_audio(path)["id"]
    # la pista dividida en dos clips, el segundo con ganancia: así se ve que los clips se conservan
    cs = h.engine.clips(tid)
    assert json.loads(b.clipEdit(tid, json.dumps({"op": "split", "clip": cs[0]["id"], "at": cs[0]["start"] + secs / 2})))["ok"]
    cs = h.engine.clips(tid)
    assert json.loads(b.clipEdit(tid, json.dumps({"op": "gain", "clip": cs[1]["id"], "db": -6})))["ok"]
    before = h.engine.clips(tid)
    alt = tmp_path / "rehecho.wav"
    y = sf.read(path, dtype="float32")[0]
    sf.write(alt, y[::-1], SR, subtype="PCM_16")

    r = json.loads(b.trackSetSource(tid, str(alt)))
    assert r["ok"], r
    assert r["previous"] == path and h.tracks[tid]["originalPath"] == str(alt)
    key = lambda c: (round(c["start"], 3), round(c["length"], 3), round(c["offset"], 3), round(c["gain_db"], 2))
    assert [key(c) for c in r["clips"]] == [key(c) for c in before]
    assert len(r["track"]["peaks"]) > 0

    u = json.loads(b.clipEdit(tid, json.dumps({"op": "set", "clips": before, "source": path})))
    assert u["ok"], u
    assert u["source"] == path and h.tracks[tid]["originalPath"] == path and u["peaks"]
    assert [key(c) for c in u["clips"]] == [key(c) for c in before]
    gone = json.loads(b.clipEdit(tid, json.dumps({"op": "set", "clips": before, "source": str(tmp_path / "no.wav")})))
    assert not gone["ok"]
    assert not json.loads(b.aiRepaint(9999, "{}"))["ok"]                 # sin pista de audio
    print(f"{genre}: {len(before)} clips conservados al cambiar de archivo y al deshacer")


def _env(y: np.ndarray, sr: int, hop: float = 0.05) -> np.ndarray:
    n = int(hop * sr)
    m = len(y) // n
    return np.sqrt(np.mean(y[: m * n].reshape(m, n) ** 2, axis=1) + 1e-12)


@pytest.mark.skipif(ai_music.engine_dir() is None or not (ai_music.models_dir() / ai_music.SYNTH_MODEL).is_file(),
                    reason="sin motor ACE-Step o sin el sintetizador")
def test_rehacer_zona_de_un_rock_en_la_gpu(bridge, tmp_path):
    from PySide6.QtCore import QCoreApplication
    import librosa
    from scipy.signal import resample_poly
    h, b = bridge
    path, secs = _mix("rock", tmp_path)
    tid = h.add_audio(path)["id"]
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    a, z = round(secs / 2 - 2, 2), round(secs / 2 + 2, 2)
    r = json.loads(b.aiRepaint(tid, json.dumps({"start": a, "end": z, "style": "Rock", "bpm": 120, "seed": 7})))
    assert r["ok"], r
    t0 = time.monotonic()
    while not any(e.get("phase") == "done" for e in events) and time.monotonic() - t0 < 600:
        QCoreApplication.processEvents()
        h.pump()
        time.sleep(0.02)
    done = next(e for e in events if e.get("phase") == "done")
    took = time.monotonic() - t0
    assert done["ok"], done
    assert done["repaint"]["trackId"] == tid and done["repaint"]["start"] == a

    y, sr = sf.read(done["path"], dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        y = resample_poly(y, SR, sr).astype("float32")
    x = sf.read(path, dtype="float32", always_2d=True)[0].mean(axis=1)
    n = min(len(x), len(y))
    ex, ey = _env(x[:n], SR), _env(y[:n], SR)
    t = np.arange(len(ex)) * 0.05
    out = (t < a - 0.5) | (t > z + 0.5)
    ins = (t > a + 0.5) & (t < z - 0.5)
    c_out = float(np.corrcoef(ex[out], ey[out])[0, 1])
    c_in = float(np.corrcoef(ex[ins], ey[ins])[0, 1])
    # fuera de la zona: el mismo timbre (cromagrama) que la canción; dentro: otro
    cx = librosa.feature.chroma_stft(y=x[:n], sr=SR, hop_length=2205)
    cy = librosa.feature.chroma_stft(y=y[:n], sr=SR, hop_length=2205)
    m = min(cx.shape[1], cy.shape[1], len(t))
    diff = np.abs(cx[:, :m] - cy[:, :m]).mean(axis=0)
    d_out, d_in = float(diff[out[:m]].mean()), float(diff[ins[:m]].mean())
    lvl = 20 * np.log10(float(np.sqrt(np.mean(y[int(a * SR):int(z * SR)] ** 2))) + 1e-12)
    print(f"rock {secs:.1f} s, zona {a}–{z} s en {took:.0f} s: envolvente fuera r={c_out:.2f} dentro r={c_in:.2f}; "
          f"croma fuera {d_out:.3f} dentro {d_in:.3f}; nivel en la zona {lvl:.1f} dBFS; largo {len(y) / SR:.2f} s")
    assert abs(len(y) / SR - secs) < 0.5, "el archivo rehecho dura lo mismo"
    assert lvl > -40, "la zona rehecha suena"
    assert c_out > 0.8, "fuera de la zona sigue la canción"
    assert d_in > 1.5 * d_out, "dentro de la zona hay algo distinto"

    # la pista pasa a usar el archivo rehecho y «Deshacer» vuelve al original
    before = h.engine.clips(tid)
    s = json.loads(b.trackSetSource(tid, done["path"]))
    assert s["ok"] and s["previous"] == path
    u = json.loads(b.clipEdit(tid, json.dumps({"op": "set", "clips": before, "source": path})))
    assert u["ok"] and h.tracks[tid]["originalPath"] == path
