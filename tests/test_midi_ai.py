"""Composición MIDI con IA (midi_ai.py): decodificación del vocabulario AMT, .mid de ida y vuelta,
reparto en pistas y notas con duración y velocidad propias en el sintetizador del motor."""
import json

import numpy as np
import pytest
import soundfile as sf

from allforone import midi_ai as m
from allforone.engine_host import EngineHost, afo_audio


def trio(t_s, d_s, pitch, prog):
    return [int(round(t_s * 100)), m.DUR_OFFSET + int(round(d_s * 100)), m.NOTE_OFFSET + prog * 128 + pitch]


def test_vocabulario_coincide_con_midi_llm():
    # AMT: SEPARATOR 55025 y AUTOREGRESS (el «BOS» de la música) 55026; 55 030 fichas tras las 128 256 de Llama
    assert (m.REST, m.CONTROL_OFFSET, m.SEPARATOR, m.AUTOREGRESS) == (27512, 27513, 55025, 55026)


def test_decodifica_tríos_y_descarta_basura():
    toks = trio(0.0, 0.5, 60, 0) + [5] + trio(0.5, 0.25, 36, m.DRUMS) + trio(0.0, 0.3, 60, 0) + [m.REST, 1]
    notes = m.decode(toks)
    assert notes == [(0.0, 0.5, 60, 0), (0.5, 0.25, 36, 128)]          # duplicada: queda la más larga
    # SEPARATOR: la sección siguiente empieza donde acabó la anterior
    sep = m.decode(trio(0, 1.0, 64, 0) + [m.SEPARATOR] * 3 + trio(0, 0.5, 67, 0))
    assert sep[1][0] == pytest.approx(1.0)


def test_pistas_por_instrumento_y_batería_a_carriles():
    notes = [(0.0, 1.0, 60, 0), (0.5, 0.5, 40, 33), (0.0, 0.1, 36, 128), (0.25, 0.1, 42, 128), (1.0, 0.1, 49, 128)]
    tracks = m.split_tracks(notes, 120)
    kinds = [(t["type"], t.get("voice")) for t in tracks]
    assert kinds == [("inst", m.PIANO), ("inst", m.BASS), ("drum", None)]   # batería al final
    assert tracks[0]["midi"] == [[0.0, 2.0, 60, 96]]                         # 1 s a 120 BPM = 2 negras
    assert [n[2] for n in tracks[2]["midi"]] == [36, 38, 42]                 # bombo, hi-hat, platillo
    assert m.gm_to_voice(53) == m.CHOIR and m.gm_to_voice(48) == m.STRINGS and m.gm_to_voice(9) == m.BELLS


def test_mid_de_ida_y_vuelta(tmp_path):
    notes = [(0.0, 0.5, 60, 0), (0.5, 1.0, 64, 0), (0.25, 0.75, 40, 33), (0.0, 0.1, 36, 128)]
    f = tmp_path / "c.mid"
    m.write_mid(f, notes, 96)
    back = m.read_mid(f)
    assert len(back) == 4
    for a, b in zip(sorted(notes), back):
        assert b[0] == pytest.approx(a[0], abs=0.002) and b[1] == pytest.approx(a[1], abs=0.002)
        assert b[2:] == a[2:]
    with pytest.raises(ValueError):
        (tmp_path / "x.mid").write_bytes(b"RIFF....")
        m.read_mid(tmp_path / "x.mid")


def test_estado_sin_modelo(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_MIDI_MODELS", str(tmp_path))
    st = m.model_status()
    assert st["size"] == m.MODEL_SIZE and not st["done"] and st["have"] == 0
    ai = m.MidiAi(lambda e: None)
    with pytest.raises(RuntimeError):
        ai.generate({"prompt": "piano"})


@pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
def test_notas_con_duración_y_velocidad(tmp_path):
    h = EngineHost.create()
    assert h.ok, h.error
    eng = h.engine
    eng.set_tempo(120.0)
    tid = eng.add_synth_track("MIDI", 0)["id"]
    eng.set_synth_settings(tid, mode=0, wave=4, vel=100, bri=100)
    # La 440 de 2 negras (1 s) desde 0,5 s y otra flojita (velocidad 30) en 2 s
    length = eng.set_synth_midi(tid, [(1.0, 2.0, 69, 120), (4.0, 0.5, 69, 30)], 0.0)
    assert length == pytest.approx(2.25, abs=0.01)
    out = tmp_path / "midi.wav"
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    y = y[:, 0]
    seg = lambda a, b: float(np.abs(y[int(a * sr): int(b * sr)]).max())
    assert seg(0, 0.49) < 1e-4
    assert seg(1.3, 1.45) > 0.1                    # sigue sonando mientras la nota está pulsada
    assert seg(1.95, 2.0) < 0.02                   # release tras el note-off (1,5 s)
    assert seg(2.05, 2.2) < 0.5 * seg(0.6, 0.7)    # la velocidad cuenta
    # La rejilla de 16 pasos sigue con su nota corta de siempre
    eng.set_synth_notes(tid, [(1.0, 69)], 8.0)
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    y = y[:, 0]
    assert seg(0.85, 1.0) < 1e-3
    # engine_host: una pista con «midi» usa set_synth_midi
    n = h.update_synth(tid, {"type": "inst", "cfg": {"v": 4}, "midi": [[0.0, 1.0, 60, 100]]})
    assert n == pytest.approx(0.5, abs=0.01)
    h.engine = None


@pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
def test_puente_abre_un_mid(tmp_path):
    from PySide6.QtWidgets import QApplication
    from allforone.bridge import Bridge

    QApplication.instance() or QApplication([])
    f = tmp_path / "tema.mid"
    m.write_mid(f, [(0.0, 0.5, 60, 0), (0.0, 0.1, 36, 128)], 120)
    br = Bridge(EngineHost.create())
    r = json.loads(br.midiOpen(str(f), 100.0))
    assert r["ok"] and r["notes"] == 2 and [t["type"] for t in r["tracks"]] == ["inst", "drum"]
    st = json.loads(br.midiStatus())
    assert st["ok"] and "model" in st
