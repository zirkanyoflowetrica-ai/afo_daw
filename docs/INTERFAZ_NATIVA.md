# Interfaz nativa (Qt Quick) — sin HTML ni Chromium

AllForOne es una app de escritorio 100 % nativa que conserva la imagen y el funcionamiento de
`templates/AllForOne/PLANTILLA_DAW.html`, la **referencia visual**. Desde la fase 5 es la única interfaz: la
versión web (Qt WebEngine + QWebChannel) se retiró.

Se conserva tal cual: motor C++ (`native/`), `EngineHost`, el Mezclador V4.2 y su adaptador, la
importación de audio y el `Bridge` de Python (sus métodos son slots de Qt: QML los llama
directamente, igual que antes JavaScript por QWebChannel). Solo cambió la capa que dibuja.

```
python -m allforone              # abrir AllForOne
python -m allforone --selftest   # autoprueba: motor, render e interfaz con el motor real
python tools/native_compare.py   # comparación píxel a píxel con la plantilla
```

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Ventana, cabecera (transporte, tempo, zoom, Ver todo, Restaurar diseño, tema), lienzo infinito con puntos, 12 módulos movibles (13 con Efectos) y redimensionables, cables con curva, conectores y cuadrados de curva arrastrables, diseño y tema guardados, módulo **Pistas** con el motor real, arrastrar audios a la ventana | **Hecha** |
| 1 | Audios, Mezcla (consola, faders, rol de voz, MEZCLAR AUTOMÁTICAMENTE), Mezcla final (VU, master, exportar) | **Hecha** |
| 2 | Afinador, Master IA, Antes / Después | **Hecha** |
| 3 | Piano roll, Instrumentos, Batería, Pistas con IA, con sonido del motor (hoy son la demo Web Audio) | **Hecha** |
| 4 | Grabador de cintas grabando con el motor, configuración de audio (drivers, ASIO), módulo Efectos (Biblioteca nativa, Hito 1) | **Hecha** |
| 5 | Interfaz nativa como única interfaz, Qt WebEngine retirado, QML ordenado en carpetas | **Hecha** |


## Fase 0: cómo se hizo

- `app/allforone/qml/`: `Main.qml` (ventana, cabecera, lienzo, cables, conectores), `ModulePanel.qml`
  (módulo), `TracksBody.qml` (Pistas), `NeoButton.qml` (botón con sombra dura), `Theme.qml`
  (colores claro / oscuro de la plantilla y de `afo_theme_dark.css`), `layout.js` (la matemática del
  lienzo portada de la plantilla: `anchor`, `cableShape`, `nearestPin`, `fit`).
- `app/allforone/native_ui.py`: carga fuentes y QML, expone `afo` (Bridge) y `layoutStore`
  (diseño en `datos/diseno_nativo.json`, sin almacenamiento del navegador).
- **Fuente:** Qt no lee WOFF2 y aplica mal los grosores de una fuente variable, así que Space
  Grotesk (OFL 1.1) va como tres TTF estáticos (500, 600, 700) generados de la misma fuente.
- **Símbolos** (■ ▶ ◐ ✕): no están en Space Grotesk; se dibujan con Segoe UI Symbol, como hace el
  navegador en Windows.

## Comparación medida (1600×900, datos limpios)

| Zona | Píxeles distintos | Qué explica la diferencia |
|---|---|---|
| Cabecera, tema claro | 8,0 % | Posiciones iguales a ±1 px; el resto es el suavizado del texto (Chromium y Qt rasterizan distinto) |
| Cabecera, tema oscuro | 8,1 % | Igual |
| Lienzo | 30 % (claro) / 18 % (oscuro) | Cuerpos de los módulos de las fases 1–4 y pistas DEMO de la plantilla, que la nativa no muestra |

Encuadre inicial: zoom 0,6157 (web 0,6159).

## Fase 1: cómo se hizo

- `Mixer.qml` + `mixdata.js`: el estado del Mezclador V4.2 (antes `AFO_MX` en `afo_panels.js`):
  fichas de audio, tipo y rol de voz, plantilla, escalón L/R, espacio vocal, progreso, historial y
  las decisiones reales por tira. Habla con Python por el mismo `afo.mixer(...)`.
- `AudiosBody.qml`: contador, zona para soltar, + Audios / + Referencia / ⇢ Crear pistas / Vaciar,
  lista con tipo y rol editables. Soltar audios en cualquier parte de la ventana crea ficha, pista
  y tira (los WAV de 64 bits se convierten en segundo plano y se enlazan al llegar).
