"""Vocal Align (AF-67) en el motor C++: una toma se ajusta en el tiempo a una voz guía.

Con PROYECTOS COMPLETOS (la voz de la balada de song_factory): la toma es la misma voz movida a
tramos (de −70 a +80 ms, con transiciones de 150 ms), más baja y con soplido. Se mide el desfase real
por ventanas de 0,5 s con la envolvente: tras alinear queda a pocos ms; con fuerza 0, o si ya
cuadraba, la toma sale idéntica; el tono no cambia; con fuerza 50 % se queda a medio camino. Por el
puente: las dos pistas en otro sitio de la línea de tiempo, la alineación corre en su hilo, la pista
pasa al archivo nuevo con los mismos clips y el render de la toma cae sobre el de la guía.
"""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.ndimage import uniform_filter1d
from scipy.signal import hilbert

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
STEPS = [0.06, -0.045, 0.08, 0.0, -0.07, 0.04, 0.025, -0.03, 0.07, -0.06, 0.05, 0.0, -0.04, 0.06, 0.03]


@pytest.fixture(scope="module")
def voz(tmp_path_factory):
    from song_factory import write_song
    song = write_song("balada", tmp_path_factory.mktemp("balada"))
    p = next(p for p in song["paths"] if Path(p).stem.endswith("Voz_Lead"))
    y, sr = sf.read(p, always_2d=True)
    return y[:, 0].copy(), sr


