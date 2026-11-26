"""FX Lab (AF-62): dos ramas de efectos en paralelo y 4 macros, en el motor C++.

En la cadena de la pista el FX Lab son tres piezas: «FX Lab» (guarda la señal), «Rama B» (separa:
lo de antes es la rama A, lo de después la B) y «Fin» (mezcla A, B y seco). Se mide el render real:
las dos ramas salen alineadas aunque sus efectos tengan latencias distintas, el cruce A↔B deja oír
solo una, las macros mueven parámetros también al exportar (con su automatización) y todo se guarda
y se recupera con el proyecto. Al final, una canción entera con la voz por un FX Lab.
"""
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from allforone import project
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")
SR = 48000
POS = [0, 300, 1500, 6000, 24000]


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


def db(x):
    return 20 * np.log10(max(1e-9, float(x)))


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def _wav(tmp_path, y, name):
    p = tmp_path / name
    sf.write(str(p), np.stack([y, y], 1) if y.ndim == 1 else y, SR, subtype="FLOAT")
    return str(p)


def _impulses(tmp_path):
    x = np.zeros(2 * SR)
    x[POS] = 0.25
    return _wav(tmp_path, x, "imp.wav")


def _render(eng, tmp_path, name="out.wav"):
    out = tmp_path / name
    assert eng.render_to_wav(str(out))
    y, sr = sf.read(str(out))
    assert sr == SR
    return y


def _lab(eng, tid, a=(), b=(), **params):
    """FX Lab con los efectos `a` en la rama A y `b` en la B. Devuelve (id del FX Lab, {clave: id})."""
    lab = eng.add_effect(tid, "fxlab")["id"]
    ids = {k: eng.add_effect(tid, k)["id"] for k in a}
    eng.add_effect(tid, "fxlab_b")
    ids.update({k: eng.add_effect(tid, k)["id"] for k in b})
    eng.add_effect(tid, "fxlab_end")
    for k, v in params.items():
        assert eng.set_effect_param(lab, k, float(v)), k
    return lab, ids


def _peaks(y):
    """Pico de cada impulso en las 60 muestras que lo siguen: (posición relativa, valor)."""
    a = np.abs(y[:, 0])
    return [(int(np.argmax(a[p: p + 60])), float(a[p: p + 60].max())) for p in POS]


def test_ramas_alineadas_con_latencias_distintas(host, tmp_path):
    """Spectral (2048 muestras de latencia) en A y Limiter (72) en B: cada impulso sale una sola vez,
    con A y B sumados en el mismo sitio, y el mismo retraso que sin FX Lab."""
    eng = host.engine
    src = _impulses(tmp_path)
    t0 = eng.add_audio_track(src, "ref")["id"]
    ref = _peaks(_render(eng, tmp_path, "ref.wav"))
    eng.remove_track(t0)

    tid = eng.add_audio_track(src, "lab")["id"]
    lab, ids = _lab(eng, tid, a=["spectral"], b=["limiter"])
    eng.set_effect_param(ids["spectral"], "amount", 0)
    info = eng.fx_lab_info(lab)
    assert info["linked"] and info["branch_a"] == [ids["spectral"]] and info["branch_b"] == [ids["limiter"]]
    assert round(info["latency_a"] * SR) == 2048 and round(info["latency_b"] * SR) == 72
    y = _render(eng, tmp_path, "lab.wav")
    got = _peaks(y)
    print("referencia", ref, "FX Lab", got)
    assert {p for p, _ in got} == {p for p, _ in ref}                   # mismo sitio que sin FX Lab
    # A (Spectral neutro) + B (Limiter sin tocar) ≈ el doble del impulso, sin ecos a 72 ni a 2048 muestras
    assert all(v > 0.4 for _, v in got), got
    a = np.abs(y[:, 0])
    for p in POS:
        a[max(0, p - 5): p + 60] = 0
    assert a.max() < 0.02, a.max()


def test_cruce_y_seco(host, tmp_path):
    """Cruce 0 = solo A, 100 = solo B; el seco suma la señal limpia, alineada con las ramas."""
    eng = host.engine
    src = _impulses(tmp_path)
    tid = eng.add_audio_track(src, "lab")["id"]
    # A invierte la polaridad, B la deja: así se sabe qué rama suena
    lab, ids = _lab(eng, tid, a=["gain", "limiter"], b=["spectral"])
    eng.set_effect_param(ids["gain"], "polarity", 1)
    eng.set_effect_param(ids["spectral"], "amount", 0)
    sign = lambda y: [float(y[p + o, 0]) for p, (o, _) in zip(POS, _peaks(y))]      # noqa: E731
    eng.set_effect_param(lab, "cross", 0)
    only_a = sign(_render(eng, tmp_path, "a.wav"))
    eng.set_effect_param(lab, "cross", 100)
    only_b = sign(_render(eng, tmp_path, "b.wav"))
    eng.set_effect_param(lab, "cross", 50)
    both = _render(eng, tmp_path, "ab.wav")                              # se cancelan: −x + x
    eng.set_effect_param(lab, "dry", 100)
    eng.set_effect_param(lab, "levelA", -36)
    eng.set_effect_param(lab, "levelB", -36)
    dry = sign(_render(eng, tmp_path, "seco.wav"))
    print("solo A", only_a, "solo B", only_b, "A+B pico", np.abs(both).max(), "seco", dry)
    assert all(v < -0.2 for v in only_a) and all(v > 0.2 for v in only_b)
    assert np.abs(both).max() < 0.05                                    # alineadas: se anulan entre sí
    assert all(0.2 < v < 0.3 for v in dry)


