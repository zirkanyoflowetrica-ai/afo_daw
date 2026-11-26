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
| Los módulos, sus parámetros y `registerFx` | `native/src/fx/FxPlugins.h` |
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
| AF-15 | Glue Compressor | Compresor de bus: ratios 2/4/10:1, ataques 0,1–30 ms y liberaciones 0,1–1,2 s fijos (como los de consola), rodilla de 6 dB, paso alto en la cadena lateral, mezcla paralela | Pico −12 dBFS, umbral −24, 4:1 → −21 dBFS y reducción ≈ −9 dB; con el filtro lateral a 300 Hz un tono de 60 Hz casi no comprime; mezcla 0 = intacto |
| AF-22 | Transient Designer | Ataque y sostenido de −100 a +100 % comparando envolventes rápidas y lentas (sin umbral: igual a cualquier nivel) | Golpes de batería: +100 % de ataque sube el golpe frente a la cola, +100 % de sostenido sube la cola; a 0/0 la señal sale intacta |
| AF-14 | Limiter | Entrada, techo (dBFS), liberación; anticipación de 1,5 ms compensada; recorte final en el techo. Es el último efecto de la cadena del master automático | Tono empujado contra −3 dBFS no pasa del techo y marca su reducción; bajo el techo, señal idéntica |
| AF-18 | Gate | Umbral, rango, ataque, mantenimiento, liberación, histéresis | Cierra 60 dB por debajo del umbral; por encima deja la señal intacta (±0,1 dB) |
| AF-20 | De-Esser | Detector de banda (frecuencia, Q), umbral, rango, modo Banda/Ancha, escucha de la sibilancia | Baja la sibilancia y deja la voz grave intacta |
| AF-26 | Saturator | Tubo / Cinta / Recorte con sobremuestreo ×4, tono, bias, mezcla | 3.er armónico presente; aliasing < −70 dB; mezcla 0 = referencia |
| AF-35 | Space | Sala / Hall / Placa / Cámara: predelay, reflexiones, FDN de 8 líneas, amortiguación, anchura | RT60 ≈ 2 s medido por integración de Schroeder |
| AF-41 | Digital Delay | Libre o sincronizado al tempo, realimentación con saturación, ping-pong, filtros, ducking | Eco a 250 ms; negra a 120 BPM = 500 ms |
| AF-60 | Pitch Correct (Tune) | Afinación en tiempo real: detección YIN (rango de voz), escala y tónica, velocidad, naturalidad en notas largas, intensidad, mezcla; desplazador de tono de dos lecturas sobre 30 ms, latencia compensada. Medidores: nota, destino y corrección en cents | +45 cents → 440 Hz ±1,5; en Do mayor −7,4 semitonos → Re 293,7 Hz; un La afinado sale intacto |
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

## Búsqueda de plugins aparte y versiones de master (API 11)

- `scan_plugin_folders(list_file, extra_folders=[], progress=None)` es una función libre (con su propio
  `ScopedJuceInitialiser_GUI`) que escribe la lista XML tras cada archivo. La usa el proceso hijo
  `AllForOne --scan-plugins LISTA` (`app/allforone/plugin_scan.py`): si un plugin rompe o cuelga el
  hijo (vigilancia de 150 s), el padre lee el «pedal» (UTF-16 de JUCE), relanza el hijo y el plugin
  queda en la lista negra (`failed`). Al terminar, `reload_plugins` relee la lista en el motor.
- Versiones de master (Rebobinado): `masterSnapshot` guarda la cadena del master, el techo y su
  sonoridad medida; `masterLoad` la restaura. La mezcla automática ya no toca el master.

## Siguientes hitos (metas, no funciones existentes)

