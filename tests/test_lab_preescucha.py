"""Preescucha del Instrumental Lab con pistas reales (C9), con PROYECTOS COMPLETOS de cinco géneros.

Las variantes son las partes reales de cada canción (song_factory): la batería, el bajo, el piano, el
sintetizador… y una segunda batería de otro género. Por el puente, como la interfaz:
  preescuchar (una pista borrador por familia) → el render del motor es la suma de las elegidas →
  cambiar de variante cambia el audio de la MISMA pista → solo de una familia → enviar al proyecto
  (copia en `enviadas/`, sobrevive a la papelera) → descartar → golpes sueltos de la batería.
No usa motores de IA: se prueba el camino del audio, no la generación (eso es tests/test_lab.py)."""
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import lab as L
from allforone.engine_host import EngineHost, afo_audio

pytestmark = pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado")

STEMS = {"Batería": ("Drums", "Kick", "Snare", "Clap", "HiHat"), "Bajo": ("Bajo", "808"),
         "Piano / teclados": ("Piano",), "Sintetizador": ("Synth",), "Cuerdas": ("Pad_Cuerdas",),
         "Guitarra": ("Guitarra_Ritmica", "Guitarra_Lead")}


def _parts(genre: str, folder: Path) -> dict[str, np.ndarray]:
    song = F.write_song(genre, folder)
    by = {p.split(f"{genre.capitalize()}_", 1)[1][:-4]: sf.read(p, always_2d=True, dtype="float32")[0] for p in song["paths"]}
    out = {}
    for fam, names in STEMS.items():
        got = [by[n] for n in names if n in by]
        if got:
            out[fam] = sum(got)
    return out


def _render(h, path: Path) -> np.ndarray:
    assert h.engine.render_to_wav(str(path))
    y, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if sr != 44100:
        from scipy.signal import resample_poly
        y = resample_poly(y, 44100, sr, axis=0).astype("float32")
    return y.mean(axis=1)


def _corr(render: np.ndarray, ref: np.ndarray) -> float:
    """Correlación tras alinear: el motor trabaja a 48 kHz y el remuestreo deja ~2 muestras de desfase
    (medido), que en una batería bajan r de 0,99 a 0,84 sin que nada suene distinto."""
    n = min(len(render), len(ref), 44100 * 4)
    c = np.correlate(render[:n], ref[:n], "full")[n - 1 - 64:n + 64]
    lag = int(np.argmax(c)) - 64
    a = render[lag:] if lag >= 0 else np.pad(render, (-lag, 0))
    m = min(len(a), len(ref))
    return float(np.corrcoef(a[:m], ref[:m])[0, 1])


@pytest.mark.parametrize("genre,other", [("hiphop", "rock"), ("trap", "house"), ("lofi", "regueton"),
                                         ("house", "trap"), ("cinematico", "balada")])
def test_preescucha_enviar_y_golpes(genre, other, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    g = F.TODOS[genre]
    parts = _parts(genre, tmp_path / "a")
    drums2 = _parts(other, tmp_path / "b")["Batería"]
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    try:
        bars = int(16 * g.bpm / 240)
        key = f"{g.key} {'minor' if g.minor else 'major'}"
        st = b.lab.new({"style": "Libre", "bpm": g.bpm, "key": key, "bars": bars, "families": list(parts)})
        n = L.n_samples(st["context"])
        ids = {fam: b.lab._add_variant(fam, L.fit(x * 0.5, n), "prueba", 0, None)["id"] for fam, x in parts.items()}
        if "Batería" not in parts:
            b.lab.add_family("Batería")
            ids["Batería"] = b.lab._add_variant("Batería", L.fit(parts.get("Percusión", drums2) * 0.5, n), "prueba", 0, None)["id"]
            parts["Batería"] = drums2
        alt = b.lab._add_variant("Batería", L.fit(drums2 * 0.5, n), "prueba", 1, None)["id"]

        def chosen_sum():
            return sum(L.fit(L._read(Path(c["path"])), n) for c in b.lab.chosen()).mean(axis=1)

        # 1) una pista borrador por familia; el motor suena como la suma de las elegidas
        r = json.loads(b.labPreview())
        assert r["ok"], r
        assert {t["family"] for t in r["tracks"]} == set(ids) and all(t["change"] == "new" for t in r["tracks"])
        tid = {t["family"]: t["id"] for t in r["tracks"]}
        assert all(h.tracks[i]["name"].endswith("Lab (borrador)") for i in tid.values())
        c1 = _corr(_render(h, tmp_path / "r1.wav"), chosen_sum())
        # 2) otra batería: misma pista, audio nuevo; el resto no se toca
        assert json.loads(b.labSet("Batería", alt, "chosen", True))["ok"]
        r = json.loads(b.labPreview())
        ch = {t["family"]: t for t in r["tracks"]}
        assert ch["Batería"]["change"] == "audio" and ch["Batería"]["id"] == tid["Batería"]
        assert all(t["change"] == "same" for f, t in ch.items() if f != "Batería") and len(h.tracks) == len(tid)
        c2 = _corr(_render(h, tmp_path / "r2.wav"), chosen_sum())
        # 3) solo de la batería: el render es esa batería
        states = [[i, False, i == tid["Batería"]] for i in tid.values()]
        assert json.loads(b.setTrackStates(json.dumps(states)))["ok"]
        c3 = _corr(_render(h, tmp_path / "r3.wav"), L.fit(drums2 * 0.5, n).mean(axis=1))
        b.setTrackStates(json.dumps([[i, False, False] for i in tid.values()]))
        print(f"{genre}: render = suma de las elegidas r={c1:.3f}; tras cambiar la batería r={c2:.3f}; solo batería r={c3:.3f}")
        assert c1 > 0.95 and c2 > 0.95 and c3 > 0.95
        # 4) enviar al proyecto: copia propia que sobrevive a la papelera
        r = json.loads(b.labSend())
        assert r["ok"] and {t["id"] for t in r["tracks"]} == set(tid.values())
        for t in r["tracks"]:
            p = Path(h.tracks[t["id"]]["originalPath"])
            assert p.parent.name == "enviadas" and p.is_file()
        b.lab.remove("Batería", alt)
        assert Path(h.tracks[tid["Batería"]]["originalPath"]).is_file(), "lo enviado no depende de la variante"
        assert json.loads(b.labDiscard())["ids"] == [], "lo enviado ya no es borrador"
        # 5) otra preescucha y descartar: devuelve las pistas borrador para quitarlas
        r = json.loads(b.labPreview())
        assert all(t["change"] == "new" for t in r["tracks"])
        assert sorted(json.loads(b.labDiscard())["ids"]) == sorted(t["id"] for t in r["tracks"])
        # 6) golpes sueltos de la batería elegida
        r = json.loads(b.labOneShots("Batería"))
        assert r["ok"], r
        hits = r["state"]["oneshots"]["hits"]
        assert set(hits) <= set(L.S.DRUM_PARTS) and hits, hits
        for label, p in hits.items():
            y, sr = sf.read(p, always_2d=True, dtype="float32")
            pk = float(np.abs(y).max())
            att = int(np.argmax(np.abs(y).max(axis=1) > 0.5 * pk)) / sr
            print(f"{genre} · golpe {label}: {len(y) / sr:.2f} s, pico {20 * np.log10(pk):.1f} dBFS, ataque a {att * 1000:.0f} ms")
            assert len(y) <= 0.8 * sr + 1 and abs(20 * np.log10(pk) + 1) < 0.1 and att < 0.03
    finally:
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None
