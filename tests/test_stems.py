"""Separador de stems (Demucs v4 de 6 fuentes, demucs.cpp) con PROYECTOS COMPLETOS: la mezcla entera
de una canción en una sola pista → «Dividir en pistas» → cada parte se compara con su stem real
(SDR en dB: cuánto se parece; la mezcla sin separar sirve de referencia). La batería se divide
además en Bombo, Caja / Clap y Platos. Se salta si faltan el separador o su modelo."""
import json
import time

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import stems
from allforone.engine_host import EngineHost, afo_audio

pytestmark = [
    pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado"),
    pytest.mark.skipif(not (stems.status()["engineOk"] and stems.status()["modelOk"]),
                       reason="sin el separador Demucs o sin su modelo"),
]


def _sdr(ref: np.ndarray, est: np.ndarray) -> float:
    n = min(len(ref), len(est))
    ref, est = ref[:n], est[:n]
    return float(10 * np.log10(np.sum(ref ** 2) / (np.sum((ref - est) ** 2) + 1e-12)))


def _mono44(path: str) -> np.ndarray:
    return stems._load_44k(path).mean(axis=1)


def test_division_de_bateria_suma_exacta():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((44100, 2)).astype("float32") * 0.1
    parts = stems.split_drums(x)
    assert list(parts) == list(stems.DRUM_PARTS)
    assert np.max(np.abs(sum(parts.values()) - x)) < 1e-4, "las tres partes suman la batería"


@pytest.mark.parametrize("genre", ["trap", "rock"])
def test_dividir_cancion_completa(genre, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    song = F.write_song(genre, tmp_path / "stems")
    truth, mix = {}, None
    for p in song["paths"]:
        y, sr = sf.read(p, always_2d=True, dtype="float32")
        mix = y if mix is None else mix + y
        truth[p.split(f"{genre.capitalize()}_", 1)[1][:-4]] = p      # «Kick», «808», «Voz_Lead»…
    peak = float(np.max(np.abs(mix)))
    mpath = tmp_path / f"{genre}_mezcla.wav"
    sf.write(str(mpath), mix / peak * 0.9, sr)
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    try:
        tid = h.add_audio(str(mpath))["id"]
        assert not json.loads(b.stemsSplit(9999, False))["ok"]
        r = json.loads(b.stemsSplit(tid, True))
        assert r["ok"], r
        t0 = time.monotonic()
        while not any(e.get("type") == "stems" and e.get("phase") == "done" for e in events) and time.monotonic() - t0 < 900:
            app.processEvents()
            h.pump()
            time.sleep(0.05)
        done = next(e for e in events if e.get("type") == "stems" and e.get("phase") == "done")
        assert done["ok"], done
        assert done["trackId"] == tid and any(e.get("phase") == "progress" for e in events if e.get("type") == "stems")
        got = {s["label"]: s["path"] for s in done["stems"]}
        assert "Batería" not in got and {"Bombo", "Bajo"} <= set(got), got   # la batería llega ya dividida
        m = _mono44(str(mpath))
        scale = 0.9 / peak

        def ref(*names):
            ys = [_mono44(truth[n]) * scale for n in names if n in truth]
            return sum(ys) if ys else None
        res = {}
        bass = ref("808", "Bajo")
        drums = ref("Drums", "Kick", "Snare", "Clap", "HiHat")
        if bass is not None:
            res["Bajo"] = (_sdr(bass, _mono44(got["Bajo"])), _sdr(bass, m))
        est_drums = sum(_mono44(got[k]) for k in stems.DRUM_PARTS if k in got)
        res["Batería (3 partes)"] = (_sdr(drums, est_drums), _sdr(drums, m))
        if "Kick" in truth:
            res["Bombo"] = (_sdr(ref("Kick"), _mono44(got["Bombo"])), _sdr(ref("Kick"), m))
        if "HiHat" in truth and "Platos" in got:
            res["Platos"] = (_sdr(ref("HiHat"), _mono44(got["Platos"])), _sdr(ref("HiHat"), m))
        for k, (s, base) in res.items():
            print(f"{genre} · {k}: SDR {s:.1f} dB (sin separar {base:.1f} dB)")
        print(f"{genre}: {done['message']}")
        assert res["Batería (3 partes)"][0] > 8.0 and res["Batería (3 partes)"][0] > res["Batería (3 partes)"][1] + 10
        if "Bajo" in res:
            assert res["Bajo"][0] > 8.0, res["Bajo"]
        if "Bombo" in res:
            assert res["Bombo"][0] > res["Bombo"][1] + 10, res["Bombo"]
        # Las partes reconstruyen la canción (no se pierde ni se inventa audio)
        allp = sum(_mono44(p) for p in got.values())
        assert _sdr(m, allp) > 8.0, _sdr(m, allp)
    finally:
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None