- `MixBody.qml`: una tira por pista con tipo, rol, LCD de la decisión del mezclador (ganancia y
  posición medidas), Pan, fader y medidor del motor; debajo, MEZCLAR / REMEZCLAR, progreso, estado e
  historial. Al terminar, faders y paneo se mueven a lo que decidió el mezclador.
- `MasterBody.qml`: VU con balística ~300 ms sobre el pico L/R del motor (no mide sonoridad), fader
  master (70 = 0 dB) con medidores L/R reales y Exportar mezcla. **Saturación, Tono y Limitador
  siguen sin procesar audio**: lo dicen al pasar el ratón y al usarlos.
- Controles nuevos: `Knob.qml`, `Fader.qml`, `Meter.qml`, `Select.qml`, `Lcd.qml`.
- Rol de voz también en cada fila de Pistas; cambiarlo en Audios, Pistas o la consola lo cambia en
  los tres.

Comprobado con `--selftest` (motor real): soltar 3 audios (uno en 64 bits) → 3 fichas,
pistas y tiras; clasificación por nombre; MEZCLAR en ~2,4 s; faders en 59 / 51 / 53, idénticos a la
web; medidores del master con el nivel del motor. Con los 10 stems reales de PPPP: 10 tiras con su
rol (P, L, R) deducido del nombre.

Comparación por módulo a zoom 1 tras importar y mezclar (compensando desplazamientos de ±4 px):
Mezcla final 11,8 %, Audios 21,8 %, cabecera de Mezcla 6,6 %. Lo que queda es el rayado de fondo
desfasado unos píxeles, el suavizado del texto y alguna línea que parte distinto. El bloque de mezcla
automática no es comparable: la web tiene encima 3 tiras DEMO de la plantilla que la nativa todavía
no muestra (fase 3).

## Fase 2: cómo se hizo

- `TuneBody.qml` (Afinador): pantalla CONFIRMADO / SIN CONFIRMAR con tonalidad y BPM, modos
  Automático / Asistido / Manual, Tónica, Escala, BPM, Analizar música, ✔ Confirmar, estado,
  Intensidad, voces a afinar (P, L, R, _B) y la lista de tiras conectadas. Con intensidad > 0 % sale
  **un cable a la tira exacta** de cada voz con ese rol; los cables siguen a las tiras al desplazar
  la consola. La curva de tono antes/después sigue pendiente y el módulo lo dice.
- `MasteringBody.qml` (Master IA) y `ReviewBody.qml` (Antes / Después) se rehicieron para la
  mezcla en vivo: ver «Mezcla y master en vivo» más abajo (ya no hay WAVs, ZIP ni escucha de archivos).
- `Mixer.qml` añade el estado del afinador (la confirmación se anula si cambian los audios, los
  roles o la tonalidad) y las acciones de escucha. `Note.qml` es el recuadro de notas.
- Un botón con RichText informa `lineCount = 1` aunque tenga dos líneas: `NeoButton` cuenta las
  líneas por la altura del contenido.

Comprobado con `--selftest` (motor real): cable del Afinador a la tira de la voz P;
confirmar F menor 91 BPM en modo manual; **REMEZCLAR con afinación al 60 %: la mezcla sale
«afinada»**; master enviado a Pistas; escucha B del master, A/B de una pista y parada en el motor.

Diferencias que quedan con la web: el texto de la curva pendiente no sale estirado (en la web el
SVG lo deforma), y en Master IA los tres botones caben en una fila porque el texto nativo es algo
más estrecho.

## Fase 3: cómo se hizo

**Sonido en el motor C++ (JUCE + Tracktion), no en el navegador ni en Python.**

- `native/src/AfoSynth.*`: la DSP del sonido de la plantilla (osciladores, lowpass según el Brillo,
  envolvente exponencial; batería con barridos, cuadradas y ruido filtrado), voz a voz.
- `AfoSynthPlugin` (en `AfoEngine.cpp`): plugin propio de Tracktion. Cada pista de Instrumento o
  Batería es una pista del motor con ese plugin y **un clip MIDI** en tiempos de compás. El plugin
  toca las notas en el callback de audio: editar una nota solo rehace el clip (sin renderizar), y la
  pista tiene fader, paneo, mute/solo, medidores y exportación como cualquier otra.
- Escuchar al pulsar (teclado, rejilla, instrumento, golpe) usa la misma DSP por el reproductor de
  escucha del motor, sin tocar el transporte.
