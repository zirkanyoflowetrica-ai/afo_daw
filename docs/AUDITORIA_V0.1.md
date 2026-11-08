# Auditoría inicial (V0.1)

Fecha: 2026-11-07. Fuentes analizadas: `PLANTILLA_DAW.html`, `Mezclador_Automatico.zip` (V4.2) y `E:\AFO`.

## 0. Estado de `E:\AFO`

A petición expresa del usuario, el contenido anterior de `E:\AFO` se **borró** antes de empezar
(no había carpeta `.git`; contenía `AGENTS.md`, `CMakeLists.txt`, `src/`, `libs/`, `.toolchains/`,
`installer/`, `tests/`, `tools/`, un `BUILD_ALLFORONE.ps1`, etc.). Ese código **no se ha podido
inspeccionar ni conservar**; AllForOne V0.1 parte de cero con los dos archivos que el usuario
colocó después (`PLANTILLA_DAW.html` y `Mezclador_Automatico.zip`), que se conservan intactos en
la raíz como referencia.

## 1. Plantilla: real / demostración / pendiente

| Módulo / función | En la plantilla | Estado en V0.1 |
|---|---|---|
| Lienzo infinito, rejilla de puntos, zoom (rueda, −/+, Ver todo) | Real (JS) | **Se conserva tal cual** |
| Paneles arrastrables / redimensionables (8 tiradores), Enfocar, ✕, chips de módulos | Real (JS) | Se conserva |
| Cables Bézier, conectores movibles en el perímetro, punto de curvatura | Real, **solo visual** | Se conserva; aún no representan routing del motor (V0.2/V0.3) |
| Restaurar diseño / persistencia de layout | `localStorage` | Funciona (perfil persistente de Qt WebEngine en `%LOCALAPPDATA%\AllForOne\web`). Formato `.afo` en V0.2 |
| Transporte ▶/■, tiempo, tempo | Temporizador JS | **Real: transporte del motor C++** |
| Pistas (Mesa MT-8): M/S/✕, selección | Real (datos JS) | Real para pistas de audio del motor; las de Instrumento/Batería/IA siguen siendo demo |
| Importar audio | No existía | **Real** (`+ Audio`: WAV/AIFF/FLAC/OGG/MP3 vía lectores de JUCE) |
| Formas de onda | Solo grabaciones del navegador | **Reales** para audio importado (picos leídos por el motor) |
| Mezcla (Consola 6C): faders, pan, medidores | Faders solo para la demo; pan sin efecto; medidores aleatorios | **Reales** para pistas del motor; medidores reales |
| Master VU: fader, aguja, L/R | Aleatorio | **Real** (pico); limitador/saturación/tono **pendientes** (V0.7) |
| Exportar mezcla | Mensaje sin exportar | **Real** (render del motor a WAV 24 bits) |
| Piano roll S-61 + teclado | Osciladores Web Audio | **DEMO** (etiquetado). MIDI real + VST3 en V0.4 |
| Instrumentos (Banco VST-1) | Lista ficticia con osciladores | **DEMO** (etiquetado). Hosting VST3 real en V0.3/V0.4 |
| Batería R-16 (16 pasos) | Ruido/osciladores Web Audio | **DEMO** (etiquetado). Sampler real en V0.4 |
| Grabador de cintas RX-2 | `MediaRecorder` del navegador; si falla el micrófono **inventa una toma** | Pendiente de grabación nativa (V0.4). Riesgo conocido: la toma simulada sigue existiendo si se niega el micrófono |
| Pistas con IA (AI-1) | Clips aleatorios, ya rotulado "Demostración" | **DEMO** (etiquetado). Modelos reales en V0.8 |

## 2. Mezclador Automático V4.2 — inventario

Línea base: `pytest -q` sobre el zip original sin cambios → **27 aprobadas** (Python 3.13, numpy 2.5.4,
scipy 1.18.1, pedalboard 0.9.26, gradio 6.x). Coincide con su `PRUEBAS.md`.

