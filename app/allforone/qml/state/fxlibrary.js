.pragma library
// Mapa del navegador de la Biblioteca nativa AFO (96 módulos, 6 secciones, 20 carpetas), tal como lo
// define docs/BIBLIOTECA_NATIVA.md. Qué módulos existen ya lo dice el motor (afo.fxCatalog): el resto
// se muestra como «por construir», nunca como un efecto que funciona.
var FAMILIES = [
 {
  "name": "Instrumentos",
  "folders": [
   {
    "name": "Sintetizadores",
    "items": [
     [
      "AF-81",
      "Wavetable Synth"
     ],
     [
      "AF-82",
      "Analog Synth"
     ],
     [
      "AF-83",
      "FM Synth"
     ]
    ]
   },
   {
    "name": "Samplers y baterías",
    "items": [
     [
      "AF-84",
      "Granular Instrument"
     ],
     [
      "AF-85",
      "Sampler Pro"
     ],
     [
      "AF-86",
      "Drum Rack"
     ],
     [
      "AF-87",
      "Drum Synth"
     ],
     [
      "AF-88",
      "808 Lab"
     ]
    ]
   },
   {
    "name": "Teclados y modelado",
    "items": [
     [
      "AF-89",
      "Keys"
     ],
     [
      "AF-90",
      "Physical Model"
     ]
    ]
   }
  ]
 },
 {
  "name": "Efectos de audio",
  "folders": [
   {
    "name": "Utilidades y señal",
    "items": [
     [
      "AF-01",
      "Gain"
     ],
     [
      "AF-03",
      "Phase Align"
     ],
     [
      "AF-04",
      "Stereo Tool"
     ],
     [
      "AF-05",
      "Routing"
     ],
     [
      "AF-06",
      "Tuner"
     ]
    ]
   },
   {
    "name": "Ecualización y resonancias",
    "items": [
     [
      "AF-07",
      "Parametric EQ"
     ],
     [
      "AF-08",
      "Dynamic EQ"
     ],
     [
      "AF-09",
      "Linear EQ"
     ],
     [
      "AF-10",
      "Graphic EQ"
     ],
     [
      "AF-11",
      "Tilt EQ"
     ],
     [
      "AF-12",
      "Resonance Control"
     ]
    ]
   },
   {
    "name": "Dinámica y transitorios",
    "items": [
     [
      "AF-13",
      "Compressor"
     ],
     [
      "AF-14",
      "Analog Compressor"
     ],
     [
      "AF-15",
      "Glue Compressor"
     ],
     [
      "AF-16",
      "Multiband Dynamics"
     ],
     [
      "AF-17",
      "Upward Compressor"
     ],
     [
      "AF-18",
      "Gate"
     ],
     [
      "AF-19",
      "Expander"
     ],
     [
      "AF-20",
      "De-Esser"
     ],
     [
      "AF-21",
      "De-Plosive"
     ],
     [
      "AF-22",
      "Transient Designer"
     ],
     [
      "AF-23",
      "Ducker"
     ],
     [
      "AF-24",
      "Vocal Rider"
     ],
     [
      "AF-25",
      "Envelope Shaper"
     ]
    ]
   },
   {
    "name": "Saturación y color",
    "items": [
     [
      "AF-26",
      "Saturator"
     ],
     [
      "AF-27",
      "Tape"
     ],
     [
      "AF-28",
      "Clipper"
     ],
     [
      "AF-29",
      "Waveshaper"
     ],
     [
      "AF-30",
      "Bitcrusher"
     ],
     [
      "AF-31",
      "Exciter"
     ],
     [
      "AF-32",
      "Sub Generator"
     ],
     [
      "AF-33",
      "Amp & Cabinet"
     ],
     [
      "AF-34",
      "Lo-Fi"
     ]
    ]
   },
   {
    "name": "Reverberación y espacios",
    "items": [
     [
      "AF-35",
      "Space"
     ],
     [
      "AF-36",
      "Convolution"
     ],
     [
      "AF-37",
      "Shimmer"
     ],
     [
      "AF-38",
      "Texture Verb"
     ],
     [
      "AF-39",
      "Reverse & Gated Verb"
     ],
     [
      "AF-40",
      "Infinity"
     ]
    ]
   },
   {
    "name": "Delays y ecos",
    "items": [
     [
      "AF-41",
      "Digital Delay"
     ],
     [
      "AF-42",
      "Tape Echo"
     ],
     [
      "AF-43",
      "MultiTap"
     ],
     [
      "AF-44",
      "Pitch Delay"
     ],
     [
      "AF-45",
      "Diffusion Delay"
     ],
     [
      "AF-46",
      "Reverse Delay"
     ]
    ]
   },
   {
    "name": "Modulación y tono",
    "items": [
     [
      "AF-47",
      "Chorus / Ensemble"
     ],
     [
      "AF-48",
      "Flanger"
     ],
     [
      "AF-49",
      "Phaser"
     ],
     [
      "AF-50",
      "Tremolo / AutoPan"
     ],
     [
      "AF-51",
      "Rotary / Vibrato"
     ],
     [
      "AF-52",
      "Frequency Shifter / Ring Mod"
     ],
     [
      "AF-53",
      "Formant / Vocoder"
     ],
     [
      "AF-54",
      "Resonator"
     ]
    ]
   },
   {
    "name": "Ritmo y glitch",
    "items": [
     [
      "AF-55",
      "Trance Gate"
     ],
     [
      "AF-56",
      "Glitch / Beat Repeat"
     ],
     [
      "AF-60",
      "Tape Stop / Time FX"
     ]
    ]
   },
   {
    "name": "Granular y espectral",
    "items": [
     [
      "AF-57",
      "Granular FX"
     ],
     [
      "AF-58",
      "Spectral FX"
     ],
     [
      "AF-61",
      "Creative Convolver"
     ]
    ]
   },
   {
    "name": "Filtros creativos",
    "items": [
     [
      "AF-59",
      "Filter Motion"
     ]
    ]
   }
  ]
 },
 {
  "name": "Voz y afinación",
  "folders": [
   {
    "name": "Afinación y armonías",
    "items": [
     [
      "AF-63",
      "Tune"
     ],
     [
      "AF-64",
      "Pitch Editor"
     ],
     [
      "AF-65",
      "Harmonizer"
     ],
     [
      "AF-66",
      "Doubler"
     ]
    ]
   },
   {
    "name": "Edición y reparación vocal",
    "items": [
     [
      "AF-67",
      "Vocal Align"
     ],
     [
      "AF-68",
      "Noise Reducer"
     ],
     [
      "AF-69",
      "Vocal Repair"
     ]
    ]
   }
  ]
 },
 {
  "name": "Mastering y análisis",
  "folders": [
   {
    "name": "Mastering tonal y dinámica",
    "items": [
     [
      "AF-71",
      "True Peak Limiter"
     ],
     [
      "AF-72",
      "Master Dynamics"
     ],
     [
      "AF-73",
      "Match EQ"
     ],
     [
      "AF-74",
      "Master Imager"
     ],
     [
      "AF-79",
      "Reference"
     ],
     [
      "AF-80",
      "Dither & Export"
     ]
    ]
   },
   {
    "name": "Medición y análisis",
    "items": [
     [
      "AF-75",
      "Loudness"
     ],
     [
      "AF-76",
      "Spectrum Analyzer"
     ],
     [
      "AF-77",
      "Oscilloscope"
     ],
     [
      "AF-78",
      "Phase Meter"
     ]
    ]
   }
  ]
 },
 {
  "name": "MIDI y composición",
  "folders": [
   {
    "name": "Generadores MIDI",
    "items": [
     [
      "AF-91",
      "Arpeggiator"
     ],
     [
      "AF-92",
      "Chord Tool"
     ],
     [
      "AF-94",
      "Step Sequencer"
     ],
     [
      "AF-96",
      "Pattern Generator"
     ]
    ]
   },
   {
    "name": "Transformadores MIDI",
    "items": [
     [
      "AF-93",
      "Scale Lock"
     ],
     [
      "AF-95",
      "Humanizer"
     ]
    ]
   }
  ]
 },
 {
  "name": "Racks y cadenas",
  "folders": [
   {
    "name": "Racks y cadenas",
    "items": [
     [
      "AF-02",
      "Channel Strip"
     ],
     [
      "AF-62",
      "FX Lab"
     ],
     [
      "AF-70",
      "Vocal Studio"
     ]
    ]
   }
  ]
 }
]