- Nuevo en `afo_audio` (API 3): `add_synth_track`, `set_synth_settings`, `set_synth_notes`,
  `audition_synth`. `engine_host.pattern_notes` convierte piano roll / patrón + clips en notas,
  igual que el reloj de la plantilla.

**Interfaz:** `Sequencer.qml` (pistas, pista activa por módulo, piano roll, patrón, IA),
`PianoBody.qml`, `InstBody.qml`, `DrumsBody.qml`, `IaBody.qml`, `TrackTabs.qml`. Pistas muestra
los clips con sus notas o golpes, un cable desde el módulo de origen hasta la fila de cada pista, y
la consola una tira por pista con el color de su módulo. Arranca con las 3 pistas de la plantilla
(Acordes, Bajo, Batería 1), que ahora suenan de verdad.

**Lo que se dice tal cual:** el sonido es la síntesis básica de la plantilla, no instrumentos
muestreados (el subtítulo lo pone: «síntesis»). Reverb y Swing no los usaba la plantilla y siguen
sin cambiar el audio (lo avisan). Pistas con IA ya no es una demo: genera instrumentales reales con
ACE-Step en el equipo y las añade como pistas de audio (`docs/IA_LOCAL.md`). Quitar Instrumentos o Batería del lienzo
desconecta sus pistas (no suenan), como en la plantilla.

Comprobado: render real del motor (nota La a 440 Hz exactamente en su tiempo, silencio antes;
batería en negras; rehacer el patrón sustituye el clip); `--selftest`: las 3 pistas de la
plantilla suenan en el render, editar el piano roll cambia el patrón, escuchar una nota, + Instrumento
crea pista con sintetizador, IA sin audio, desconectar silencia. Vista inicial frente a la web:
cabecera 8 %, lienzo 20 % (antes 30 %).

## Fase 4: cómo se hizo

**Grabar lo hace el motor.** Tracktion graba desde la entrada del dispositivo (`WaveInputDevice`)
y escribe el WAV en su hilo; la interfaz solo arma, manda grabar o parar y lee el medidor real de
la entrada. Nunca pasa audio por el puente.

- `afo_audio` (API 5): `record_inputs`, `add_record_track`, `arm_track(track, input, monitor)`,
  `start_recording`, `stop_recording(discard)`, `record_state` (incluye el nivel de entrada en dB).
- `CintaBody.qml` (Cinta RX-2, como la plantilla): bobinas que giran mientras graba o suena la toma,
  contador LCD, pestañas de pistas de voz, entrada, **Monitor** (oír la entrada) y medidor de entrada;
  ● Grabar, ■ Parar, ▶ Escuchar toma. «+ Voz» en Pistas crea la pista; la toma se ve como onda
  donde empezó y entra en la consola como cualquier audio. Quitar el Grabador del lienzo desarma.
- **Configuración de audio** (botón «Audio» de la cabecera y del Grabador, `AudioSettings.qml`):
  driver (Windows Audio, exclusivo, baja latencia, DirectSound, **ASIO**), salida, entrada,
  frecuencia, búfer con su latencia en ms y el **panel propio del driver ASIO**. Funciona con
  cualquier driver ASIO instalado: ASIO4ALL 2.x, los de cada interfaz, FL Studio ASIO… Si un driver
  no abre, el motor vuelve al dispositivo anterior: nunca te deja sin audio. El ajuste se guarda.

**Efectos.** Módulos «Efectos» (Rack FX-96) y «Efectos master» (Rack FX-M), ambos `FxBody.qml`
(`master: true` fija la pista 0). Cabecera «VOZ P / CADENA DE EFECTOS · RACK VOZ P». A la izquierda
la cadena en orden de señal: casilla de activo/puenteado, nombre (el que le dio la mezcla
automática, si fue ella), menú ⋮ (subir, bajar, quitar) y «+ Agregar efecto», que abre la
Biblioteca (6 secciones, 20 carpetas) e inserta al final, sin límite. A la derecha una tarjeta por
efecto: ⏻, nombre, ≡ (detalle) y ⋮, preset, una mini gráfica y sus perillas. Las gráficas se
calculan en `state/fxgraph.js` con las mismas fórmulas que el motor (biquads RBJ de `FxDsp.h`, ley
del compresor y de la puerta, curvas del Saturator, decaimiento del Space, repeticiones del Delay
con el tiempo real que informa el motor) y el Analizador dibuja el espectro medido. Debajo, el
detalle del efecto elegido: medidores de entrada/salida y de reducción, curva real del EQ,
presets propios y automatización. El rack del canal sigue a la tira elegida en Mezcla (clic en su
nombre; `studio.rackTrack`). Detalle de los efectos en `docs/BIBLIOTECA_NATIVA.md`.

