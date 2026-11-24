"""Parte nueva acorde al proyecto (ACE-Step «lego», modelo base) sobre un PROYECTO COMPLETO: los stems
de un rock (batería, bajo, guitarras, voces) en el motor, «Generar parte» guitarra y se mide lo que
sale: un audio nuevo (no una copia de la mezcla), del largo del proyecto y a su tempo.
Corre de verdad en la tarjeta gráfica; se salta si no están el motor o el modelo base."""
import json
import time

import numpy as np
import pytest
import soundfile as sf

import song_factory as F
from allforone import ai_music
from allforone.engine_host import EngineHost, afo_audio

pytestmark = [
    pytest.mark.skipif(afo_audio is None, reason="afo_audio no compilado"),
    pytest.mark.skipif(ai_music.engine_dir() is None or not ai_music.pack_status("partes")["installed"],
                       reason="sin motor ACE-Step o sin el sintetizador base"),
]


def test_peticion_lego():
    r = ai_music.build_part_request({"part": "Piano / teclados", "style": "Trap", "bpm": 140, "key": "F minor"})
    assert r["task_type"] == "lego" and r["track"] == "keyboard" and r["synth_model"] == ai_music.BASE_MODEL
    assert r["bpm"] == 140 and r["keyscale"] == "F minor" and r["guidance_scale"] > 1
    with pytest.raises(ValueError):
        ai_music.build_part_request({"part": "Kazoo"})


def test_guitarra_sobre_un_rock(tmp_path, monkeypatch):
    import librosa
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    from allforone.bridge import Bridge
    song = F.write_song("rock", tmp_path / "stems")
    g = song["genre"]
    h = EngineHost.create()
    assert h.ok, h.error
    b = Bridge(h)
    events = []
    b.aiEvent.connect(lambda s: events.append(json.loads(s)))
    try:
        for p in song["paths"]:
            if "Guitarra" not in p:                     # el rock sin sus guitarras: la IA pone una
                h.add_audio(p)
        assert not json.loads(b.aiPart(json.dumps({"part": "Kazoo"})))["ok"]
        r = json.loads(b.aiPart(json.dumps({"part": "Guitarra", "style": "Rock", "bpm": g.bpm,
                                            "key": g.key + (" minor" if g.minor else " major"), "seed": 1})))
        assert r["ok"], r
        t0 = time.monotonic()
        while not any(e.get("phase") == "done" for e in events) and time.monotonic() - t0 < 600:
            app.processEvents()
            h.pump()
            time.sleep(0.02)
        done = next(e for e in events if e.get("phase") == "done")
        assert done["ok"], done
        assert done["part"] == "Guitarra" and any(e.get("phase") == "progress" for e in events)
        ctx, sr = librosa.load(str(ai_music.output_dir() / ".contexto_parte.wav"), sr=22050, mono=True)
        y, _ = librosa.load(done["path"], sr=22050, mono=True)
        n = min(len(y), len(ctx))
        assert abs(len(y) - len(ctx)) / sr < 1.0, (len(y) / sr, len(ctx) / sr)
        assert 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12) > -40, "la parte suena"
        corr = abs(np.corrcoef(y[:n], ctx[:n])[0, 1])
        assert corr < 0.5, f"es una parte nueva, no la mezcla (corr {corr:.2f})"
        tempo = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])
        assert any(abs(tempo * k - g.bpm) / g.bpm < 0.08 for k in (0.5, 1, 2)), (tempo, g.bpm)
        o1 = librosa.onset.onset_strength(y=y, sr=sr)
        o2 = librosa.onset.onset_strength(y=ctx, sr=sr)
        m = min(len(o1), len(o2))
        align = np.corrcoef(o1[:m], o2[:m])[0, 1]
        print(f"guitarra IA: corr {corr:.2f}, tempo {tempo:.1f} (proyecto {g.bpm}), ataques {align:.2f}, {done['meta']['seconds']} s")
        assert align > 0.1, f"los ataques siguen a la batería ({align:.2f})"
    finally:
        b._timer.stop()
        b._mixer_timer.stop()
        h.engine = None