def test_sin_enlazar_pasa_tal_cual(host, tmp_path):
    """Con las piezas en mal orden el FX Lab no hace nada y lo dice (linked = False)."""
    eng = host.engine
    src = _impulses(tmp_path)
    tid = eng.add_audio_track(src, "lab")["id"]
    lab, ids = _lab(eng, tid, a=["gain"], b=[], cross=0, output=-12)
    split = eng.fx_lab_info(lab)["split_id"]
    assert eng.move_effect(split, 0)                                     # «Rama B» antes del FX Lab
    assert not eng.fx_lab_info(lab)["linked"]
    got = _peaks(_render(eng, tmp_path, "suelto.wav"))
    assert all(0.2 < v < 0.3 for _, v in got), got                       # ni la salida −12 dB ni nada
    assert eng.move_effect(split, 2)                                     # vuelve a su sitio
    assert eng.fx_lab_info(lab)["linked"]


def test_macro_mueve_parametros_y_se_automatiza(host, tmp_path):
    """La macro 1 lleva la entrada del Gain de la rama A de 0 a −36 dB; su automatización (de 0 a
    100 % a mitad de la canción) se oye en el export. La perilla del Gain no cambia."""
    eng = host.engine
    t = np.arange(4 * SR) / SR
    src = _wav(tmp_path, 0.25 * np.sin(2 * np.pi * 220 * t), "tono.wav")
    tid = eng.add_audio_track(src, "lab")["id"]
    lab, ids = _lab(eng, tid, a=["gain"], cross=0)
    g = ids["gain"]
    assert eng.set_effect_macro(lab, 1, g, "input", -1.0)
    assert not eng.set_effect_macro(lab, 5, g, "input", 0.5)             # solo hay 4 macros
    assert not eng.set_effect_macro(lab, 1, g, "nada", 0.5)
    assert not eng.set_effect_macro(lab, 1, lab, "cross", 0.5)           # no a sí mismo
    assert [(m["effect_id"], m["param"], m["macro"]) for m in eng.effect_macros(lab)] == [(g, "input", 1)]
    y0 = _render(eng, tmp_path, "m0.wav")[:, 0]
    eng.set_effect_param(lab, "m1", 100)
    y1 = _render(eng, tmp_path, "m1.wav")[:, 0]
    eng.set_effect_param(lab, "m1", 0)
    assert eng.set_effect_automation(lab, "m1", [(0.0, 0.0), (1.9, 0.0), (2.0, 100.0), (4.0, 100.0)])
    y2 = _render(eng, tmp_path, "auto.wav")[:, 0]
    knob = eng.effect_info(g)["values"][0]
    l0, l1 = db(rms(y0[SR // 2: SR])), db(rms(y1[SR // 2: SR]))
    early, late = db(rms(y2[SR // 2: SR])), db(rms(y2[int(2.5 * SR): 3 * SR]))
    print(f"macro 0 %: {l0:.1f} dB · 100 %: {l1:.1f} dB · automatizada {early:.1f} → {late:.1f} dB · perilla {knob}")
    assert abs(l0 - l1 - 36) < 1.5 and abs(early - l0) < 0.5 and abs(late - l1) < 1.5 and knob == 0
    # Quitar la asignación (amount 0) devuelve el parámetro a su perilla; quitar el efecto, la borra
    assert eng.set_effect_macro(lab, 1, g, "input", 0.0) and not eng.effect_macros(lab)
    assert eng.set_effect_macro(lab, 2, g, "input", 0.5)
    eng.remove_effect(g)
    assert not eng.effect_macros(lab)


def test_proyecto_guarda_y_recupera(host, tmp_path):
    """La cadena con el FX Lab, sus ramas y sus macros vuelve igual al abrir el proyecto y suena igual."""
    eng = host.engine
    cat = host.effect_catalog()
    t = np.arange(3 * SR) / SR
    src = _wav(tmp_path, 0.3 * np.sin(2 * np.pi * 330 * t) * (t % 0.5 < 0.25), "pulsos.wav")
    tid = eng.add_audio_track(src, "orig")["id"]
    eng.add_effect(tid, "eq")
    lab, ids = _lab(eng, tid, a=["saturator"], b=["delay", "limiter"], cross=40, dry=30, panA=-50, m2=60)
    assert eng.set_effect_macro(lab, 2, ids["delay"], "mix", 0.5)
    assert eng.set_effect_macro(lab, 3, ids["saturator"], "drive", -0.25)
    saved = json.loads(json.dumps(project.chain_of(eng, cat, tid)))
    assert [fx["key"] for fx in saved] == ["eq", "fxlab", "saturator", "fxlab_b", "delay", "limiter", "fxlab_end"]
    assert saved[1]["macros"] == [{"target": 4, "param": "mix", "macro": 2, "amount": 0.5},
                                  {"target": 2, "param": "drive", "macro": 3, "amount": -0.25}]
    y0 = _render(eng, tmp_path, "orig.wav")
    eng.set_track_mute(tid, True)

    t2 = eng.add_audio_track(src, "abierto")["id"]
    assert project.restore_chain(eng, cat, t2, saved) == []
    chain = eng.effects(t2)
    lab2 = chain[1]["id"]
    info = eng.fx_lab_info(lab2)
    assert info["linked"] and info["branch_a"] == [chain[2]["id"]] and info["branch_b"] == [chain[4]["id"], chain[5]["id"]]
    assert sorted((m["macro"], m["effect_id"], m["param"]) for m in eng.effect_macros(lab2)) == \
        [(2, chain[4]["id"], "mix"), (3, chain[2]["id"], "drive")]
    y1 = _render(eng, tmp_path, "abierto.wav")
    n = min(len(y0), len(y1))
    diff = db(rms(y1[:n] - y0[:n])) - db(rms(y0[:n]))
    print(f"diferencia tras guardar y abrir: {diff:.1f} dB")
    assert diff < -60


def test_cancion_con_la_voz_por_un_fx_lab(host, tmp_path):
    """Una balada entera: la voz por un FX Lab (rama A sala, rama B saturación + eco, algo de seco) y la
    macro 1 abriendo a la vez la sala y el eco en el estribillo. La mezcla sale limpia y la voz con
    el FX Lab suena distinta de la seca, sin perder nivel ni desplazarse."""
    from song_factory import write_song
    song = write_song("balada", tmp_path / "balada")
    g = song["genre"]
    eng = host.engine
    eng.set_tempo(g.bpm)
    ids = {Path(p).stem.split("_", 1)[1]: eng.add_audio_track(p, Path(p).stem)["id"] for p in song["paths"]}
    voz = "Voz_Lead"
    for k, t in ids.items():
        eng.set_track_mute(t, k != voz)
    dry = _render(eng, tmp_path, "voz0.wav")[:, 0]
    lab, fx = _lab(eng, ids[voz], a=["space"], b=["saturator", "delay"], dry=60, levelA=-6, levelB=-8)
    eng.set_effect_param(fx["space"], "mix", 100)
    eng.set_effect_param(fx["delay"], "mix", 100)
    assert eng.set_effect_macro(lab, 1, fx["space"], "decay", 0.4)
    assert eng.set_effect_macro(lab, 1, fx["delay"], "feedback", 0.3)
    length = len(dry) / SR
    eng.set_effect_automation(lab, "m1", [(0.0, 0.0), (length / 2, 0.0), (length / 2 + 0.1, 100.0)])
    wet = _render(eng, tmp_path, "voz1.wav")[:, 0]
    n = min(len(dry), len(wet))
    # Alineado: la correlación máxima entre seco y FX Lab, a 0 muestras. Se admite 1: el Saturator de la
    # rama B (la parte que más pesa) tiene un retraso fraccionario de sus filtros de sobremuestreo, el
    # mismo +1 que da sin FX Lab (tests/test_export_alineado.py); el FX Lab compensa lo que informa (6)
    seg = slice(SR, min(n, 6 * SR))
    lags = range(-64, 65)
    corr = [float(np.dot(dry[seg], np.roll(wet, -k)[seg])) for k in lags]
    best = list(lags)[int(np.argmax(corr))]
    change = db(rms(wet[:n] - dry[:n])) - db(rms(dry[:n]))
    for t in ids.values():
        eng.set_track_mute(t, False)
    mix = _render(eng, tmp_path, "mix.wav")
    print(f"balada: voz con FX Lab difiere {change:.1f} dB de la seca, desfase {best} muestras, "
          f"nivel {db(rms(dry)):.1f} → {db(rms(wet)):.1f} dB; mezcla pico {np.abs(mix).max():.2f}")
    assert abs(best) <= 1 and change > -12 and abs(db(rms(wet)) - db(rms(dry))) < 9
    assert np.isfinite(mix).all() and 0.05 < np.abs(mix).max() <= 1.0