## Entradas y salidas: placas de rack

Cada módulo es un aparato de rack: a su **izquierda** una placa **ENTRADAS** y a su **derecha** una
placa **SALIDAS** (negras, con la cabecera del color del módulo y el número de conexiones). Los
jacks están en esas placas, rotulados con lo que viaja por el cable (`layout.js` `JACKS`: SONIDO,
NOTAS, RITMO, INSTRUMENTAL, VOZ, AUDIO, PISTAS → CANALES, INSERT → CANAL, MIX, MASTER → VERSIONES,
RACK/MASTER → A/B, AFINADA; las pistas llevan su nombre a la salida y «PISTA n» a la entrada).
Una placa solo aparece si ese lado tiene conexiones reales; nada es decorativo. Los jacks de un
mismo lado se apilan y se pueden deslizar por su placa, pero no cambiar de lado: el sonido siempre
entra por la izquierda y sale por la derecha.

El diseño de fábrica (versión 5 del lienzo) sigue el camino del sonido de izquierda a derecha:
fuentes → Piano / Batería / Audios → Pistas (con el Afinador debajo, que entrega la voz afinada a
Mezcla) → Mezcla → Efectos → Mastering → Efectos master → Rebobinado, con Antes / Después al final
cableado desde el rack que mide (Efectos o Efectos master). Entre módulos queda sitio para las dos
placas y el cable (`gapX` en `Main.qml`; al arrastrar, un módulo se para antes de pisar las placas
del vecino).

## Vista Arreglo (estilo Studio One / Ableton, noviembre 2026)

La ventana tiene dos vistas, que se cambian en la cabecera («Arreglo | Módulos», F5 / F6) y se
recuerdan en el diseño guardado. **Arreglo** es la vista por defecto: muestra la canción entera para
poder ver qué hizo la mezcla.

- **Regla** de compases (al tempo del proyecto) y segundos; clic para mover el cursor.
- **Una fila por pista**: color, nombre, tipo del Mezclador (Voz principal, Bajo…), M/S y la cadena de
  inserts en orden («FX: HPF › De-esser › Compresor…»). Clips de audio con su forma de onda, notas MIDI
  o el patrón de 16 pasos. El master es la última fila.
- **Carriles de automatización** bajo cada pista (se pliegan con «▸ ∿ N» o «Curvas: todas / ninguna»):
  la curva real que reproduce el motor, con el efecto, el parámetro, el rango del catálogo y el
  **valor que tiene ahora** bajo el cursor (las frecuencias, en la escala sesgada de su perilla).
  Doble clic abre ese efecto en el módulo Efectos.
- **Consola** (botón «Consola»): una tira por pista con sus inserts (punto verde activo, tachado si está
  puenteado, ∿ si tiene parámetros automatizados), paneo, fader, medidores L/R y pico; y la tira master.
- **Buses Aux y envíos** («+ Aux» en la barra de Arreglo o en Pistas): un bus es una pista del motor con
  el *Aux Return* de Tracktion al principio y sus propios efectos, fader y paneo (doble clic en el nombre
  de su tira abre sus efectos). Cada tira gana la sección **ENVÍOS**: una fila por bus con el nivel
  (arrastrar; −48…+6 dB, doble clic = apagado) y **PRE** (antes del fader: no sigue al volumen de la
  pista). El bus sigue sonando cuando otra pista está en solo (*solo seguro*); quitar un bus quita los
  envíos que le llegaban. Motor: `addAuxTrack`, `setSend`, `sends` (`AuxSendPlugin` antes o después del
  fader); puente: `auxCreate`, `sendSet`, `sendList` y `sends` en `dawLanes`; el proyecto guarda los
  envíos de cada pista con el uid del bus.
