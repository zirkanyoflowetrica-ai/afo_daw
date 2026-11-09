"""Biblioteca nativa de efectos (Hito 1), dispositivo de audio y grabación: medidas reales del motor.

Cada efecto se comprueba con un render offline de Tracktion y una medida objetiva (nivel, retardo,
RT60, armónicos...), como pide el criterio de aceptación de docs/BIBLIOTECA_NATIVA.md.
"""
import sys

import numpy as np
import pytest
import soundfile as sf

from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000


@pytest.fixture()
def host():
    h = EngineHost.create()
    assert h.ok, h.error
    yield h
    h.engine = None


def db(x):
    return 20 * np.log10(max(1e-9, float(x)))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def sine(hz=440.0, amp_db=-12.0, seconds=2.0):
    t = np.arange(int(seconds * SR)) / SR
    return 10 ** (amp_db / 20) * np.sin(2 * np.pi * hz * t)


def tone(tmp_path, hz=440.0, amp_db=-12.0, seconds=2.0, name="tono.wav"):
    y = sine(hz, amp_db, seconds)
    p = tmp_path / name
    sf.write(str(p), np.stack([y, y], 1), SR, subtype="FLOAT")
    return str(p)


def click(tmp_path, at=0.5, seconds=3.0, name="click.wav"):
    y = np.zeros(int(seconds * SR))
    y[int(at * SR)] = 0.8
    p = tmp_path / name
    sf.write(str(p), np.stack([y, y], 1), SR, subtype="FLOAT")
    return str(p)


def render(eng, tmp_path, name="out.wav"):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert sr == SR
    return y


def mid(y):                     # zona estable de un tono de 2 s (sin el arranque de los detectores)
    return y[int(0.8 * SR): int(1.8 * SR)]


def with_fx(eng, path, key, **params):
    tid = eng.add_audio_track(path, "src")["id"]
    fx = eng.add_effect(tid, key)
    for k, v in params.items():
        assert eng.set_effect_param(fx["id"], k, float(v)), k
    return tid, fx["id"]


def test_catalogo():
    cat = afo_audio.effect_catalog()
    keys = [c["key"] for c in cat]
    assert keys == ["gain", "strip", "eq", "compressor", "gate", "deesser", "saturator", "delay", "space", "analyzer"]
    assert {c["af"] for c in cat} == {"AF-01", "AF-02", "AF-07", "AF-13", "AF-18", "AF-20", "AF-26", "AF-41", "AF-35", "AF-76"}
    for c in cat:
        assert c["params"], c["key"]
        for p in c["params"]:
            assert p["min"] <= p["def"] <= p["max"], (c["key"], p["id"])
            if p["choices"]:
                assert len(p["choices"]) == int(p["max"] - p["min"]) + 1, (c["key"], p["id"])


def test_gain_polaridad_y_pan(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path), "gain", input=6)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-12 - 3.01 + 6, abs=0.1)
    eng.set_effect_param(fx, "input", 0)
    eng.set_effect_param(fx, "pan", 100)                 # todo a la derecha: L en silencio, R intacto
    y = render(eng, tmp_path)
    assert rms(mid(y[:, 0])) < 1e-4
    assert db(rms(mid(y[:, 1]))) == pytest.approx(-15.01, abs=0.1)
    eng.set_effect_param(fx, "pan", 0)
    ref = render(eng, tmp_path, "ref.wav")[:, 0]
    eng.set_effect_param(fx, "polarity", 1)
    y = render(eng, tmp_path)[:, 0]
    seg = slice(int(SR), int(SR) + 2000)
    assert np.abs(ref[seg]).max() > 0.1
    assert np.allclose(y[seg], -ref[seg], atol=1e-4)