| Hito | Módulos |
|---|---|
| 2 · Instrumentales y MIDI | **Completo**: Transient Designer AF-22, Glue AF-15, 808 Lab, Drum Synth, Drum Rack, Step Sequencer, Analog Synth, Wavetable Synth, Sampler Pro y Arpegiador (Step Sequencer: el patrón de la Batería se convierte en el motor, `synth::expandSteps`, con fuerza (normal / fuerte / suave), probabilidad (100–25 %, decidida con una semilla: «Otra variación» cambia dónde suenan y la misma suena igual al exportar), repeticiones 1–4 dentro del paso y largo propio de cada pad, 1–16 pasos, para polimetrías; Drum Rack: cada pad de la Batería con su paneo, su grupo de corte (Corte A / B: el hi-hat cerrado corta al abierto con un fundido de 5 ms, a la muestra exacta) y su golpe grabado propio; Sampler Pro: preset «Sampler» del Instrumento que toca el sonido cargado en la pista (hasta 30 s), afinado desde su nota raíz, con inicio, bucle con fundido en la unión, ataque y liberación; Wavetable Synth: preset «Sinte de tablas» con cuatro tablas de 8 ondas (Básica, Vocal, Metálica, Digital), una versión por octava sin aliasing, posición, barrido, movimiento, ataque y liberación; Analog Synth: preset «Sinte analógico» con dos sierras PolyBLEP desafinadas y filtro TPT resonante con envolvente, ataque y liberación; Drum Synth: afinación, caída, tono y nivel propios de cada pad de la Batería, `Voice::startDrum`: el arpegiador va en el sintetizador del motor, `AfoPlugins.h`, con patrón arriba / abajo / arriba y abajo / al azar repetible, negras a fusas al tempo de la sesión, 1–4 octavas y duración de nota) |
| 3 · Diseño sonoro | **Completo**: MultiTap (AF-43), Trance Gate (AF-55), Shimmer (AF-37), Texture Verb (AF-38), Infinity (AF-40), Granular FX (AF-57), Spectral FX (AF-58) y FX Lab (AF-62), ver abajo |
| 4 · Voz profesional | **Hechos**: Harmonizer (AF-65), Doubler (AF-66), Dynamic EQ (AF-08) y Noise Reducer (AF-68), ver abajo (De-Esser AF-20 y Tune AF-60 ya estaban). Faltan Pitch Editor y Vocal Align |
| 5 · Mastering | True Peak Limiter validado, Loudness, Master Dynamics, Match EQ, Linear EQ, Master Imager, Dither y el resto |

## Hito 3 — diseño sonoro (completo)

