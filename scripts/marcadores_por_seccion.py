"""Marcadores por sección
Analiza el audio que suena y pone un marcador en cada sección (A, B, A…) bajo la regla del Arreglo.
"""
# Script de ejemplo de AllForOne (F8). Usa el mismo análisis que «Editar › Analizar el proyecto»,
# pero solo escribe las secciones (los acordes y la tonalidad no se tocan).
r = afo.analyze()
secciones = r["sections"]
if not secciones:
    raise ScriptError("No se encontraron secciones: el audio es demasiado corto o no tiene pulso")
vistas = {}
marcas = []
for s in secciones:
    vistas[s["label"]] = vistas.get(s["label"], 0) + 1
    marcas.append({"start": s["start"], "end": s["end"], "label": f"{s['label']}{vistas[s['label']]}"})
afo.set_markers(marcas)
afo.log(f"{len(marcas)} secciones: " + " ".join(m["label"] for m in marcas))