| Archivo | Líneas | API pública | Dependencias | Clasificación para la integración |
|---|---|---|---|---|
| `mixer_engine.py` | 775 | `render_mix`, `master`, `analyze`, `guess_type`, `is_backing_voice`, `is_lateral_voice`, `pan_from_filename`, `load_stem`, `stereo`, `save_wav`, `backing_position`, `Analysis`; 4 masters (`MASTERS`), `MAX_TRACKS=30`, `SR=44100` | numpy, scipy, pyloudnorm, soundfile, pedalboard + módulos locales | **Listo**: núcleo offline; se llamará desde un trabajador fuera del hilo de audio (V0.5) |
| `scale_tuner.py` | 298 | `tune_to_scale` (PSOLA), `track_pitch`, `allowed_notes`, `KEYS`, `SCALES` | numpy, scipy, pedalboard | **Listo** (V0.6). No se sustituye el PSOLA |
| `vocal_dsp.py` | 145 | `process_vocal`, `dynamic_cut`, `pitch_profile`, `phase_notes`, `compare_phase`, `vocal_effects` | numpy, scipy, pedalboard | Listo |
| `vocal_space.py` | 154 | `render_space`, `SpaceProfile` (reverb/delay por rol) | numpy, pedalboard | Listo |
| `track_tools.py` | 123 | `resonance_eq`, `section_balance`, `level_match_pair`, `repair_vocal`, `level_phrases` | numpy, scipy | Listo |
| `sonic_tools.py` | 75 | `saturation`, `parallel_compression`, `enhance_vocal/bus/master` | numpy, scipy, pedalboard | Listo |
| `spectral_tools.py` | 23 | `spectrum`, `excerpts`, `classification_excerpt` | numpy, scipy | Listo (útil para Antes/Después, V0.3) |
| `mastering_tools.py` | 73 | `true_peak_db`, `limit_linked`, `dynamics_summary` | numpy, scipy | Listo (V0.7) |
| `mix_templates.py` | 392 | 9 perfiles (`PROFILES`), `recommendations`, `export_guide`, `role_for`, modos `GUIDE_ONLY` / `SOFT_GUIDE` | stdlib | Listo |
| `music_analysis.py` | 296 | `analyze_music`, `backend_status`, `MusicResult` | numpy, scipy, soundfile, librosa; opcionales Essentia (WSL) y beat_this | **Requiere adaptación**: backends opcionales y rutas |
| `music_analysis_legacy.py` | 188 | `analyze_music` (librosa) | librosa | Listo (respaldo) |
| `music_confirmation.py` | 39 | `resolve_choice`, `signature` | stdlib | Listo |
| `audio_intelligence.py` | 61 | `identify_audio` | numpy, scipy | Listo |
| `drum_split.py` | 72 | `split_drums` (STFT) | numpy, scipy | Listo |
| `ai_classifier.py` | 80 | `recognize` (CLAP `laion/clap-htsat-unfused`) | torch, transformers (opcional, GB) | **Experimental / opcional** → "no instalado" si falta |
| `neural_drums.py` | 63 | `try_separate` (DrumSep) | modelo de terceros con licencia no aclarada; requiere opt-in | **Experimental**; no se activará sin revisar licencia |
| `essentia_helper.py` | 35 | `run` | Essentia en WSL | Experimental |
| `runtime_setup.py` | 27 | `ROOT`, `CACHE`, `logger`, `check_space` | stdlib | **Requiere adaptación** a `%LOCALAPPDATA%\AllForOne` |
| `app.py` | 371 | Interfaz Gradio + orquestación (`process`, `process_ui`, `preview_*`, `confirm_hybrid`) | gradio | **Se reemplaza la UI**; su orquestación se reutilizará con un adaptador. No se abrirá Gradio |
| `tests/` | 12 archivos | 27 pruebas | pytest | Se ejecutarán en cada versión que toque el mezclador |

Licencias a vigilar para V0.5+: `pedalboard` (GPLv3) y `praat-parselmouth` (GPLv3) son compatibles
con una distribución GPLv3/AGPLv3; los pesos de DrumSep no.

## 3. Herramientas de compilación

- La sesión de Claude solo tiene acceso a una **VM Linux** sobre el equipo del usuario, no a Windows:
  no puede ejecutar MSVC. El motor, la extensión, la interfaz y la autoprueba se compilaron y
  verificaron en Linux (GCC 13); la compilación Windows (MSVC + Ninja) la hace `build_and_run.bat`.
- Versiones fijadas: JUCE commit `19edd538` (8.0.6+19, el que fija Tracktion v3.2.0), Tracktion Engine
  `v3.2.0`, pybind11 3.1.0, PySide6 6.12.0, Nuitka 4.3.4, CMake 3.31.6, Ninja 1.13.2, Python 3.12.
