# Diseño de AllForOne como DAW de uso diario (investigación y plan, 23-11-2026)

El usuario pidió dejar atrás la idea modular (paneles sueltos en un lienzo) y una interfaz para usar
todos los días con todo lo que ya está integrado. Este documento resume cómo organizan la pantalla
los DAW que la gente usa a diario y fija la distribución nueva. Manda sobre la parte de «módulos» de
`AGENTS.md` §1; las reglas de color, contraste y «nada falso» siguen igual.

## 1. Qué tienen en común los DAW de uso diario

Se revisaron Ableton Live, Bitwig Studio, Logic Pro, Studio One, Cubase, FL Studio y Reaper. Las
ideas comunes son de interacción, no de aspecto: no se copia la apariencia de ninguno.

1. **Una sola ventana con zonas fijas.** Nada flota ni se solapa. Arriba van el transporte y el
   estado. A la izquierda, el navegador. En el centro, la vista principal. Abajo, el detalle de lo
   seleccionado. Las zonas se pliegan, pero no se cambian de sitio: la memoria espacial es lo que
   hace rápido el uso diario.
2. **Dos vistas grandes y nada más:** Arreglo (línea de tiempo) y Mezclador (consola). Se cambia
   con una tecla (Tab o F3 en varios DAW). El resto (piano roll, editor de audio, efectos) es
   *detalle* de lo seleccionado, no una vista aparte.
3. **La selección manda.**
   - Al elegir una pista, el inspector muestra sus ajustes y el panel de abajo su cadena de efectos.
   - Al elegir un efecto de la cadena, se abre su editor grande.
   - Al elegir un clip, se abre su editor (notas o audio).
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
│ VST3      │                                                                       │ (Mezcla IA), voz a     │
│ Sonidos   │                                                                       │ afinar                 │
│ IA        │                                                                       │ Asistente IA:          │
│ Archivos  │                                                                       │ Mezcla IA · Master IA  │
├───────────┴───────────────────────────────────────────────────────────────────────┴────────────────────────┤
│ Panel de detalle (lo seleccionado): [EQ]→[Comp]→[AF-60]→[Space] … + editor grande del efecto elegido       │
│ o editor del clip: piano roll / patrón de batería / audio (cortes, fundidos)                               │
└──────────────── Barra de estado: qué está pasando y qué hace el botón bajo el ratón ───────────────────────┘
```

### De los módulos actuales a su sitio

| Hoy (módulo) | Sitio nuevo |
|---|---|
| Pistas (`TracksBody`) | Cabeceras de pista del Arreglo + Inspector |
| Arreglo (`ArrangeView`) | Vista principal |
| Mezcla (`MixBody`) | Vista Mezclador (Tab) |
| Efectos (`FxBody`) | Panel de detalle: cadena de la pista elegida y editor del efecto elegido |
| Afinador (`TuneBody`) | **Editor del efecto nativo AF-60** dentro del panel de detalle (sale al elegir AF-60 en la cadena). La parte de la Mezcla IA (voces e intensidad) pasa al Asistente IA |
| Master (`MasterBody`), Master IA (`MasteringBody`), Antes/Después (`ReviewBody`) | Pista Master en el Mezclador + Asistente IA |
| Instrumentos, Batería, Piano (`InstBody`, `DrumsBody`, `PianoBody`) | Panel de detalle al elegir una pista de instrumento o un clip MIDI |
| Cinta (`CintaBody`) | Grabación desde la cabecera de pista (armar ● y R); la cinta queda como medidor de entrada en el Inspector |
| IA (`IaBody`): canción, MIDI, **parte para el proyecto** | Navegador › IA (las generaciones entran como pistas) |
| Audios (`AudiosBody`) | Navegador › Archivos |
| Inicio / Biblioteca (X10, X11) | Pantalla de inicio (F4) y Navegador › Inicio |

El doble flujo (F7, Arreglo en otra ventana) se mantiene: la ventana aparte muestra la vista
principal y la ventana principal pasa al Mezclador.

## 3. Efectos nativos organizados

Todos salen del catálogo del motor C++ (`afo_audio.effect_catalog()`). El navegador los agrupa así:

| Categoría | Efectos |
|---|---|
| Dinámica | Compresor, Puerta, Limitador, De-esser |
| EQ y filtro | EQ paramétrico, Tira de canal |
| Tono y voz | **Afinador AF-60** (`tune`), Saturador |
| Espacio | Space (reverb), Delay digital |
| Utilidad | Ganancia, Analizador de espectro |

- La Mezcla IA y el Master IA ponen estos mismos efectos, marcados «IA», y se editan igual que los
  puestos a mano.
- Desde el 23-11-2026 la Mezcla IA afina por defecto con el AF-60 nativo, que queda en la cadena.
  La copia PSOLA es la opción «Copia precisa».

## 4. Plan por fases

1. **Esqueleto fijo** (X14): cabecera, navegador, vista principal Arreglo ⇄ Mezclador, inspector,
   panel de detalle y barra de estado. Se quitan el lienzo modular y el menú de módulos. Cada zona se
   pliega con un botón y su atajo.
2. **Panel de detalle de efectos** (X15): la cadena de la pista seleccionada como fila de
   dispositivos con el mismo marco; al elegir uno se abre su editor. El editor del AF-60 es el
   `TuneBody` actual, sin la parte de Mezcla IA.
3. **Navegador** (X16): efectos por categoría (tabla de arriba), VST3, IA, Archivos e Inicio; doble
   clic añade a la pista elegida.
4. **Inspector y Asistente IA** (X17): ajustes de la pista, envíos y la Mezcla IA / Master IA /
   A/B en un mismo sitio.
5. **Editores de clip** (X18): piano roll, patrón de batería y audio en el panel de detalle.

Cada fase deja el programa usable y pasa el selftest (contraste ≥ 4,5:1, objetivos ≥ 24 px, nada
decorativo). Las fases visuales son de Codex (docs/TAREAS.md); los cambios de puente y motor que
pidan, de Claude.
