# AGENTS.md — reglas para trabajar en AllForOne

Especificación completa: `docs/MASTER_PROMPT.md`. Resumen de lo que no se negocia:

1. **Referencia visual:** `templates/AllForOne/PLANTILLA_DAW.html` (colores, tipografía, controles) y, para los
   módulos, `templates/AllForOne/REFERENCIA_PANELES.webp` (noviembre 2026, del usuario: marco grueso del color del
   módulo, cabecera negra con chip blanco del modelo, □ maximizar y ✕, consola CANALES / MIXER). Es un
   DAW profesional con otro flujo, no un juego: los módulos no se solapan y el menú lateral lleva a
   ellos. La interfaz es **nativa Qt Quick** (`app/allforone/qml/`, sin HTML ni Chromium; la web se
   retiró); `tools/native_compare.py` mide la diferencia con la plantilla (`docs/INTERFAZ_NATIVA.md`). Carpetas de QML:
   `theme/` (colores), `controls/` (botones, perillas, medidores…), `modules/` (cuerpo de cada
   módulo), `state/` (estado y lógica compartida), `assets/` (fuentes e icono). Algo que aún no
   funciona lo dice en su cuerpo; nunca se rellena con controles decorativos.
   **Temas:** cada carpeta de `templates/` con un `theme.json` es un tema (AllForOne es el de fábrica;
   Professional imita un DAW típico). Los colores y estilos salen de `Theme.qml` (`Theme.apply`), nunca
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

## Verificar

```
build_and_run.bat                      # Windows: entorno, CMake/MSVC, ctest, pytest, --selftest, arranca
package_windows.bat                    # Windows: EXE\AllForOne.exe + release\*.zip + autoprueba en .cache\tmp
python -m allforone --selftest         # desde app/: motor, render e interfaz QML (también AllForOne.exe --selftest)
python tools/native_compare.py         # diferencia píxel a píxel entre la plantilla y la interfaz
```
Linux (desarrollo): `cmake -G Ninja -B build/linux -DPython_EXECUTABLE=$(which python) && ninja -C build/linux`,
pruebas con `xvfb-run python -m pytest tests`.
