# Temas de AllForOne

Cada carpeta de aquí con un `theme.json` es un **tema** y aparece en el selector **Tema** de la
cabecera (pulsa ↻ en el selector para releer la carpeta sin reiniciar).

- **Compartir un tema:** copia su carpeta en la carpeta `templates` del AllForOne de tu amigo
  (junto a `AllForOne.exe`). Al actualizar AllForOne se conservan los temas que hayas añadido.
- **Crear uno:** copia la carpeta de un tema, cámbiale el nombre y edita `theme.json`. Lo que no
  pongas toma el valor del tema AllForOne.

```json
{
  "name": "Mi tema",
  "description": "una línea que se ve en el selector",
  "dark": true,
  "font": "Segoe UI",
  "colors":  { "canvas": "#1d1d1d", "ink": "#d6d6d6", "button": "#3a3a3a", "accent": "#ffa53c", "...": "..." },
  "style":   { "frame": 0, "border": 1, "shadow": 0, "buttonShadow": 0, "radius": 3, "headHeight": 32,
               "titleSize": 13, "upperTitles": false, "bodyTint": 0.0, "canvas": "grid", "knob": "arc",
               "accentStripe": 3 },
  "modules": { "pistas": "#e0aa2c", "mezcla": "#4fc79c", "...": "..." }
}
```

Las claves de `colors`, `style` y `modules` están en `app/allforone/qml/theme/Theme.qml` (objeto
`base`). La carpeta `AllForOne` guarda además la plantilla original (`PLANTILLA_DAW.html`) y la
imagen de referencia de los módulos (`REFERENCIA_PANELES.webp`).