def test_eq_campana_paso_alto_y_curva(host, tmp_path):
    eng = host.engine
    # −24 dBFS: con +12 dB el pico queda bajo el techo del limitador del master (−1 dBFS)
    tid, fx = with_fx(eng, tone(tmp_path, amp_db=-24), "eq", mid1Freq=440, mid1Gain=12, mid1Q=1)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-27.01 + 12, abs=0.2)
    curve = eng.effect_meters(fx)[2:]                    # [entrada, salida, curva de 64 puntos]
    assert len(curve) == 64
    k = int(round(63 * np.log10(440 / 20) / 3))
    assert curve[k] == pytest.approx(12, abs=1.0)
    assert abs(curve[0]) < 0.5 and abs(curve[-1]) < 0.5
    eng.set_effect_param(fx, "mid1Gain", 0)
    eng.set_effect_param(fx, "hpf", 1000)
    eng.set_effect_param(fx, "hpfSlope", 1)              # 24 dB/oct: 440 Hz cae más de 20 dB
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) < -27 - 20


def test_compresor_ratio_y_reduccion(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path), "compressor", threshold=-24, ratio=4, knee=0, attack=1, release=50)
    y = render(eng, tmp_path)
    # Pico −12 dBFS, umbral −24, 4:1 → la salida queda en −24 + 12/4 = −21 dBFS de pico
    assert db(np.abs(mid(y[:, 0])).max()) == pytest.approx(-21, abs=0.5)
    gr = eng.effect_meters(fx)[2]
    assert gr == pytest.approx(-9, abs=1.0)
    eng.set_effect_param(fx, "mix", 0)                   # paralelo al 0 %: sin cambio
    y = render(eng, tmp_path)
    assert db(np.abs(mid(y[:, 0])).max()) == pytest.approx(-12, abs=0.05)


def test_gate_cierra_bajo_el_umbral(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path), "gate", threshold=-6, range=-60)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) < -15 - 55
    eng.set_effect_param(fx, "threshold", -30)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-15.01, abs=0.1)


def test_saturador_armonicos_y_mezcla_en_fase(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path, hz=500), "saturator", drive=24, character=0, bias=0)
    y = mid(render(eng, tmp_path)[:, 0])
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    f = np.fft.rfftfreq(len(y), 1 / SR)
    h1 = spec[np.argmin(abs(f - 500))]
    h3 = spec[np.argmin(abs(f - 1500))]
    assert db(h3 / h1) > -30                              # el tanh añade tercer armónico
    alias = spec[(f > 3000) & (f < 20000) & (np.abs((f / 500) - np.round(f / 500)) > 0.1)].max()
    assert db(alias / h1) < -70                           # el sobremuestreo ×4 mantiene bajo el aliasing
    # Mezcla 0 %: la señal seca va retrasada lo mismo que la procesada y Tracktion compensa esa
    # latencia, así que el resultado coincide con la pista sin el efecto
    eng.set_effect_param(fx, "mix", 0)
    out = render(eng, tmp_path)[:, 0]
    assert eng.effects(tid)[0]["latency_seconds"] > 0
    eng.remove_effect(fx)
    ref = render(eng, tmp_path, "ref.wav")[:, 0]
    assert np.abs(out[SR: 2 * SR - 4800] - ref[SR: 2 * SR - 4800]).max() < 2e-3


def test_sin_subnormales_tras_un_impulso(host, tmp_path):
    # Las colas de los IIR caen a números subnormales; sin ScopedNoDenormals el render se atasca
    eng = host.engine
    tid, fx = with_fx(eng, click(tmp_path, seconds=1), "saturator", drive=0, mix=100)
    eng.add_effect(tid, "space")
    import time
    t0 = time.perf_counter()
    render(eng, tmp_path)
    assert time.perf_counter() - t0 < 20


