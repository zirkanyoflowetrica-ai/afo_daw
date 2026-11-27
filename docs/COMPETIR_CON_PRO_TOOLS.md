# Qué le falta a AllForOne para competir con Pro Tools (23-11-2026)

Revisión del código real (motor `native/src`, puente `bridge.py`, interfaz `qml/`), no de la
documentación. Cada punto dice qué hay hoy y qué haría falta. Orden: lo que un ingeniero echa de
menos en la primera hora de trabajo va primero.

## Lo que ya compite

| Área | AllForOne hoy |
|---|---|
| Motor | Tracktion Engine + JUCE en C++, compensación de latencia de plugins de Tracktion, VST3 (instrumentos y efectos) |
| Mezcla automática | En vivo: cadena real por pista, rides de voz, ecos y reverbs lanzados, ducking, barridos, master por objetivo LUFS |
| Edición de clips | mover, cortar, volumen de clip, fundidos, deshacer / rehacer de clips |
| Medición | pico, RMS, LUFS momentáneo / corto / integrado por pista y en el master |
| IA local | canciones con voz (ACE-Step) y composición MIDI (MIDI-LLM) sin nube; Pro Tools no tiene nada igual |
| Vista | Arreglo con curvas de automatización y consola con inserts (desde esta revisión) |
| Envíos y buses Aux | hasta 16 buses con sus efectos; envío por pista pre o post fader, solo seguro, guardado en el proyecto (23-11-2026) |

## Lo que falta (prioridad 1: imprescindible en un estudio)

1. ~~**Envíos y buses auxiliares.**~~ **Hecho (23-11-2026):** «+ Aux», envíos pre/post fader en cada
   tira de la consola, solo seguro y proyecto. Queda: automatizar el nivel del envío, envíos desde el
   módulo Mezcla y que la mezcla automática use una reverb compartida en vez de una por pista.
2. ~~**Automatización escrita en vivo.**~~ **Hecho (23-11-2026):** modos **Read / Touch / Latch / Write**
   por pista (botón R/T/L/W en Arreglo); mientras suena, el fader, el paneo (consola y módulo Mezcla) y
   las perillas de los efectos graban su curva; curvas de volumen y paneo de pista en el motor; editar
   puntos en los carriles (clic, arrastrar, clic derecho). Queda: automatizar el nivel de los envíos,
   modo Trim, deshacer de una pasada y que el fader se mueva solo siguiendo la curva en Read.
3. **Grabación seria.** Hay una toma por vez en la pista de voz. Faltan: armar varias pistas a la vez,
   **punch in / out**, pre-roll, **loop recording con tomas (playlists) y comping**, metrónomo (click)
   y cuenta atrás, y monitorización por entrada con su latencia mostrada.
4. **Grabación MIDI desde un teclado.** El MIDI llega por IA o importando `.mid`; no hay entrada MIDI
   de hardware ni grabación de notas, ni cuantización.
5. **Editor de notas libre (piano roll real).** Las pistas MIDI suenan y se ven, pero no se editan
   nota a nota; la rejilla de 16 pasos no sirve para piano, cuerdas ni voces.
6. **Deshacer global.** Hay deshacer en la edición de clips; falta para mezcla, efectos,
   automatización y pistas (historial único como Edit > Undo History).
7. **Rejilla, marcadores y bucle.** No hay marcadores de sección, rango de bucle en la regla, modos de
   rejilla / nudge ni ajuste al compás en la vista Arreglo.

## Prioridad 2: lo que separa un DAW de aficionado de uno profesional

8. **Ruteo de E/S**: salida de cada pista a bus o a salidas físicas, entradas por pista, más de 2
   canales de salida (cascos, monitores B). Pro Tools vive de su matriz I/O.
9. **Grupos y VCA**: mover varios faders juntos, solo/mute de grupo.
10. **Sidechain** en compresor y gate (por ejemplo bombo → bajo: la mezcla automática ya lo pide y hoy se salta
    como «ducking del bajo con el bombo»).
11. **Bounce / consolidar / congelar** pistas (freeze) para ahorrar CPU, y exportar stems por pista.
12. **Time-stretch y edición de tempo** (Elastic Audio): ajustar audio al tempo y cuantizar audio.
13. **Edición de voces a fondo**: Melodyne-like nota a nota, clip gain dibujado, crossfades
    automáticos al cortar. **Hecho (23-11-2026):** afinación **en tiempo real** como un plugin de
    afinación (AF-60: YIN + desplazador de tono en el motor, escala y tónica, velocidad, naturalidad,
    rango de voz; pantalla de nota y cents, gráfica de tono y teclado de escala).
14. **Rendimiento comprobado**: pruebas con 64–128 pistas y docenas de plugins, medidor de CPU / disco
    a la vista y aviso de dropouts.

## Prioridad 3: ecosistema y entrega

15. **Formatos**: AAX no es posible (es de Avid) y AU no existe en Windows; **CLAP** sería un plus.
    Importar / exportar **AAF / OMF** para intercambiar sesiones con Pro Tools, y MIDI de varias pistas.
16. **Vídeo** sincronizado (cine, publicidad) y código de tiempo / SMPTE.
17. **Surround y Dolby Atmos**: hoy todo es estéreo.
18. **Control por hardware**: superficies de control (Mackie Control / HUI) y atajos configurables.
19. **Sesiones colaborativas / respaldo**: autoguardado con versiones (hay recuperación de cierre,
    falta el historial de sesiones).

## Aspecto profesional (lo que se arregla en esta revisión)

- El tema por defecto pasa a **Professional**: grises planos, bordes de 1 px, sin sombras duras,
  perillas de arco y una franja del color de cada módulo (AllForOne claro / oscuro siguen en «Tema»).
- Los módulos tenían unos 400 colores y grosores escritos a mano (bordes negros de 2–3 px, sombras
  desplazadas) que el tema no podía cambiar; pasan a salir de `Theme.qml` (`line`, `border`,
  `buttonBorder`, sombras solo si el tema las tiene), como exige `AGENTS.md`.

## Orden de trabajo propuesto

1. ~~Envíos + buses Aux (motor y consola).~~ Hecho.
2. ~~Automatización Touch / Latch y edición de puntos en Arreglo.~~ Hecho.
3. Metrónomo, bucle, marcadores y rejilla en Arreglo.
4. Entrada MIDI + piano roll libre.
5. Grabación multipista con punch y tomas.
6. Deshacer global.
7. Sidechain y bounce / freeze.
