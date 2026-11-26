"""C31: el export sale en su sitio desde la primera muestra, con o sin efectos con latencia.

Tracktion arranca el render con un salto del cabezal y el primer bloque salía corrido (64 muestras sin
efectos) o, con un efecto con latencia (Limiter, Saturator, Tune, Spectral), desplazado o perdido si
el bloque del dispositivo no divide la latencia (480 con Windows Audio). El motor ahora empieza un
segundo antes, en silencio, y lo recorta. Queda un retraso fijo de 2 muestras del lector de clips de
Tracktion (interpolador Lagrange), igual para todo: aquí se mide que sea el mismo en toda la canción.
"""
import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000
POS = [0, 65, 300, 700, 1500, 3000, 6000, 24000]


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    d = h.engine.device_info()
    if d["sample_rate"] != SR:
        err = h.engine.set_audio_device(d["type"], d["output"], d["input"], float(SR), d["buffer_size"])
        if err:
            pytest.skip(f"el dispositivo de audio no abre a {SR} Hz: {err}")
    yield h
    h.engine = None


@pytest.mark.parametrize("key,params", [(None, {}), ("limiter", {}), ("saturator", {"drive": 0}),
                                        ("tune", {"mix": 0}), ("spectral", {"mode": 0, "amount": 0})])
def test_impulsos_en_su_sitio(host, tmp_path, key, params):
    eng = host.engine
    x = np.zeros(2 * SR)
    x[POS] = 0.5
    src = tmp_path / "imp.wav"
    sf.write(str(src), np.stack([x, x], 1), SR, subtype="FLOAT")
    tid = eng.add_audio_track(str(src), "imp")["id"]
    if key:
        fx = eng.add_effect(tid, key)["id"]
        for k, v in params.items():
            assert eng.set_effect_param(fx, k, float(v))
    out = tmp_path / "out.wav"
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert sr == SR and len(y) >= len(x)
    # El pico de cada impulso en las 50 muestras que lo siguen (el Saturator sobremuestrea y lo reparte)
    a = np.abs(y[:, 0])
    peaks = [(p + int(np.argmax(a[p: p + 50])), float(a[p: p + 50].max())) for p in POS]
    print(f"{key}: bloque {eng.device_info()['buffer_size']}, picos en {peaks}")
    assert all(v > 0.1 for _, v in peaks), peaks                      # ninguno perdido
    shift = {f - p for (f, _), p in zip(peaks, POS)}
    assert len(shift) == 1 and 0 <= shift.pop() <= 4, peaks           # el mismo retraso en toda la canción
    assert np.abs(y[POS[-1] + 2000:, 0]).max() < 0.1                  # y nada más (sin ecos ni duplicados)
    assert not (tmp_path / "out.afo-render.wav").exists()             # sin restos del render previo
