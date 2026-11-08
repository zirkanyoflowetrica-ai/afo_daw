# Validación adicional V4.2

- Pruebas automáticas: **27 aprobadas** (`pytest -q`), incluyendo seis de V4.2.
- La selección de 9 plantillas produce recomendaciones diferentes, incluso a nivel de cada stem.
- Agrupación de 3 sintetizadores, 2 guitarras y voces L/R y _B_L verificada.
- Se comprobó que las recomendaciones no fuerzan sesgos en audio silencioso y nunca superan ±1 dB.
- Modo `Solo guía`: la misma mezcla produce audio **idéntico muestra por muestra** con dos plantillas diferentes.
- Modo `Guía + balance muy sutil`: diferencias detectables en pistas no silenciosas con reportes específicos.
- Exportación real con 3 stems y 4 masters: ZIP válido con `guia_mezcla_por_stems.md`, `.json` y `sesion.json` con perfil registrado.
- Interfaz Gradio construida correctamente. **No se realizó evaluación perceptiva con audio real de una canción en esta revisión**.

---

# Auditoría V4.0 — detección musical y afinación individual

- Inspección directa del código V3.9: la función `render_mix` llamaba `process_vocal` una vez **por stem vocal**, antes de sumar a buses; el paneo y el escalón sucedían después. La modificación mantiene ese orden.
- Biblioteca usada para análisis: **librosa**. Tonalidad: HPSS + chroma STFT + perfiles Mayor/Menor natural. Ritmo: onset strength y beat tracking dinámico.
- `pytest tests/test_v40.py tests/test_v39.py tests/test_v38.py tests/test_v37.py tests/test_v36.py tests/test_backing_vocals.py`: **14 pruebas aprobadas**, 0 fallos (al actualizar el test de interfaz V3.9 para el nombre nuevo del campo BPM).
- Prueba con piano de notas Do/Mi/Sol/Do y batería sintética a 120 BPM: obtuvo **C Mayor (82 %)** y **117.5 BPM**.
- Prueba sin instrumentos: no inventó tónica ni BPM. Con afinación automática pidió selección manual y dejó la voz sin afinación.
- Prueba de ruteo con Voz_Principal/Voz_L/Voz_R: tres llamadas a procesamiento independientes, con `True, True, False` al seleccionar solo las dos primeras.
- Prueba de inyección de predicción musical: se comprobó que el afinador de la voz recibe la tonalidad detectada y que queda registrada en `details['music_analysis']`.
- Integración completa mediante `app.process_ui`: 3 stems, análisis instrumental, cuatro masters y ZIP íntegro (`testzip() is None`), con metadata de análisis dentro de `sesion.json`.
- Se preservan los controles de reverb/delay, perfil por rol, volumen L/R, afinador PSOLA, EQ y mastering.

**Límites:** no hay audio de voces reales usado para certificar ausencia de artefactos; la escala inferida puede ser ambigua (modos, cromatismos, cambios de tonalidad o mezcla muy percusiva). La autoafinación se omite con confianza baja. El BPM puede aparecer a medio/doble tiempo, especialmente trap. No se ejecutó en el Windows de la persona usuaria. No hay motor de separación automática de voces solapadas dentro de un único WAV.

---

# Auditoría V3.9 (ejecutada en entorno Linux de pruebas)

- Validación de sintaxis `app.py`, `mixer_engine.py`, `vocal_space.py`: OK.
- `pytest tests/test_v39.py tests/test_v38.py tests/test_v36.py tests/test_backing_vocals.py`: 7 pruebas aprobadas.
- Tests heredados por ejecución directa `test_v32.py`, `test_v33.py`, `test_v34.py`, `test_v35.py`, `test_v37.py`: OK (salidas registradas).
- `test_pipeline.py`: informe terminó con `TESTS OK`, pero la ejecución conjunta alcanzó el límite externo de tiempo al finalizar; no se presenta como verificación cronometrada exitosa del comando total.
- Una exportación completa real a través de `app.process_ui` usando stems sintéticos de 4 segundos, `BPM=120`, cuatro masters y ZIP comprobado (`testzip==None`): OK.
- Comparación FX OFF vs ON: las pistas vocales e instrumentales secas son iguales antes de la ganancia global de normalización; los FX nuevos aparecen solo en los buses separados.
- Validación de protección estéreo, predelay, cero FX, BPM fuera de rango, nivel RMS y reverb diferenciada: OK.

**Limitaciones:** las pruebas se hicieron con audio sintético y stems de auditoría; no certifican calidad subjetiva en canciones reales. No se ha ejecutado en el Windows del usuario. El sistema de `room_size` no controla el tiempo de cola en segundos exactos; el BPM no se adivina automáticamente. Los retornos se recortan al final de la canción, conservando la longitud sincronizada de los stems (igual que en la base original).
