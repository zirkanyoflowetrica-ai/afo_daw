# Biblioteca nativa AFO (efectos e instrumentos propios)

Especificación de origen: *AllForOne — Biblioteca Nativa, 96 plugins* (noviembre 2026): 96 módulos
C++ (AF-01 … AF-96) en 6 secciones y 20 carpetas, construidos por hitos. Este documento dice qué
existe de verdad y cómo está hecho; el mapa completo del navegador está en
`app/allforone/qml/fxlibrary.js`.

## Reglas (de la especificación, aplicadas aquí)

- Los efectos son **módulos nativos dentro de AllForOne** (plugins de Tracktion escritos en C++),
  no VST3 externos. Exportarlos como VST3 sería otro objetivo de compilación aparte.
- Un módulo cuenta como hecho cuando **procesa audio real, informa su latencia y supera pruebas de
  señal**. Además debe ser automatizable y tener presets (ver «Estado»).
- Nada decorativo: medidores, curvas y espectros vienen del motor. Los módulos que aún no existen se
  ven en el navegador como «por construir» y no se pueden insertar.

## Dónde está

| Pieza | Archivo |
|---|---|
| DSP compartida (biquad RBJ, líneas de retardo con Lagrange, compresor con rodilla, puerta, FDN de 8 líneas, FIFO de osciloscopio) | `native/src/fx/FxDsp.h` |
| Los 9 módulos, sus parámetros y `registerFx` | `native/src/fx/FxPlugins.h` |
| Cadena por pista y en el master (insertar, mover, puentear, quitar, medidores, espectro) | `native/src/AfoEngine.cpp` (`addEffect` … `effectSpectrum`) |
| API Python | `afo_audio.effect_catalog()`, `Engine.add_effect`, `move_effect`, `set_effect_param`, `set_effect_enabled`, `effects`, `effect_meters`, `effect_spectrum` |
| Slots de la interfaz | `bridge.py`: `fxCatalog`, `fxAdd`, `fxList`, `fxMove`, `fxRemove`, `fxParam`, `fxEnable`, `fxMeters`, `fxSpectrum` |
| Módulo «Efectos» (Rack FX-96) | `app/allforone/qml/FxBody.qml` |
| Pruebas de señal | `tests/test_engine_fx.py`; en la interfaz, `--nativo --selftest` |

Todos derivan de `FxBase`: parámetros `ParameterWithStateValue` (automatizables y guardados en el
Edit de Tracktion), suavizado en bloques de 32 muestras, `ScopedNoDenormals`, sin reservar memoria
en el hilo de audio, medidores de entrada/salida atómicos. Los efectos se insertan **antes del
fader** de la pista (o del master) y Tracktion compensa la latencia que informan.

## Hito 1 — base real de mezcla (hecho)

| AF | Módulo | Qué hace | Prueba de señal |
|---|---|---|---|
| AF-01 | Gain | Ganancia de entrada/salida, paneo, polaridad, mono | Polaridad invertida = −referencia; paneo a un lado |
| AF-02 | Channel Strip | HPF, puerta, EQ de 3 bandas, compresor y saturación en una tira | Compresión de la tira: pico −30 + 18/4 dB y reducción > 10 dB en su medidor |
| AF-07 | Parametric EQ | 6 bandas (paso alto 12/24 dB/oct, grave, 2 medios, agudo, paso bajo) | Campana +12 dB medida en el tono; curva real; HPF 24 dB/oct |
| AF-13 | Compressor | Rodilla suave, detector Peak/RMS, compensación, mezcla paralela | Reducción ≈ −9 dB en el caso de prueba; mezcla 0 = señal intacta |
| AF-18 | Gate | Umbral, rango, ataque, mantenimiento, liberación, histéresis | Cierra 60 dB por debajo del umbral; por encima deja la señal intacta (±0,1 dB) |
| AF-26 | Saturator | Tubo / Cinta / Recorte con sobremuestreo ×4, tono, bias, mezcla | 3.er armónico presente; aliasing < −70 dB; mezcla 0 = referencia |
| AF-35 | Space | Sala / Hall / Placa / Cámara: predelay, reflexiones, FDN de 8 líneas, amortiguación, anchura | RT60 ≈ 2 s medido por integración de Schroeder |
| AF-41 | Digital Delay | Libre o sincronizado al tempo, realimentación con saturación, ping-pong, filtros, ducking | Eco a 250 ms; negra a 120 BPM = 500 ms |
| AF-76 | Spectrum Analyzer | FFT de 4096 con ventana de Hann en bandas logarítmicas 20 Hz – 20 kHz | Ve 440 Hz a ≈ −12 dB |

También se comprueba: orden de la cadena, mover, quitar, bypass, insertar en el master, y que un
impulso no deje colas denormales (el render termina en tiempo normal).

**Pendiente para cerrar el Hito 1 tal como lo pide la especificación:** presets por módulo, dibujar
y editar la automatización en la interfaz (los parámetros ya son automatizables en Tracktion) y
Abrir / Guardar proyecto en AllForOne para que la sesión con sus efectos sea recuperable.

## Siguientes hitos (metas, no funciones existentes)

| Hito | Módulos |
|---|---|
| 2 · Instrumentales y MIDI | Sampler Pro, Drum Rack, Drum Synth, 808 Lab, Wavetable/Analog Synth, Step Sequencer, Arpeggiator, Transient Designer, Glue |
| 3 · Diseño sonoro | Texture Verb, Shimmer, Infinity, MultiTap, Trance Gate, Granular FX, Spectral FX, FX Lab |
| 4 · Voz profesional | Tune, Pitch Editor, Vocal Align, Harmonizer, Doubler, De-Esser, Dynamic EQ, Noise Reducer |
| 5 · Mastering | True Peak Limiter validado, Loudness, Master Dynamics, Match EQ, Linear EQ, Master Imager, Dither y el resto |

## Añadir un módulo

1. Descriptor (`FxDesc` con sus `ParamDesc`) y clase derivada de `FxBase` en `FxPlugins.h`
   (`prepareFx`, `resetFx`, `processFx`, y `extraMeters` si mide algo propio). Si introduce
   latencia, que sea un número entero de muestras (Tracktion solo compensa muestras enteras).
2. Añadirlo a `fxTypes()` y a `registerFx`.
3. Prueba de señal en `tests/test_engine_fx.py` comparando con un render de referencia (el render
   tiene un desfase fijo de 2 muestras y el limitador del master corta en −1 dBFS: usar tonos bajos).
4. El navegador lo muestra como disponible solo con eso: el catálogo sale del motor.
