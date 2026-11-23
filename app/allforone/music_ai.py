"""Segunda opinión de tonalidad y tempo sobre el análisis del Mezclador V4.2 (que no se reescribe).

El V4.2 vota la tonalidad con perfiles de croma por stem y el tempo con el seguidor de pulsos de
Librosa. Falla en dos casos habituales: confunde tonalidades **relativas** (Mi menor ↔ Sol mayor: mismas
notas) y el tempo de patrones **sincopados** (bombo de trap). Aquí:

* **Tempo**: autocorrelación de la envolvente de ataques de cada instrumento rítmico y armónico,
  normalizada y sumada; se puntúa cada BPM candidato con sus múltiplos (pulso, medio pulso, compás)
  y una preferencia suave por 70–160 BPM. Los charles en semicorcheas y la caja fijan el pulso aunque
  el bombo esté sincopado.
* **Tonalidad**: perfil de Krumhansl–Kessler sobre el croma sumado de los instrumentos armónicos (los
  graves pesan más en la tónica); entre la mejor tonalidad y su **relativa** decide el **bajo**: la
  tónica es la nota en la que más se apoya (duración y primeros tiempos de compás).

Devuelve votos que `mixer_service` combina con los del V4.2. Solo usa numpy, scipy y librosa (local).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SR = 22050
HOP = 512


def _load(path: str, seconds: float = 30.0):
    import soundfile as sf
    import librosa
    info = sf.info(path)
    frames = int(min(info.frames, seconds * info.samplerate))
    y, sr = sf.read(path, frames=frames, always_2d=True, dtype="float32")
    y = y.mean(axis=1)
    return librosa.resample(y, orig_sr=sr, target_sr=SR) if sr != SR else y


def _kind(path: str) -> str:
    """Tipo del stem con las reglas del V4.2 (por nombre)."""
    from mixer_engine import guess_type, is_backing_voice
    name = Path(path).name
    if is_backing_voice(name):
        return "voz"
    t = guess_type(name)
    if t.startswith("Voz") or t in ("Coros", "Voz doble"):
        return "voz"
    if t in ("Bajo",):
        return "bajo"
    if t in ("Drums", "Kick", "Snare", "Hi-hat", "Overheads / Platillos", "Toms", "Percusion"):
        return "ritmo"
    if t in ("FX", "Otro"):
        return "otro"
    return "armonia"


# ----------------------------------------------------------------------------- tempo
def tempo_vote(signals: list[tuple[np.ndarray, float]]):
    """(bpm, acuerdo 0..1) a partir de [(audio, peso)]."""
    import librosa
    acc = None
    for y, w in signals:
        env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
        env = env - env.mean()
        if not np.any(env):
            continue
        n = len(env)
        f = np.fft.rfft(env, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[:n]
        ac = ac / (ac[0] + 1e-12)
        acc = w * ac if acc is None else acc[: len(ac)] + w * ac[: len(acc)]
    if acc is None:
        return None, 0.0
    fps = SR / HOP
    def at(lag):
        i = int(np.floor(lag)); fr = lag - i
        return 0.0 if i + 1 >= len(acc) or i < 1 else (1 - fr) * acc[i] + fr * acc[i + 1]
    cands = np.arange(60.0, 200.0, 0.25)
    score = []
    for bpm in cands:
        lag = 60.0 * fps / bpm
        s = at(lag) + 0.5 * at(2 * lag) + 0.5 * at(4 * lag) + 0.25 * at(lag / 2)
        s *= np.exp(-0.5 * (np.log2(bpm / 110.0) / 0.9) ** 2)        # preferencia suave, centrada en 110
        score.append(s)
    score = np.asarray(score)
    i = int(np.argmax(score))
    best = float(cands[i])
    # afinar con la pendiente local
    rest = np.delete(score, np.where(np.abs(cands - best) < best * 0.06))
    agree = float(np.clip((score[i] - (rest.max() if len(rest) else 0)) / (abs(score[i]) + 1e-9) * 3, 0, 1))
    return round(best, 1), agree


# ----------------------------------------------------------------------------- tonalidad
def bass_roots(bass: list[np.ndarray]) -> np.ndarray:
    """Reparto (suma 1) de las notas en que se apoya el bajo; la primera y la última pesan más."""
    import librosa
    root = np.zeros(12)
    for y in bass:
        c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, fmin=librosa.note_to_hz("C1"), n_octaves=4)
        e = np.sqrt(np.mean(y[: len(y) // HOP * HOP].reshape(-1, HOP) ** 2, axis=1))[: c.shape[1]]
        on = c[:, : len(e)] * (e > 0.25 * (e.max() + 1e-12))
        act = on.max(axis=0) > 0
        peak = on.argmax(axis=0)
        w = np.ones(len(peak))
        idx = np.flatnonzero(act)
        if len(idx):                     # la primera y la última nota del bajo suelen ser la tónica
            edge = max(1, int(0.08 * len(idx)))
            w[idx[:edge]] = 3.0; w[idx[-edge:]] = 2.0
        root += np.bincount(peak[act], weights=w[act], minlength=12)
    return root / root.sum() if root.sum() else root


def key_vote(harm: list[tuple[np.ndarray, float]], bass: list[np.ndarray]):
    """(tónica, 'Mayor'|'Menor natural', acuerdo 0..1, detalle)."""
    import librosa
    chroma = np.zeros(12)
    for y, w in harm + [(b, 1.5) for b in bass]:
        c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, bins_per_octave=36)
        e = np.sqrt(np.mean(c ** 2, axis=0) + 1e-12)
        chroma += w * (c * (e > 0.2 * e.max())).sum(axis=1) / (c.shape[1] + 1e-9)
    if chroma.sum() <= 0:
        return None, None, 0.0, "sin notas"
    chroma /= chroma.sum()
    scores = {}
    for t in range(12):
        scores[(t, "Mayor")] = float(np.corrcoef(chroma, np.roll(KK_MAJOR, t))[0, 1])
        scores[(t, "Menor natural")] = float(np.corrcoef(chroma, np.roll(KK_MINOR, t))[0, 1])
    order = sorted(scores, key=scores.get, reverse=True)
    best = order[0]
    rel = ((best[0] + 9) % 12, "Menor natural") if best[1] == "Mayor" else ((best[0] + 3) % 12, "Mayor")
    detail = f"perfil: {NOTES[best[0]]} {best[1]} ({scores[best]:.2f}) / relativa {NOTES[rel[0]]} {rel[1]} ({scores[rel]:.2f})"
    # el bajo decide entre la tonalidad y su relativa
    root = bass_roots(bass) if bass else np.zeros(12)
    if root.sum():
        a, b = root[best[0]], root[rel[0]]
        detail += f"; bajo en {NOTES[best[0]]} {a:.0%}, en {NOTES[rel[0]]} {b:.0%}"
        if b > a * 1.15:
            best, rel = rel, best
    gap = scores[order[0]] - scores[order[2] if order[1] == rel else order[1]]
    key_vote.last = {"scores": scores, "bass": root}
    return NOTES[best[0]], best[1], float(np.clip(gap * 4 + 0.3, 0, 1)), detail


def analyze(paths: list[str]) -> dict:
    """Votos de tempo y tonalidad de la canción (sin las voces)."""
    harm, bass, rhythm = [], [], []
    for p in paths:
        k = _kind(p)
        if k in ("voz", "otro"):
            continue
        try:
            y = _load(p)
        except (OSError, RuntimeError, ValueError):
            continue
        if len(y) < SR * 2 or np.max(np.abs(y)) < 1e-4:
            continue
        if k == "bajo":
            bass.append(y); rhythm.append((y, 0.5))
        elif k == "ritmo":
            rhythm.append((y, 1.0))
        else:
            harm.append((y, 1.0)); rhythm.append((y, 0.4))
    bpm, bc = tempo_vote(rhythm) if rhythm else (None, 0.0)
    key_vote.last = {"scores": {}, "bass": np.zeros(12)}
    key, scale, kc, detail = key_vote(harm, bass) if (harm or bass) else (None, None, 0.0, "sin instrumentos armónicos")
    return {"bpm": bpm, "bpm_agree": bc, "key": key, "scale": scale, "key_agree": kc, "detail": detail,
            "scores": key_vote.last["scores"], "bass": key_vote.last["bass"]}


MAJOR_STEPS, MINOR_STEPS = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 10)


def combine(v42: dict, ai: dict) -> dict:
    """Une el análisis del V4.2 y esta segunda opinión en una sola decisión, explicada.

    Tonalidad: para cada una de las 24, perfil armónico + voto del V4.2 (a ella y a su relativa) + cuánto se apoya
    el bajo en esa tónica − notas del bajo fuera de esa escala. Tempo: si coinciden (o son doble / mitad)
    manda el V4.2; si no, el que tenga más acuerdo, prefiriendo la periodicidad de los ataques.
    """
    out = dict(v42)
    notes = []
    scores, bass = ai.get("scores") or {}, ai.get("bass")
    if scores:
        vk, vs = v42.get("key"), v42.get("scale")
        vconf = float(v42.get("key_confidence") or 0.6)
        best, total = None, {}
        for (t, mode), corr in scores.items():
            steps = MAJOR_STEPS if mode == "Mayor" else MINOR_STEPS
            sc = corr
            # el V4.2 acierta el conjunto de notas pero no distingue la relativa: su voto vale para las dos
            if vk and vs in ("Mayor", "Menor natural"):
                vt = NOTES.index(vk)
                rel = ((vt + 9) % 12, "Menor natural") if vs == "Mayor" else ((vt + 3) % 12, "Mayor")
                if (t, mode) in ((vt, vs), rel):
                    sc += 0.25 + 0.25 * vconf
            if bass is not None and np.sum(bass) > 0:
                inside = sum(bass[(t + k) % 12] for k in steps)
                sc += 1.5 * bass[t] / np.max(bass) - 1.5 * (1.0 - inside)    # tónica relativa a la nota más tocada
            total[(t, mode)] = sc
        best = max(total, key=total.get)
        ordered = sorted(total.values(), reverse=True)
        key, scale = NOTES[best[0]], best[1]
        if (key, scale) != (vk, vs):
            notes.append(f"Tonalidad: {key} {scale} (V4.2 decía {vk or 'sin conclusión'} {vs or ''}); {ai.get('detail', '')}")
        out.update(key=key, scale=scale, key_confidence=round(float(np.clip((ordered[0] - ordered[1]) * 2 + 0.3, 0, 1)), 3))
    vb, ab = v42.get("bpm"), ai.get("bpm")
    if ab:
        same = vb and any(abs(vb * k - ab) / ab < 0.04 for k in (0.5, 1, 2))
        if not same:
            out["bpm"] = ab
            out["bpm_confidence"] = round(float(ai.get("bpm_agree") or 0), 3)
            notes.append(f"Tempo: {ab:.1f} BPM por la periodicidad de los ataques (V4.2 decía {vb or 'nada'})")
    out["ai_notes"] = notes
    return out
