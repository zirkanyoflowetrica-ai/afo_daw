"""IA local (ai_music.py): petición a ACE-Step, avance leído del registro del motor, descarga
reanudable de modelos y, si el motor y los modelos están en el equipo, una generación real."""
import http.server
import json
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from allforone import ai_music


def test_peticion_desde_lo_que_elige_el_usuario():
    r = ai_music.build_request({"prompt": "piano oscuro", "style": "Trap", "bpm": 140, "duration": 45,
                                "key": "A minor", "creativity": 100, "seed": 9}, "calidad")
    assert r["caption"].startswith("trap, 808 bass") and r["caption"].endswith("piano oscuro")
    assert r["lyrics"] == "[Instrumental]" and r["vocal_language"] == "unknown"
    assert (r["bpm"], r["duration"], r["keyscale"], r["seed"]) == (140, 45, "A minor", 9)
    assert r["lm_temperature"] == pytest.approx(1.1)
    assert r["lm_model"] == "acestep-5Hz-lm-4B-Q8_0.gguf" and r["synth_model"] == ai_music.SYNTH_MODEL
    # Tempo y tonalidad libres: la IA los elige; con voz y sin letra, la IA la escribe
    r = ai_music.build_request({"prompt": "balada", "style": "Libre", "bpm": 0, "key": "Auto",
                                "instrumental": False, "lyrics": ""}, "ligero")
    assert "bpm" not in r and "keyscale" not in r and r["lyrics"] == "" and r["vocal_language"] == "es"
    assert r["lm_model"] == "acestep-5Hz-lm-1.7B-Q8_0.gguf"
    with pytest.raises(ValueError):
        ai_music.build_request({"prompt": " ", "style": "Libre"}, "calidad")
    # Límites: duración 10..240 s, tempo 40..220
    r = ai_music.build_request({"prompt": "x", "duration": 9999, "bpm": 999}, "calidad")
    assert r["duration"] == ai_music.max_seconds() and r["bpm"] == 220


def test_avance_desde_el_registro_del_motor():
    p = lambda line, st="lm": ai_music.progress_of(line, st, 30)  # noqa: E731
    assert p("[Store] Load LM: 3417 ms")[0] < p("[LM-Phase2] Step 50, 1 active, 51 total codes")[0]
    assert p("[LM-Phase2] Step 150, 1 active")[0] == pytest.approx(0.40)     # 30 s = 150 códigos
    assert p("[DiT] Step 4/8 t=0.833", "synth")[0] == pytest.approx(0.70)
    assert p("[WAV] Wrote x.wav", "synth")[0] > p("[Store] Load VAE-Dec: 1 ms", "synth")[0]
    assert p("[GGUF] cualquier otra cosa") is None


def test_nombre_de_archivo_sin_acentos():
    assert ai_music.slug("Reguetón · Ñandú café!") == "regueton_nandu_cafe"
    assert ai_music.slug("···") == "ia"


def test_paquetes_y_estado_de_los_modelos(tmp_path):
    st = ai_music.pack_status("calidad", tmp_path)
    assert not st["installed"] and st["got"] == 0 and len(st["files"]) == 4
    assert st["size"] == sum(ai_music.FILES[f][0] for f in ai_music.pack_files("calidad"))
    assert ai_music.recommended_pack(16) == "calidad" and ai_music.recommended_pack(8) == "ligero"
    assert ai_music.installed_pack(tmp_path) is None


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    data = b""
    cut = 0          # primera petición: se corta tras `cut` bytes (descarga interrumpida)
    ranges: list = []

    def do_GET(self):  # noqa: N802
        start = 0
        rng = self.headers.get("Range")
        type(self).ranges.append(rng)
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
        else:
            self.send_response(200)
        body = self.data[start:]
        if type(self).cut:
            body = body[:type(self).cut]
            type(self).cut = 0
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_descarga_reanudable(tmp_path, monkeypatch):
    payload = np.random.default_rng(1).integers(0, 255, 3_000_000, dtype=np.uint8).tobytes()
    _RangeHandler.data, _RangeHandler.cut, _RangeHandler.ranges = payload, 0, []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        name = "prueba.gguf"
        monkeypatch.setitem(ai_music.FILES, name, (len(payload), "Archivo de prueba"))
        monkeypatch.setattr(ai_music, "HF_URL", f"http://127.0.0.1:{srv.server_port}/{{name}}")
        events = []
        svc = ai_music.AiMusic(events.append)
        # 1) La conexión se corta a mitad: queda un .parte y se avisa del error
        _RangeHandler.cut = 1_000_000
        with pytest.raises(RuntimeError, match="incompleto"):
            svc._fetch(name, len(payload), tmp_path, 0, len(payload))
        part = tmp_path / (name + ".parte")
        assert part.stat().st_size == 1_000_000 and not (tmp_path / name).exists()
        # 2) Reanudar pide solo lo que falta (Range) y el archivo final es idéntico
        svc._fetch(name, len(payload), tmp_path, 0, len(payload))
        assert _RangeHandler.ranges[-1] == "bytes=1000000-"
        assert (tmp_path / name).read_bytes() == payload and not part.exists()
    finally:
        srv.shutdown()


@pytest.mark.skipif(ai_music.engine_dir() is None or ai_music.installed_pack() is None,
                    reason="motor de ACE-Step o modelos no instalados en este equipo")
def test_generacion_real_en_la_gpu(tmp_path, monkeypatch):
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path))
    events = []
    svc = ai_music.AiMusic(events.append)
    svc.generate({"prompt": "simple drum groove with bass", "style": "Funk", "duration": 10, "bpm": 110,
                  "seed": 5, "key": "E minor"})
    t0 = time.time()
    while svc.generating and time.time() - t0 < 600:
        time.sleep(0.2)
    done = [e for e in events if e.get("phase") == "done"][-1]
    assert done["ok"], done
    prog = [e["progress"] for e in events if e.get("phase") == "progress"]
    assert prog == sorted(prog) and len(prog) > 5                  # avance real y siempre hacia delante
    audio, sr = sf.read(done["path"])
    assert sr == 48000 and audio.ndim == 2 and audio.shape[1] == 2
    assert 9.0 < len(audio) / sr < 11.0
    rms = float(np.sqrt(np.mean(audio ** 2)))
    assert rms > 0.01                                            # no es silencio
    meta = json.loads(open(done["path"][:-4] + ".json", encoding="utf-8").read())
    assert meta["composed"]["bpm"] == 110 and meta["composed"]["keyscale"] == "E minor"
    assert [g["path"] for g in ai_music.list_generations()] == [done["path"]]
