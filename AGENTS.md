# AGENTS.md — reglas para trabajar en AllForOne

Especificación completa: `docs/MASTER_PROMPT.md`. Resumen de lo que no se negocia:

1. **`PLANTILLA_DAW.html` es la referencia visual.** No se rediseña. La app pasa a interfaz
   **nativa Qt Quick** (`app/allforone/qml/`, sin HTML ni Chromium) por fases
   (`docs/INTERFAZ_NATIVA.md`); debe igualar la plantilla, medido con `tools/native_compare.py`.
   Mientras dure la migración la interfaz web sigue siendo la predeterminada:
   `app/allforone/ui/index.html` = plantilla + 3 líneas (ver `docs/CAMBIOS_PLANTILLA.md`;
   `tests/test_template_fidelity.py` lo vigila) y su lógica va en `afo_bridge.js`. La web se retira
   solo cuando la nativa haga todo lo que hace ella. Un módulo aún no migrado lo dice en su cuerpo;
   nunca se rellena con controles decorativos.
2. **Capas:** JS dibuja → QWebChannel (`bridge.py`, objeto `afo`, respuestas JSON) → Python coordina
   (`engine_host.py`) → C++ (`native/src/AfoEngine.*`, Tracktion + JUCE) procesa. Nunca pasar bloques
   de audio por QWebChannel. Nunca ejecutar Python en el callback de audio.
3. **El motor se usa desde un solo hilo** (el principal de Qt). En Windows Qt despacha los mensajes
   de JUCE; en Linux `EngineHost.pump()` los procesa.
4. **Nada falso:** ni medidores aleatorios, ni "IA" con clips aleatorios sin la etiqueta DEMO, ni
   botones decorativos presentados como terminados, ni pruebas no ejecutadas dadas por buenas.
5. **Mezclador V4.2** (`Mezclador_Automatico.zip`): se reutiliza, no se reescribe. Sus 27 pruebas deben
   seguir pasando.
6. Ocultar ≠ silenciar ≠ desconectar.

## Verificar

```
build_and_run.bat                      # Windows: entorno, CMake/MSVC, ctest, pytest, --selftest, arranca
package_windows.bat                    # Windows: EXE\AllForOne.exe + release\*.zip + autoprueba en .cache\tmp
python -m allforone --selftest         # desde app/ (también AllForOne.exe --selftest)
python -m allforone --nativo --selftest  # interfaz nativa QML con el motor real
python tools/visual_compare.py         # diferencia píxel a píxel con la plantilla
python tools/native_compare.py         # web vs nativa (añade --oscuro para el tema oscuro)
```
Linux (desarrollo): `cmake -G Ninja -B build/linux -DPython_EXECUTABLE=$(which python) && ninja -C build/linux`,
pruebas con `xvfb-run python -m pytest tests`.
