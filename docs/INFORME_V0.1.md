# Informe de entrega — AllForOne V0.1 «Plantilla nativa compilada»

Fecha: 2026-11-07

## Resumen

V0.1 está **compilada, probada, empaquetada e instalada en Windows 11** (equipo del usuario,
2026-11-07): `build_and_run.bat` → `package_windows.bat` → `install_windows.bat`. También se verificó
en Linux durante el desarrollo.

## Resultados en Windows 11 Pro (build 26300, MSVC 14.51 / VS Build Tools 2026, Python 3.12.10)

| Paso | Resultado |
|---|---|
| Python | El instalador MSI de winget falló (código 1603). Solución: Python 3.12.10 portátil oficial (NuGet) en `.toolchains`, sin administrador |
| Compilación CMake + Ninja + MSVC | OK: `afo_audio.cp312-win_amd64.pyd` (10,9 MB), ~1,5 min |
| `ctest` (pruebas nativas) | OK |
| `pytest` | 9/9 OK |
| `--selftest` desde el código | OK, **incluida la reproducción en tiempo real**: WASAPI («Windows Audio», 48 kHz, buffer 480), transporte avanza 1,0 s, medidor master −6 dBFS con audio real |
| Nuitka standalone | OK en 2,0 min → `dist\AllForOne\AllForOne.exe` + ZIP de 194 MB |
| `AllForOne.exe --selftest` desde una copia en `%TEMP%`, PATH limpio | OK (todas las comprobaciones, incluido audio en tiempo real) |
| Uso real del `.exe` | Abre la plantilla (≈5 s de pantalla blanca mientras inicia Qt WebEngine); `+ Tono de prueba`, ▶ (el tiempo avanza a 2.1), ■ y cierre limpio |
| Instalación | `%LOCALAPPDATA%\Programs\AllForOne` + accesos directos (menú Inicio y escritorio) |

Fallos reales encontrados y corregidos en Windows:
1. **WAV corrupto al sobrescribir** un archivo existente (los streams de JUCE no truncan). Ahora se
   borra antes de renderizar; prueba nativa nueva.
2. **Medidores con dos lectores**: el pico se "lee y borra" y la interfaz y la autoprueba competían.
   Ahora hay un único lector (`EngineHost.read_levels`).
3. `afo_audio.pyd` bloqueado por una instancia abierta: los scripts cierran antes cualquier
   AllForOne lanzado desde la carpeta del proyecto.
4. PowerShell 5.1: precedencia de `,` sobre `+` y argumentos con espacios mal entrecomillados
   rompían la llamada a Nuitka.

Nota: el dispositivo por defecto que abrió el motor fue la salida HDMI («SMART TV»), no la
Behringer UMC22. Falta un selector de dispositivo (V0.2).

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
| Nuitka 4.3.4 standalone (Linux, 4,3 min, 526 MB) copiado a `/tmp` y ejecutado con entorno vacío (`env -i`, sin Python ni PYTHONPATH) `--selftest` | **OK**: las mismas 16 comprobaciones que en desarrollo (`frozen: True`); incluye Qt WebEngine, plantilla, fuentes y `afo_audio` |

**Pendiente:** prueba con la UMC22 como salida (requiere selector de dispositivo) y en una VM de
Windows limpia (la prueba en `%TEMP%` con PATH limpio sí se hizo).

## Compilación

- Linux: `afo_audio.cpython-313-x86_64-linux-gnu.so` (24 MB) y `afo_engine_tests`; 33 unidades de
  compilación, ~1,5 min con 2 núcleos tras configurar.
- Nuitka (Linux): carpeta standalone de 526 MB con `QtWebEngineProcess`, recursos `.pak`, `allforone/ui` y `allforone/_native/afo_audio.so`. Mismas opciones que usa `tools/package.ps1` en Windows.
- Windows: `build\win-release\`, salida `app\allforone\_native\afo_audio.cp312-win_amd64.pyd`;
  ejecutable en `dist\AllForOne\AllForOne.exe` tras `package_windows.bat`.

## Interfaz

`app/allforone/ui/index.html` = plantilla + 3 líneas (verificado por test). CSS sin cambios.
Capturas en `docs/visual/`.

## Rendimiento

Sin mediciones en tiempo real todavía (no hay dispositivo en la VM). Render offline de 8 s de
audio estéreo: ~0,1 s. Polling de estado UI: 33 ms.

## Errores conocidos / riesgos

1. ≈5 s de ventana en blanco al arrancar el `.exe` (inicio de Qt WebEngine). Mejorable con una pantalla de carga.
2. Si no hay dispositivo de salida abierto, ▶ muestra un aviso en vez de reproducir (correcto, pero
   aún no hay selector de dispositivo: llega en V0.2/V0.4).
3. Las pistas Instrumento/Batería siguen sonando por Web Audio (DEMO), en paralelo al motor.
4. El grabador puede crear una toma simulada si se deniega el micrófono (heredado de la plantilla).
5. Licencia: AGPLv3 (`LICENSE`), compatible con JUCE y Tracktion para publicarlo gratis en GitHub.

## Git

Checkpoint `v0.1` en el repositorio local de `E:\AFO`.

## Siguiente versión (V0.2)

Formato `.afo` versionado (pistas, clips, layout, zoom, cables), plantillas vacía/demo, importación
múltiple con colocación en el tiempo, zoom horizontal/vertical de pistas, selector de dispositivo de
audio, cables sincronizados con el routing real.
