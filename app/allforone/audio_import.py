"""Compatibilidad de formatos al importar audio al motor nativo.

El lector WAV de JUCE acepta 8, 16, 24 y 32 bits (`bitsPerSample <= 32`, ver
`juce_WavAudioFormat.cpp`). Muchos DAW exportan stems en **coma flotante de 64 bits**
(`WAVE_FORMAT_IEEE_FLOAT`, 64 bits/muestra), y también existen RF64 y Wave64 para
archivos de más de 4 GB. El motor no los puede abrir.

Cuando el motor rechaza un archivo, aquí se genera una **copia** legible —32 bits en
coma flotante, misma frecuencia y mismos canales, sin recortar picos por encima de
0 dBFS— dentro de la carpeta de datos de AllForOne. El archivo original **nunca se
modifica ni se mueve**, y la pista avisa de la conversión.

La caché está indexada por ruta + tamaño + fecha, así que un mismo stem se convierte
una sola vez; cuando pasa del presupuesto de disco se borran las conversiones menos
usadas (nunca los originales).
"""
from __future__ import annotations

import hashlib
import logging
import re
import struct
from pathlib import Path

from . import paths

log = logging.getLogger("allforone.audio")

#: Tope de la caché de conversiones. Al superarlo se borran las más antiguas.
CACHE_BUDGET_BYTES = 8 * 1024 ** 3
BLOCK_FRAMES = 1 << 16


def cache_dir() -> Path:
    p = paths.user_data_dir() / "convertidos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:60] or "audio"


def cache_path(src: Path) -> Path:
    """Nombre estable para la conversión de este archivo concreto."""
    st = src.stat()
    key = f"{src.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    digest = hashlib.sha1(key.encode("utf-8", "surrogateescape")).hexdigest()[:16]
    return cache_dir() / f"{digest}-{_safe_stem(src.stem)}.wav"


def describe(path: str | Path) -> str:
    """Descripción corta del formato, para el aviso al usuario. '' si no se sabe."""
    fmt = _wav_format(Path(path))
    if fmt is None:
        return ""
    tag, channels, rate, bits = fmt
    kind = {1: "PCM", 3: "coma flotante"}.get(tag, f"formato {tag}")
    return f"WAV {kind} de {bits} bits, {channels} canal(es), {rate} Hz"


def _wav_format(src: Path) -> tuple[int, int, int, int] | None:
    """(formatTag, canales, frecuencia, bits) leyendo solo la cabecera RIFF/WAVE."""
    try:
        with src.open("rb") as fh:
            if fh.read(4) != b"RIFF":
                return None
            fh.seek(8)
            if fh.read(4) != b"WAVE":
                return None
            while True:
                head = fh.read(8)
                if len(head) < 8:
                    return None
                cid, size = struct.unpack("<4sI", head)
                if cid == b"fmt ":
                    body = fh.read(min(size, 40))
                    if len(body) < 16:
                        return None
                    tag, ch, rate, _br, _ba, bits = struct.unpack("<HHIIHH", body[:16])
                    if tag == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                        tag = struct.unpack("<H", body[24:26])[0]
                    return tag, ch, rate, bits
                fh.seek(size + (size & 1), 1)
    except OSError:
        return None


# --- conversión ----------------------------------------------------------------

def _convert_soundfile(src: Path, dest: Path) -> bool:
    """libsndfile: cubre WAV de 64 bits, RF64, Wave64, AIFF, FLAC, OGG…"""
    try:
        import soundfile as sf
    except Exception as exc:  # pragma: no cover - depende del entorno
        log.info("soundfile no disponible para convertir: %s", exc)
        return False
    info = sf.info(str(src))
    with sf.SoundFile(str(src)) as fin, sf.SoundFile(
        str(dest), "w", samplerate=info.samplerate, channels=info.channels,
        format="WAV", subtype="FLOAT",
    ) as fout:
        while True:
            block = fin.read(BLOCK_FRAMES, dtype="float32", always_2d=True)
            if not len(block):
                break
            fout.write(block)
    return True


def _convert_float64_wav(src: Path, dest: Path) -> bool:
    """Respaldo sin dependencias para el caso concreto: WAV float de 64 bits."""
    fmt = _wav_format(src)
    if fmt is None or fmt[0] != 3 or fmt[3] != 64:
        return False
    _tag, channels, rate, _bits = fmt
    with src.open("rb") as fh:
        fh.seek(12)
        data_at = data_len = 0
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            cid, size = struct.unpack("<4sI", head)
            if cid == b"data":
                data_at, data_len = fh.tell(), size
                break
            fh.seek(size + (size & 1), 1)
        if not data_at:
            return False
        fh.seek(data_at)
        # El módulo `wave` no escribe coma flotante: componemos el RIFF a mano.
        with dest.open("wb") as out:
            total = data_len // 8 * 4
            out.write(b"RIFF" + struct.pack("<I", 36 + total) + b"WAVEfmt ")
            out.write(struct.pack("<IHHIIHH", 16, 3, channels, rate, rate * channels * 4, channels * 4, 32))
            out.write(b"data" + struct.pack("<I", total))
            left = data_len
            while left > 0:
                chunk = fh.read(min(left, BLOCK_FRAMES * channels * 8))
                if not chunk:
                    break
                left -= len(chunk)
                n = len(chunk) // 8
                out.write(struct.pack(f"<{n}f", *struct.unpack(f"<{n}d", chunk[: n * 8])))
    return True


def to_engine_wav(path: str | Path) -> tuple[Path, str]:
    """Devuelve (archivo legible por el motor, aviso para el usuario).

    Lanza RuntimeError si no se puede convertir. El original no se toca.
    """
    src = Path(path)
    if not src.is_file():
        raise RuntimeError(f"El archivo no existe: {src}")
    dest = cache_path(src)
    detail = describe(src)
    note = f"convertido a 32 bits en coma flotante{' (original: ' + detail + ')' if detail else ''}"
    if dest.is_file() and dest.stat().st_size > 44:
        return dest, note

    tmp = dest.with_suffix(".parcial")
    try:
        if not _convert_soundfile(src, tmp) and not _convert_float64_wav(src, tmp):
            raise RuntimeError(
                f"formato no compatible con el motor{' (' + detail + ')' if detail else ''} "
                "y no se pudo convertir (falta soundfile)"
            )
        tmp.replace(dest)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"no se pudo convertir el audio: {exc}") from exc

    log.info("Audio convertido para el motor: %s -> %s", src.name, dest.name)
    prune_cache()
    return dest, note


def prune_cache(budget: int = CACHE_BUDGET_BYTES) -> int:
    """Borra las conversiones más antiguas si la caché pasa del presupuesto. Devuelve bytes liberados."""
    files = sorted(cache_dir().glob("*.wav"), key=lambda p: p.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    freed = 0
    for f in files:
        if total - freed <= budget:
            break
        size = f.stat().st_size
        try:
            f.unlink()
        except OSError:  # pragma: no cover - archivo en uso
            continue
        freed += size
    return freed
