"""G4: cadena lateral. El compresor y la puerta nativos escuchan otra pista (bombo → bajo) en canciones
completas (tests/song_factory.py): se exporta con el efecto escuchando y sin él y se compara el nivel de
la pista procesada en los golpes del bombo y entre golpes."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone import project
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


def _frames(x, sr, hop=0.01):
    n = int(hop * sr)
    k = len(x) // n
    return np.sqrt(np.mean(x[: k * n].reshape(k, n) ** 2, axis=1) + 1e-12)


def _render(eng, keep, tmp_path, name):
    """Exporta con solo las pistas `keep` sonando; devuelve (mono, sr)."""
    for t in eng.tracks():
        eng.set_track_mute(t["id"], t["id"] not in keep)
    out = tmp_path / f"{name}.wav"
    assert eng.render_to_wav(str(out))
    x, sr = sf.read(str(out), always_2d=True)
    return x.mean(axis=1), sr


def _processed(eng, fx, target, key, tmp_path):
    """La pista `target` con el efecto escuchando a `key` y sin él (RMS cada 10 ms), y el nivel de `key`.
    Una pista callada no manda nada a la cadena lateral (Tracktion la calla en sus clips), así que la
    fuente suena: lo procesado = lo seco + (mezcla con efecto − mezcla sin efecto)."""
    mix_wet, sr = _render(eng, {target, key}, tmp_path, "mezcla_con")
    eng.set_effect_enabled(fx, False)
    mix_dry, _ = _render(eng, {target, key}, tmp_path, "mezcla_sin")
    dry, _ = _render(eng, {target}, tmp_path, "seco")
    only_key, _ = _render(eng, {key}, tmp_path, "fuente")
    eng.set_effect_enabled(fx, True)
    n = min(len(mix_wet), len(mix_dry), len(dry), len(only_key))
    wet = dry[:n] + (mix_wet[:n] - mix_dry[:n])
    return _frames(wet, sr), _frames(dry[:n], sr), _frames(only_key[:n], sr)


def _set(eng, fx, values):
    for k, v in values.items():
        assert eng.set_effect_param(fx, k, v), k


def test_el_bombo_hace_respirar_al_bajo(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "house")
    bass, kick = ids["Bajo"][0], ids["Kick"][0]
    fx = eng.add_effect(bass, "compressor", -1)
    assert fx["can_sidechain"] and fx["sidechain"] == 0
    _set(eng, fx["id"], {"threshold": -20, "ratio": 20, "attack": 0.1, "release": 60, "knee": 0, "makeup": 0, "mix": 100})
    assert eng.set_sidechain(fx["id"], kick) == ""
    assert eng.effect_info(fx["id"])["sidechain"] == kick
    wet, dry, k = _processed(eng, fx["id"], bass, kick, tmp_path)
    ok = dry > 1e-3                                          # donde suena el bajo
    golpe = ok & (k > np.percentile(k, 90))
    entre = ok & (k < k.max() * 10 ** (-45 / 20))
    assert golpe.sum() > 20 and entre.sum() > 20, (golpe.sum(), entre.sum())
    r = wet / dry
    assert np.median(r[golpe]) < 0.4, np.median(r[golpe])    # en cada golpe el bajo baja más de 8 dB
    assert np.median(r[entre]) > 0.85, np.median(r[entre])   # entre golpes suena igual

    # Sin cadena lateral el mismo compresor no sigue al bombo (aprieta el bajo por su propio nivel)
    assert eng.set_sidechain(fx["id"], 0) == ""
    assert eng.effect_info(fx["id"])["sidechain"] == 0
    own, dry2, _ = _processed(eng, fx["id"], bass, kick, tmp_path)
    ro = own / dry2
    assert abs(np.median(ro[golpe]) - np.median(ro[entre])) < 0.15, (np.median(ro[golpe]), np.median(ro[entre]))


def test_la_puerta_abre_al_ritmo_de_otra_pista(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "trap")
    pad, kick = ids["Pad_Cuerdas"][0], ids["Kick"][0]
    fx = eng.add_effect(pad, "gate", -1)
    _set(eng, fx["id"], {"threshold": -20, "range": -80, "attack": 0.05, "hold": 0, "release": 20, "hysteresis": 4})
    assert eng.set_sidechain(fx["id"], kick) == ""
    wet, dry, k = _processed(eng, fx["id"], pad, kick, tmp_path)
    ok = dry > 1e-3
    golpe = ok & (k > np.percentile(k, 90))
    lejos = ok & (k < k.max() * 10 ** (-45 / 20))
    assert golpe.sum() > 10 and lejos.sum() > 10, (golpe.sum(), lejos.sum())
    r = np.clip(wet, 0, None) / dry
    assert np.median(r[golpe]) > 0.7, np.median(r[golpe])    # con el bombo, el pad pasa
    assert np.median(r[lejos]) < 0.1, np.median(r[lejos])    # lejos de él, cerrado


def test_errores_claros_y_se_guarda_con_el_proyecto(host, tmp_path):
    eng = host.engine
    ids = _song(host, tmp_path, "regueton")
    bass, kick = ids["Bajo"][0], ids["Kick"][0]
    eq = eng.add_effect(bass, "eq", -1)
    assert not eq["can_sidechain"]
    assert "compresor" in eng.set_sidechain(eq["id"], kick)
    comp = eng.add_effect(bass, "compressor", -1)
    assert "otra pista" in eng.set_sidechain(comp["id"], bass)
    assert eng.set_sidechain(comp["id"], kick) == ""

    cat = host.effect_catalog()
    uid_of = {kick: "a_kick", bass: "a_bass"}
    saved = project.chain_of(eng, cat, bass, uid_of=uid_of)
    assert [f.get("keyFrom") for f in saved] == [None, "a_kick"]
    ids_new: list = []
    project.restore_chain(eng, cat, bass, saved, ids_out=ids_new)
    assert len(ids_new) == 2 and all(ids_new)
    assert eng.effect_info(ids_new[1])["sidechain"] == 0          # se reconecta cuando están todas las pistas
    assert eng.set_sidechain(ids_new[1], kick) == ""
    assert eng.effect_info(ids_new[1])["sidechain"] == kick
    assert eng.remove_track(kick)                                 # sin su fuente vuelve a su propia señal
    assert eng.effect_info(ids_new[1])["sidechain"] == 0