def _toma(g, sr, steps=STEPS):
    """La guía movida a tramos de 2 s: toma(t) = guía(t − retraso(t)); más baja y con soplido."""
    t = np.arange(len(g)) / sr
    k = np.minimum((t // 2).astype(int), len(steps) - 1)
    delay = uniform_filter1d(np.asarray(steps)[k], int(0.15 * sr))
    d = np.interp(t - delay, t, g) * 0.6 + 1e-3 * np.random.default_rng(2).standard_normal(len(g))
    return d, delay


def _lags(g, b, sr):
    """Desfase (ms) de `b` respecto a `g` por ventanas de 0,5 s con voz: correlación de envolventes."""
    env = lambda x: uniform_filter1d(np.abs(hilbert(x)), int(0.01 * sr))
    a, bb = env(g), env(b)
    a = a - uniform_filter1d(a, int(0.3 * sr))
    bb = bb - uniform_filter1d(bb, int(0.3 * sr))
    n, m = int(0.5 * sr), int(0.15 * sr)
    out = {}
    for s in range(sr, len(a) - n - m, n):
        if np.sqrt(np.mean(g[s:s + n] ** 2)) < 0.02:
            continue
        x = a[s:s + n]
        best = max(range(-m, m + 1, 24), key=lambda L: float(np.dot(x, bb[s + L:s + L + n])))
        best = max(range(best - 24, best + 25), key=lambda L: float(np.dot(x, bb[s + L:s + L + n])))
        out[s + n // 2] = best / sr * 1000
    return out


def _fiables(g, d, delay, sr):
    """Ventanas en las que la medida acierta el retraso puesto (±15 ms): ahí se juzga el resultado."""
    return {c: v for c, v in _lags(g, d, sr).items() if abs(v - delay[c] * 1000) < 15}


def _write(p, y, sr):
    sf.write(str(p), np.stack([y, y], 1) if y.ndim == 1 else y, sr, subtype="FLOAT")
    return str(p)


def test_alinea_la_toma_a_la_guia(voz, tmp_path):
    g, sr = voz
    d, delay = _toma(g, sr)
    gp, dp, op = _write(tmp_path / "g.wav", g, sr), _write(tmp_path / "d.wav", d, sr), tmp_path / "o.wav"
    t0 = time.perf_counter()
    r = afo_audio.align_voice(gp, 0.0, dp, 0.0, str(op), 1.0, 150.0)
    took = time.perf_counter() - t0
    assert r["ok"], r
    o, osr = sf.read(str(op), always_2d=True)
    assert osr == sr and o.shape == (len(d), 2)
    ok = _fiables(g, d, delay, sr)
    before = np.array([abs(delay[c]) * 1000 for c in ok])
    after = np.array([abs(v) for c, v in _lags(g, o[:, 0], sr).items() if c in ok])
    print(f"vocal align: {len(ok)} ventanas; desfase medio {before.mean():.1f} → mediana {np.median(after):.1f} ms, "
          f"{np.mean(after < 20) * 100:.0f} % a menos de 20 ms; el motor midió {r['mean_shift_ms']:.1f} ms "
          f"(máx. {r['max_shift_ms']:.1f}); {r['seconds']:.0f} s en {took:.2f} s")
    assert len(ok) >= 15 and before.mean() > 35
    assert np.median(after) < 10 and np.mean(after < 20) >= 0.85
    assert 25 < r["mean_shift_ms"] < 80


def test_fuerza_cero_o_ya_alineada_no_cambia_nada(voz, tmp_path):
    g, sr = voz
    d, _ = _toma(g, sr)
    gp, dp = _write(tmp_path / "g.wav", g, sr), _write(tmp_path / "d.wav", d, sr)
    assert afo_audio.align_voice(gp, 0.0, dp, 0.0, str(tmp_path / "o0.wav"), 0.0, 150.0)["ok"]
    o0 = sf.read(str(tmp_path / "o0.wav"))[0][:, 0]
    r = afo_audio.align_voice(gp, 0.0, gp, 0.0, str(tmp_path / "same.wav"), 1.0, 150.0)
    same = sf.read(str(tmp_path / "same.wav"))[0][:, 0]
    print(f"fuerza 0: {np.abs(o0 - d).max():.1e}; ya alineada: movió {r['mean_shift_ms']:.1f} ms, {np.abs(same - g).max():.1e}")
    assert np.abs(o0 - d).max() < 1e-6 and r["mean_shift_ms"] < 1 and np.abs(same - g).max() < 1e-6


def test_no_cambia_el_tono(voz, tmp_path):
    import librosa
    g, sr = voz
    d, _ = _toma(g, sr)
    gp, dp, op = _write(tmp_path / "g.wav", g, sr), _write(tmp_path / "d.wav", d, sr), tmp_path / "o.wav"
    assert afo_audio.align_voice(gp, 0.0, dp, 0.0, str(op), 1.0, 150.0)["ok"]
    o = sf.read(str(op))[0][:, 0]

    def notas(y):
        f, v, _ = librosa.pyin(y.astype(np.float32), fmin=70, fmax=1000, sr=sr, frame_length=2048, hop_length=512)
        f = f[v & np.isfinite(f)]
        return np.round(12 * np.log2(f / 440.0) * 100)       # cents respecto a La 440
    a, b = notas(d), notas(o)
    hist = lambda c: np.bincount(np.clip(((c + 6000) // 25).astype(int), 0, 480), minlength=481)
    corr = float(np.corrcoef(hist(a), hist(b))[0, 1])
    print(f"tono: mediana {np.median(a):.0f} → {np.median(b):.0f} cents, histograma de notas r = {corr:.3f}")
    assert abs(np.median(a) - np.median(b)) <= 5 and corr > 0.9


def test_fuerza_media_se_queda_a_medio_camino(voz, tmp_path):
    g, sr = voz
    d, delay = _toma(g, sr)
    gp, dp, op = _write(tmp_path / "g.wav", g, sr), _write(tmp_path / "d.wav", d, sr), tmp_path / "o.wav"
    assert afo_audio.align_voice(gp, 0.0, dp, 0.0, str(op), 0.5, 150.0)["ok"]
    ok = _fiables(g, d, delay, sr)
    lag = _lags(g, sf.read(str(op))[0][:, 0], sr)
    ratio = np.median([abs(lag[c]) / (abs(delay[c]) * 1000) for c in ok if abs(delay[c]) > 0.035])
    print(f"fuerza 50 %: queda el {ratio * 100:.0f} % del desfase")
    assert 0.3 < ratio < 0.7


def test_errores(voz, tmp_path):
    g, sr = voz
    gp = _write(tmp_path / "g.wav", g, sr)
    r = afo_audio.align_voice(gp, 0.0, gp, 500.0, str(tmp_path / "o.wav"), 1.0, 150.0)
    assert not r["ok"] and "coinciden" in r["error"]
    r = afo_audio.align_voice(str(tmp_path / "no.wav"), 0.0, gp, 0.0, str(tmp_path / "o.wav"), 1.0, 150.0)
    assert not r["ok"] and "guía" in r["error"]


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


def test_puente_alinea_en_la_linea_de_tiempo(voz, bridge, tmp_path):
    """La guía empieza en el segundo 1; la toma lleva 0,5 s de silencio y su clip empieza en 0,5: las
    dos caen juntas en el proyecto. Tras alinear, la pista de la toma usa el archivo nuevo con los
    mismos clips, «Deshacer» tendría el archivo anterior y el render de la toma cae sobre la guía."""
    h, b = bridge
    g, sr = voz
    d, delay = _toma(g, sr)
    gid = h.add_audio(_write(tmp_path / "guia.wav", g, sr), "Guía")["id"]
    dpath = _write(tmp_path / "toma.wav", np.concatenate([np.zeros(sr // 2), d]), sr)
    did = h.add_audio(dpath, "Toma")["id"]
    for tid, start in ((gid, 1.0), (did, 0.5)):
        c = h.engine.clips(tid)[0]
        r = json.loads(b.clipEdit(tid, json.dumps({"op": "range", "clip": c["id"], "start": start,
                                                   "length": c["length"], "offset": c["offset"]})))
        assert r["ok"], r
    clips_before = h.engine.clips(did)

    def solo(tid, name):
        for t in (gid, did):
            h.engine.set_track_mute(t, t != tid)
        assert h.engine.render_to_wav(str(tmp_path / name))
        y, rsr = sf.read(str(tmp_path / name), always_2d=True)
        return y[:, 0], rsr
    rg, rsr = solo(gid, "rg.wav")
    rd0, _ = solo(did, "rd0.wav")
    n = min(len(rg), len(rd0))
    # ventanas fiables: la medida antes de alinear da el retraso puesto (la guía empieza en el segundo 1)
    puesto = lambda c: delay[min(len(delay) - 1, max(0, int((c / rsr - 1.0) * sr)))] * 1000
    ok = {c for c, v in _lags(rg[:n], rd0[:n], rsr).items() if abs(v - puesto(c)) < 15}
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    assert not json.loads(b.vocalAlign(did, did, "{}"))["ok"]
    r = json.loads(b.vocalAlign(did, gid, json.dumps({"strength": 100, "maxShiftMs": 150})))
    assert r["ok"], r
    assert not json.loads(b.vocalAlign(did, gid, "{}"))["ok"]          # ya hay una en marcha
    t0 = time.time()
    while not events and time.time() - t0 < 60:
        b._drain_mixer_events(); time.sleep(0.05)
    ev = events[-1]
    assert ev["type"] == "align" and ev["ok"], ev
    assert ev["previous"] == dpath and Path(ev["path"]).is_file() and ev["path"] != dpath
    assert h.tracks[did]["originalPath"] == ev["path"]
    keep = lambda cs: [(round(c["start"], 6), round(c["length"], 6), round(c["offset"], 6)) for c in cs]
    assert keep(h.engine.clips(did)) == keep(clips_before)
    rd, _ = solo(did, "rd.wav")
    n = min(n, len(rd))
    lag = _lags(rg[:n], rd[:n], rsr)
    after = np.array([v for c, v in lag.items() if c in ok])
    assert len(after) >= 15
    print(f"puente: movió {ev['meanShiftMs']} ms de media; en el render la toma queda a mediana {np.median(np.abs(after)):.1f} ms "
          f"de la guía ({np.mean(np.abs(after) < 20) * 100:.0f} % a menos de 20 ms, {len(after)} ventanas)")
    assert np.median(np.abs(after)) < 10 and np.mean(np.abs(after) < 20) >= 0.85