- **Automatización en vivo** (botón **R/T/L/W** en la cabecera de cada pista: Read → Touch → Latch →
  Write). Fuera de Read, mientras suena, mover el fader o el paneo (consola de Arreglo o módulo Mezcla) o
  una perilla de un efecto de esa pista graba su curva: **Touch** escribe mientras se sujeta y al soltar
  vuelve a la curva anterior en 0,25 s; **Latch** mantiene el último valor hasta parar; **Write** como
  Latch y al parar la pista pasa a Touch. Lógica en `automation_write.py` (`AutoWriter`, hilo de Qt;
  rehace la curva del motor en cada movimiento, nunca toca el hilo de audio); puente: `autoMode`,
  `autoModes`, `autoTouch`, `trackAutoSet`; motor: `setTrackAutomation` / `trackAutomation` (volumen en
  dB y paneo del `VolumeAndPanPlugin`). Pausar o parar cierra las pasadas. En los carriles: **clic**
  añade un punto, **arrastrar** lo mueve (muestra tiempo y valor), **clic derecho** lo borra. Una pista
  fuera de Read muestra su carril de volumen aunque esté vacío. El proyecto guarda `trackAuto` y
  `autoMode` por pista.
- Datos: el slot `dawLanes(ids)` del puente devuelve en una llamada, por pista, los inserts y las curvas
  (`effect_automation`) con nombre, unidad, mínimo, máximo y centro del catálogo. Se refresca al cambiar
  una cadena (`fxRev`), las pistas, al mostrar la vista y cada 2 s.
- Coherencia con el resto (revisión del 23-11-2026): el **tema oscuro es el de fábrica** (un diseño
  guardado con el claro de fábrica pasa una vez al oscuro; luego manda lo que elija el usuario); los
  controles del lienzo (zoom, Ver todo, Restaurar diseño) y el menú de módulos solo aparecen en
  Módulos; la barra de estado da la ayuda y el zoom de la vista que se ve; el reloj de la cabecera
  marca compás.tiempo de la posición real del motor (antes daba la vuelta a los 16 compases); el texto
  de la vista no baja de 11 px ni usa transparencia (contraste de la guía).
- Autoprueba: tras MEZCLAR AUTOMÁTICAMENTE comprueba que la vista muestra todos los inserts y todas las
  curvas que tiene el motor y guarda `logs/selftest_arreglo.png`.

## Mezcla y master en vivo (sin WAVs)

- **Mezcla:** `mixer_service._live` (hilo del mezclador) llama a `live_mix.plan`: las mismas
  medidas y criterios del V4.2 (`analyze`, `TYPES`, `_adaptive_chain`, `pitch_profile`, escalón de
  `_blend_backing`, `vocal_space.PROFILES`, aire de `enhance_vocal`) dan por pista ganancia, paneo y
  una cadena de la Biblioteca con sus valores. El puente (`Bridge._apply_plan`, hilo principal)
  la pone en el motor, sustituyendo solo los efectos que puso la mezcla anterior, y la consola
  coloca faders y paneos. Lo que el V4.2 hace sobre el audio y una cadena no reproduce (ducking
  bombo→bajo, enmascaramiento dinámico, balance por secciones, EQ dinámica de la voz, compresión
  paralela por bus) se informa en el estado, no se finge. Solo se escribe audio
  si se pide afinación (PSOLA no es un efecto en tiempo real): una copia afinada por voz elegida,
  que sustituye al audio de su pista.
- **Automatizaciones de la mezcla** (`live_mix.automate`, tras decidir las cadenas): se analiza la voz
  principal (RMS de 400 ms cada 50 ms; canta lo que pasa del p95 − 22 dB; huecos < 0,25 s no cortan
  la frase) y se escriben curvas de Tracktion (`set_effect_automation`, desde el inicio de la pista)
  que el motor sigue al reproducir:
  - **Ride de voz:** un «Ride de voz (automático)» (ganancia) tras el de-esser lleva cada frase
    hacia el nivel típico de la voz (media recortada p10–p90): 70 % de la diferencia, ±4 dB, suave
    (600 ms) y quieto en los silencios. Curva aligerada con Ramer–Douglas–Peucker (0,35 dB).
  - **Ecos lanzados:** la mezcla del delay sube a ~3× al final de las frases seguidas de un hueco
    ≥ 0,6 s (como mucho uno cada 6 s), dos tiempos, y vuelve en 0,35 s.
  - **Reverb lanzada:** +22 en la mezcla del espacio antes de los huecos ≥ 1,8 s (uno cada 8 s).
  - **Ducking:** guitarras, teclados, pads, piano, FX y «Otro» llevan «Ducking bajo la voz
    (automático)»: −1,5 dB (−2 dB «Otro») mientras canta, frases a < 0,8 s unidas para no bombear.
  - **Barrido de filtro:** la música lleva al principio un EQ con el paso alto de 20 a 650 Hz en dos
    compases (exponencial) antes de cada entrada de la voz tras ≥ 6 s sin ella (intro, puente), y
    se abre de golpe al entrar.

  En **Efectos** las perillas de todos los efectos automatizados del rack se mueven al reproducir
  (los efectos llevan «∿»); en **Mezcla** la tira marca «∿» y su ayuda dice qué se automatizó, y el
  estado resume rides, lanzamientos, ducking y barridos. Las curvas se editan en la línea de
  automatización del efecto y se guardan con el proyecto.
