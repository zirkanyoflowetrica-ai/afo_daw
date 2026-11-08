# Informe de entrega — AllForOne V0.2 «Mezclador V4.2 en los paneles»

Fecha: 2026-11-08

## Qué cambia

El Mezclador Automático V4.2 (mezcla automática, afinación PSOLA, espacio vocal, masters y
comparaciones) funciona dentro de AllForOne, repartido en módulos del mismo lienzo. La plantilla y
el DAW de V0.1 se conservan tal cual (`index.html` sigue siendo la plantilla + 3 líneas).

| Módulo nuevo | Qué hace (código original del V4.2) |
|---|---|
| **Mezcla IA** | Arrastrar stems desde el Explorador (o «+ Stems», o «Usar pistas de audio»); clasificación por nombre con tipo y rol editables; 9 guías trap/rap; Solo guía / Guía + balance sutil; escalón L/R; espacio vocal; **MEZCLAR AUTOMÁTICAMENTE** y **REMEZCLAR** (historial, nada se sobrescribe) |
| **Afinador** | Analizar música (librosa; las voces no participan), Automático/Asistido/Manual, Confirmar (igual que el original: sin confirmación no se afina), intensidad 0–100 %, voces principal/L/R/dobles |
| **Master IA** | Dinámico −14, Comercial −11, Fuerte −8,5, Plataformas −14/−2 dBTP y Según referencia, con LUFS, true peak y limitación reales; escucha A/B; enviar a Pistas; ZIP de sesión; abrir carpeta |
| **Antes / Después** | A/B por pista al mismo volumen y decisiones del mezclador |

Además: **tema oscuro** (botón ◐), **icono** propio, arrastrar audio a **Pistas**, y
reproductor nativo de previsualización en el motor C++ (A/B por la tarjeta de sonido).

## Dónde queda todo

- Programa: **`E:\AFO\EXE\AllForOne.exe`** (acceso directo `E:\AFO\AllForOne.lnk`).
- Datos (mezclas, ajustes, registros): `E:\AFO\EXE\datos` (en desarrollo `E:\AFO\data`).
- ZIP para publicar: `E:\AFO\release`.
- Cachés y temporales de compilación: `E:\AFO\.cache`.
- Tracktion ya no escribe en `%APPDATA%` (almacén de configuración propio). `limpiar_fuera_de_AFO.bat`
  eliminó lo que V0.1 había creado fuera (instalación en `%LOCALAPPDATA%`, accesos directos,
  AppData, caché de Nuitka, temporales).

## Cómo se integró el mezclador (sin reescribirlo)

- Los 18 módulos se copiaron **sin cambios** a `app/allforone/mixer_v42/`. Sus **27 pruebas
  originales** pasan contra esa copia (`tests/mixer_v42`, con Gradio instalado; en Windows corren
  las 10 que no importan la interfaz Gradio).
- `mixer_service.py` sustituye solo la interfaz Gradio (`app.py`): reproduce `process()`,
  `preview_hybrid()` y `confirm_hybrid()` (mismas carpetas, informe, `sesion.json`, guía por stem,
  A/B y ZIP), en un hilo aparte.
- El mezclador clasifica por nombre de archivo: si corriges tipo o rol en el panel, se mezcla una
  **copia** con un nombre que él interpreta así (p. ej. `toma_3.wav` → `double_toma_3.wav`); el
  original no se toca y el informe lo indica.
- Diferencias deliberadas: Essentia (vía WSL) desactivado por defecto (podía bloquear hasta 110 s);
  si no confirmas la tonalidad puedes mezclar igualmente con intensidad 0 % (sin afinación y con
  delays libres), y el informe lo dice; con intensidad > 0 % la confirmación es obligatoria, como en el original.

## Pruebas

| Prueba | Resultado |
|---|---|
| Pruebas nativas (ctest) | OK, incluida la previsualización y los datos en carpeta propia |
| pytest Linux | 36/36 (9 AllForOne + 27 originales del mezclador) |
| pytest Windows | 19/19 (9 + 10 del mezclador sin Gradio) |
| Autoprueba en Windows (código) | OK: soltar 3 stems con evento de arrastre real de Qt → MEZCLAR (2,9 s) → 4 masters (Plataformas −14,1 LUFS / −2,11 dBTP) → A/B → ZIP → Master a Pistas → **escucha A/B por la tarjeta de sonido** → transporte y medidores |
| Adaptador con 8 stems sintéticos + afinación 60 % + reclasificación | OK en 6,3 s; análisis detecta 95,7 BPM y, como el original, rechaza una tonalidad ambigua |
| Autoprueba de `AllForOne.exe` (copia en `.cache\tmp`, PATH limpio, `frozen: True`) | **OK completa**: mezclador cargado, soltar stems, MEZCLAR en 2,8 s, 4 masters, A/B por la tarjeta de sonido, medidores |
| Uso manual del `.exe` instalado en `EXE` | Tono de prueba → «Usar pistas de audio» → **Analizar música** (librosa/numba funcionan dentro del exe) → **MEZCLAR** (1,9 s) → Master IA con LUFS reales → escucha B · master |
| Empaquetado Windows | Nuitka 4.3.4, 13,9 min; ZIP de 250 MB en `release` |

Pendiente (V0.6): curva de afinación antes/después en el panel Afinador (marcada «pendiente»).

## Errores encontrados y corregidos en esta versión

1. QWebChannel no reenvía señales emitidas desde otro hilo: los eventos del mezclador se encolan y
   se emiten desde el hilo principal.
2. Orden de carga: si el puente conectaba antes que `afo_panels.js`, el panel no se suscribía.
3. El arrastre de Qt necesita `DragEnter` antes de `Drop` (la autoprueba ahora lo simula completo).
4. Medidor master huérfano cuando Tracktion recrea su contexto de reproducción en la misma dirección
   de memoria: se re-registra en cada lectura.
5. Empaquetado: los módulos del mezclador se incluyen uno a uno (`--include-module`).
