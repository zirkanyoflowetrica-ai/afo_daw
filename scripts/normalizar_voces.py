"""Normalizar las voces
Deja el pico de cada clip de voz en -3 dBFS con la ganancia de clip (sin tocar el archivo).
"""
# Script de ejemplo de AllForOne (F8). Corre en un proceso aparte sobre una copia del proyecto;
# lo que cambia se aplica al terminar y Ctrl+Z lo deshace de una vez.
OBJETIVO_DB = -3.0

voces = afo.voices()
if not voces:
    raise ScriptError("No hay pistas de voz con clips (tipo Voz o con «voz», «vocal» o «coro» en el nombre)")
n = 0
for pista in voces:
    for clip in pista.clips:
        pico = clip.peak_db()
        if pico <= -90:
            continue                        # clip en silencio: no se sube
        clip.set_gain(clip.gain_db + OBJETIVO_DB - pico)
        n += 1
afo.log(f"{n} clip(s) de {len(voces)} voz/voces con el pico en {OBJETIVO_DB:.0f} dBFS")
