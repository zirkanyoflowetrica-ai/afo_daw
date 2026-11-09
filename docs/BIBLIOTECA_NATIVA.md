# Biblioteca nativa AFO (efectos e instrumentos propios)

Especificación de origen: *AllForOne — Biblioteca Nativa, 96 plugins* (noviembre 2026): 96 módulos
C++ (AF-01 … AF-96) en 6 secciones y 20 carpetas, construidos por hitos. Este documento dice qué
existe de verdad y cómo está hecho; el mapa completo del navegador está en
`app/allforone/qml/state/fxlibrary.js`.

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
| Los 10 módulos, sus parámetros y `registerFx` | `native/src/fx/FxPlugins.h` |
| Sonoridad BS.1770 (LUFS M/S/I, RMS, pico) por pista y en el master | `native/src/AfoLoudness.h` |
| Cadena por pista y en el master (insertar, mover, puentear, quitar, medidores, espectro) | `native/src/AfoEngine.cpp` (`addEffect` … `effectSpectrum`) |
| API Python | `afo_audio.effect_catalog()`, `Engine.add_effect`, `move_effect`, `set_effect_param`, `set_effect_enabled`, `effects`, `effect_info`, `effect_meters`, `effect_spectrum`, `set_effect_automation`, `effect_automation`, `chain_scope` (antes/después de una cadena), `read_levels` (incluye `loud` y `master_loud`), `reset_loudness`, `measure_mix` (sesión procesada en memoria), `set_master_ceiling` |
| Mezcla y master en vivo | `app/allforone/live_mix.py` (decisiones del V4.2 como cadenas) |
| Presets (de fábrica y del usuario) | `app/allforone/fx_presets.py`; los del usuario en `datos/presets/fx/<efecto>.json` |
| Proyecto `.afo` | `app/allforone/project.py` (efectos, automatización y rutas) y `qml/state/Project.qml` (pistas, tempo, master) |
| Slots de la interfaz | `bridge.py`: `fxCatalog`, `fxAdd`, `fxList`, `fxMove`, `fxRemove`, `fxParam`, `fxEnable`, `fxMeters`, `fxSpectrum`, `fxInfo`, `fxPresets`, `fxApplyPreset`, `fxSavePreset`, `fxDeletePreset`, `fxAutomation`, `fxSetAutomation`, `fxRestore`, `projectSave`, `projectOpen` |
| Módulos «Efectos» (Rack FX-96) y «Efectos master» (Rack FX-M) | `app/allforone/qml/modules/FxBody.qml`, gráficas en `qml/state/fxgraph.js` |
| Pruebas de señal | `tests/test_engine_fx.py`, `tests/test_project.py`, `tests/test_live_mix.py`; en la interfaz, `--selftest` |

El master también admite cadenas largas: `AfoEngineBehaviour` sube los límites de Tracktion
(16 efectos por pista y 4 en el master por defecto) a 512, y `addEffect` falla en voz alta si
Tracktion no acepta un efecto. **Medidas sin archivos:** `chain_scope` toma la entrada del primer
efecto activo y la salida del último (espectro y RMS); cada pista y el master llevan un medidor
BS.1770 (ponderación K con los coeficientes exactos de la norma para cualquier frecuencia de
muestreo; coincide con pyloudnorm ±0,3 LU); `measure_mix` procesa toda la sesión en memoria.

Todos derivan de `FxBase`: parámetros `ParameterWithStateValue` (automatizables y guardados en el
Edit de Tracktion), suavizado en bloques de 32 muestras, `ScopedNoDenormals`, sin reservar memoria
en el hilo de audio, medidores de entrada/salida atómicos. Los efectos se insertan **antes del
fader** de la pista (o del master) y Tracktion compensa la latencia que informan.

## Hito 1 — base real de mezcla (completo)

| AF | Módulo | Qué hace | Prueba de señal |
|---|---|---|---|
| AF-01 | Gain | Ganancia de entrada/salida, paneo, polaridad, mono | Polaridad invertida = −referencia; paneo a un lado |
| AF-02 | Channel Strip | HPF, puerta, EQ de 3 bandas, compresor y saturación en una tira | Compresión de la tira: pico −30 + 18/4 dB y reducción > 10 dB en su medidor |
| AF-07 | Parametric EQ | 6 bandas (paso alto 12/24 dB/oct, grave, 2 medios, agudo, paso bajo) | Campana +12 dB medida en el tono; curva real; HPF 24 dB/oct |
| AF-13 | Compressor | Rodilla suave, detector Peak/RMS, compensación, mezcla paralela | Reducción ≈ −9 dB en el caso de prueba; mezcla 0 = señal intacta |
| AF-18 | Gate | Umbral, rango, ataque, mantenimiento, liberación, histéresis | Cierra 60 dB por debajo del umbral; por encima deja la señal intacta (±0,1 dB) |
| AF-20 | De-Esser | Detector de banda (frecuencia, Q), umbral, rango, modo Banda/Ancha, escucha de la sibilancia | Baja la sibilancia y deja la voz grave intacta |
| AF-26 | Saturator | Tubo / Cinta / Recorte con sobremuestreo ×4, tono, bias, mezcla | 3.er armónico presente; aliasing < −70 dB; mezcla 0 = referencia |
| AF-35 | Space | Sala / Hall / Placa / Cámara: predelay, reflexiones, FDN de 8 líneas, amortiguación, anchura | RT60 ≈ 2 s medido por integración de Schroeder |
| AF-41 | Digital Delay | Libre o sincronizado al tempo, realimentación con saturación, ping-pong, filtros, ducking | Eco a 250 ms; negra a 120 BPM = 500 ms |
| AF-76 | Spectrum Analyzer | FFT de 4096 con ventana de Hann en bandas logarítmicas 20 Hz – 20 kHz | Ve 440 Hz a ≈ −12 dB |

