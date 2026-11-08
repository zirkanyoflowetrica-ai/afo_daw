# Interfaz nativa (Qt Quick) — sin HTML ni Chromium

Objetivo: que AllForOne sea una app de escritorio 100 % nativa conservando la imagen y el
funcionamiento de `PLANTILLA_DAW.html`, que pasa a ser la **referencia visual**.

Se conserva tal cual: motor C++ (`native/`), `EngineHost`, el Mezclador V4.2 y su adaptador, la
importación de audio y el `Bridge` de Python (sus métodos son slots de Qt: QML los llama
directamente, igual que antes JavaScript por QWebChannel). Solo cambia la capa que dibuja.

```
python -m allforone --nativo            # abrir la interfaz nativa
python -m allforone --nativo --selftest # autoprueba con el motor real
python tools/native_compare.py [--oscuro]   # comparación píxel a píxel con la interfaz web
```

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Ventana, cabecera (transporte, tempo, zoom, Ver todo, Restaurar diseño, tema), lienzo infinito con puntos, 12 módulos movibles y redimensionables, cables con curva, conectores y cuadrados de curva arrastrables, diseño y tema guardados, módulo **Pistas** con el motor real, arrastrar audios a la ventana | **Hecha** |
| 1 | Audios, Mezcla (consola, faders, rol de voz, MEZCLAR AUTOMÁTICAMENTE), Mezcla final (VU, master, exportar) | Pendiente |
| 2 | Afinador, Master IA, Antes / Después | Pendiente |
| 3 | Piano roll, Instrumentos, Batería, Pistas con IA, con sonido del motor (hoy son la demo Web Audio) | Pendiente |
| 4 | Grabador de cintas grabando con el motor; autoprueba completa sobre QML; retirar Qt WebEngine | Pendiente |

Los módulos de fases pendientes muestran en su cuerpo que aún no están migrados y dónde usarlos.

## Fase 0: cómo se hizo

- `app/allforone/qml/`: `Main.qml` (ventana, cabecera, lienzo, cables, conectores), `ModulePanel.qml`
  (módulo), `TracksBody.qml` (Pistas), `NeoButton.qml` (botón con sombra dura), `Theme.qml`
  (colores claro / oscuro de la plantilla y de `afo_theme_dark.css`), `layout.js` (la matemática del
  lienzo portada de la plantilla: `anchor`, `cableShape`, `nearestPin`, `fit`).
- `app/allforone/native_ui.py`: carga fuentes y QML, expone `afo` (Bridge) y `layoutStore`
  (diseño en `datos/diseno_nativo.json`, sin almacenamiento del navegador).
- **Fuente:** Qt no lee WOFF2 y aplica mal los grosores de una fuente variable, así que Space
  Grotesk (OFL 1.1) va como tres TTF estáticos (500, 600, 700) generados de la misma fuente.
- **Símbolos** (■ ▶ ◐ ✕): no están en Space Grotesk; se dibujan con Segoe UI Symbol, como hace el
  navegador en Windows.

## Comparación medida (1600×900, datos limpios)

| Zona | Píxeles distintos | Qué explica la diferencia |
|---|---|---|
| Cabecera, tema claro | 8,0 % | Posiciones iguales a ±1 px; el resto es el suavizado del texto (Chromium y Qt rasterizan distinto) |
| Cabecera, tema oscuro | 8,1 % | Igual |
| Lienzo | 30 % (claro) / 18 % (oscuro) | Cuerpos de los módulos de las fases 1–4 y pistas DEMO de la plantilla, que la nativa no muestra |

Encuadre inicial: zoom 0,6157 (web 0,6159).