- **Master IA:** `live_mix.apply_master` reproduce `master()` del V4.2 con medidas del motor:
  `Engine::measureMix()` procesa la sesión entera en memoria (un `RenderTask` propio con los
  plugins del master, sin archivo) y devuelve LUFS integrada, RMS y pico del master y de cada
  pista. Primero mide con la cadena a −24 dB (el limitador no actúa y el pico se lee a la entrada),
  lleva la mezcla a 0,88 de pico y a −18 LUFS, añade EQ, compresión si el crest pasa de 13 dB,
  color y nivel final, fija el techo del limitador del preset y ajusta la ganancia final hasta el
  objetivo sin pasar del presupuesto de limitación (si la mezcla es muy dinámica se queda corto y
  lo dice, como el original). «Según referencia» usa la sonoridad medida de la canción elegida.
- **Antes / Después:** dos pantallas juntas con el espectro y el nivel a la entrada del primer
  efecto activo y a la salida del último (`chainScope`, ~10 tomas/s mientras suena). Se conecta al
  rack del canal o al master. A / B puentea toda la cadena y la deja como estaba.
- **Medidores:** cada pista y el master llevan un `AfoMeterPlugin` (BS.1770: momentánea, corto
  plazo, integrada; RMS de 300 ms; pico). Las tiras de Mezcla eligen dB, LUFS o RMS; Master IA
  muestra las tres del master.
- **A/B de la mezcla automática** (Mezcla) puentea o activa todos los efectos que puso.
- El proyecto `.afo` guarda el nombre y la marca «mezcla automática» de cada efecto y el techo del
  limitador del master.

Comprobado: `tests/test_live_automation.py` (frases, ride, lanzamientos, ducking y barridos con
una voz sintética; el ride reduce en el render del motor la diferencia entre frase fuerte y suave;
la mezcla desde el puente escribe las curvas y el proyecto las guarda y recupera),
`tests/test_live_mix.py` (cadenas y faders reales; master −14 LUFS y pico ≤ −2 dB sin
escribir audio; A/B y quitar el master; el proyecto conserva la mezcla) y `--selftest` (mezcla y
master en vivo desde la interfaz, rack de la voz al elegir su tira, A/B, medidores dB/LUFS/RMS,
remezcla afinada, ningún WAV nuevo).

Comprobado: `tests/test_engine_fx.py` (13 pruebas de señal + dispositivo + grabación real) y
`--selftest`: «+ Voz», armar en una entrada real (si el dispositivo no tiene entradas, la
autoprueba cambia a ASIO4ALL como lo haría el usuario y al final vuelve al de antes), grabar 1 s y
ver la onda; insertar EQ y Analizador en una pista, espectro real del tono, bypass y quitar.
Vista inicial frente a la web: cabecera 12 % (los botones «Audio» y «Efectos», que la web no
tiene; el chip de Efectos va en la primera fila para no añadir otra fila de chips), lienzo 20 %.

## Fase 5: cómo se hizo

- `python -m allforone` abre la interfaz Qt Quick; `--nativo` se sigue aceptando y no hace nada.
- Retirados: `app/allforone/ui/` (index.html, afo_bridge.js, afo_panels.*), la ventana Qt WebEngine
  de `main.py`, los slots del grabador web (`takeBegin/Chunk/End`), `tests/test_template_fidelity.py`,
  `tools/visual_compare.py` y `docs/CAMBIOS_PLANTILLA.md`. El paquete ya no lleva Chromium
  (`package.ps1` falla si aparece `QtWebEngineProcess.exe`).
- Una sola autoprueba, `--selftest`: extensión nativa, motor, render del tono a 440 Hz y después
  toda la interfaz QML con el motor real (las comprobaciones del Mezclador V4.2 que hacía la web
  pasaron aquí; desde la mezcla en vivo comprueban cadenas, master y que no se escriban WAVs).
- QML ordenado: `Main.qml` y `theme/` (Theme, singleton), `controls/` (NeoButton, Knob, Fader,
  Meter, Lcd, Select, ModulePanel…), `modules/` (un cuerpo por módulo y el diálogo de audio),
  `state/` (Mixer, Sequencer y las librerías JS), `assets/` (fuentes Space Grotesk e icono).
  La plantilla de referencia vive en `templates/AllForOne/`.
