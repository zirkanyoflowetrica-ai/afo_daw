# Diseño de AllForOne como DAW de uso diario (investigación y plan, 23-11-2026)

> **26-11-2026:** §2 y §4 quedan sustituidos por `docs/FLUJO_PROFESIONAL.md` (IA dentro del flujo, un solo mezclador, menús, editor que sigue a la selección, Python).

El usuario pidió dejar atrás la idea modular (paneles sueltos en un lienzo) y una interfaz para usar
todos los días con todo lo que ya está integrado. Este documento resume cómo organizan la pantalla
los DAW que la gente usa a diario y fija la distribución nueva. Manda sobre la parte de «módulos» de
`AGENTS.md` §1; las reglas de color, contraste y «nada falso» siguen igual.

## 1. Qué tienen en común los DAW de uso diario

Se revisaron Ableton Live, Bitwig Studio, Logic Pro, Studio One, Cubase, FL Studio y Reaper. Las
ideas comunes son de interacción, no de aspecto: no se copia la apariencia de ninguno.

1. **Una sola ventana con zonas fijas.** Nada flota ni se solapa. Arriba van el transporte y el
   estado. A la izquierda, el inspector; a la derecha, el navegador (F2, noviembre 2026, como Logic y
   Cubase: los ajustes de lo elegido junto a sus pistas, el catálogo junto al lado donde se suelta). En
   el centro, la vista principal. Abajo, el detalle de lo seleccionado. Inspector y navegador no
   tienen pestañas: cada página es una sección plegable (la abierta ocupa el sitio y las demás quedan
   como títulos con su «?»). El editor de abajo (F3) tampoco tiene pestañas fijas: dice qué edita
   («EDITOR · Voz») y ofrece solo los modos de lo elegido: instrumento → notas, sonido y efectos;
   batería → patrón y efectos; audio y voz → efectos, tono (AF-64) y afinador (AF-60); master → efectos. La cabecera lleva solo vistas, transporte, tempo, tono y audio; abrir,
   guardar, Inicio y Crear IA están en los menús Archivo y Ver. Las zonas se pliegan, pero no se cambian de sitio: la memoria espacial es lo que
   hace rápido el uso diario.
   El reparto se ajusta a la pantalla (F12, noviembre 2026), sin huecos:
   - el navegador y el inspector miden el 21 % y el 25 % del ancho, con un máximo de 390 y 460 px;
   - el panel de abajo toma el alto del usuario hasta el 36 % del alto;
   - la cabecera pasa a dos filas antes que salirse;
   - las pestañas se estrechan;
   - las tiras del Mezclador alargan o acortan sus faders para llenar el alto.
   La autoprueba lo mide desde 1280×720 hasta el tamaño de la pantalla.
2. **Dos vistas grandes y nada más:** Arreglo (línea de tiempo) y Mezclador (consola). Se cambia
   con una tecla (Tab o F3 en varios DAW). El resto (piano roll, editor de audio, efectos) es
   *detalle* de lo seleccionado, no una vista aparte.
3. **La selección manda.**
   - Al elegir una pista, el inspector muestra sus ajustes y el panel de abajo su cadena de efectos.
   - Al elegir un efecto de la cadena, se abre su editor grande.
   - Al elegir un clip, se abre su editor (notas o audio).
   - La IA trabaja sobre el clip, desde su clic derecho (F4), en un cuadro junto al clip que dice
     dónde quedará el resultado. Rehacer y Alinear dejan una toma nueva en la misma pista (la
     cabecera de la pista elige cuál suena; Ctrl+Z la quita). Separar y Versión dejan pistas en la
     carpeta de la original, que se pliega sin silenciarlas. La barra del Arreglo no tiene botones
     fijos de IA.
   - Pista nueva (F5) es un solo diálogo: Audio, Instrumento, Batería, Voz, Intérprete IA, Generar
     con IA y Por piezas. Lo generado entra como pista y se regenera desde el Inspector como toma
     nueva; las variantes del laboratorio son las tomas de su pista. El Navegador ya no tiene IA y
     no hay vista Crear IA.
   - Un solo mezclador (F6): la mezcla automática es una orden del Mezclador (barra y menú Mezcla,
     ajustes en su diálogo, A/B en la barra, Ctrl+Z la deshace) y lo que pone se ve en las tiras con
     la marca «IA». Master automático es un dispositivo más del master, con su A/B en la tira MASTER. El
     Inspector ya no tiene Asistente IA.
   - Análisis del proyecto (F7): Editar › Analizar el proyecto escribe, bajo la regla del Arreglo,
     las secciones (A, B, A…) y la pista de acordes, y la tonalidad del proyecto. Ctrl+Z lo deshace.
   - Fondo (F10): Ver › Fondo… pone una imagen o capas de parallax detrás de las zonas (apagado de
     fábrica); los controles y los textos siguen sobre su superficie.
   - Scripts (F8): menú Scripts y Ctrl+K; cada script de `scripts/` corre aparte y un Ctrl+Z en el
     Arreglo deshace todo lo que hizo (`docs/SCRIPTS.md`).
   - El usuario nunca busca dónde está algo: está donde está lo seleccionado.
