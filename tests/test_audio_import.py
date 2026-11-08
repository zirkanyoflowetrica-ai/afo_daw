"""Importar audio que el motor no sabe leer (WAV en coma flotante de 64 bits).

Caso real: stems exportados por el DAW del usuario en float de 64 bits. JUCE solo lee
hasta 32 bits (`juce_WavAudioFormat.cpp`: `bitsPerSample <= 32`), así que la importación
fallaba con «no se puede leer el audio». Ahora se convierte una copia y el original queda igual.
"""
from __future__ import annotations

import math
import struct

import pytest

from allforone import audio_import


def write_float64_wav(path, seconds=0.25, rate=48000, channels=2):
    frames = int(seconds * rate)
    data = bytearray()
    for i in range(frames):
        v = 0.9 * math.sin(2 * math.pi * 440.0 * i / rate)
        for c in range(channels):
            data += struct.pack("<d", v if c == 0 else -v)
    body = bytes(data)
    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt ")
        fh.write(struct.pack("<IHHIIHH", 16, 3, channels, rate, rate * channels * 8, channels * 8, 64))
        fh.write(b"data" + struct.pack("<I", len(body)) + body)
    return frames


def read_wav(path):
    """(tag, canales, frecuencia, bits, bytes de datos) de un WAV simple."""
    with open(path, "rb") as fh:
        assert fh.read(4) == b"RIFF"
        fh.seek(8)
        assert fh.read(4) == b"WAVE"
        fmt = data = None
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            cid, size = struct.unpack("<4sI", head)
            if cid == b"fmt ":
                fmt = struct.unpack("<HHIIHH", fh.read(16)[:16])
                fh.seek(size - 16 + (size & 1), 1)
            elif cid == b"data":
                data = fh.read(size)
            else:
                fh.seek(size + (size & 1), 1)
    return fmt, data


def test_detecta_float64(tmp_path):
    src = tmp_path / "stem.wav"
    write_float64_wav(src)
    assert audio_import._wav_format(src) == (3, 2, 48000, 64)
    assert "64 bits" in audio_import.describe(src)


@pytest.mark.parametrize("via_soundfile", [False, True])
def test_convierte_a_float32(tmp_path, monkeypatch, via_soundfile):
    if via_soundfile:
        pytest.importorskip("soundfile")
    else:  # comprobamos también el respaldo sin dependencias
        monkeypatch.setattr(audio_import, "_convert_soundfile", lambda s, d: False)

    src = tmp_path / "stem.wav"
    frames = write_float64_wav(src)
    before = src.read_bytes()

    dest, note = audio_import.to_engine_wav(src)

    assert dest.is_file() and dest != src
    assert "32 bits" in note and "64 bits" in note
    assert src.read_bytes() == before, "el original no se puede tocar"

    fmt, data = read_wav(dest)
    tag, channels, rate, _br, _ba, bits = fmt
    assert (tag, channels, rate, bits) == (3, 2, 48000, 32)
    assert len(data) == frames * 2 * 4

    # Mismas muestras (float32 es exacto frente a float64 salvo mantisa inaudible)
    orig = struct.unpack(f"<{frames * 2}d", before[-frames * 2 * 8:])
    got = struct.unpack(f"<{frames * 2}f", data)
    assert max(abs(a - b) for a, b in zip(orig, got)) < 1e-6


def test_cachea_y_no_reconvierte(tmp_path, monkeypatch):
    src = tmp_path / "stem.wav"
    write_float64_wav(src, seconds=0.05)
    first, _ = audio_import.to_engine_wav(src)
    stamp = first.stat().st_mtime_ns

    def boom(*a, **k):
        raise AssertionError("no debería volver a convertir")

    monkeypatch.setattr(audio_import, "_convert_soundfile", boom)
    monkeypatch.setattr(audio_import, "_convert_float64_wav", boom)
    again, _ = audio_import.to_engine_wav(src)
    assert again == first and again.stat().st_mtime_ns == stamp


def test_formato_desconocido_da_error_claro(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_import, "_convert_soundfile", lambda s, d: False)
    bad = tmp_path / "roto.wav"
    bad.write_bytes(b"no soy un wav")
    with pytest.raises(RuntimeError):
        audio_import.to_engine_wav(bad)
    assert not list(audio_import.cache_dir().glob("*.parcial"))
