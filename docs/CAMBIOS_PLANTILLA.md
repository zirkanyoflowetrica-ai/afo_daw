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
