# Scripts del usuario (F8)

Un script es un archivo `.py` en la carpeta `scripts/` (junto a `AllForOne.exe`, o en la raíz del
proyecto durante el desarrollo). Cada uno sale en el menú **Scripts** y en la paleta (Ctrl+K) con el
nombre de la primera línea de su docstring; el resto de la docstring es su explicación.

```python
"""Bajar las palmas
Deja las pistas de palmas 3 dB más bajas.
"""
for pista in afo.tracks():
    if "clap" in pista.name.lower() or "palmas" in pista.name.lower():
        pista.set_volume(pista.volume_db - 3)
afo.log("Palmas más bajas")
```

## Cómo corre

1. La ventana manda una copia del proyecto (pistas, clips, archivo que suena en cada una, tempo,
   tonalidad, acordes, secciones y efectos disponibles).
2. El script corre en **otro proceso** (`AllForOne.exe --run-script`). La interfaz sigue respondiendo
   y el audio no se entera: un script nunca toca el bloque de audio.
3. Al terminar, sus órdenes vuelven por el puente y se aplican juntas. **Un Ctrl+Z en el Arreglo
   deshace todo lo que hizo el script.**
4. Si falla (una excepción, `ScriptError`, más de 5 minutos), no se aplica nada y la barra de estado
   dice el error y su línea.

## La API `afo`

| Llamada | Qué hace |
|---|---|
| `afo.tracks(type=None)` | Pistas (`audio`, `voz`, `inst`, `drum`, `ia`, `aux`) |
| `afo.track(nombre)` | La pista con ese nombre |
| `afo.voices()` | Pistas de voz con clips (tipo Voz, o «voz», «vocal», «coro»… en el nombre) |
| `afo.bpm`, `afo.key`, `afo.chords`, `afo.markers` | Tempo, tonalidad, acordes y secciones del proyecto |
| `afo.effects`, `afo.colors` | Efectos de la Biblioteca nativa y colores de la paleta del tema |
| `afo.mix(pistas=None)` | Suma mono a 22,05 kHz (numpy) de esas pistas o de las que suenan |
| `afo.analyze(pistas=None)` | Tempo, tonalidad, acordes y secciones (como «Editar › Analizar el proyecto») |
| `afo.set_markers([...])`, `afo.set_chords([...])`, `afo.set_key(k, escala)` | Cambian la canción |
| `afo.seek(s)`, `afo.play()`, `afo.stop()` | Transporte |
| `afo.export_stems(carpeta="", tracks=None)` | Un WAV por pista (con efectos y master); por defecto en `stems/` junto al proyecto |
| `afo.log(...)` | Mensaje que sale en la barra de estado al terminar |
| `pista.name`, `.type`, `.volume_db`, `.pan`, `.mute`, `.solo`, `.color`, `.path`, `.clips`, `.is_voice` | Lectura |
| `pista.set_volume(dB)`, `.set_pan(−1…1)`, `.set_mute()`, `.set_solo()`, `.rename()`, `.set_color()`, `.add_effect(clave)` | Cambios |
| `clip.start`, `.length`, `.offset`, `.gain_db`, `clip.audio()`, `clip.peak_db()`, `clip.set_gain(dB)` | Clips de audio |
| `ScriptError("…")` | Para el script con un mensaje claro para el usuario |

Los colores son nombres de la paleta del tema (`afo.colors`), nunca un `#…`: así cambian con el tema.

## Ejemplos incluidos

- **Normalizar las voces** (`normalizar_voces.py`): pico de cada clip de voz a −3 dBFS con la
  ganancia de clip.
- **Colorear las pistas por tipo** (`colorear_por_tipo.py`): batería, voces, bajo, teclas, guitarras
  y efectos con su color.
- **Marcadores por sección** (`marcadores_por_seccion.py`): analiza el audio y pone A1, B1, A2…
- **Exportar stems** (`exportar_stems.py`): un WAV por pista que suena.

## Límites de hoy

- Un script no crea ni borra pistas, ni edita notas MIDI.
- «Exportar stems» renderiza en el hilo de la interfaz (como Archivo › Exportar mezcla): la ventana
  espera mientras se escriben los archivos.
- Los scripts son código Python con los permisos del usuario: usa solo los que hayas escrito tú o
  de alguien de confianza.