def test_delay_tiempo_libre_y_sincronizado(host, tmp_path):
    eng = host.engine
    eng.set_tempo(120.0)
    tid, fx = with_fx(eng, click(tmp_path), "delay", sync=0, time=250, feedback=0, mix=50, hp=20, lp=20000)
    y = render(eng, tmp_path)[:, 0]
    peaks = np.argsort(np.abs(y))[-2:]
    assert sorted(peaks / SR) == pytest.approx([0.5, 0.75], abs=0.002)
    eng.set_effect_param(fx, "sync", 2)                   # negra a 120 BPM = 0,5 s
    y = render(eng, tmp_path)[:, 0]
    echo = np.argmax(np.abs(y[int(0.6 * SR):])) / SR + 0.6
    assert echo == pytest.approx(1.0, abs=0.003)


def test_reverb_rt60(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, click(tmp_path, seconds=6), "space", decay=2.0, mix=100, predelay=0, early=0, lowcut=20, damping=20000)
    y = render(eng, tmp_path)[:, 0]
    tail = y[int(0.5 * SR):]
    edc = np.cumsum(tail[::-1] ** 2)[::-1]                # integral de Schroeder
    edc_db = 10 * np.log10(edc / edc[0] + 1e-20)
    t5, t25 = np.argmax(edc_db < -5) / SR, np.argmax(edc_db < -25) / SR
    rt60 = 3 * (t25 - t5)
    assert rt60 == pytest.approx(2.0, rel=0.25)


def test_analizador_ve_el_tono_sin_tocar_el_audio(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path), "analyzer", averaging=0, slope=0)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-15.01, abs=0.05)
    spec = eng.effect_meters(fx)[2:]
    b = int(np.argmax(spec))
    lo, hi = 20 * 1000 ** (b / 64), 20 * 1000 ** ((b + 1) / 64)
    assert lo <= 440 <= hi
    assert spec[b] == pytest.approx(-12, abs=3)


def test_channel_strip_comprime(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path), "strip", compThr=-30, ratio=4)
    y = render(eng, tmp_path)
    assert db(np.abs(mid(y[:, 0])).max()) == pytest.approx(-30 + 18 / 4, abs=1.0)
    assert eng.effect_meters(fx)[2] < -10


def test_cadena_orden_bypass_y_master(host, tmp_path):
    eng = host.engine
    tid = eng.add_audio_track(tone(tmp_path), "src")["id"]
    a = eng.add_effect(tid, "gain")["id"]
    b = eng.add_effect(tid, "eq")["id"]
    c = eng.add_effect(tid, "delay", 0)["id"]             # al principio de la cadena
    assert [e["id"] for e in eng.effects(tid)] == [c, a, b]
    assert eng.move_effect(c, 2)
    assert [e["id"] for e in eng.effects(tid)] == [a, b, c]
    assert eng.remove_effect(c) and eng.remove_effect(b)
    eng.set_effect_param(a, "input", -6)
    eng.set_effect_enabled(a, False)                      # bypass: como si no estuviera
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-15.01, abs=0.05)
    assert eng.effects(tid)[0]["enabled"] is False
    m = eng.add_effect(0, "gain")["id"]                   # inserción en el master
    eng.set_effect_param(m, "input", -6)
    y = render(eng, tmp_path)
    assert db(rms(mid(y[:, 0]))) == pytest.approx(-21.01, abs=0.1)
    assert eng.effects(0)[0]["key"] == "gain"
    assert eng.remove_track(tid)
    assert eng.effects(0) and not any(e["track_id"] == tid for e in eng.effects(0))


def test_dispositivo_y_drivers(host):
    eng = host.engine
    info = eng.device_info()
    if sys.platform == "win32":
        assert "ASIO" in info["available_types"]          # compilado con el SDK de Steinberg
    if not info["open"]:
        pytest.skip("sin dispositivo de audio abierto")
    # Un driver que no abre no deja la aplicación sin audio: se vuelve al anterior
    err = eng.set_audio_device("ASIO", "No existe este driver", "", 0, 0)
    assert err and eng.device_info()["open"] and eng.device_info()["output"] == info["output"]
    o = eng.audio_device_options("")
    assert o["type"] == info["type"] and o["outputs"]
    assert info["sample_rate"] in o["sample_rates"] and info["buffer_size"] in o["buffer_sizes"]
    assert eng.set_audio_device(info["type"], info["output"], info["input"], info["sample_rate"], info["buffer_size"]) == ""
    after = eng.device_info()
    assert after["open"] and after["output"] == info["output"]


