"""G1: metrónomo y bucle del transporte, sonando de verdad por el dispositivo.

El clic de Tracktion se suma a la salida (lo mide el medidor del master) y no entra en las
exportaciones; el bucle devuelve el cursor al principio del tramo mientras suena una canción
completa (tests/song_factory.py), no un tono suelto.
"""
import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")


@pytest.fixture()
def eng():
    h = EngineHost.create()
    assert h.ok, h.error
    if not h.engine.device_info()["open"]:
        pytest.skip("sin dispositivo de salida de audio")
    afo_audio.pump_messages(600)                 # el dispositivo termina de arrancar (si no, el primer play no avanza)
    yield h.engine
    h.engine.stop()
    h.engine = None


def _silence(tmp_path, seconds=12.0, sr=48000):
    p = tmp_path / "silencio.wav"
    sf.write(str(p), np.zeros((int(seconds * sr), 2), np.float32), sr, subtype="FLOAT")
    return str(p)


def _play_peak(eng, ms):
    """Reproduce `ms` milisegundos y devuelve el pico más alto que midió el master."""
    eng.read_levels()
    peak = -200.0
    eng.play()
    for _ in range(max(1, ms // 50)):
        afo_audio.pump_messages(50)
        lv = eng.read_levels()
        peak = max(peak, lv["master_l_db"], lv["master_r_db"])
    eng.pause()
    return peak


def test_metronomo_suena_solo_encendido(eng, tmp_path):
    eng.add_audio_track(_silence(tmp_path), "Silencio")
    eng.set_tempo(120)
    eng.set_position_seconds(0)
    assert _play_peak(eng, 1200) < -90                     # sin clic: silencio de verdad
    eng.set_click_volume(1.0)
    eng.set_click(True)
    eng.set_position_seconds(0)
    on = _play_peak(eng, 1200)                             # 120 BPM: 2–3 clics en 1,2 s
    eng.set_click(False)
    assert on > -40, on
    eng.set_position_seconds(0)
    assert _play_peak(eng, 800) < -90


def test_bucle_vuelve_al_principio(eng, tmp_path):
    from song_factory import write_song                       # canción completa (rock, con voces), no un tono
    for p in write_song("rock", tmp_path / "rock")["paths"]:
        eng.add_audio_track(p, p.rsplit("_", 1)[-1][:-4])
    eng.set_loop(True, 2.0, 3.0)
    assert eng.loop() == {"on": True, "start": pytest.approx(2.0), "end": pytest.approx(3.0)}
    eng.set_position_seconds(2.0)
    eng.play()
    for _ in range(100):                                   # el primer play con muchas pistas tarda en arrancar
        afo_audio.pump_messages(50)
        if eng.position_seconds() > 2.05:
            break
    seen = []
    for _ in range(50):                                    # 2,5 s: el tramo de 1 s pasa más de dos veces
        afo_audio.pump_messages(50)
        seen.append(eng.position_seconds())
    eng.pause()
    eng.set_loop(False, 0, 0)
    assert all(1.95 <= t <= 3.1 for t in seen), (min(seen), max(seen))
    jumps = sum(1 for a, b in zip(seen, seen[1:]) if b < a - 0.5)
    assert jumps >= 2, seen