4. **Cadena de efectos como fila de dispositivos**, en el orden en que suena. Cada uno lleva el
   mismo marco: nombre, encendido/puenteo, preset, A/B y quitar. Se reordena arrastrando. Los
   efectos propios del programa y los VST3 se ven igual en la cadena; solo cambia lo de dentro del
   marco.
5. **El navegador es la puerta de todo lo que se añade:** sonidos, instrumentos, efectos nativos
   por categoría, VST3, archivos del proyecto y la biblioteca. Se arrastra a una pista o se hace
   doble clic.
6. **Color con propósito:**
   - Grises neutros de fondo.
   - El color de cada pista es casi el único color.
   - Un acento para la selección.
   - Rojo solo para grabar; verde/amarillo/rojo solo en medidores.
7. **Texto pequeño pero legible:**
   - Una sola familia.
   - Tres tamaños: título, etiqueta y valor.
   - Números de ancho fijo para que los valores no bailen.
8. **Uso diario:**
   - Pantalla de inicio con recientes.
   - Guardado automático y deshacer en todo.
   - Atajos visibles en los tooltips.
   - El estado (grabando, CPU, afinado, mezclando) siempre en la barra de estado.

## 2. Distribución nueva de AllForOne

```
┌──────────────── Cabecera: transporte · tempo · tonalidad · Artista › Lanzamiento › Canción · CPU ───────────────┐
│ Navegador │  Vista principal: ARREGLO  ⇄  MEZCLADOR (Tab)                         │ Inspector de la pista  │
│ (plegable)│                                                                       │ (plegable)             │
│ Inicio    │                                                                       │ volumen, paneo, envíos │
│ Efectos   │                                                                       │ salida, tipo y rol     │
│ VST3      │                                                                       │ (Mezcla automática), voz a     │
│ Sonidos   │                                                                       │ afinar                 │
│ IA        │                                                                       │ Asistente IA:          │
│ Archivos  │                                                                       │ Mezcla automática · Master automático  │
├───────────┴───────────────────────────────────────────────────────────────────────┴────────────────────────┤
│ Panel de detalle (lo seleccionado): [EQ]→[Comp]→[AF-60]→[Space] … + editor grande del efecto elegido       │
│ o editor del clip: piano roll / patrón de batería / audio (cortes, fundidos)                               │
└──────────────── Barra de estado: qué está pasando y qué hace el botón bajo el ratón ───────────────────────┘
```

### De los módulos actuales a su sitio

| Hoy (módulo) | Sitio nuevo |
|---|---|
| Pistas (`TracksBody`) | Cabeceras y clips del Arreglo + Inspector (la pestaña «Clips» se retiró el 25-11-2026) |
| Arreglo (`ArrangeView`) | Vista principal |
| Mezcla (`MixBody`) | Vista Mezclador (Tab) |
| Efectos (`FxBody`) | Panel de detalle: cadena de la pista elegida y editor del efecto elegido |
| Afinador (`TuneBody`) | **Editor del efecto nativo AF-60** dentro del panel de detalle (sale al elegir AF-60 en la cadena). La parte de la mezcla automática (voces e intensidad) va en la orden «Mezcla automática» (F6) |
| Master (`MasterBody`, `MasteringBody`), Master automático (`AutoMasterBox`), Antes/Después (`ReviewBody`) | Tira MASTER del Mezclador, Inspector › Master y, en Efectos › Master, el dispositivo Master automático y el Antes / Después (F6) |
| Instrumentos, Batería, Piano (`InstBody`, `DrumsBody`, `PianoBody`) | Panel de detalle al elegir una pista de instrumento o un clip MIDI |
| Cinta (`CintaBody`) | Grabación desde la cabecera de pista (armar ● y R); la cinta queda como medidor de entrada en el Inspector |
| IA (`IaBody`): canción, MIDI, **parte para el proyecto** | Navegador › IA (las generaciones entran como pistas) |
| Audios (`AudiosBody`) | Navegador › Archivos |
| Inicio / Biblioteca (X10, X11) | Pantalla de inicio (F4) y Navegador › Inicio |