def test_grabacion_real(host, tmp_path):
    eng = host.engine
    before = eng.device_info()
    try:
        if not eng.record_inputs():
            # El dispositivo actual no tiene entradas: se prueba con otro driver que sí (ASIO4ALL, DirectSound…),
            # como haría el usuario en «Audio», y al final se vuelve al de antes.
            for kind in ("ASIO", "DirectSound"):
                o = eng.audio_device_options(kind)
                if o["inputs"] and o["outputs"]:
                    eng.set_audio_device(kind, o["outputs"][0], o["inputs"][0], 0, 0)
                    if eng.device_info()["open"] and eng.record_inputs():
                        break
        if not eng.device_info()["open"] or not eng.record_inputs():
            pytest.skip("sin entrada de audio")
        afo_audio.pump_messages(400)                 # el driver termina de arrancar (ASIO4ALL pide un reinicio)
        tid = eng.add_record_track("Voz 1")["id"]
        assert eng.arm_track(tid, "", False) == ""
        assert eng.record_state()["armed_track"] == tid
        assert eng.start_recording() == ""
        afo_audio.pump_messages(1500)
        st = eng.record_state()
        assert st["recording"] and st["seconds"] > 1.0
        info = eng.stop_recording(False)
        assert info["source_path"] and info["length_seconds"] == pytest.approx(st["seconds"], abs=0.5)
        y, sr = sf.read(info["source_path"])
        assert len(y) / sr == pytest.approx(info["length_seconds"], abs=0.1)
        eng.disarm()
        assert eng.record_state()["armed_track"] == 0
    finally:
        now = eng.device_info()
        if before["open"] and (now["type"], now["output"]) != (before["type"], before["output"]):
            assert eng.set_audio_device(before["type"], before["output"], before["input"],
                                        before["sample_rate"], before["buffer_size"]) == ""


def test_automatizacion_sigue_la_curva_en_el_render(host, tmp_path):
    eng = host.engine
    tid, fx = with_fx(eng, tone(tmp_path, amp_db=-18, seconds=4.0), "gain")
    assert eng.set_effect_automation(fx, "output", [(0.0, -24.0), (2.0, -24.0), (2.0001, 0.0), (4.0, 0.0)])
    assert [round(t, 3) for t, _ in eng.effect_automation(fx, "output")] == [0.0, 2.0, 2.0, 4.0]
    assert eng.effect_info(fx)["automated"] == ["output"]
    y = render(eng, tmp_path)[:, 0]
    early, late = db(rms(y[int(0.5 * SR): int(1.5 * SR)])), db(rms(y[int(2.5 * SR): int(3.5 * SR)]))
    assert early == pytest.approx(-18 - 3.01 - 24, abs=0.5)   # RMS de un seno = pico − 3 dB
    assert late == pytest.approx(-18 - 3.01, abs=0.5)
    # Sin curva el parámetro vuelve a su valor fijo
    assert eng.set_effect_automation(fx, "output", [])
    assert eng.effect_info(fx)["automated"] == []
    y = render(eng, tmp_path, "out2.wav")[:, 0]
    assert db(rms(y[int(0.5 * SR): int(1.5 * SR)])) == pytest.approx(-21.01, abs=0.5)


