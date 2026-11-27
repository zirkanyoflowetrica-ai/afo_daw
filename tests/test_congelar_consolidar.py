"""G5: consolidar y congelar pistas en canciones completas (tests/song_factory.py).
Consolidar: los clips editados (cortes, huecos, ganancia, fundidos) pasan a un solo archivo y la exportación
suena igual que antes; los efectos siguen en la cadena. Congelar: el audio congelado es la pista con su
instrumento y efectos, la pista no se puede editar hasta descongelarla y el fader sigue vivo."""
import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine.stop()
    h.engine = None


def _song(h, tmp_path, genre):
    from song_factory import write_song
    ids = {}
    for p in write_song(genre, tmp_path / genre)["paths"]:
        name = Path(p).stem.split("_", 1)[1]
        ids[name] = (h.add_audio(p, name)["id"], p)
    return ids


def _solo(eng, keep, tmp_path, name):
    for t in eng.tracks():
        eng.set_track_mute(t["id"], t["id"] != keep)
    out = tmp_path / f"{name}.wav"
    assert eng.render_to_wav(str(out))
    x, sr = sf.read(str(out), always_2d=True)
    return x.mean(axis=1), sr


def _rms_db(x):
    return 10 * np.log10(np.mean(x ** 2) + 1e-20)


def _best_corr(a, b, max_lag=400):
    """Correlación normalizada máxima entre a y b desplazando b hasta ±max_lag muestras (el render empieza
    con un salto de bloque: el congelado puede salir unas muestras corrido)."""
    n = min(len(a), len(b)) - 2 * max_lag
    x = a[max_lag:max_lag + n]
    best = (-1.0, 0)
    for lag in range(-max_lag, max_lag + 1, 1):
        y = b[max_lag + lag:max_lag + lag + n]
        c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-20))
        if c > best[0]:
            best = (c, lag)
    return best


