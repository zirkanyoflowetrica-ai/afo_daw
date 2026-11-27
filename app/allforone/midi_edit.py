"""G2: notas que llegan de un teclado MIDI y cuantización. G7: notas de la IA escritas en la rejilla.

El motor graba (Tracktion, «All MIDI Ins»); aquí solo se pasan las notas a la lista `midi` de la pista
([inicio en negras, duración en negras, nota, velocidad]) y se alinean a la rejilla. Todo en negras
desde el principio del proyecto, igual que `set_synth_midi`.
"""
from __future__ import annotations

from .engine_host import pattern_notes, transpose_of

# Rejillas de «Cuantizar» en negras (T = tresillo)
GRIDS = {"1/4": 1.0, "1/8": 0.5, "1/8T": 1 / 3, "1/16": 0.25, "1/16T": 1 / 6, "1/32": 0.125}
MIN_LEN = 1 / 64


def _note(start, length, note, vel) -> list:
    return [round(max(0.0, float(start)), 6), round(max(MIN_LEN, float(length)), 6),
            max(0, min(127, int(note))), max(1, min(127, int(vel)))]


def track_notes(track: dict) -> list[list]:
    """Notas de la pista tal como se guardan (sin la transposición de la pista): su MIDI o, si solo
    tiene la rejilla del piano roll, esa rejilla pasada a notas (una semicorchea, fuerza 100)."""
    if track.get("midi"):
        return [_note(*n[:4]) for n in track["midi"]]
    tr = transpose_of(track)
    return [_note(b, 0.25, n - tr, 100) for b, n in pattern_notes(track)]


def merge_take(track: dict, recorded) -> list[list]:
    """Suma lo grabado a las notas de la pista (grabar encima, como en un DAW). Lo grabado es lo que
    sonó; como al reproducir se suma la transposición de la pista, se guarda sin ella."""
    tr = transpose_of(track)
    out = track_notes(track) + [_note(s, l, n - tr, v) for s, l, n, v in recorded]
    out.sort(key=lambda n: (n[0], n[2]))
    return out


def ai_fill(track: dict, ai_notes, start: float, end: float, grid: str = "1/16") -> tuple[list[list], int]:
    """G7: escribe en la pista las notas que compuso la IA (en negras desde 0) entre `start` y `end`
    (negras del proyecto): cada inicio y cada duración caen en la rejilla del Piano roll, lo que pasa
    de `end` se corta y lo que la pista tenía en ese tramo se sustituye; fuera de él no se toca. Las
    notas se guardan sin la transposición de la pista, para que suenen a la altura que eligió la IA.
    Devuelve las notas de la pista y cuántas escribió la IA."""
    g = GRIDS.get(grid)
    if g is None:
        raise ValueError(f"Rejilla desconocida: {grid}")
    start, end = float(start), float(end)
    if end - start < g:
        raise ValueError("El tramo es más corto que la rejilla")
    tr = transpose_of(track)
    keep = [n for n in track_notes(track) if not (start - 1e-6 <= n[0] < end - 1e-6)]
    new, seen = [], set()
    for n in ai_notes:
        s = start + round(float(n[0]) / g) * g
        if s >= end - 1e-6 or s < start - 1e-6:
            continue
        key = (round(s, 6), int(n[2]))
        if key in seen:                                  # dos notas iguales en la misma línea: una
            continue
        seen.add(key)
        ln = min(max(g, round(float(n[1]) / g) * g), end - s)
        new.append(_note(s, ln, int(n[2]) - tr, n[3]))
    out = sorted(keep + new, key=lambda n: (n[0], n[2]))
    return out, len(new)


def quantize(notes, grid: str = "1/16", strength: float = 100.0, ends: bool = False) -> tuple[list[list], int]:
    """Lleva el inicio de cada nota hacia la línea más cercana de la rejilla (`strength` %: 100 = encima).
    Con `ends`, también el final (la nota nunca queda más corta que media rejilla).
    Devuelve las notas y cuántas se movieron."""
    g = GRIDS.get(grid)
    if g is None:
        raise ValueError(f"Rejilla desconocida: {grid}")
    k = max(0.0, min(100.0, float(strength))) / 100
    out, moved = [], 0
    for n in notes:
        s, ln, note, vel = float(n[0]), float(n[1]), n[2], n[3]
        e = s + ln
        s2 = s + (round(s / g) * g - s) * k
        e2 = e + (round(e / g) * g - e) * k if ends else s2 + ln
        q = _note(s2, max(e2 - s2, g / 2 if ends else MIN_LEN), note, vel)
        if abs(q[0] - s) > 1e-5 or abs(q[1] - ln) > 1e-5:
            moved += 1
        out.append(q)
    out.sort(key=lambda n: (n[0], n[2]))
    return out, moved