def test_audio_de_un_proyecto_en_pista_de_voz(host, tmp_path):
    eng = host.engine
    tid = eng.add_record_track("Voz 1")["id"]
    info = eng.set_track_audio(tid, tone(tmp_path, amp_db=-18, seconds=1.0), 1.5)
    assert info["start_seconds"] == pytest.approx(1.5) and info["length_seconds"] == pytest.approx(1.0, abs=0.01)
    y = render(eng, tmp_path)[:, 0]
    assert db(np.abs(y[: int(1.4 * SR)]).max()) < -80                 # silencio antes de la toma
    assert db(np.abs(y[int(1.6 * SR): int(2.4 * SR)]).max()) == pytest.approx(-18, abs=0.5)


def test_deesser_baja_solo_la_sibilancia(host, tmp_path):
    """AF-20: un tono en la banda vigilada baja hasta el rango; uno grave queda intacto."""
    eng = host.engine
    hi = eng.add_audio_track(tone(tmp_path, 6000, -12, 2.0, "hi.wav"), "hi")["id"]
    fx = eng.add_effect(hi, "deesser")["id"]
    for k, v in (("freq", 6000), ("threshold", -30), ("range", -6)):
        eng.set_effect_param(fx, k, v)
    y = render(eng, tmp_path, "hi_out.wav")[SR:2 * SR, 0]
    assert db(rms(y)) == pytest.approx(-12 - 3.01 - 6, abs=0.5)
    assert eng.effect_meters(fx)[2] < -5
    eng.remove_track(hi)
    lo = eng.add_audio_track(tone(tmp_path, 500, -12, 2.0, "lo.wav"), "lo")["id"]
    fx = eng.add_effect(lo, "deesser")["id"]
    eng.set_effect_param(fx, "threshold", -30)
    y = render(eng, tmp_path, "lo_out.wav")[SR:2 * SR, 0]
    assert db(rms(y)) == pytest.approx(-12 - 3.01, abs=0.2)


def test_antes_y_despues_de_la_cadena(host, tmp_path):
    """chain_scope: nivel a la entrada del primer efecto activo y a la salida del último."""
    eng = host.engine
    tid = eng.add_audio_track(tone(tmp_path, 440, -12, 2.0), "t")["id"]
    assert eng.chain_scope(tid, 32)["active"] == 0
    g = eng.add_effect(tid, "gain")["id"]
    eng.set_effect_param(g, "output", -6.0)
    eng.add_effect(tid, "analyzer")
    render(eng, tmp_path)
    c = eng.chain_scope(tid, 32)
    assert c["active"] == 2 and len(c["pre"]) == 32 and len(c["post"]) == 32
    assert c["pre_db"] > -20 and c["post_db"] - c["pre_db"] == pytest.approx(-6, abs=0.3)
    assert max(c["pre"]) - max(c["post"]) == pytest.approx(6, abs=1.0)


def test_sonoridad_lufs_rms_sin_archivos(host, tmp_path):
    """measure_mix: LUFS integrada como pyloudnorm (BS.1770), RMS y pico, sin escribir archivos."""
    import pyloudnorm as pyln
    eng = host.engine
    t = np.arange(int(30 * SR)) / SR
    y = 0.1 * np.sin(2 * np.pi * 1000 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.5 * t)) / 1.5
    p = tmp_path / "mod.wav"
    sf.write(str(p), np.stack([y, y], 1), SR, subtype="FLOAT")
    tid = eng.add_audio_track(str(p), "m")["id"]
    before = set(tmp_path.iterdir())
    m = eng.measure_mix()
    assert m["ok"] and m["seconds"] > 29
    assert set(tmp_path.iterdir()) == before                       # nada escrito
    ref = pyln.Meter(SR).integrated_loudness(np.stack([y, y], 1))
    for d in (m["master"], m["tracks"][tid]):
        assert d["lufs_i"] == pytest.approx(ref, abs=0.3), (d, ref)
        assert d["max_peak_db"] == pytest.approx(db(np.max(np.abs(y))), abs=0.2)
    lv = eng.read_levels()
    assert set(lv["master_loud"]) == {"peak_db", "max_peak_db", "rms_db", "lufs_m", "lufs_s", "lufs_i"}
    assert tid in lv["loud"]