def _read_freeze(path):
    """El audio congelado de Tracktion (.freeze): cabecera de 512 bytes (marca, tamaño, frecuencia,
    muestras, canales) y muestras float32 intercaladas."""
    raw = Path(path).read_bytes()
    head = np.frombuffer(raw[:12], "<i4")
    n = int(np.frombuffer(raw[12:20], "<i8")[0])
    ch = int(np.frombuffer(raw[20:22], "<i2")[0])
    x = np.frombuffer(raw[int(head[1]):int(head[1]) + n * ch * 4], "<f4").reshape(n, ch)
    return x, int(head[2])


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def test_consolidar_deja_un_audio_que_suena_igual(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "rock")
    bass, path = ids["Bajo"]
    before_md5 = _md5(path)
    eq = eng.add_effect(bass, "eq", -1)
    clips = [
        {"start": 0.0, "length": 2.0, "offset": 0.0, "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0},
        {"start": 3.0, "length": 3.0, "offset": 2.0, "gain_db": -6.0, "fade_in": 0.2, "fade_out": 0.5},
        {"start": 7.0, "length": 2.5, "offset": 6.0, "gain_db": 3.0, "fade_in": 0.0, "fade_out": 0.3},
    ]
    eng.set_clips(bass, clips)
    a, sr = _solo(eng, bass, tmp_path, "antes")
    info = host.engine.consolidate_track(bass, str(tmp_path / "Bajo_consolidado.wav"))
    assert info["source_path"].endswith("Bajo_consolidado.wav") and Path(info["source_path"]).is_file()
    now = eng.clips(bass)
    assert len(now) == 1 and abs(now[0]["start"]) < 1e-6 and abs(now[0]["length"] - 9.5) < 0.05, now
    assert [e["id"] for e in eng.effects(bass)] == [eq["id"]]          # los efectos siguen en vivo
    assert _md5(path) == before_md5                                    # el original no se toca
    b, _ = _solo(eng, bass, tmp_path, "despues")
    n = min(len(a), len(b))
    corr, lag = _best_corr(a[:n], b[:n], 64)
    assert corr > 0.999 and abs(lag) <= 4, (corr, lag)               # ≤ 4 muestras (< 0,1 ms) del remuestreo
    assert abs(_rms_db(a[:n]) - _rms_db(b[:n])) < 0.1
    # el hueco entre clips (2–3 s) sigue en silencio y el corte con −6 dB sigue más bajo
    seg = lambda x, t0, t1: x[int(t0 * sr):int(t1 * sr)]
    assert _rms_db(seg(b, 2.05, 2.95)) < -80
    # un clip de una pista sin audio no se consolida
    aux = eng.add_aux_track("Bus")
    with pytest.raises(RuntimeError, match="clips de audio"):
        eng.consolidate_track(aux["id"], str(tmp_path / "x.wav"))


def test_congelar_suena_con_sus_efectos_y_bloquea_la_edicion(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "trap")
    t808 = ids["808"][0]
    g = eng.add_effect(t808, "gain", -1)
    assert eng.set_effect_param(g["id"], "input", -12)
    eng.add_effect(t808, "eq", -1)
    with_fx, sr = _solo(eng, t808, tmp_path, "con_fx")
    eng.set_effect_enabled(g["id"], False)
    no_fx, _ = _solo(eng, t808, tmp_path, "sin_fx")
    eng.set_effect_enabled(g["id"], True)
    assert _rms_db(no_fx) - _rms_db(with_fx) > 10

    assert eng.freeze_track(t808, True) == ""
    assert eng.track_frozen(t808)
    assert next(t for t in eng.tracks() if t["id"] == t808)["frozen"]
    f = eng.frozen_file(t808)
    assert f and Path(f).is_file()
    z, zsr = _read_freeze(f)
    assert zsr == sr
    z = z.mean(axis=1)
    n = min(len(z), len(with_fx))
    corr, lag = _best_corr(with_fx[:n], z[:n])
    assert corr > 0.99, (corr, lag)                                   # lo congelado es la pista con sus efectos
    assert abs(_rms_db(z[:n]) - _rms_db(with_fx[:n])) < 1.0

    with pytest.raises(RuntimeError, match="congelada"):
        eng.set_effect_param(g["id"], "input", 0)
    with pytest.raises(RuntimeError, match="congelada"):
        eng.add_effect(t808, "compressor", -1)
    with pytest.raises(RuntimeError, match="congelada"):
        eng.set_clips(t808, eng.clips(t808))
    with pytest.raises(RuntimeError, match="congelada"):
        eng.consolidate_track(t808, str(tmp_path / "y.wav"))
    eng.set_track_gain_db(t808, -3.0)                                   # el fader sigue vivo
    eng.set_track_gain_db(t808, 0.0)
    again, _ = _solo(eng, t808, tmp_path, "congelada")                  # exportar no cambia
    m = min(len(again), len(with_fx))
    assert abs(_rms_db(again[:m]) - _rms_db(with_fx[:m])) < 0.1

    assert eng.freeze_track(t808, False) == ""
    assert not eng.track_frozen(t808) and eng.frozen_file(t808) == "" and not Path(f).exists()
    assert eng.set_effect_param(g["id"], "input", 0)                    # se vuelve a editar
    assert eng.effect_info(g["id"])["enabled"]
    assert [e["key"] for e in eng.effects(t808)] == ["gain", "eq"]       # el punto de congelación no queda


def test_congelar_un_instrumento_y_errores_claros(host, tmp_path):
    eng = host.engine
    _song(host, tmp_path, "lofi")
    inst = eng.add_synth_track("Teclas", 0)
    notes = [(b * 1.0, 0.9, 60 + (b % 4) * 3, 100) for b in range(16)]
    eng.set_synth_midi(inst["id"], notes, 16.0)
    assert eng.freeze_track(inst["id"], True) == ""
    z, _ = _read_freeze(eng.frozen_file(inst["id"]))
    assert _rms_db(z) > -50                                              # el sintetizador quedó en el audio
    with pytest.raises(RuntimeError, match="congelada"):
        eng.set_synth_midi(inst["id"], notes[:4], 4.0)
    assert eng.freeze_track(inst["id"], True) == ""                     # ya lo está: nada que hacer
    assert eng.freeze_track(inst["id"], False) == ""
    aux = eng.add_aux_track("Bus")
    assert "nada que congelar" in eng.freeze_track(aux["id"], True)
