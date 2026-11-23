"""Escritura de automatización en vivo, como en Pro Tools: modos Read / Touch / Latch / Write por pista.

Mientras suena, mover un control (perilla de un efecto, fader o paneo de la pista) en una pista que no
está en Read graba sus valores en la curva del motor:

* **Touch**: escribe mientras se sujeta el control; al soltarlo vuelve en `GLIDE` segundos a la curva
  que había.
* **Latch**: sigue escribiendo el último valor tras soltar, hasta que se para la reproducción.
* **Write**: como Latch, y al parar la pista pasa sola a Touch (para no borrar otra pasada sin querer).

Todo corre en el hilo de Qt (nunca en el de audio): cada movimiento rehace la curva del parámetro con
`set_effect_automation` / `set_track_automation`, y Tracktion la sigue en el siguiente bloque. El tiempo
lo da `now()` (la posición del transporte), que las pruebas sustituyen por un reloj falso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

MODES = ("read", "touch", "latch", "write")
GLIDE = 0.25            # s: vuelta a la curva anterior al soltar en Touch
MIN_DT = 0.03           # s: entre puntos grabados (unos 33 por segundo)
EDGE = 0.005            # s: separación de los puntos que cierran una pasada


def value_at(points: list[tuple[float, float]], t: float, default: float) -> float:
    """Valor de una curva en el segundo t (lineal entre puntos, como el motor)."""
    if not points:
        return default
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t < t1:
            f = (t - t0) / max(1e-9, t1 - t0)
            return v0 + (v1 - v0) * f
    return points[-1][1]


@dataclass
class Pass:
    """Una pasada de escritura sobre un parámetro."""
    target: tuple                        # ("fx", effect_id, param) o ("track", track_id, "volume" | "pan")
    track: int
    mode: str
    t0: float
    base: float                          # valor antes de tocar (curva vacía: el valor fijo)
    original: list[tuple[float, float]]
    rec: list[tuple[float, float]] = field(default_factory=list)
    released: float | None = None        # Latch / Write: soltado, sigue escribiendo el último valor


class AutoWriter:
    def __init__(self, engine, now: Callable[[], float] | None = None,
                 playing: Callable[[], bool] | None = None):
        self.engine = engine
        self.now = now or engine.position_seconds
        self.playing = playing or engine.is_playing
        self.modes: dict[int, str] = {}
        self.passes: dict[tuple, Pass] = {}

    # --- modos -------------------------------------------------------------------
    def mode(self, track_id: int) -> str:
        return self.modes.get(int(track_id), "read")

    def set_mode(self, track_id: int, mode: str) -> str:
        if mode not in MODES:
            raise ValueError(f"Modo de automatización desconocido: {mode}")
        tid = int(track_id)
        if mode == "read":
            self.modes.pop(tid, None)
            self.finish(track=tid)
        else:
            self.modes[tid] = mode
        return self.mode(tid)

    def forget_track(self, track_id: int) -> None:
        tid = int(track_id)
        self.modes.pop(tid, None)
        for k in [k for k, p in self.passes.items() if p.track == tid]:
            self.passes.pop(k)

    # --- curvas del motor ----------------------------------------------------------
    def _get(self, target: tuple) -> list[tuple[float, float]]:
        kind, ident, param = target
        if kind == "fx":
            return [tuple(p) for p in self.engine.effect_automation(ident, param)]
        return [tuple(p) for p in self.engine.track_automation(ident, param)]

    def _set(self, target: tuple, points: list[tuple[float, float]]) -> None:
        kind, ident, param = target
        if kind == "fx":
            self.engine.set_effect_automation(ident, param, points)
        else:
            self.engine.set_track_automation(ident, param, points)

    def _track_of(self, target: tuple) -> int:
        kind, ident, _ = target
        return int(self.engine.effect_info(ident)["track_id"]) if kind == "fx" else int(ident)

    # --- tocar un control ---------------------------------------------------------
    def touch(self, target: tuple, value: float, phase: str) -> bool:
        """phase: "start" | "move" | "end". Devuelve True si el valor se está escribiendo en la curva
        (si no, la interfaz lo aplica como siempre: valor fijo)."""
        target = (target[0], int(target[1]), str(target[2]))
        p = self.passes.get(target)
        if phase == "start" or p is None:
            if phase == "end":
                return False
            tid = self._track_of(target)
            mode = self.mode(tid)
            if mode == "read" or not self.playing():
                return False
            t = max(0.0, self.now())
            orig = self._get(target)
            p = Pass(target, tid, mode, t, value_at(orig, t, float(value)), orig)
            self.passes[target] = p
            p.rec = [(t, float(value))]
            self._apply(p, t)
            return True
        t = max(p.t0, self.now())
        if phase == "move":
            p.released = None
            if p.rec and t - p.rec[-1][0] < MIN_DT:
                p.rec[-1] = (p.rec[-1][0], float(value))
            else:
                p.rec.append((t, float(value)))
            self._apply(p, t)
            return True
        # soltar
        if p.rec and t - p.rec[-1][0] >= MIN_DT:
            p.rec.append((t, float(value)))
        if p.mode == "touch":
            self._apply(p, t, glide=True)
            self.passes.pop(target, None)
        else:                                   # Latch / Write: el último valor sigue hasta parar
            p.released = t
            self._apply(p, t)
        return True

    def _apply(self, p: Pass, t_end: float, glide: bool = False) -> None:
        """Curva = original antes de la pasada + lo grabado + (Touch al soltar) vuelta a la original."""
        t0 = p.t0
        before = [q for q in p.original if q[0] < t0 - EDGE]
        lead = [(max(0.0, t0 - EDGE), p.base)] if t0 > EDGE else []
        rec = [q for q in p.rec if q[0] <= t_end + 1e-9]
        if not rec:
            return
        pts = before + lead + rec
        last_v = rec[-1][1]
        if t_end > rec[-1][0] + 1e-9:
            pts.append((t_end, last_v))
        if glide:
            back = t_end + GLIDE
            pts.append((back, value_at(p.original, back, p.base)))
            pts += [q for q in p.original if q[0] > back + EDGE]
        # mientras escribe (sujetando o en Latch) el último valor se mantiene: la curva vieja de más
        # adelante no suena hasta soltar (Touch) o parar (Latch / Write)
        self._set(p.target, _clean(pts))

    # --- parar --------------------------------------------------------------------
    def finish(self, stop_at: float | None = None, track: int | None = None) -> int:
        """Cierra las pasadas abiertas (al parar o pausar). Latch / Write escriben el último valor hasta
        `stop_at`. Devuelve cuántas cerró."""
        n = 0
        for key, p in list(self.passes.items()):
            if track is not None and p.track != track:
                continue
            end = max(p.rec[-1][0] if p.rec else p.t0, stop_at if stop_at is not None else self.now())
            if p.mode == "touch":
                self._apply(p, end, glide=True)
            else:
                rec_end = p.rec[-1][0] if p.rec else p.t0
                last = p.rec[-1][1] if p.rec else p.base
                tail = [(end, last)] if end > rec_end + EDGE else []
                after = [q for q in p.original if q[0] > end + EDGE]
                bridge = [(end + EDGE, value_at(p.original, end + EDGE, p.base))] if after else []
                before = [q for q in p.original if q[0] < p.t0 - EDGE]
                lead = [(max(0.0, p.t0 - EDGE), p.base)] if p.t0 > EDGE else []
                self._set(p.target, _clean(before + lead + p.rec + tail + bridge + after))
            self.passes.pop(key, None)
            n += 1
        if track is None:
            for tid, m in list(self.modes.items()):
                if m == "write":                 # tras una pasada en Write la pista queda en Touch
                    self.modes[tid] = "touch"
        return n

    @property
    def writing(self) -> bool:
        return bool(self.passes)


def _clean(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Ordena y quita puntos con el mismo instante (se queda el último)."""
    out: list[tuple[float, float]] = []
    for t, v in sorted(points, key=lambda q: q[0]):
        if out and abs(out[-1][0] - t) < 1e-6:
            out[-1] = (t, v)
        else:
            out.append((round(t, 4), float(v)))
    return out
