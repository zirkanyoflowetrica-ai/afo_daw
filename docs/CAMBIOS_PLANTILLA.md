# Diferencias intencionales respecto a `PLANTILLA_DAW.html`

`PLANTILLA_DAW.html` (raíz del proyecto) es la fuente de verdad visual y **no se modifica**.
La interfaz que carga AllForOne es `app/allforone/ui/index.html`, que es esa misma plantilla con
**3 líneas** distintas. La prueba `tests/test_template_fidelity.py` falla si aparece cualquier
otra diferencia.

## Cambios en el HTML (3 líneas)

| Línea | Original | AllForOne | Problema que resuelve |
|---|---|---|---|
| 7 | `<link href="https://fonts.googleapis.com/...Space+Grotesk...">` | `<link href="fonts/space-grotesk.css">` | La app debe funcionar sin Internet. Se sirve la misma familia **Space Grotesk** (OFL 1.1) desde `ui/fonts/`, con el mismo nombre de familia, así que el CSS original no cambia. |
| 401 | — | `<script src="qrc:///qtwebchannel/qwebchannel.js">` | Biblioteca de Qt para hablar con Python. |
| 402 | — | `<script src="afo_bridge.js">` | Puente con el motor (ver abajo). |

El CSS original **no se ha tocado** (ni una regla).

## Cambios de comportamiento (en `afo_bridge.js`, sin editar la plantilla)

`afo_bridge.js` se ejecuta después del script de la plantilla y envuelve sus funciones globales.
Solo actúa cuando el motor nativo está conectado; si no, la plantilla funciona igual que en el navegador.

| Elemento | Antes (plantilla) | Ahora | Motivo |
|---|---|---|---|
| ▶ Reproducir / ■ | Temporizador `setInterval` de JavaScript | Transporte del motor C++ (Tracktion). El cursor, el tiempo `compás.tiempo` y el secuenciador de la demo siguen la posición real del motor | Audio real; el motor es el reloj |
| Medidores de canal y L/R | `Math.random()` | Pico real del motor en dBFS (escala −60…0 dB) | Prohibido mostrar medidores falsos |
| Aguja VU | `Math.random()` | Promedio de picos L/R con balística aproximada (~300 ms) | Igual. **No es una medición de sonoridad**: LUFS y true peak llegan en V0.7 |
| Fader master | 85 por defecto, sin efecto en audio | 70 por defecto = 0 dB; controla la ganancia real | Ley de fader: `dB = 40·log10(pos/70)` → 70 = 0 dB, 100 = +6,2 dB, 35 = −12 dB, 0 = silencio |
| Faders y Pan de pista | Solo visuales (pan sin efecto) | Ganancia y paneo reales en las pistas del motor | |
| M / S | Solo afectaban a la demo | También mute/solo del motor (la exportación respeta mute/solo) | |
| Exportar mezcla | Mensaje "lista para exportar" sin exportar | Render real del motor a WAV 24 bits con diálogo de guardado | |
| Tempo | Solo la demo | También el tempo del motor | |
| Barra de Pistas | `+ Instrumento + Batería + IA + Voz` | **`+ Audio`** y **`+ Tono de prueba`** al principio | Importar audio real; el tono (440 Hz, −12 dBFS, sintético) sirve para comprobar el motor |
| Subtítulo de pistas Instrumento / Batería / IA | `Instrumento: Piano de cola` | `Instrumento: DEMO · Piano de cola` | Su sonido sigue siendo la demostración Web Audio de la plantilla; el usuario debe poder distinguirlo |
| Pistas de audio | — | Tipo nuevo "Audio" con forma de onda real (600 picos leídos del archivo por el motor) y subtítulo `Audio: mm:ss · motor nativo` | |
| Limitador | Botón sin efecto | Igual, con aviso `title` "Pendiente (V0.7)" | No se presenta como función terminada |

## Comparación medida

`tools/visual_compare.py` renderiza la plantilla original y AllForOne en Qt WebEngine a 1600×900
con almacenamiento limpio y compara píxel a píxel (umbral 24/255):

- **0,35 % de píxeles distintos** (15 de 920 celdas de 40 px).
- Todas las zonas cambiadas están en la cabecera de la tabla de Pistas (botones nuevos) y en los
  subtítulos "DEMO ·". Fondo, cabeceras, colores, bordes, sombras, cables, conectores, perillas,
  faders, piano roll, secuenciador y tipografía: idénticos.

Capturas: `docs/visual/original.png`, `docs/visual/allforone.png`, `docs/visual/diff.png`.


## V0.2 — Paneles del Mezclador V4.2, tema oscuro e icono

Todo se añade sin editar `index.html` (sigue siendo plantilla + 3 líneas). `afo_bridge.js` carga
`afo_panels.css`, `afo_theme_dark.css` y `afo_panels.js`.

### Módulos nuevos en el mismo lienzo (misma estructura que los originales)

Se registran en `PANELS`/`POS`/`PC` de la plantilla, así que tienen cabecera negra, chip en
«Módulos», Enfocar, ✕, 8 tiradores, conectores, cables con curva y posición guardada.

| Módulo | Color | Contenido (del Mezclador V4.2) |
|---|---|---|
| Mezcla IA · Auto-Mix V4.2 | `#ff9f45` | Zona para arrastrar stems y referencia, lista con tipo y rol editables (P/B/L/R/B_L/B_R), plantilla artística (9 guías trap/rap), modo (Solo guía / Guía + balance sutil), escalón L/R (5–10 dB), espacio vocal, **MEZCLAR AUTOMÁTICAMENTE**, **REMEZCLAR**, progreso e historial |
| Afinador · PSOLA AT-1 | `#7ae7ff` | Análisis Automático/Asistido/Manual, tónica, escala, BPM, Analizar música, Confirmar, intensidad 0–100 %, voces a afinar |
| Master IA · Master M-4 | `#ff6b9a` | 4 masters + master según referencia con LUFS, true peak y limitación reales; A/B; enviar a Pistas; ZIP; abrir carpeta |
| Antes / Después · A/B Comp | `#e6d3a3` | Comparación A/B por pista al mismo volumen y decisiones del mezclador |

Cables nuevos: Pistas → Mezcla IA → Master IA → Mezcla final; Afinador → Mezcla IA; Mezcla IA → Antes/Después.
Estilos nuevos solo con clases propias (`.afo-*`), mismo lenguaje (bordes negros, sombras sólidas, LCD ámbar).

### Tema oscuro (botón ◐ en la cabecera)

`afo_theme_dark.css` solo actúa con `<html data-theme="dark">`. Misma composición, componentes y
colores de módulo; superficies oscuras teñidas con el color de cada módulo y sombras sólidas de su
color. El tema claro original no cambia. La preferencia se recuerda en el equipo.

### Icono

`ui/icon.svg` → `icon.ico` (16–256 px): diseño original «todos en uno», ocho señales con los colores
de los módulos convergiendo en un único conector. Se usa en la ventana y en `AllForOne.exe`.