El doble flujo (F7, Arreglo en otra ventana) se mantiene: la ventana aparte muestra la vista
principal y la ventana principal pasa al Mezclador.

### Uno de cada (25-11-2026)

El usuario vio dos mezcladores, dos paneles de pistas y dos editores de efectos, y pidió que todo
ocurra en uno de cada uno:

| Antes (duplicado) | Ahora (uno solo) |
|---|---|
| Consola bajo el Arreglo **y** vista Mezclador | **Vista Mezclador**: cada tira lleva sus inserts en orden (doble clic = abrirlo en Efectos, «+» = añadir uno), sus envíos a los buses Aux (nivel, PRE) y «+ AUX». El botón «Mezclador» del Arreglo lleva a ella |
| Pestaña «Clips» (`TracksBody`) **y** Arreglo | **Arreglo**: los clips de audio se eligen, mueven, recortan, cortan (S), duplican, borran, funden, cambian de volumen, normalizan, se rehacen o versionan con IA y se deshacen ahí mismo; la cabecera de cada pista la quita (con confirmación) o la separa con Demucs |
| Pestañas «Efectos» **y** «Efectos master» | **Efectos**: el master es un canal más (en el selector, en la tira MASTER del Mezclador o en el Arreglo); con el master elegido, debajo del rack va «Masterizar automáticamente». El Inspector solo enlaza a Efectos y Navegador › Efectos sigue siendo el catálogo |

## 3. Efectos nativos organizados

Todos salen del catálogo del motor C++ (`afo_audio.effect_catalog()`). El navegador los agrupa así:

| Categoría | Efectos |
|---|---|
| Dinámica | Compresor, Puerta, Limitador, De-esser |
| EQ y filtro | EQ paramétrico, Tira de canal |
| Tono y voz | **Afinador AF-60** (`tune`), Saturador |
| Espacio | Space (reverb), Delay digital |
| Utilidad | Ganancia, Analizador de espectro |

- La mezcla automática y el Master automático ponen estos mismos efectos, marcados «IA», y se editan igual que los
  puestos a mano.
- Desde el 23-11-2026 la mezcla automática afina por defecto con el AF-60 nativo, que queda en la cadena.
  La copia PSOLA es la opción «Copia precisa».

## 4. Plan por fases

1. **Esqueleto fijo** (X14): cabecera, navegador, vista principal Arreglo ⇄ Mezclador, inspector,
   panel de detalle y barra de estado. Se quitan el lienzo modular y el menú de módulos. Cada zona se
   pliega con un botón y su atajo.
2. **Panel de detalle de efectos** (X15): la cadena de la pista seleccionada como fila de
   dispositivos con el mismo marco; al elegir uno se abre su editor. El editor del AF-60 es el
   `TuneBody` actual, sin la parte de la mezcla automática.
3. **Navegador** (X16): efectos por categoría (tabla de arriba), VST3, IA, Archivos e Inicio; doble
   clic añade a la pista elegida.
4. **Inspector** (X17; F6 quitó el Asistente IA): ajustes de la pista, envíos, master y grabación;
   la IA de mezcla vive en el Mezclador y en el master.
5. **Editores de clip** (X18): piano roll, patrón de batería y audio en el panel de detalle.

Cada fase deja el programa usable y pasa el selftest (contraste ≥ 4,5:1, objetivos ≥ 24 px, nada
decorativo). Las fases visuales son de Codex (docs/TAREAS.md); los cambios de puente y motor que
pidan, de Claude.
