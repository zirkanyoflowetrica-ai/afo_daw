"""Drum Rack (Batería, motor C++): cada pad con su paneo, su grupo de corte (el hi-hat cerrado corta al
abierto) y, si se quiere, un golpe grabado propio. Medido en el render real; y un trap completo con la
batería repartida en el estéreo y los hi-hats en un grupo de corte."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import LANE_DEFAULTS, EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

KICK, SNARE, HAT, OPEN, CLAP, TOM, CYM, BELL = range(8)


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _lanes(**over):
    """over = {pad: {índice: valor}} sobre los valores de fábrica (0 afinación … 4 paneo, 5 grupo)."""
    out = [list(LANE_DEFAULTS) for _ in range(8)]
    for lane, kv in over.items():
        for k, v in kv.items():
            out[int(lane)][k] = float(v)
    return out


def _render(eng, tmp_path, hits, lanes=None, name="rack.wav", samples=None, bpm=120.0):
    """hits = [(negra, pad)] en una pista de batería nueva; devuelve (L, R, sr)."""
    eng.set_tempo(bpm)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Batería", 1)["id"]
    if samples:
        eng.set_drum_samples(tid, samples)
    eng.set_synth_settings(tid, mode=1, vol=60, tun=50, lanes=lanes or [])
    eng.set_synth_midi(tid, [(b, 0.25, 36 + p, 100) for b, p in hits], max(b for b, _ in hits) + 4.0)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], y[:, 1], sr


def _high(x, sr, f=5000, kind="highpass"):
    from scipy.signal import butter, sosfilt
    return sosfilt(butter(4, f, kind, fs=sr, output="sos"), x)


def test_paneo_de_cada_pad(host, tmp_path):
    eng = host.engine
    l0, r0, _ = _render(eng, tmp_path, [(0.0, KICK)])
    lc, rc, _ = _render(eng, tmp_path, [(0.0, KICK)], _lanes(**{str(KICK): {4: 50}}))
    ll, rl, _ = _render(eng, tmp_path, [(0.0, KICK)], _lanes(**{str(KICK): {4: 0}}))
    lr, rr, _ = _render(eng, tmp_path, [(0.0, KICK)], _lanes(**{str(KICK): {4: 100}}))
    lq, rq, _ = _render(eng, tmp_path, [(0.0, KICK)], _lanes(**{str(KICK): {4: 25}}))
    pk = lambda x: float(np.abs(x).max())
    print(f"bombo: centro L {pk(lc):.3f} / R {pk(rc):.3f} · izquierda R {pk(rl):.1e} · derecha L {pk(lr):.1e} · "
          f"paneo 25: R/L {pk(rq) / pk(lq):.3f}")
    assert np.allclose(lc, l0) and np.allclose(rc, r0) and np.allclose(lc, rc), "en el centro suena igual que antes"
    assert pk(rl) < 1e-6 and pk(ll) == pytest.approx(pk(lc), rel=1e-4)
    assert pk(lr) < 1e-6 and pk(rr) == pytest.approx(pk(rc), rel=1e-4)
    assert pk(rq) / pk(lq) == pytest.approx(0.5, rel=0.01)
    # Escuchar el pad al pulsarlo también suena en su paneo
    assert eng.audition_synth(36 + KICK, 0.0, mode=1, vol=60, lanes=_lanes(**{str(KICK): {4: 0}}))
    eng.preview_stop()


def test_grupo_de_corte(host, tmp_path):
    """Hi-hat abierto largo (caída 100) en la negra 0; hi-hat cerrado (mudo, nivel 0) a la semicorchea (0,125 s)."""
    eng = host.engine
    hits = [(0.0, OPEN), (0.25, HAT)]
    quiet = {3: 0}                                          # el cerrado no se oye: solo se ve el corte
    free, _, sr = _render(eng, tmp_path, hits, _lanes(**{str(HAT): quiet, str(OPEN): {1: 100}}))
    cut, _, _ = _render(eng, tmp_path, hits, _lanes(**{str(HAT): {**quiet, 5: 1}, str(OPEN): {1: 100, 5: 1}}))
    other, _, _ = _render(eng, tmp_path, hits, _lanes(**{str(HAT): {**quiet, 5: 2}, str(OPEN): {1: 100, 5: 1}}))
    at = int(0.125 * sr)
    before = np.abs(cut[:at - 1] - free[:at - 1]).max()
    tail_free = np.abs(free[at + int(0.006 * sr): at + int(0.1 * sr)]).max()
    tail_cut = np.abs(cut[at + int(0.006 * sr): at + int(0.1 * sr)]).max()
    print(f"hi-hat abierto tras el cerrado: sin corte {tail_free:.4f} · con corte {tail_cut:.1e} · "
          f"antes del golpe, diferencia {before:.1e}")
    assert before < 1e-7, "hasta el golpe que corta, nada cambia"
    assert tail_free > 0.01 and tail_cut < 1e-6
    assert np.allclose(other, free), "un pad de otro grupo no corta"


def test_golpe_grabado_con_paneo_y_corte(host, tmp_path):
    eng = host.engine
    rng = np.random.default_rng(7)
    sr0 = 48000
    t = np.arange(sr0) / sr0
    ride = (0.4 * rng.standard_normal(sr0) * np.exp(-t * 1.5)).astype(np.float32)   # platillo de 1 s
    path = tmp_path / "ride.wav"
    sf.write(str(path), ride, sr0)
    samples = [""] * 8
    samples[OPEN] = str(path)
    hits = [(0.0, OPEN), (0.5, HAT)]
    lanes = _lanes(**{str(OPEN): {4: 100, 5: 1}, str(HAT): {3: 0, 5: 1}})
    l, r, sr = _render(eng, tmp_path, hits, lanes, samples=samples)
    at = int(0.25 * sr)
    print(f"golpe grabado a la derecha: L {np.abs(l).max():.1e}, R {np.abs(r).max():.3f}; "
          f"tras el corte {np.abs(r[at + int(0.006 * sr):]).max():.1e}")
    assert np.abs(l).max() < 1e-6 and np.abs(r[:at]).max() > 0.05
    assert np.abs(r[at + int(0.006 * sr):]).max() < 1e-4


def test_ajustes_desde_la_pista():
    s = synth_settings({"type": "drum", "cfg": {"lanes": [None, [40, None, None, None, 80, 2], [50, 50, 50, 50]]}})
    assert s["lanes"] == [list(LANE_DEFAULTS), [40.0, 50.0, 50.0, 50.0, 80.0, 2.0], [50.0, 50.0, 50.0, 50.0, 50.0, 0.0]]


def test_trap_completo_con_bateria_en_estereo_y_hihats_en_corte(host, tmp_path):
    """Un trap entero (808, pad, voces) con la batería del motor: hi-hats a la derecha (70) en el grupo
    A, el abierto largo en la última corchea del compás y el cerrado del compás siguiente lo corta;
    cencerro a la izquierda. Bombo y caja en el centro."""
    from song_factory import write_song
    song = write_song("trap", tmp_path / "trap")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]
              if Path(p).stem.split("_", 1)[1] not in ("Kick", "Clap", "HiHat", "Snare", "Drums")]
    tid = eng.add_synth_track("Drum Rack", 1)["id"]
    rack = _lanes(**{str(HAT): {4: 70, 5: 1}, str(OPEN): {1: 80, 4: 70, 5: 1}, str(BELL): {4: 20}})
    bars = int(g.seconds * g.bpm / 60 // 4)
    notes = []
    for b in range(bars):
        o = b * 4.0
        notes += [(o, 0.25, 36 + KICK, 110), (o + 2.5, 0.25, 36 + KICK, 100),
                  (o + 1, 0.25, 36 + CLAP, 100), (o + 3, 0.25, 36 + CLAP, 100), (o + 1.75, 0.25, 36 + BELL, 70)]
        notes += [(o + k * 0.5, 0.25, 36 + HAT, 80) for k in range(7)]
        notes.append((o + 3.5, 0.25, 36 + OPEN, 90))
    eng.set_synth_settings(tid, mode=1, vol=70, tun=50, lanes=rack)
    eng.set_synth_midi(tid, notes, bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others:
        eng.set_track_mute(o, True)
    assert eng.render_to_wav(str(tmp_path / "drums.wav"))
    d, sr = sf.read(str(tmp_path / "drums.wav"))
    no_cut = [r[:4] + [r[4], 0.0] for r in rack]
    eng.set_synth_settings(tid, mode=1, vol=70, tun=50, lanes=no_cut)
    assert eng.render_to_wav(str(tmp_path / "free.wav"))
    f, _ = sf.read(str(tmp_path / "free.wav"))
    eng.set_synth_settings(tid, mode=1, vol=70, tun=50, lanes=rack)        # sin hi-hat abierto: lo que queda
    eng.set_synth_midi(tid, [n for n in notes if n[2] != 36 + OPEN], bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "noopen.wav"))
    z, _ = sf.read(str(tmp_path / "noopen.wav"))
    beat = 60 / g.bpm
    hl, hr = _high(d[:, 0], sr), _high(d[:, 1], sr)
    bl, br = _high(d[:, 0], sr, 150, "lowpass"), _high(d[:, 1], sr, 150, "lowpass")   # el bombo, sin hi-hats
    fl, zl = _high(f[:, 0], sr), _high(z[:, 0], sr)
    side, cuts, low, rings = [], [], [], []
    for b in range(bars):
        t0 = b * 4 * beat
        w = slice(int((t0 + 0.5 * beat) * sr), int((t0 + 0.5 * beat + 0.04) * sr))      # corchea solo de hi-hat
        side.append(10 * np.log10((hr[w] ** 2).sum() / (hl[w] ** 2).sum()))
        k0 = int((t0 + 0.05 * beat) * sr)
        w = slice(k0 + int(0.06 * sr), k0 + int(0.15 * sr))
        if b > 0:                                       # lo que queda del abierto del compás anterior tras el cerrado
            rings.append(np.abs(fl[w] - zl[w]).max())
            cuts.append(np.abs(hl[w] - zl[w]).max() / max(rings[-1], 1e-12))
        kw = slice(int(t0 * sr), int((t0 + 0.1) * sr))
        low.append(np.abs(bl[kw]).max() / np.abs(br[kw]).max())
    print(f"{bars} compases: hi-hat a la derecha {np.median(side):+.1f} dB (paneo 70 = +4,4 dB); "
          f"abierto sin corte {min(rings):.4f}, con corte ×{max(cuts):.3f}; bombo L/R {np.median(low):.3f}")
    assert all(s == pytest.approx(20 * np.log10(1 / 0.6), abs=0.3) for s in side)
    assert min(rings) > 0.002 and all(c < 0.05 for c in cuts)
    assert all(v == pytest.approx(1.0, abs=0.02) for v in low)
