# AGENTS.md — reglas para trabajar en AllForOne

Especificación completa: `docs/MASTER_PROMPT.md`. Resumen de lo que no se negocia:

1. **Referencia visual:** `templates/AllForOne/PLANTILLA_DAW.html` (colores, tipografía, controles) y, para los
   paneles, `templates/AllForOne/REFERENCIA_PANELES.webp` (noviembre 2026, del usuario: color de cada
   sección, consola CANALES / MIXER). Es un DAW profesional, no un juego: una sola ventana con zonas
   fijas, sin lienzo de módulos flotantes (retirado el 24-11-2026). La interfaz es **nativa Qt Quick** (`app/allforone/qml/`, sin HTML ni Chromium; la web se
   retiró); `tools/native_compare.py` mide la diferencia con la plantilla (`docs/INTERFAZ_NATIVA.md`). Carpetas de QML:
   `theme/` (colores), `controls/` (botones, perillas, medidores…), `modules/` (cuerpo de cada
   módulo), `state/` (estado y lógica compartida), `assets/` (fuentes e icono). Algo que aún no
   funciona lo dice en su cuerpo; nunca se rellena con controles decorativos.
   **Temas:** cada carpeta de `templates/` con un `theme.json` es un tema (AllForOne es el de fábrica;
   Professional imita un DAW típico).
   **Distribución (23-11-2026):** se deja atrás la idea modular; una ventana con zonas fijas según
   `docs/DISENO_DAW.md` (navegador, Arreglo ⇄ Mezclador, inspector, panel de detalle de lo seleccionado). Los colores y estilos salen de `Theme.qml` (`Theme.apply`), nunca
   fijos en un módulo. Los módulos tienen tamaño fijo: solo cambia si lo cambia el usuario.
2. **Capas:** QML dibuja → `bridge.py` (objeto `afo`, slots de Qt, respuestas JSON) → Python coordina
   (`engine_host.py`) → C++ (`native/src/AfoEngine.*`, `AfoSynth.*` y la Biblioteca nativa en
   `native/src/fx/`, Tracktion + JUCE) procesa. Todo el sonido nuevo (síntesis, efectos, grabación)
   va en el motor C++, no en Python ni en la interfaz. Nunca pasar bloques de audio por el puente.
   Nunca ejecutar Python en el callback de audio.
3. **El motor se usa desde un solo hilo** (el principal de Qt). En Windows Qt despacha los mensajes
   de JUCE; en Linux `EngineHost.pump()` los procesa.
4. **Nada falso:** ni medidores aleatorios, ni "IA" con clips aleatorios sin la etiqueta DEMO, ni
   botones decorativos presentados como terminados, ni pruebas no ejecutadas dadas por buenas.
5. **Mezclador V4.2** (`app/allforone/mixer_v42/`): se reutiliza, no se reescribe. Sus 27 pruebas deben
   seguir pasando.
6. Ocultar ≠ silenciar ≠ desconectar.
7. **Interfaz amigable:** cada cambio de interfaz pasa la lista de `docs/GUIA_DISENO_INTERFAZ.md`
   (estado visible en la barra de estado, contraste ≥ 4,5:1 medido por el selftest en los tres temas,
   objetivos ≥ 24 px, confirmación en el sitio para lo destructivo, atajos en los tooltips).
8. **Fallos:** los slots del puente no lanzan (`@_safe` devuelve el error a la interfaz y lo registra);
   un cierre inesperado deja su traza en `logs/cierre.log` (`diagnostics.py`).
9. **IA local** (`docs/IA_LOCAL.md`): la generación de música corre en el equipo con el motor
   acestep.cpp (`motores/acestep`, procesos aparte, Vulkan) y modelos GGUF que se descargan desde la
   app a `modelos/acestep`; nada de servicios en la nube ni programas externos. `package.ps1`
   conserva `EXE\modelos`.

## Verificar

```
build_and_run.bat                      # Windows: entorno, CMake/MSVC, ctest, pytest, --selftest, arranca
package_windows.bat                    # Windows: EXE\AllForOne.exe + release\*.zip + release\*-Setup.exe (Inno Setup) + autoprueba
tools\package_partes.ps1               # lo mismo por partes (mitad de núcleos, pausas) y se retoma tras un apagón
python -m allforone --selftest         # desde app/: motor, render e interfaz QML (también AllForOne.exe --selftest)
python tools/native_compare.py         # diferencia píxel a píxel entre la plantilla y la interfaz
```
Linux (desarrollo): `cmake -G Ninja -B build/linux -DPython_EXECUTABLE=$(which python) && ninja -C build/linux`,
pruebas con `xvfb-run python -m pytest tests`.
Pruebas de mezcla, afinación y master: **proyectos completos** de varios géneros y voces
(`tests/song_factory.py`, `tests/test_proyectos_completos.py`), no solo tonos.

## Reparto entre IA (Claude y Codex)

El tablero es `docs/TAREAS.md`, una línea por tarea: `ID | dueño | estado | archivos | hecho cuando`.
Cada IA solo toca los archivos de sus tareas abiertas; para tocar otros, primero se apunta en el
tablero. Una tarea se cierra con commit en `main` («ID: …») y la prueba de su línea pasada.