- `tools/native_compare.py` compara ahora con la propia plantilla (dibujada con Qt WebEngine solo en
  esa herramienta de desarrollo, con la fuente local y el mismo encuadre inicial). A 1600×900:
  cabecera 37 % (la plantilla tiene 8 chips de módulo y AllForOne 12, más Audio, Efectos y el
  botón de tema: los chips se recolocan), lienzo 23,5 % (módulos que la plantilla no tiene, como
  Audios, Afinador y Mezcla, y el texto de las pistas reales).


## Rediseño de los módulos y flujo de DAW (noviembre 2026)

Referencia: `templates/AllForOne/REFERENCIA_PANELES.webp` (imagen del usuario).

- `controls/ModulePanel.qml`: marco del color del módulo, cabecera negra con el título en su color,
  chip blanco con el modelo, □ maximizar / ❐ restaurar y ✕; cuerpo crema (`Theme.panelColor`) con
  barra de desplazamiento. Doble clic en el título lo renombra; en la cabecera, maximiza. Las asas de
  tamaño solo aparecen al pasar el ratón.
- **Choques** (`Main.qml`): `slideTo` mueve por ejes y se detiene a 28 px del primer módulo que
  pisaría; `sizeTo` igual al redimensionar; `pushFrom` empuja hacia abajo a los que quedan debajo
  cuando un módulo crece (cola `queuePush`: `Qt.callLater` juntaría las llamadas y solo empujaría el
  último); `settleAll` ordena todo al abrir y al restaurar el diseño. Nada de esto actúa con un
  módulo maximizado.
- **Maximizar** (`toggleMax`, `fitMax`): el módulo llena el visor a zoom 1; los demás, los cables y
  los puertos se ocultan; Esc restaura. El diseño guardado conserva la posición previa.
- **Menú lateral** (`controls/SideMenu.qml`, 290 px): Módulos (miniatura `ShaderEffectSource`,
  nombre editable, ojo para mostrar / ocultar, **+** para otro rack o pista), Instrumentos y Efectos
  (familias de la Biblioteca nativa; las que aún no tienen módulos se listan en una línea «Por
  construir», sin botones). Los racks extra (`fx~2`, …) se guardan con su nombre y su pista.
- `layout.js` versión 3 (diseño de fábrica nuevo); guarda también `names`, `extra` y `targets`.
- **Pistas** (`modules/TracksBody.qml`): barra de edición (Mover, Cortar, Dividir, Duplicar,
  Borrar, Normalizar, Vol −/+, fundidos, rejilla, deshacer / rehacer, zoom), regla con compases
  (clic = ir ahí), clips de audio con su forma de onda según desplazamiento, ganancia y fundidos.
  Cada edición llama a `afo.clipEdit` (motor: `splitClip`, `setClipRange`, `setClipGain`,
  `setClipFades`, `setClips` para deshacer). El proyecto guarda los clips (`aclips`).
- **Mezcla**: caja CANALES / MIXER con tiras de cabecera de color, PAN, dB del fader, medidor estéreo
  del motor, S / M y la tira MASTER; el cable al rack lleva la etiqueta «PISTA → FX».
- **Batería**: Drum pad de 8 pads (teclas 1–8) que suenan en el motor y pueden grabar en el patrón.
- **VST3**: Instrumentos elige el sintetizador del motor o un VST3 («Abrir instrumento» muestra su
  ventana); el rack de Efectos acepta efectos VST3 («Abrir plugin»). Su estado viaja en el proyecto;
  si un plugin falta al abrir, se avisa y se sigue.

`--selftest` lo comprueba: ningún módulo solapado al abrir, arrastre que se detiene, maximizar y
restaurar, rack extra con nombre, el menú lleva al módulo, y dividir / recortar / fundidos /
normalizar / deshacer clips en el motor.

## Después de la fase 5: cierre del Hito 1 en la interfaz

- Cabecera: **Abrir** y **Guardar** proyecto junto al transporte (Ctrl+O, Ctrl+S, Ctrl+Mayús+S).
  No están en la plantilla: son funciones nuevas y alargan un poco la primera fila, lo que
  `tools/native_compare.py` ve como diferencia en la cabecera.
- `state/Project.qml` reúne la sesión de la interfaz y la reconstruye al abrir (`allforone/project.py`
  añade del motor los efectos, la automatización y las rutas de los audios).
