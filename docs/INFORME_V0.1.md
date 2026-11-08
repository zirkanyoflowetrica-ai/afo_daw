# Informe de entrega — AllForOne V0.1 «Plantilla nativa compilada»

Fecha: 2026-11-07

## Resumen honesto

Todo el código de V0.1 está escrito y **verificado en Linux** (motor C++ compilado, extensión Python,
interfaz, puente, autoprueba, comparación visual y empaquetado con Nuitka). **Todavía no se ha
compilado en Windows**: la sesión de desarrollo solo tenía acceso a una VM Linux, sin MSVC. El primer
`build_and_run.bat` en el equipo del usuario es, por tanto, la primera compilación Windows real; los
scripts están preparados para detenerse y registrar cualquier error en `logs\`.

## Implementado (real y verificado)

- **Motor nativo C++20** (`native/src/AfoEngine.*`) sobre **Tracktion Engine v3.2.0 + JUCE 8.0.6+19**:
  Edit, pistas de audio con clip, ganancia, paneo, mute, solo, master, tempo, transporte
  (play/pausa/stop/posición), medidores por pista y master (LevelMeasurer, picos reales),
  formas de onda (picos leídos del archivo), render offline a WAV 24 bits que respeta mute/solo,
  tono de prueba sintético, medición de pico/RMS de archivos.
- **Extensión `afo_audio`** (pybind11, API v1): `afo_audio.pyd` en Windows (`.so` en Linux).
- **Aplicación PySide6 + Qt WebEngine** que carga la plantilla original desde archivos locales
  (sin servidor, sin Internet, fuente Space Grotesk local).
- **QWebChannel**: objeto `afo` con `hello, togglePlay, stop, setTempo, setMasterVolume,
  setTrackVolume, setTrackPan, setTrackStates, importAudio, addTestTone, removeTrack, exportMix`
  y la señal `stateChanged` (~30 Hz: posición, reproducción, niveles).
- **Controles de la plantilla conectados al motor**: ▶/■, tempo, fader master, faders y pan de
  pista, M/S, ✕, Exportar mezcla, medidores L/R y de canal, aguja VU; botones `+ Audio` y
  `+ Tono de prueba`. Detalle en `docs/CAMBIOS_PLANTILLA.md`.
- **Autoprueba integrada** `AllForOne --selftest` (también en el .exe): informe JSON + captura.
- **Scripts Windows**: `build_and_run.bat` (detecta e instala dependencias, compila, prueba,
  arranca) y `package_windows.bat` (Nuitka standalone + autoprueba desde una copia en `%TEMP%`
  con entorno limpio + ZIP).

## No implementado (pendiente, por versión)

- V0.2: formato `.afo`, proyecto vacío/demo, zoom horizontal/vertical de pistas, edición de clips,
  cables como routing real, pantalla completa por módulo.
- V0.3: escaneo/hosting VST3, racks, inspector, Antes/Después.
- V0.4: grabación nativa (el grabador sigue usando el navegador y **puede inventar una toma** si
  falla el micrófono), MIDI real, piano roll/batería/instrumentos reales (hoy **DEMO** Web Audio, rotulado).
- V0.5–V0.7: Mezclador V4.2, afinador, análisis, mastering (limitador, LUFS, true peak).
- ASIO desactivado (requiere SDK de Steinberg): se usan WASAPI y DirectSound. La Behringer UMC22
  funciona por WASAPI; su driver ASIO no se usa todavía.

## Pruebas ejecutadas (Linux x86_64, GCC 13.3, Python 3.13.18, Xvfb, sin tarjeta de sonido)

| Comando | Resultado |
|---|---|
| `pytest -q` en el zip original del Mezclador V4.2 (línea base, sin cambios) | **27 aprobadas** |
| `ctest` → `afo_engine_tests` | **16/16 OK**: tono −12,00 dBFS; pista −6 dB → −18,00 dBFS exactos; solo de pista a −20 dB → −32,00 dBFS; todo silenciado → no exporta; picos; tempo; master 0 dB; borrar pistas |
| `xvfb-run pytest -q tests` | **9 aprobadas**: fidelidad de la plantilla (índice = original + 3 líneas, colores, fuente local, sin `Math.random`), ley de fader, render −24,04 dBFS con FFT a 440 Hz, paneo total a la izquierda, estado del transporte, autoprueba completa en subproceso |
| `python -m allforone --selftest` | **OK**: importa afo_audio, motor, pista 8 s, forma de onda, render −12 dBFS, 440 Hz por FFT, WebEngine carga la plantilla, JS→Python, 8 módulos, fondo `#fff1c9`, Space Grotesk cargada, cabeceras negras, medidores sin aleatorio, clic en `+ Tono de prueba` crea la pista en C++ y se dibuja con 600 picos. **Reproducción en tiempo real: omitida** (sin dispositivo de audio en la VM) |
| `tools/visual_compare.py` (1600×900) | **0,35 % de píxeles distintos**, solo en los botones nuevos y subtítulos DEMO |
| Nuitka 4.3.4 standalone (Linux) + `--selftest` del binario | ver sección Compilación |

**No ejecutado todavía (requiere tu Windows):** compilación MSVC, reproducción por WASAPI con la
UMC22, medidores con audio sonando en tiempo real, `AllForOne.exe` empaquetado, prueba en Windows
limpio/VM. `build_and_run.bat` y `package_windows.bat` ejecutan exactamente esas comprobaciones.

## Compilación

- Linux: `afo_audio.cpython-313-x86_64-linux-gnu.so` (24 MB) y `afo_engine_tests`; 33 unidades de
  compilación, ~1,5 min con 2 núcleos tras configurar.
- Windows: `build\win-release\`, salida `app\allforone\_native\afo_audio.cp312-win_amd64.pyd`;
  ejecutable en `dist\AllForOne\AllForOne.exe` tras `package_windows.bat`.

## Interfaz

`app/allforone/ui/index.html` = plantilla + 3 líneas (verificado por test). CSS sin cambios.
Capturas en `docs/visual/`.

## Rendimiento

Sin mediciones en tiempo real todavía (no hay dispositivo en la VM). Render offline de 8 s de
audio estéreo: ~0,1 s. Polling de estado UI: 33 ms.

## Errores conocidos / riesgos

1. Primera compilación MSVC no probada: posibles avisos/errores específicos de MSVC en Tracktion.
2. Si no hay dispositivo de salida abierto, ▶ muestra un aviso en vez de reproducir (correcto, pero
   aún no hay selector de dispositivo: llega en V0.2/V0.4).
3. Las pistas Instrumento/Batería siguen sonando por Web Audio (DEMO), en paralelo al motor.
4. El grabador puede crear una toma simulada si se deniega el micrófono (heredado de la plantilla).
5. Licencia del proyecto sin decidir (ver `THIRD_PARTY_NOTICES.md`).

## Git

Checkpoint `v0.1` en el repositorio local de `E:\AFO`.

## Siguiente versión (V0.2)

Formato `.afo` versionado (pistas, clips, layout, zoom, cables), plantillas vacía/demo, importación
múltiple con colocación en el tiempo, zoom horizontal/vertical de pistas, selector de dispositivo de
audio, cables sincronizados con el routing real.