| AF | Módulo | Qué hace | Prueba de señal (`tests/test_diseno_sonoro.py`) |
|---|---|---|---|
| AF-43 | MultiTap | Hasta 8 ecos a distancias iguales (libre o 1/4, 1/8 con puntillo, 1/8, 1/16, 1/8 tresillo), forma Caída / Crecida / Plana, apertura L/R alterna, realimentación desde el último eco, filtros y mezcla. Medidor: distancia real en ms | Corcheas a 120 BPM: ecos a 250 ms exactos, L-R-L-R, −6 dB cada uno con caída 50 %, nada al otro lado; Crecida sube 6 dB por eco |
| AF-37 | Shimmer | Reverb (FDN de Space) cuya cola vuelve a entrar transportada (+12, +7, +19, +24 o −12 semitonos) por un desplazador de dos lecturas (`GrainShifter`, granos de 50 ms con ventana sen²), con paso alto y tanh en el lazo; brillo, caída, tamaño, amortiguación, corte grave, pre-delay, mezcla | La 440 de 1 s: sin brillo la octava queda a −60 dB del La en la cola; con brillo 60, a −15 dB y la doble octava a −21 dB; la quinta da 660 Hz; nunca pasa de 0 dBFS |
| AF-38 | Texture Verb | Reverb con las 8 líneas moduladas (hasta ±2 ms, fases distintas: `Fdn::mod`) y tres texturas: Seda (solo la ondulación), Grano (la cola troceada con granos de Hann al azar, semilla fija), Cinta (vaivén y temblor, saturación suave, paso bajo a 7 kHz) | 1 kHz sostenido: sin movimiento la cola es el tono puro (−68 dB fuera de él) y su RT60 es el pedido; Seda abre bandas laterales; Grano hace saltar el nivel de un tramo de 10 ms a otro |
| AF-40 | Infinity | Reverb de hasta 60 s; «Congelar» quita las pérdidas del lazo (`Fdn::freeze`, matriz ortogonal) y cierra la entrada en 20 ms: la cola se sostiene sin fin. Automatizable para congelar un acorde. Medidor: congelada | Caída 20 s: −9 dB en 3 s; congelada en el segundo 1 por automatización: la cola no se mueve (< 0,5 dB en 3 s) |
| AF-57 | Granular FX | Búfer de 6 s y hasta 32 granos con ventana de Hann: tamaño, densidad, tono (±24 st) y tono al azar, distancia y dispersión, reversa, apertura L/R, «Congelar» (deja de escuchar y sigue granulando lo último) y mezcla. Azar con semilla fija: el mismo render siempre. Medidor: granos sonando | La 440 a +12 st: 880 Hz más de 100 dB sobre 440; sierra que sube: hacia delante 0 % de muestras bajan, en reversa 100 %; congelado a 0,9 s: la cola sigue a −17 dB en 440 Hz (sin congelar, silencio) |
| AF-58 | Spectral FX | STFT de 2048 puntos (Hann, salto 512) con 5 modos: Desenfoque (arrastra cada franja en el tiempo), Robot (fase fija: armónicos de sr/512), Susurro (fase al azar), Puerta (quita lo que queda bajo el umbral) y Congelar; Desplazar mueve el espectro con la fase corregida en cada salto. Latencia de 2048 muestras informada a Tracktion; el seco va retrasado lo mismo | Neutro = el original (−132 dB); Puerta a −40 dB quita 99 dB de ruido sin tocar el La; +500 Hz lleva 440 a 932 Hz; Robot a 468,75 Hz (5 × 93,75); Congelar sostiene el La estable; lo-fi completo: batería alineada (−131 dB), desenfocada pierde 6 dB de pegada, voz granulada una octava arriba |
| AF-62 | FX Lab | Dos ramas de efectos en paralelo dentro de la cadena de la pista: tres piezas, «FX Lab» (guarda la señal), «Rama B» (lo de antes es la rama A; lo de después, la B, que recibe la misma entrada) y «Fin» (mezcla). El motor enlaza las piezas en cada cambio de la cadena y retrasa cada rama lo que la otra tarda (latencia de sus efectos activos; los recién insertados se preparan antes para medirla); el total lo compensa Tracktion. Cruce A↔B de igual potencia, nivel y paneo por rama, seco y salida. 4 macros: cada una mueve uno o varios parámetros de los efectos de la pista (±% del recorrido) dentro del bloque de audio, también al exportar y con su automatización; las asignaciones se guardan en el proyecto. Las piezas procesan el bloque entero (sin troceo de automatización fina). Panel: ramas, compensación y macros; etiqueta «RAMA A/B» en cada efecto | `tests/test_fx_lab.py`: Spectral (2048) en A y Limiter (72) en B: cada impulso sale una vez, en el mismo sitio que sin FX Lab y con A + B sumadas; A con polaridad invertida y B sin ella se anulan (−126 dB); cruce 0/100 deja solo una; en mal orden pasa tal cual; la macro 1 lleva la entrada del Gain de 0 a −36 dB (automatizada a mitad del export); guardar y abrir: −165 dB de diferencia; balada entera con la voz por sala ∥ saturación + eco: alineada y mezcla limpia |
| AF-55 | Trance Gate | Patrón de 16 pasos (8 patrones) a 1/8, 1/16 o 1/32 del tempo, largo, profundidad, ataque, liberación, alterno L/R y mezcla. El paso sale de la posición del transporte (`FxBase::songPos`), así que cae en la rejilla también al exportar o al empezar a mitad; parado, sigue un reloj libre. Medidor: paso actual | Abierto = tono intacto, cerrado < −70 dB; profundidad 50 % = −6 dB; «Contratiempo» a 90 BPM solo en los pasos 3/7/11/15; alterno: pares a la izquierda, impares a la derecha; house completo con el sinte cortado en el patrón «Trance» |

## Hito 4 — voz profesional (en curso)

