"""G3: grabación multipista, punch in/out con el tramo del bucle y tomas por pasada.

Cada pasada es una toma entera de la pista (un archivo): sobre el audio de antes si lo había, así el
punch conserva lo de fuera y las tomas se eligen como las de F4 (cambiando el archivo de la pista).

Graba el motor de verdad desde la entrada del dispositivo (si no hay entrada, se salta) mientras suena
una canción completa (tests/song_factory.py), como al grabar voces encima de una base.
"""
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
    if not h.engine.device_info()["open"]:
        pytest.skip("sin dispositivo de audio")
    eng = h.engine
    before = eng.device_info()
    for _ in range(40):                                   # las entradas aparecen cuando el driver termina de arrancar
        afo_audio.pump_messages(100)
        if eng.record_inputs():
            break
    if not eng.record_inputs():                           # como en «Audio»: otro driver que sí tenga entradas
        for kind in ("ASIO", "DirectSound"):
            o = eng.audio_device_options(kind)
            if o["inputs"] and o["outputs"]:
                eng.set_audio_device(kind, o["outputs"][0], o["inputs"][0], 0, 0)
                afo_audio.pump_messages(400)
                if eng.device_info()["open"] and eng.record_inputs():
                    break
    if not eng.device_info()["open"] or not eng.record_inputs():
        pytest.skip("el dispositivo no tiene entradas")
    afo_audio.pump_messages(400)
    yield h
    now = eng.device_info()
    if before["open"] and (now["type"], now["output"]) != (before["type"], before["output"]):
        eng.set_audio_device(before["type"], before["output"], before["input"], before["sample_rate"], before["buffer_size"])
    h.engine.set_punch(False)
    h.engine.set_loop(False, 0, 0)
    h.engine.stop()
    h.engine = None


def _song(eng, tmp_path, genre="rock"):
    from song_factory import write_song
    paths = write_song(genre, tmp_path / genre)["paths"]
    for p in paths:
        eng.add_audio_track(p, Path(p).stem.rsplit("_", 1)[-1])
    return paths


def _record(eng, seconds, start=0.0):
    eng.set_position_seconds(start)
    assert eng.start_recording() == ""
    for _ in range(100):                                  # que el transporte arranque
        afo_audio.pump_messages(20)
        if eng.position_seconds() > start + 0.05:
            break
    afo_audio.pump_messages(int(seconds * 1000))


def test_dos_pistas_graban_en_la_misma_pasada(host, tmp_path):
    eng = host.engine
    _song(eng, tmp_path)
    a = host.add_record_track("Voz principal")["id"]
    b = host.add_record_track("Coros")["id"]
    assert eng.arm_track(a, "", False) == ""
    assert eng.arm_track(b, "", False, True) == ""
    assert sorted(eng.armed_tracks()) == sorted([a, b]) and eng.record_state()["armed_track"] == a
    _record(eng, 1.5)
    infos = {i["id"]: i for i in host.finish_takes()}
    assert set(infos) == {a, b}
    for i in infos.values():
        assert i["source_path"] and Path(i["source_path"]).is_file(), i
        assert 1.0 < i["length_seconds"] < 3.0
        assert i["takes"] == [i["source_path"]]               # pista vacía: la toma es la grabación
        assert i["previous"]["source"] == "" and len(i["clips"]) == 1
    assert infos[a]["source_path"] != infos[b]["source_path"]
    la, lb = (sf.info(infos[x]["source_path"]).duration for x in (a, b))
    assert la == pytest.approx(lb, abs=0.05)                   # la misma pasada: misma duración
    eng.unarm_track(b)
    assert eng.armed_tracks() == [a]
    eng.disarm()
    assert eng.armed_tracks() == []


def test_punch_graba_solo_en_el_tramo_y_conserva_el_resto(host, tmp_path):
    eng = host.engine
    paths = _song(eng, tmp_path, "balada")
    v = host.add_record_track("Voz")["id"]
    eng.set_track_audio(v, paths[-1], 0.0)                      # la voz que ya había (toda la canción)
    host.tracks[v].update(originalPath=paths[-1], source_path=paths[-1])
    before = eng.clips(v)
    assert len(before) == 1
    eng.set_loop(False, 2.0, 3.0)                               # tramo marcado, bucle apagado
    eng.set_punch(True)
    assert eng.punch()
    assert eng.arm_track(v, "", False) == ""
    _record(eng, 3.6, start=0.5)                                # pasa de largo por el tramo
    info = host.finish_takes()[0]
    assert info["previous"]["source"] == paths[-1] and len(info["takes"]) == 1
    toma = info["takes"][0]
    assert info["source_path"] == toma and toma.endswith("_toma.wav") and toma != paths[-1]
    clips = eng.clips(v)
    assert [(round(c["start"], 3), round(c["length"], 3)) for c in clips] == [(round(c["start"], 3), round(c["length"], 3)) for c in before]
    base, sr = sf.read(paths[-1], always_2d=True)
    new, sr2 = sf.read(toma, always_2d=True)
    assert sr2 == sr and new.shape[0] >= base.shape[0]
    fuera = slice(int(0.5 * sr), int(1.9 * sr))                  # antes del tramo: lo mismo (24 bits)
    assert np.max(np.abs(new[fuera, 0] - base[fuera, 0])) < 1e-3
    despues = slice(int(3.1 * sr), int(5.0 * sr))
    assert np.max(np.abs(new[despues, 0] - base[despues, 0])) < 1e-3
    dentro = slice(int(2.1 * sr), int(2.9 * sr))                 # dentro: la grabación, no lo de antes
    if np.sqrt(np.mean(base[dentro, 0] ** 2)) > 1e-3:
        assert np.max(np.abs(new[dentro, 0] - base[dentro, 0])) > 1e-3
    eng.disarm()


def test_cada_vuelta_del_bucle_es_una_toma(host, tmp_path):
    eng = host.engine
    _song(eng, tmp_path, "trap")
    v = host.add_record_track("Voz")["id"]
    eng.set_loop(True, 1.0, 2.0)
    eng.set_punch(True)
    assert eng.arm_track(v, "", False) == ""
    assert "Punch y bucle" in eng.start_recording()             # Tracktion no deja las dos cosas a la vez
    eng.set_punch(False)
    assert "2 s" in eng.start_recording()                       # ni un bucle de menos de 2 s
    eng.set_loop(True, 1.0, 3.2)
    _record(eng, 5.6, start=1.0)                                # dos vueltas y media
    info = host.finish_takes()[0]
    takes = info["takes"]
    assert len(takes) >= 2, takes
    assert all(Path(t).is_file() for t in takes) and len(set(takes)) == len(takes)
    assert info["source_path"] == takes[-1]                     # suena la última
    for t in takes[:2]:                                         # las vueltas enteras duran el tramo
        assert sf.info(t).duration >= 2.0
    clips = eng.clips(v)
    assert len(clips) == 1 and clips[0]["start"] == pytest.approx(1.0, abs=0.05)
    eng.set_clips(v, clips)                                     # editar clips no la aplana a otro archivo
    assert next(t for t in eng.tracks() if t["id"] == v)["source_path"] == takes[-1]
    eng.disarm()