- Módulo Efectos: selector de **Preset** con guardar / borrar los propios, y línea de
  **Automatización** del parámetro elegido con el cursor de reproducción; las perillas automatizadas
  llevan «∿» y siguen la curva mientras suena.


## Temas, tamaños fijos y flujo de mastering (noviembre 2026)

- **Temas** (`theme/Theme.qml`, `app/allforone/themes.py`): un objeto `base` con colores, estilo y
  colores de módulo; cada `templates/<Tema>/theme.json` se mezcla encima con `Theme.apply`. Fichas:
  `canvas`, `panelHead`, `chip`, `device*`, `knobArc/Track/Value`, `frame`, `border`, `radius`,
  `headHeight`, `knobStyle` (`metal` o `arc`), `canvasStyle` (puntos o rejilla)… El diseño guardado
  recuerda el tema. Professional: grises oscuros, sin marco grueso ni sombra dura, perillas de arco.
- **Tamaños fijos**: `ModulePanel` usa siempre `fixedHeight`; el contenido se desplaza dentro. Ya no
  hay altura automática ni empuje al crecer. `layout.js` versión 4.
- **Cables = flujo**: inst → piano → pistas; ia, cinta, audios → pistas; pistas → mezcla → fx y
  antes; mezcla → mastia (Mastering) → fxm (Efectos master) → master (Rebobinado).
- **Efectos** (`modules/FxBody.qml`): cadena horizontal de dispositivos como en un DAW (cabecera con
  activar, nombre, ◀ ▶ ≡ ✕; preset, gráfica, perillas en dos filas) y un hueco final «+ Agregar».
- **Mezcla**: la mezcla IA va arriba de la consola y solo mezcla. **Mastering**
  (`MasteringBody.qml`) es la mesa del master; **MASTERIZAR AUTOMÁTICAMENTE** (`AutoMasterBox.qml`)
  va bajo Efectos master; **Rebobinado** (`MasterBody.qml`) lista las versiones para cargar,
  renombrar, borrar y exportar.

## Estabilidad y diseño amigable (21 de noviembre de 2026)

Guía: `docs/GUIA_DISENO_INTERFAZ.md` (heurísticas de Nielsen, reglas de Shneiderman, WCAG 2.2,
leyes de Fitts y Hick, convenciones de los dispositivos de Ableton). Lo que se aplicó:

- **Barra de estado** fija abajo (`controls/StatusBar.qml`): dispositivo, frecuencia, búfer y
  latencia; «⚠ Sin salida de audio» en rojo con texto (clic abre ⚙ Audio); proyecto y «● cambios
  sin guardar (Ctrl+S)»; ayuda corta y zoom. Sustituye al cuadro de ayuda flotante. El título de la
  ventana lleva «●» con cambios sin guardar.
- **Espacio** reproduce o pausa; los tooltips del transporte dicen su atajo.
- **Confirmación en el sitio** (`NeoButton.confirm`): quitar una pista o borrar una versión de master
  pide un segundo clic («¿Quitar?» / «¿Borrar?» en rojo) antes de 3 s; si no, el botón vuelve solo.
- **Dispositivos de efecto** como en Ableton: activador de 14 px (área de 24), nombre tachado en
  bypass, doble clic en el nombre pliega la tarjeta, chip «AUTO» para lo que puso la mezcla automática,
  valores de las perillas a 11 px sin transparencias, botones de 24 × 24 px.
- **Contraste medido:** el selftest calcula la relación WCAG de cada par texto/fondo de los tres temas
  (`layoutCommand("contrast")`) y exige ≥ 4,5:1.
- **Driver de audio sin dispositivo abierto:** cambiarlo en marcha podía cerrar el programa dentro
  del driver (ASIO); ahora se guarda y se aplica al arrancar, con un botón «Reiniciar ahora».
- **Fallos:** los slots del puente devuelven el error en vez de lanzar; `logs/cierre.log` guarda la
  traza de un cierre inesperado y los avisos de QML van al registro.
- **AFO Limiter (AF-14)** cierra la cadena del master automático con el techo del preset y presets
  de mastering nuevos en EQ, compresor y saturador.
- **Perillas de los dispositivos:** mostraban siempre el valor por defecto (buscaban su índice con
  `indexOf` sobre una copia del parámetro); ahora lo buscan por id y enseñan el valor real del motor,
  también el que deja la mezcla o el master automático. Los botones ◀ ▶ ≡ de la cabecera salen al
  pasar el ratón o con la tarjeta elegida, para que el nombre quepa; el selector dice «Preset…».