| AF | Módulo | Qué hace | Prueba de señal (`tests/test_voz_pro.py`) |
|---|---|---|---|
| AF-65 | Harmonizer | Una o dos voces de armonía a partir de la voz en mono. En la escala: detecta la nota cantada con el mismo YIN del afinador (`PitchTracker`, compartido con AF-60), toma la nota de la escala más cercana (con histéresis) y sube o baja 3ª, 4ª, 5ª, 6ª (grados de la escala) u octava; la voz de armonía va a esa nota exacta, así que sale afinada aunque la voz no lo esté. Fijo: semitonos constantes (con Cromática, siempre fijo). Desplazador de dos lecturas sincronizado con el tono: la media ventana (~25 ms) es un número entero de periodos de la nota, y las lecturas se suman en fase (con ventana fija, una 8ª daba picos a 40–77 cents). Nivel y paneo por voz, deslizamiento, rango de voz y voz original; latencia fija de 25 ms que compensa Tracktion. No conserva formantes | La 3ª de La en Do mayor es Do (523,2 Hz), fija es Do# (554,4), la 5ª abajo Re, la 3ª de Sol es Si y la de Si en La menor es Re, la 8ª abajo 220 Hz (todas a menos de 5 cents); cantada 20 cents alta sale igual; Do-Re-Mi-Fa-Sol da Mi-Fa-Sol-La-Si; sin voces deja la voz igual que sin efecto (< −100 dB); balada entera: la armonía a 12,5 c de la escala con la voz a 32,5 c, 3,3 semitonos por encima, mezcla limpia |
| AF-66 | Doubler | Imita otra toma: 1–4 copias de la voz en mono, cada una por un retardo que se mueve despacio (seno lento y recorrido aleatorio suavizado, distinto por copia) y un desplazador de ventana corta (20 ms) desafinado ± cents alternando; repartidas a izquierda y derecha (igual potencia). La voz original no se retrasa (latencia 0) | Mezcla 0: idéntico (< −120 dB); una copia a la izquierda sale a 30 ms (±2 muestras) y desafinada 20 cents (±2); dos copias abiertas: correlación L/R 0,88 y +0,5 dB; balada con los coros doblados: mezcla limpia |
| AF-08 | Dynamic EQ | Hasta 3 bandas (campana, graves o agudos) en paralelo con la señal: cada una filtra la entrada (paso banda de pico 0 dB, paso bajo o paso alto de 2.º orden), sigue su nivel con ataque y liberación y por cada dB sobre el umbral cambia 2/3 dB (3:1) hasta el rango (negativo baja, positivo sube). Salida = entrada + (g − 1)·banda: una campana o un estante de ganancia g, y g = 1 deja la señal intacta. «Escuchar» saca solo la zona de una banda. Medidores: la ganancia de cada banda; el dibujo muestra la curva máxima y la de ahora. Latencia 0 | Campana a 3 kHz, umbral −30, rango −12: un tono de 3 kHz a −12 dBFS baja 11,5 dB, a −24 baja 3,5 (6 dB × 2/3 con la banda), a −40 nada; 300 Hz y 1 kHz a −12 no se tocan (≤ 0,05 dB); con las bandas apagadas sale idéntico (< −120 dB) |
| AF-68 | Noise Reducer | Resta espectral: STFT de 2048 (Hann, salto 512) con una ganancia por frecuencia común a los dos canales. El suelo de ruido de cada frecuencia es el mínimo en los últimos 3 s de la potencia suavizada (~100 ms y 9 franjas vecinas) × 1,3; no cuenta lo que está bajo −120 dBFS ni las 4 primeras ventanas tras un silencio (si no, el suelo se quedaría casi a 0 tras el silencio del principio). Ganancia = 1 − sensibilidad·suelo/potencia, nunca bajo −reducción, suavizada entre frecuencias y en el tiempo (cierra despacio, abre al momento). «Lo que quita» saca la diferencia para no quitar voz; mezcla con el original retrasado igual. Medidores: suelo (dBFS de un ruido blanco equivalente) y reducción media. Latencia 2048 muestras | Soplido a −50 dBFS y un La a −20: en la pausa el ruido baja 20 dB, el de 2–8 kHz con el tono sonando 19,7 dB y el tono no cambia (−0,01 dB); «Lo que quita» da el ruido a −0,6 dB y el tono a −28; mezcla 0: idéntico (< −100 dB); balada con la voz y un soplido de −55 dBFS: pausas −18 dB, voz cantada −0,14 dB, y con el Dynamic EQ en la voz la mezcla sale limpia |

## Añadir un módulo

1. Descriptor (`FxDesc` con sus `ParamDesc`) y clase derivada de `FxBase` en `FxPlugins.h`
   (`prepareFx`, `resetFx`, `processFx`, y `extraMeters` si mide algo propio). Si introduce
   latencia, que sea un número entero de muestras (Tracktion solo compensa muestras enteras).
2. Añadirlo a `fxTypes()` y a `registerFx`.
3. Prueba de señal en `tests/test_engine_fx.py` comparando con un render de referencia (el render
   tiene un desfase fijo de 2 muestras y el limitador del master corta en −1 dBFS: usar tonos bajos).
4. El navegador lo muestra como disponible solo con eso: el catálogo sale del motor.
