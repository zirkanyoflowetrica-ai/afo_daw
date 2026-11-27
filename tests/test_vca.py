"""G6: grupos VCA en una canción completa (tests/song_factory.py). El fader del grupo desplaza el de sus
pistas sin juntar su audio en un bus: las que están fuera no cambian, a 0 dB la mezcla es idéntica, el
fader de cada pista se suma y a −100 dB el grupo las calla."""
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
        ids[Path(p).stem.split("_", 1)[1]] = h.add_audio(p, Path(p).stem)["id"]
    return ids


def _render(eng, tmp_path, name, only=None):
    for t in eng.tracks():
        eng.set_track_mute(t["id"], only is not None and t["id"] != only)
    out = tmp_path / f"{name}.wav"
    assert eng.render_to_wav(str(out))
    x, _ = sf.read(str(out), always_2d=True)
    return x.mean(axis=1)


def _vca_db(track_db, vca_db):
    """Ley de Tracktion: el VCA mueve la posición del fader de la pista (posición = e^((dB − 6)/20)) la
    misma distancia que se movió el suyo desde 0 dB; con la pista a 0 dB el resultado son los dB del grupo."""
    pos = lambda db: np.exp((db - 6.0) / 20.0)
    return 20.0 * np.log(pos(track_db) + pos(vca_db) - pos(0.0)) + 6.0


def _rms_db(x):
    return 10 * np.log10(np.mean(x ** 2) + 1e-20)


def test_vca_baja_sus_pistas_y_deja_las_demas(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "house")
    names = list(ids)
    a, b, other = ids[names[0]], ids[names[1]], ids[names[2]]
    ref_mix = _render(eng, tmp_path, "mezcla")
    ref_a = _render(eng, tmp_path, "a", a)
    ref_o = _render(eng, tmp_path, "o", other)

    v = eng.add_vca("Ritmo")
    assert v["members"] == [] and abs(v["db"]) < 1e-6
    assert eng.set_vca_members(v["id"], [a, b]) == ""
    assert sorted(eng.vcas()[0]["members"]) == sorted([a, b])
    assert eng.track_vca(a) == v["id"] and eng.track_vca(other) == 0

    # a 0 dB, meter pistas en el grupo no cambia nada
    same = _render(eng, tmp_path, "mezcla_vca0")
    n = min(len(same), len(ref_mix))
    assert np.max(np.abs(same[:n] - ref_mix[:n])) < 1e-4

    eng.set_vca_gain_db(v["id"], -12.0)
    assert abs(eng.vcas()[0]["db"] + 12) < 1e-4
    low_a = _render(eng, tmp_path, "a12", a)
    low_o = _render(eng, tmp_path, "o12", other)
    assert abs((_rms_db(ref_a) - _rms_db(low_a)) - 12.0) < 0.3, (_rms_db(ref_a), _rms_db(low_a))
    assert abs(_rms_db(ref_o) - _rms_db(low_o)) < 0.05             # fuera del grupo: igual

    eng.set_track_gain_db(a, -6.0)                                  # el grupo desplaza el fader de la pista
    both = _render(eng, tmp_path, "a18", a)
    assert abs((_rms_db(ref_a) - _rms_db(both)) - -_vca_db(-6.0, -12.0)) < 0.4, (_rms_db(ref_a) - _rms_db(both))
    eng.set_track_gain_db(a, 0.0)

    eng.set_vca_gain_db(v["id"], -100.0)                            # el grupo abajo del todo: silencio
    assert _rms_db(_render(eng, tmp_path, "mudo", a)) < -90
    eng.set_vca_gain_db(v["id"], 0.0)


def test_vca_mover_vaciar_quitar_y_errores(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "house")
    a, b = list(ids.values())[:2]
    ref_a = _render(eng, tmp_path, "a", a)
    g1, g2 = eng.add_vca("Uno"), eng.add_vca("Dos")
    assert eng.set_vca_members(g1["id"], [a, b]) == ""
    assert eng.set_vca_members(g2["id"], [a]) == ""                 # una pista, un grupo
    by = {v["id"]: v for v in eng.vcas()}
    assert by[g1["id"]]["members"] == [b] and by[g2["id"]]["members"] == [a]
    eng.set_vca_gain_db(g1["id"], -20.0)                            # ya no afecta a «a»
    assert abs(_rms_db(_render(eng, tmp_path, "a_g1", a)) - _rms_db(ref_a)) < 0.05
    eng.set_vca_gain_db(g2["id"], -6.0)
    assert abs((_rms_db(ref_a) - _rms_db(_render(eng, tmp_path, "a_g2", a))) - 6.0) < 0.3

    assert eng.set_vca_members(g2["id"], []) == ""                  # vaciar: «a» vuelve a sonar entera
    assert eng.track_vca(a) == 0
    assert abs(_rms_db(_render(eng, tmp_path, "a_suelta", a)) - _rms_db(ref_a)) < 0.05

    assert eng.remove_vca(g1["id"]) and eng.track_vca(b) == 0
    assert not eng.remove_vca(g1["id"])
    assert [v["id"] for v in eng.vcas()] == [g2["id"]]
    assert {t["id"] for t in eng.tracks()} >= {a, b}                # las pistas siguen ahí

    assert "ya no existe" in eng.set_vca_members(999, [a])
    assert "ya no existe" in eng.set_vca_members(g2["id"], [12345])
    aux = eng.add_aux_track("Bus")
    assert "Aux" in eng.set_vca_members(g2["id"], [aux["id"]])
    with pytest.raises(Exception):
        eng.set_vca_gain_db(999, 0.0)

    # congelar una pista del grupo sigue funcionando y el VCA la sigue moviendo
    assert eng.set_vca_members(g2["id"], [a]) == ""
    assert eng.freeze_track(a, True) == ""
    frozen = _render(eng, tmp_path, "a_cong", a)
    assert abs((_rms_db(ref_a) - _rms_db(frozen)) - 6.0) < 0.4
    assert eng.freeze_track(a, False) == ""
    assert eng.remove_vca(g2["id"])


def test_quitar_una_pista_del_grupo(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "balada")
    a, b = list(ids.values())[:2]
    v = eng.add_vca("Voces")
    assert eng.set_vca_members(v["id"], [a, b]) == ""
    eng.remove_track(a)
    assert eng.vcas()[0]["members"] == [b]
    assert eng.remove_vca(v["id"])
