"""Perfil del equipo (hardware.py): el modelo y la carga de la gráfica salen del equipo detectado.

Sin motores de IA: se comprueban los perfiles por memoria, la elección del compositor según lo
instalado, las opciones que reciben ace-lm / ace-synth, el descanso entre trabajos y la comprobación
de memoria de vídeo libre."""
import threading
import time

import pytest

from allforone import ai_music as A
from allforone import hardware as H
from allforone import stems as S


@pytest.fixture
def equipo(monkeypatch, tmp_path):
    """Equipo simulado: fija gráfica, RAM e hilos y vacía la caché del perfil."""
    monkeypatch.setenv("AFO_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setattr(H, "_cache", {})

    def set_hw(vram, ram, threads=12):
        H._cache.clear()
        H._cache["hw"] = {"gpu": "Prueba", "vram_gb": vram, "ram_gb": ram, "threads": threads}
    return set_hw


@pytest.mark.parametrize("vram,ram,want", [
    (24, 64, "alto"), (16, 32, "alto"),
    (16, 15.9, "medio"),          # RX 7800 XT con 16 GB de RAM (el equipo del usuario): RAM justa → medio
    (12, 16, "medio"), (8, 16, "bajo"), (6, 12, "bajo"),
    (4, 16, "cpu"), (0, 32, "cpu"), (16, 8, "cpu"),
])
def test_perfil_por_memoria(vram, ram, want):
    assert H.auto_profile({"vram_gb": vram, "ram_gb": ram}) == want


def test_detecta_este_equipo():
    hw = H.detect()
    assert hw["ram_gb"] > 1 and hw["threads"] >= 1
    print("equipo:", hw, "→", H.auto_profile(hw))


def test_perfil_elegido_por_el_usuario_se_guarda(equipo):
    equipo(16, 15.9)
    assert H.profile()["id"] == "medio" and H.profile()["override"] == "auto"
    H.set_override("bajo")
    assert H.profile()["id"] == "bajo" and H.profile()["auto"] == "medio"
    H._cache.pop("profile")
    assert H.profile()["id"] == "bajo", "se lee de equipo.json"
    H.set_override("auto")
    assert H.profile()["id"] == "medio"
    with pytest.raises(ValueError):
        H.set_override("turbo")


def test_opciones_del_motor(equipo):
    equipo(16, 15.9)
    assert H.engine_args("lm") == [] and H.engine_args("synth") == ["--vae-chunk", "512"]
    equipo(4, 8)
    assert H.engine_args("lm") == ["--device", "CPU"]
    assert H.engine_args("synth") == ["--device", "CPU", "--vae-chunk", "256"]


def test_compositor_segun_perfil_e_instalados(equipo, monkeypatch):
    installed = set()
    monkeypatch.setattr(A, "pack_status", lambda p, mdir=None: {"installed": p in installed})
    equipo(16, 15.9)
    assert A.recommended_pack() == "ligero"
    assert A.pack_for_use() is None
    installed.add("calidad")
    assert A.pack_for_use() == "calidad", "solo está el 4B y la tarjeta tiene memoria para él"
    installed.add("ligero")
    assert A.pack_for_use() == "ligero", "con los dos, el del perfil"
    equipo(32, 64)
    assert A.pack_for_use() == "calidad"
    installed.discard("ligero")
    equipo(4, 16)
    assert A.pack_for_use() is None, "el 4B no cabe en 4 GB"
    assert A.recommended_pack(16) == "calidad" and A.recommended_pack(8) == "ligero"


def test_duracion_maxima_del_perfil(equipo):
    equipo(8, 16)
    assert A.build_request({"prompt": "rock", "duration": 240}, "ligero")["duration"] == 60
    assert A.build_part_request({"part": "Bajo", "duration": 240})["duration"] == 60
    equipo(32, 64)
    assert A.build_request({"prompt": "rock", "duration": 240}, "ligero")["duration"] == 240


def test_hilos_de_demucs(equipo):
    equipo(16, 15.9, threads=4)
    assert S.threads_for(120) == 2, "deja dos hilos libres"
    equipo(16, 15.9, threads=12)
    assert S.threads_for(120) == 8


def test_descanso_entre_trabajos(equipo, monkeypatch):
    equipo(16, 15.9)                           # medio: descansa la mitad de lo que trabajó
    monkeypatch.setattr(H, "vram_in_use_gb", lambda: 1.0)
    g = H.GpuGuard()
    g.before("synth")
    g.after(2.0)
    msgs = []
    t = time.monotonic()
    g.before("synth", threading.Event(), msgs.append)
    waited = time.monotonic() - t
    assert 0.9 < waited < 1.6 and msgs and "descansa" in msgs[0], (waited, msgs)
    g.after(60.0)
    stop = threading.Event()
    stop.set()
    t = time.monotonic()
    g.before("synth", stop)
    assert time.monotonic() - t < 0.5, "cancelar no espera el descanso"


def test_memoria_de_video_ocupada(equipo, monkeypatch):
    equipo(16, 15.9)
    monkeypatch.setattr(H, "vram_in_use_gb", lambda: 12.0)          # un juego abierto ocupa 12 GB
    g = H.GpuGuard()
    with pytest.raises(RuntimeError, match="4.0 GB libres"):
        g.before("lm:calidad")
    g.before("lm:ligero")                                            # el 1,7B (3,5 GB) aún cabe
    monkeypatch.setattr(H, "vram_in_use_gb", lambda: None)
    g.before("lm:calidad")                                           # sin dato no se bloquea


def test_memoria_de_video_en_uso_se_lee():
    v = H.vram_in_use_gb()
    assert v is None or 0 <= v < 256
    print("VRAM en uso:", v)
