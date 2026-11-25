"""Drum Synth (batería del motor C++): cada carril tiene afinación, caída, tono y nivel propios
(50 = el golpe de fábrica). Medido en el render real; y un hip hop completo con su batería ajustada
pad a pad (bombo grave y largo, caja más oscura) sin tocar los demás carriles."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio, synth_settings

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

KICK, SNARE, HAT = 0, 1, 2


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def _lanes(**over):
    """8 carriles de fábrica; over = {carril: (afinación, caída, tono, nivel)}"""
    out = [[50.0] * 4 for _ in range(8)]
    for lane, v in over.items():
        out[int(lane)] = [float(x) for x in v]
    return out


def _hit(eng, tmp_path, lane, lanes=None, vol=40.0, name="golpe.wav"):
    """Un solo golpe del carril en una pista de batería nueva, renderizado entero."""
    eng.set_tempo(120.0)
    for t in eng.tracks():
        eng.remove_track(t["id"])
    tid = eng.add_synth_track("Batería", 1)["id"]
    eng.set_synth_settings(tid, mode=1, vol=vol, tun=50.0, lanes=lanes or [])
    eng.set_synth_midi(tid, [(0.0, 0.25, 36 + lane, 100)], 8.0)
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    return y[:, 0], sr


def _peak_hz(x, sr, lo, hi):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)), 8 * len(x)))
    f = np.fft.rfftfreq(8 * len(x), 1 / sr)
    m = (f >= lo) & (f <= hi)
    return f[m][spec[m].argmax()]


def _centroid(x, sr):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return float((f * spec).sum() / spec.sum())


def _length_s(x, sr, below_db=-50):
    """Hasta dónde llega el golpe: última muestra por encima de `below_db` respecto a su pico."""
    env = np.abs(x)
    idx = np.flatnonzero(env > env.max() * 10 ** (below_db / 20))
    return idx[-1] / sr


def test_de_fabrica_igual_que_antes_y_carriles_independientes(host, tmp_path):
    eng = host.engine
    plain, _ = _hit(eng, tmp_path, SNARE)
    fifty, _ = _hit(eng, tmp_path, SNARE, _lanes())
    assert np.array_equal(plain, fifty), "50 en todo = el golpe de fábrica, muestra a muestra"
    other, _ = _hit(eng, tmp_path, SNARE, _lanes(**{str(KICK): (100, 100, 100, 100)}))
    assert np.array_equal(plain, other), "tocar el bombo no cambia la caja"


def test_afinacion_caida_tono_y_nivel(host, tmp_path):
    eng = host.engine
    base, sr = _hit(eng, tmp_path, KICK)
    up, _ = _hit(eng, tmp_path, KICK, _lanes(**{str(KICK): (100, 50, 50, 50)}))
    f_base = _peak_hz(base[int(0.18 * sr): int(0.40 * sr)], sr, 25, 200)
    f_up = _peak_hz(up[int(0.18 * sr): int(0.40 * sr)], sr, 25, 200)
    print(f"bombo: {f_base:.1f} Hz → {f_up:.1f} Hz con afinación 100")
    assert f_up / f_base == pytest.approx(2.0, rel=0.06), "afinación 100 = una octava arriba"

    short, _ = _hit(eng, tmp_path, SNARE, _lanes(**{str(SNARE): (50, 0, 50, 50)}))
    mid, _ = _hit(eng, tmp_path, SNARE)
    long, _ = _hit(eng, tmp_path, SNARE, _lanes(**{str(SNARE): (50, 100, 50, 50)}))
    ls, lm, ll = (_length_s(x, sr) for x in (short, mid, long))
    print(f"caja: dura {ls:.3f} s / {lm:.3f} s / {ll:.3f} s con caída 0 / 50 / 100")
    assert ls < 0.6 * lm and ll > 2.5 * lm          # la cola fija de 50 ms queda

    dark, _ = _hit(eng, tmp_path, HAT, _lanes(**{str(HAT): (50, 50, 0, 50)}))
    bright, _ = _hit(eng, tmp_path, HAT, _lanes(**{str(HAT): (50, 50, 100, 50)}))
    plain, _ = _hit(eng, tmp_path, HAT)
    c = [_centroid(x[: int(0.05 * sr)], sr) for x in (dark, plain, bright)]
    print("charles, centroide (Hz) con tono 0 / 50 / 100:", [round(v) for v in c])
    assert c[0] < c[1] < c[2]

    loud, _ = _hit(eng, tmp_path, KICK, _lanes(**{str(KICK): (50, 50, 50, 100)}), vol=20)
    soft, _ = _hit(eng, tmp_path, KICK, vol=20)
    mute, _ = _hit(eng, tmp_path, KICK, _lanes(**{str(KICK): (50, 50, 50, 0)}), vol=20)
    gain_db = 20 * np.log10(np.abs(loud).max() / np.abs(soft).max())
    print(f"nivel 100: {gain_db:+.1f} dB; nivel 0: pico {np.abs(mute).max():.6f}")
    assert gain_db == pytest.approx(12.0, abs=0.6) and np.abs(mute).max() < 1e-6

    # El pad se escucha con sus ajustes al pulsarlo (motor de previsualización)
    assert eng.audition_synth(36 + KICK, 0.0, mode=1, vol=40.0, lanes=_lanes(**{str(KICK): (20, 80, 70, 60)}))
    eng.preview_stop()


def test_ajustes_desde_la_pista():
    s = synth_settings({"type": "drum", "cfg": {"vol": 70, "lanes": [[60, None, 40], None, [50, 50, 50, 0]]}})
    # cada pad lleva además paneo (50 = centro) y grupo de corte (0 = ninguno) del Drum Rack
    assert s["lanes"] == [[60.0, 50.0, 40.0, 50.0, 50.0, 0.0], [50.0] * 5 + [0.0], [50.0, 50.0, 50.0, 0.0, 50.0, 0.0]]
    assert synth_settings({"type": "drum", "cfg": {}})["lanes"] == []


def test_hiphop_completo_con_su_bateria_ajustada(host, tmp_path):
    """Un hip hop entero (bajo, piano, voz) con la batería del motor: el bombo afinado una quinta
    abajo y largo, la caja más oscura. La mezcla no satura y cada ajuste se mide en su pad."""
    from song_factory import write_song
    song = write_song("hiphop", tmp_path / "hiphop")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    others = [eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]
              if not any(Path(p).stem.endswith(s) for s in ("_kick", "_snare", "_hats", "_drums", "_clap"))]
    tid = eng.add_synth_track("Batería", 1)["id"]
    tuned = _lanes(**{str(KICK): (50 - 50 * 7 / 12, 85, 60, 60), str(SNARE): (50, 60, 25, 50)})
    eng.set_synth_settings(tid, mode=1, vol=70, tun=50, lanes=tuned)
    bars = int(g.seconds * g.bpm / 60 // 4)
    notes = []
    for b in range(bars):
        for beat in range(4):
            t = b * 4.0 + beat
            notes.append((t, 0.25, 36 + (KICK if beat % 2 == 0 else SNARE), 100))
            notes.append((t + 0.5, 0.25, 36 + HAT, 80))
    eng.set_synth_midi(tid, notes, bars * 4.0)
    assert eng.render_to_wav(str(tmp_path / "mix.wav"))
    y, sr = sf.read(str(tmp_path / "mix.wav"))
    assert 0.05 < np.abs(y).max() <= 1.0

    for o in others:
        eng.set_track_mute(o, True)
    assert eng.render_to_wav(str(tmp_path / "drums.wav"))
    d, sr = sf.read(str(tmp_path / "drums.wav"))
    d = d[:, 0]
    beat = 60 / g.bpm
    eng.set_synth_settings(tid, mode=1, vol=70, tun=50, lanes=[])
    assert eng.render_to_wav(str(tmp_path / "plain.wav"))
    p, _ = sf.read(str(tmp_path / "plain.wav"))
    p = p[:, 0]
    ratios, darker = [], []
    for b in range(bars):
        k0 = int(b * 4 * beat * sr)
        w = slice(k0 + int(0.15 * sr), k0 + int(min(0.40, 0.95 * beat) * sr))
        ratios.append(_peak_hz(d[w], sr, 25, 120) / _peak_hz(p[w], sr, 25, 120))
        s0 = int((b * 4 + 1) * beat * sr)
        darker.append(_centroid(d[s0: s0 + int(0.04 * sr)], sr) < _centroid(p[s0: s0 + int(0.04 * sr)], sr))
    print(f"{bars} compases: bombo × {np.median(ratios):.3f} (quinta abajo = 0,667); caja más oscura en {sum(darker)}/{bars}")
    assert all(r == pytest.approx(2 ** (-7 / 12), rel=0.06) for r in ratios)
    assert all(darker)
