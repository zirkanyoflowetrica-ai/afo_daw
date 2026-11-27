"""G2: teclado MIDI (tocar y grabar en una pista de instrumento) y cuantizar.

La grabación la hace el motor (Tracktion, «All MIDI Ins»): se toca encima de una canción completa
(tests/song_factory.py), no sobre silencio, y las notas grabadas se cuantizan como en la interfaz.
"""
import pytest

from allforone import midi_edit
from allforone.engine_host import EngineHost, afo_audio


# --- funciones puras -----------------------------------------------------------------
def test_cuantizar_inicios_y_finales():
    notes = [[0.07, 0.4, 60, 90], [0.49, 0.2, 62, 80], [1.12, 0.3, 64, 100]]
    out, moved = midi_edit.quantize(notes, "1/4")
    assert [n[0] for n in out] == [0.0, 0.0, 1.0] and moved == 3
    assert [n[1] for n in out] == [0.4, 0.2, 0.3]              # sin «finales», la duración se conserva
    out, _ = midi_edit.quantize(notes, "1/16", ends=True)
    assert [(n[0], n[1]) for n in out] == [(0.0, 0.5), (0.5, 0.25), (1.0, 0.5)]
    half, _ = midi_edit.quantize([[0.1, 1, 60, 100]], "1/4", strength=50)
    assert half[0][0] == pytest.approx(0.05)
    same, moved = midi_edit.quantize([[0.5, 1, 60, 100]], "1/8")
    assert moved == 0 and same[0][0] == 0.5
    tres, _ = midi_edit.quantize([[0.3, 0.2, 60, 100]], "1/8T")
    assert tres[0][0] == pytest.approx(1 / 3, abs=1e-5)
    with pytest.raises(ValueError):
        midi_edit.quantize(notes, "1/7")


def test_toma_se_suma_sin_transposicion():
    track = {"type": "inst", "cfg": {"tr": 2}, "midi": [[0, 1, 60, 100]]}
    out = midi_edit.merge_take(track, [(0.5, 0.25, 64, 90)])
    assert out == [[0, 1, 60, 100], [0.5, 0.25, 62, 90]]          # sonó un Mi con +2: se guarda Re
    grid = {"type": "inst", "cfg": {}, "roll": {"12-0": 1}, "clips": [[0, 100]], "midi": None}
    notes = midi_edit.track_notes(grid)                          # la rejilla pasa a notas al grabar encima
    assert notes and all(n[2] == 60 and n[1] == 0.25 for n in notes)
    assert midi_edit.merge_take(grid, [])[0] == notes[0]


# --- el motor graba lo tocado --------------------------------------------------------
@pytest.fixture()
def eng():
    if afo_audio is None:
        pytest.skip("afo_audio no compilado")
    h = EngineHost.create()
    assert h.ok, h.error
    if not h.engine.device_info()["open"]:
        pytest.skip("sin dispositivo de salida de audio")
    afo_audio.pump_messages(600)
    yield h.engine
    h.engine.stop()
    h.engine = None


def _arm(eng, tid):
    err = eng.arm_midi(tid)
    for _ in range(20):                       # «All MIDI Ins» aparece al rehacer la lista de dispositivos
        if not err:
            return
        afo_audio.pump_messages(100)
        err = eng.arm_midi(tid)
    pytest.fail(err)


def test_grabar_notas_del_teclado_encima_de_una_cancion(eng, tmp_path):
    from song_factory import write_song
    song = write_song("balada", tmp_path / "balada")
    for p in song["paths"]:
        eng.add_audio_track(p, p.rsplit("_", 1)[-1][:-4])
    eng.set_tempo(120)
    tid = eng.add_synth_track("Teclas", 0)["id"]
    eng.set_synth_midi(tid, [(0.0, 1.0, 48, 100)], 0.0)           # lo que ya tenía la pista se queda
    _arm(eng, tid)
    assert eng.midi_armed() and eng.record_state()["input"] == "MIDI"
    assert isinstance(eng.midi_inputs(), list)

    eng.set_position_seconds(0)
    assert eng.start_recording() == ""
    for _ in range(100):                                          # que el transporte arranque de verdad
        afo_audio.pump_messages(20)
        if eng.position_seconds() > 0.05:
            break
    played = []
    for note in (60, 64, 67):
        t0 = eng.position_seconds()
        assert eng.midi_note(note, 100)
        afo_audio.pump_messages(250)
        assert eng.midi_note(note, 0)
        afo_audio.pump_messages(100)
        played.append((note, t0))
    eng.stop_recording(False)
    rec = eng.take_recorded_midi()
    eng.disarm()
    assert [n[2] for n in rec] == [60, 64, 67], rec
    for (note, t0), (start, length, n, vel) in zip(played, rec):
        assert start == pytest.approx(t0 * 2, abs=0.25)           # 120 BPM: 2 negras por segundo
        assert 0.25 < length < 1.0 and vel == 100
    assert eng.take_recorded_midi() == []                         # la toma sale del Edit una sola vez

    q, moved = midi_edit.quantize([list(n) for n in rec], "1/4")
    assert all(abs(n[0] - round(n[0])) < 1e-9 for n in q)
    merged = midi_edit.merge_take({"type": "inst", "cfg": {}, "midi": [[0.0, 1.0, 48, 100]]}, rec)
    assert len(merged) == 4 and merged[0][2] == 48


def test_teclado_sin_armar_no_toca(eng, tmp_path):
    from song_factory import write_song
    path = write_song("rock", tmp_path / "rock")["paths"][0]
    aid = eng.add_audio_track(path, "Audio")["id"]
    assert not eng.midi_armed()
    assert eng.midi_note(60, 100) is False                       # sin pista armada no suena nada
    assert "instrumento" in eng.arm_midi(aid)                     # una pista de audio no recibe MIDI
    assert not eng.midi_armed()