También se comprueba: orden de la cadena, mover, quitar, bypass, insertar en el master, y que un
impulso no deje colas denormales (el render termina en tiempo normal).

### Cierre del Hito 1: presets, automatización y proyecto recuperable

- **Presets:** cada módulo trae de 3 a 5 de fábrica (`fx_presets.FACTORY`, validados contra el
  catálogo del motor) y se guardan los propios (★) por efecto. Un preset nombra solo algunos
  parámetros; el resto vuelve a su valor por defecto, así que aplicar uno siempre deja el mismo sonido.
- **Automatización:** la línea del editor dibuja la curva de un parámetro sobre los 16 compases
  (clic añade, arrastrar mueve, clic derecho borra). Es la `AutomationCurve` de Tracktion: suena al
  reproducir y en el render, y las perillas la siguen. `setEffectAutomation` fuerza
  `AutomatableParameter::updateStream()` porque Tracktion recalcula la curva con un temporizador
  de 10 ms y el render siguiente usaría la anterior. Quitar la curva devuelve el valor fijo.
- **Proyecto (`.afo`, JSON):** Abrir / Guardar en la cabecera (Ctrl+O, Ctrl+S, Ctrl+Mayús+S).
  Guarda tempo, master, módulos ocultos, pistas (notas, patrones, ajustes, volumen, paneo, mute,
  solo, clasificación del mezclador) y por pista y en el master la cadena con valores, puenteo y
  automatización. Los audios se referencian (ruta absoluta y relativa al proyecto: se puede mover la
  carpeta entera); si falta uno se avisa al abrir.

Criterio de aceptación de la especificación — *una mezcla sencilla con efectos reales, A/B,
automatización y proyecto recuperable* — comprobado en `tests/test_project.py`: se guarda una
sesión con EQ automatizada, un efecto puenteado y un efecto en el master, se borra todo, se abre y
el render coincide (±0,05 dB por segundo). El A/B es el del módulo Antes / Después y el bypass de
cada efecto. `--selftest` repite el ciclo desde la interfaz con todas las pistas de la autoprueba.

## Plugins VST3 externos y edición de clips (API 10)

- `scan_plugins` explora las carpetas VST3 estándar con `juce::PluginDirectoryScanner` y guarda la
  lista en `plugins_vst3.xml` (carpeta de datos). Un archivo «pedal» salta en la siguiente búsqueda
  un plugin que colgó el programa. `known_plugins` lee la lista sin volver a explorar.
- `add_plugin_effect` inserta un `te::ExternalPlugin` en la cadena de una pista o del master
  (`describe` lo devuelve con `key = "vst3"`, `name` y `plugin_id`); `effect_state` da su estado en
  base64 para el proyecto; `show_effect_editor` abre su ventana (o el editor genérico de JUCE).
- `set_track_instrument` pone un instrumento VST3 en una pista de Instrumento (recibe su clip MIDI y
  desactiva el sintetizador del motor; `""` lo devuelve); `track_instrument_state`,
  `show_instrument_editor`.
- Clips de audio: `clips`, `set_clip_range` (inicio, largo, desplazamiento), `split_clip`,
  `duplicate_clip`, `remove_clip`, `set_clip_gain`, `set_clip_fades`, `clip_peak_db` (para
  normalizar) y `set_clips` (reemplaza la lista entera: deshacer y abrir proyecto).

## Siguientes hitos (metas, no funciones existentes)

| Hito | Módulos |
|---|---|
| 2 · Instrumentales y MIDI | Sampler Pro, Drum Rack, Drum Synth, 808 Lab, Wavetable/Analog Synth, Step Sequencer, Arpeggiator, Transient Designer, Glue |
| 3 · Diseño sonoro | Texture Verb, Shimmer, Infinity, MultiTap, Trance Gate, Granular FX, Spectral FX, FX Lab |
| 4 · Voz profesional | Tune, Pitch Editor, Vocal Align, Harmonizer, Doubler, Dynamic EQ, Noise Reducer (De-Esser ya está, AF-20) |
| 5 · Mastering | True Peak Limiter validado, Loudness, Master Dynamics, Match EQ, Linear EQ, Master Imager, Dither y el resto |

## Añadir un módulo

1. Descriptor (`FxDesc` con sus `ParamDesc`) y clase derivada de `FxBase` en `FxPlugins.h`
   (`prepareFx`, `resetFx`, `processFx`, y `extraMeters` si mide algo propio). Si introduce
   latencia, que sea un número entero de muestras (Tracktion solo compensa muestras enteras).
2. Añadirlo a `fxTypes()` y a `registerFx`.
3. Prueba de señal en `tests/test_engine_fx.py` comparando con un render de referencia (el render
   tiene un desfase fijo de 2 muestras y el limitador del master corta en −1 dBFS: usar tonos bajos).
4. El navegador lo muestra como disponible solo con eso: el catálogo sale del motor.
