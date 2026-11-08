# Informe de entrega — AllForOne V0.3 beta «Audios, consola viva y rol de voz»

Fecha: 2026-11-08 · Versión 0.3.0 (beta)

## 1. El fallo que impedía usar tus audios

Tus 10 stems de `C:\Users\…\Music\PPPP` fallaban **todos** con
`afo_audio: no se puede leer el audio: …`. No era el arrastre ni los nombres con espacios.

**Causa:** están exportados en **WAV de coma flotante de 64 bits** (`fmt=3`, 2 canales,
48 kHz, 64 bits/muestra, 166,7 MB cada uno). El lector WAV de JUCE acepta 8, 16, 24 y 32 bits y
rechaza el resto — `juce_WavAudioFormat.cpp`, línea 1997:

```cpp
if (r->sampleRate > 0 && r->numChannels > 0 && r->bytesPerFrame > 0 && r->bitsPerSample <= 32)
```

Devuelve un lector nulo, Tracktion da el archivo por inválido y el motor lanza ese error. El
Mezclador V4.2 sí los leía (usa libsndfile), así que el fallo estaba solo en la ruta hacia Pistas.

**Arreglo:** al importar, si el motor no sabe leer el archivo se genera **una copia** en 32 bits
de coma flotante dentro de `EXE\datos\convertidos`, con caché por ruta + tamaño + fecha (se
convierte una sola vez) y poda automática al pasar de 8 GB. **El original no se toca ni se mueve**,
y la pista avisa: «convertido a 32 bits en coma flotante (original: WAV coma flotante de 64 bits…)».
La conversión corre en un hilo aparte: la ventana no se bloquea aunque sean archivos de 166 MB.

| Comprobación | Resultado |
|---|---|
| Tus 10 WAV reales importados en el motor | **10/10, 0 errores, 9,7 s en total** (≈1 s por archivo de 166 MB) |
| Muestras antes y después de convertir | **idénticas** (diferencia máxima 0,0e+00 en float32) |
| Caché generada | 0,83 GB en `datos\convertidos`; los originales intactos |

### Por qué no se lee el 64 bits de forma nativa

Se probó un lector propio de 64 bits en C++ registrado junto al de JUCE (`Float64WavFormat`):
abre el archivo y mide los picos correctamente, pero Tracktion reproduce a través de
`AudioFileCache`, que **exige un lector mapeado en memoria** y, con el nuestro, el render se queda
esperando bloques indefinidamente. Un cuelgue es peor que una conversión de un segundo, así que se
descartó. Queda una prueba nativa que verifica que el motor **rechaza** esos archivos en 6 ms con
un mensaje claro — que es justo lo que dispara la conversión.

## 2. «Mezcla IA» se parte en dos

| Módulo | Qué hace |
|---|---|
| **Audios** (nuevo) | Arrastrar o elegir archivos. Cada audio **crea su pista** y, con ella, **su tira en la consola**. Tipo y rol editables, referencia opcional, volver a crear pistas borradas. |
| **Mezcla** (la consola de la plantilla) | Las tiras reales **+ la mezcla automática fusionada**: plantilla artística, modo, escalón L/R, espacio vocal, MEZCLAR / REMEZCLAR, progreso e historial. |

Al mezclar **se ve trabajar a la consola**:

- la tira que el mezclador está procesando se enciende;
- al terminar cada pista, su **fader va a la ganancia real medida** (RMS de la pista procesada
  frente a la original) y la **perilla de Pan a la posición real** que decidió el mezclador;
- un LCD bajo el fader muestra esa ganancia y la posición.

Nada de esto es animación decorativa: son medidas sobre el audio renderizado. La EQ, la
compresión, la afinación y los efectos **no** están en la consola, solo en el audio final; el
panel lo dice.

## 3. Rol de voz P / B / L / R / B_L / B_R

Visible y editable en **Audios**, en las filas de **Pistas** y en las tiras de la **consola**:
cambiarlo en cualquiera de los tres lo cambia en todos. En el **Grabador de cintas** hay un
selector «Esta toma es …» y **⇢ Guardar toma como audio**: la toma se guarda como WAV PCM de
24 bits en `datos\tomas` y entra en Audios con ese rol, lista para mezclar.

## 4. El Afinador, cableado a la consola

Con intensidad > 0 %, el Afinador tira **un cable por cada voz marcada hasta la tira exacta** de
esa pista, igual que la plantilla cablea cada fila de Pistas con su módulo. El panel lista a qué
tiras está conectado; los cables siguen a las tiras al desplazar la consola.

## 5. Icono

Icono propio (máscara con auriculares, violeta `#A800FF` sobre negro) en 16–256 px, en la ventana
y en `AllForOne.exe`.

## 6. Pruebas (todas en tu equipo, 8 nov 2026)

| Prueba | Resultado |
|---|---|
| Pruebas nativas (ctest) | OK — incluye «el motor rechaza el WAV de 64 bits en 6 ms sin colgarse» |
| pytest (Windows) | **24/24** (9 AllForOne + 10 del mezclador + 5 de importación de audio) |
| Autoprueba con interfaz y motor real | **OK completa**: soltar 3 audios (uno en 64 bits) → 3 pistas + 7 tiras + 4 selectores de rol → cable del Afinador → MEZCLAR en 2,8 s → 4 masters (Plataformas −14,1 LUFS / −2,11 dBTP) → **faders movidos a −2,9 / −5,4 / −4,8 dB reales** → A/B por la tarjeta de sonido → transporte y medidores |
| Tus 10 stems reales de 166 MB | 10/10 importados en 9,7 s |

Pendiente (más adelante): curva de afinación antes/después en el Afinador; grabar por el motor
nativo en vez del navegador; limitador del master.

## 7. El ZIP de sesión, bajo demanda

Mezclar tu canción completa (10 stems de 3:37) deja una carpeta de **5,7 GB**, de los cuales
**2,45 GB eran el `sesion_completa.zip`** que se creaba al final de **cada** mezcla (y ~40 s más
de espera). Ahora el ZIP solo se arma cuando pulsas **«Exportar sesión ZIP»** en Master IA, en
segundo plano y con progreso. Una mezcla pasa de 5,7 GB a **3,3 GB** y termina antes.
