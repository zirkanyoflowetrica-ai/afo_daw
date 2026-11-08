# AGENTS.md — reglas para trabajar en AllForOne

Especificación completa: `docs/MASTER_PROMPT.md`. Resumen de lo que no se negocia:

1. **La interfaz es `PLANTILLA_DAW.html`.** No se rediseña. `app/allforone/ui/index.html` = plantilla
   + 3 líneas (ver `docs/CAMBIOS_PLANTILLA.md`); `tests/test_template_fidelity.py` lo vigila.
   La lógica nueva va en `afo_bridge.js` envolviendo funciones globales; el CSS original no se toca
   sin explicar antes el problema y documentarlo.
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
python tools/visual_compare.py         # diferencia píxel a píxel con la plantilla
```
Linux (desarrollo): `cmake -G Ninja -B build/linux -DPython_EXECUTABLE=$(which python) && ninja -C build/linux`,
pruebas con `xvfb-run python -m pytest tests`.
