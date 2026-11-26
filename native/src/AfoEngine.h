// AllForOne — fachada del motor nativo.
//
// Todo el trabajo de audio en tiempo real lo hace Tracktion Engine (sobre JUCE).
// Esta clase solo expone una API estable y pequeña a Python. Reglas:
//  * Se crea y se usa desde UN hilo (el hilo de mensajes: el hilo principal de Qt).
//  * Ningún método ejecuta Python ni bloquea el callback de audio.
//  * Los medidores leen picos acumulados por Tracktion (LevelMeasurer), no valores inventados.
#pragma once

#include <map>
#include <memory>
#include <functional>
#include <string>
#include <tuple>
#include <vector>

#include "AfoSynth.h"

namespace afo
{

struct DeviceInfo
{
    std::string typeName;      // WASAPI, DirectSound, ASIO, ALSA...
    std::string outputName;
    std::string inputName;
    double sampleRate = 0.0;
    int bufferSize = 0;
    int numOutputChannels = 0;
    int numInputChannels = 0;
    bool open = false;
    std::vector<std::string> availableTypes;
};

// Opciones de un tipo de driver (WASAPI, DirectSound, ASIO...) para el panel de audio
struct AudioDeviceOptions
{
    std::string typeName;
    std::vector<std::string> outputs, inputs;
    bool separateInputsAndOutputs = true;      // ASIO: un solo dispositivo para entrada y salida
    // Solo si el dispositivo abierto es de este tipo:
    std::vector<double> sampleRates;
    std::vector<int> bufferSizes;
    std::vector<std::string> inputChannels, outputChannels;
    bool hasControlPanel = false;              // ASIO: panel propio del driver (ASIO4ALL, etc.)
    double inputLatencyMs = 0, outputLatencyMs = 0;
};

// Estado de la grabación
struct RecordState
{
    bool recording = false;
    int armedTrack = 0;                        // 0 = ninguna
    std::string input;                         // entrada asignada
    bool monitor = false;
    double seconds = 0;                        // duración de la toma en curso
    float inputDb = -100.0f;                   // pico de la entrada desde la última lectura
    std::string file;                          // archivo de la toma en curso
};

// Efecto nativo de la biblioteca (docs/BIBLIOTECA_NATIVA.md)
struct EffectParamInfo
{
    std::string id, name, unit, help;
    float min = 0, max = 1, def = 0, centre = 0;
    std::vector<std::string> choices;          // vacío = continuo
};

struct EffectTypeInfo
{
    std::string key, af, name, family, summary;
    std::vector<EffectParamInfo> params;
    std::vector<std::string> meters;           // medidas propias tras [entrada dB, salida dB]
};

struct EffectInfo
{
    int id = 0;
    int trackId = 0;                           // 0 = master
    std::string key;
    bool enabled = true;
    std::vector<float> values;                 // en el orden de EffectTypeInfo::params (siguen la automatización)
    std::vector<std::string> automated;        // parámetros con curva de automatización
    double latencySeconds = 0;
    std::string name;                          // nombre a mostrar (plugins externos)
    std::string pluginId;                      // plugin VST3 externo ("" = efecto nativo)
};

// FX Lab (AF-62): una macro sobre un parámetro de un efecto de la misma pista
struct MacroAssign
{
    int effectId = 0;
    std::string paramId;
    int macro = 1;                             // 1..4
    float amount = 0;                          // −1..1 del recorrido del parámetro con la macro al 100 %
};

// Estado de un FX Lab: sus piezas, sus ramas (ids de efecto en orden) y la latencia compensada
struct FxLabInfo
{
    bool linked = false;                       // «FX Lab», «Rama B» y «Fin» en orden en la pista
    int splitId = 0, endId = 0;
    std::vector<int> branchA, branchB;
    double latencyA = 0, latencyB = 0;         // segundos
};

// Un plugin VST3 encontrado en el disco
struct PluginDesc
{
    std::string id;                            // identificador de JUCE (formato, nombre, archivo, uid)
    std::string name, vendor, category, path, format;
    bool instrument = false;
};

struct PluginScan
{
    std::vector<PluginDesc> plugins;
    std::vector<std::string> failed;           // archivos que no se pudieron abrir
    std::vector<std::string> folders;          // carpetas exploradas
};

struct TrackInfo
{
    int id = 0;
    std::string name;
    std::string sourcePath;
    double startSeconds = 0.0;                 // posición del clip en la línea de tiempo
    double lengthSeconds = 0.0;
    double sampleRate = 0.0;
    int numChannels = 0;
    int auxBus = -1;                           // bus Aux que recibe esta pista (-1 = pista normal)
};

// Envío de una pista a un bus Aux (como en una consola: pre o post fader)
struct SendInfo
{
    int auxTrackId = 0;                        // pista Aux que lo recibe
    float db = 0.0f;                           // nivel del envío
    bool pre = false;                          // true = antes del fader (no sigue al volumen de la pista)
};

// Un clip de audio de una pista (edición como en un DAW). Tiempos en segundos.
struct ClipInfo
{
    long long id = 0;                          // id del clip en Tracktion (EditItemID)
    int trackId = 0;
    double start = 0.0;                        // posición en la línea de tiempo
    double length = 0.0;
    double offset = 0.0;                       // desde dónde del archivo empieza a sonar
    float gainDb = 0.0f;
    double fadeIn = 0.0, fadeOut = 0.0;
    double sourceLength = 0.0;                 // duración del archivo
};

// Parámetros de una pista de Instrumento/Batería (ver AfoSynth.h)
struct SynthSettings
{
    int mode = 0;           // 0 = instrumento, 1 = batería
    int wave = 0;           // preset 0..8 (8 = 808)
    float vel = 70, bri = 50;
    bool sus = false;
    float vol = 80, tun = 50;
    float rev = 0;          // reverb 0..100 (instrumentos)
    float glide = 30, drive = 30, punch = 50;   // 808 Lab (preset 8)
    int arp = 0, arpRate = 2, arpOct = 1;        // arpegiador (ver synth::Params)
    float arpGate = 50;
    // Drum Synth / Drum Rack: por carril [afinación, caída, tono, nivel, paneo (0..100, 50 centro), grupo de
    // corte (0 ninguno, 1 A, 2 B)]; 50 / 0 = de fábrica; vacío = de fábrica
    std::vector<std::vector<float>> lanes;
    // Sinte analógico: [desafinación, corte, resonancia, envolvente, ataque, liberación] 0..100; vacío = de fábrica
    std::vector<float> analog;
    // Sinte de tablas: [tabla, posición, barrido, movimiento, ataque, liberación]; vacío = de fábrica
    std::vector<float> wavetable;
    // Sampler: [nota raíz, inicio, bucle (0/1), inicio del bucle, ataque, liberación]; vacío = de fábrica
    std::vector<float> sampler;
};

// Sonoridad de una pista o del master (BS.1770): RMS 300 ms, LUFS momentánea/corto plazo/integrada,
// pico de muestra desde la última lectura y máximo desde el último reinicio
struct Loudness
{
    float peakDb = -100.0f, maxPeakDb = -100.0f, rmsDb = -100.0f;
    float momentary = -100.0f, shortTerm = -100.0f, integrated = -100.0f;
};

struct Levels
{
    float masterL = -100.0f, masterR = -100.0f;   // dBFS (pico desde la última lectura)
    float masterVu = -100.0f;                     // dBFS RMS con balística VU (300 ms)
    std::map<int, float> tracks;                  // id -> dBFS (máx. de canales)
    Loudness master;                              // tras la sección master
    std::map<int, Loudness> loud;                 // id -> sonoridad tras el fader de la pista
};

// Medida de la mezcla completa procesada en memoria (sin escribir archivos)
struct MixMeasure
{
    bool ok = false;
    double seconds = 0;
    Loudness master;
    std::map<int, Loudness> tracks;
};

// Busca VST3 (carpetas estándar + extra) y guarda la lista en listFile tras cada archivo. Pensado para
// un proceso aparte: si un plugin cuelga o cierra el proceso, AllForOne sigue abierto y el siguiente
// intento lo salta. `progress` recibe cada archivo antes de abrirlo.
PluginScan scanPluginFolders (const std::string& listFile, const std::vector<std::string>& extraFolders,
                              const std::function<void (const std::string&)>& progress);

class Engine
{
public:
    // dataDir: carpeta donde Tracktion guarda su configuración y sesiones temporales.
    // Vacío = carpeta por defecto del sistema. AllForOne pasa siempre su propia carpeta de datos.
    explicit Engine (const std::string& appName = "AllForOne", const std::string& dataDir = {});
    ~Engine();

    Engine (const Engine&) = delete;
    Engine& operator= (const Engine&) = delete;

    // Dispositivo
    DeviceInfo deviceInfo() const;
    AudioDeviceOptions audioDeviceOptions (const std::string& typeName) const;   // vacío = tipo actual
    // Cambia el driver y el dispositivo. Devuelve "" si todo fue bien o el error del driver.
    // sampleRate/bufferSize <= 0 conservan el valor actual. La elección se guarda para el próximo arranque.
    std::string setAudioDevice (const std::string& typeName, const std::string& output, const std::string& input,
                                double sampleRate, int bufferSize);
    bool showAudioControlPanel();             // ASIO: abre el panel del driver (bloquea hasta cerrarlo)

    // Grabación (Tracktion graba en disco desde su propio hilo; el callback de audio no hace E/S)
    std::vector<std::string> recordInputs() const;                      // entradas mono/estéreo disponibles
    TrackInfo addRecordTrack (const std::string& name);
    // Pone un audio ya grabado en una pista (al abrir un proyecto): sustituye sus clips
    TrackInfo setTrackAudio (int trackId, const std::string& path, double startSeconds);                 // pista de audio vacía para grabar
    // Arma la pista con una entrada ("" = la primera). monitor: escuchar la entrada mientras está armada.
    std::string armTrack (int trackId, const std::string& input, bool monitor);
    void disarm();
    std::string startRecording();             // graba desde la posición actual (las otras pistas suenan)
    // Detiene y devuelve la pista con la toma (o la info sin archivo si no se grabó nada)
    TrackInfo stopRecording (bool discard);
    RecordState recordState();

    // Pistas de audio
    TrackInfo addAudioTrack (const std::string& filePath, const std::string& name);
    bool removeTrack (int id);
    std::vector<TrackInfo> tracks() const;
    std::vector<float> trackPeaks (int id, int numBuckets) const;
    void setTrackGainDb (int id, float db);
    void setTrackPan (int id, float pan);              // -1..1
    void setTrackMute (int id, bool muted);
    void setTrackSolo (int id, bool solo);

    // Buses Aux: pista que recibe los envíos (Aux Return de Tracktion) y lleva sus propios efectos,
    // fader y panorama; suena aunque otra pista esté en solo (solo seguro). Hasta 16 buses.
    TrackInfo addAuxTrack (const std::string& name);
    // Envío de trackId al bus de auxTrackId: db <= -100 lo quita. pre = antes del fader de la pista.
    bool setSend (int trackId, int auxTrackId, float db, bool pre);
    std::vector<SendInfo> sends (int trackId) const;

    // Automatización del fader ("volume", puntos en dB) y del paneo ("pan", -1..1) de una pista.
    // Lista vacía = sin curva (vuelve al valor fijo del fader / paneo).
    bool setTrackAutomation (int trackId, const std::string& param, const std::vector<std::pair<double, float>>& points);
    std::vector<std::pair<double, float>> trackAutomation (int trackId, const std::string& param) const;

    // Clips de audio: mover, recortar (start/length/offset), dividir, duplicar, borrar, volumen y fundidos.
    // Todos los clips de una pista usan el audio de la pista. setClips sustituye todos (deshacer, abrir).
    std::vector<ClipInfo> clips (int trackId);
    ClipInfo setClipRange (long long clipId, double start, double length, double offset);
    std::vector<ClipInfo> splitClip (long long clipId, double atSeconds);
    ClipInfo duplicateClip (long long clipId);
    bool removeClip (long long clipId);
    ClipInfo setClipGain (long long clipId, float db);
    ClipInfo setClipFades (long long clipId, double fadeIn, double fadeOut);
    float clipPeakDb (long long clipId);                 // pico real del trozo de archivo que suena (sin la ganancia)
    std::vector<ClipInfo> setClips (int trackId, const std::vector<ClipInfo>& clips);

    // Plugins VST3 externos: buscar (carpetas estándar + extra; la lista se guarda en la carpeta de
    // datos), insertarlos como efecto en la cadena de una pista o como instrumento de una pista de
    // Instrumento (recibe su clip MIDI), abrir su ventana y leer su estado (base64) para el proyecto.
    PluginScan scanPlugins (const std::vector<std::string>& extraFolders);
    void reloadPlugins();                       // vuelve a leer la lista (tras buscar en otro proceso)
    std::vector<PluginDesc> knownPlugins();
    EffectInfo addPluginEffect (int trackId, const std::string& pluginId, int index, const std::string& state);
    std::string effectState (int effectId);
    bool showEffectEditor (int effectId);
    bool setTrackInstrument (int trackId, const std::string& pluginId, const std::string& state);   // "" = sintetizador del motor
    std::string trackInstrument (int trackId);
    std::string trackInstrumentState (int trackId);
    bool showInstrumentEditor (int trackId);

    // Pistas de Instrumento/Batería: sintetizador del motor que toca un clip MIDI
    TrackInfo addSynthTrack (const std::string& name, int mode);
    void setSynthSettings (int id, const SynthSettings&);
    // Sampler de la batería: un WAV/AIFF/FLAC por carril ("" = el sonido sintetizado). Se pasa a mono
    // y se corta a 10 s. Devuelve cuántos carriles quedan con golpe grabado; lanza si un archivo no se lee.
    int setDrumSamples (int id, const std::vector<std::string>& paths);
    // Sampler del Instrumento: el sonido que toca la pista con el preset «Sampler» ("" = ninguno)
    bool setInstrumentSample (int id, const std::string& path);
    // (tiempo en negras, nota MIDI); batería: nota 36 + carril. Devuelve la duración del clip en segundos.
    double setSynthNotes (int id, const std::vector<std::pair<double, int>>& notes, double lengthBeats);
    // Notas con duración y velocidad propias (MIDI importado o compuesto por la IA):
    // (inicio en negras, duración en negras, nota 0..127, velocidad 1..127)
    double setSynthMidi (int id, const std::vector<std::tuple<double, double, int, int>>& notes, double lengthBeats);
    // Step Sequencer de la Batería: el patrón (fuerza, probabilidad y repeticiones por paso, largo por
    // pad) se convierte aquí en el clip MIDI de la pista. Devuelve la duración del clip en segundos.
    double setStepPattern (int id, const synth::StepPattern&);
    // Escucha de una nota o golpe suelto por el reproductor de escucha (no toca el transporte)
    // trackId ≥ 0 en la batería: el pad suena con el golpe grabado de esa pista si lo tiene
    bool auditionSynth (const SynthSettings&, int midiNote, double seconds, int trackId = -1);

    // Efectos nativos: trackId 0 = master (antes de la sección master). index -1 = al final de la cadena.
    static std::vector<EffectTypeInfo> effectCatalog();
    EffectInfo addEffect (int trackId, const std::string& key, int index);
    bool removeEffect (int effectId);
    bool moveEffect (int effectId, int newIndex);
    bool setEffectParam (int effectId, const std::string& paramId, float value);
    void setEffectEnabled (int effectId, bool enabled);
    std::vector<EffectInfo> effects (int trackId) const;
    EffectInfo effectInfo (int effectId) const;
    // Automatización de un parámetro: puntos (segundos, valor en su rango) unidos en línea recta.
    // Lista vacía = sin automatización (el parámetro vuelve a su valor fijo).
    bool setEffectAutomation (int effectId, const std::string& paramId, const std::vector<std::pair<double, float>>& points);
    std::vector<std::pair<double, float>> effectAutomation (int effectId, const std::string& paramId) const;
    std::vector<float> effectMeters (int effectId);                   // [entrada dB, salida dB, propias...]
    std::vector<float> effectSpectrum (int effectId, int bands);      // espectro de la salida (dBFS)
    // FX Lab: la macro 1..4 del FX Lab `labId` mueve `paramId` del efecto `effectId` (misma pista).
    // amount 0 quita la asignación. Un parámetro lleva como mucho una macro
    bool setEffectMacro (int labId, int macro, int effectId, const std::string& paramId, float amount);
    std::vector<MacroAssign> effectMacros (int labId) const;
    FxLabInfo fxLabInfo (int labId) const;
    // Antes / después de la cadena de una pista (0 = master): entrada del primer efecto activo y
    // salida del último. active = 0 si no hay efectos activos (entonces no hay nada que comparar).
    struct ChainScope { std::vector<float> pre, post; float preDb = -100, postDb = -100; int active = 0; };
    ChainScope chainScope (int trackId, int bands);

    // Master
    void setMasterGainDb (float db);
    float masterGainDb() const;
    // Sección master: Saturación 0..100, Tono 0..100 (50 = plano), Limitador (techo −1 dBFS)
    void setMasterProcessing (float drive, float tone, bool limiter);
    void setMasterCeiling (float db);        // techo del limitador del master (−6..0 dBFS)
    float masterCeiling() const;

    // Transporte
    void play();
    void pause();
    void stop();                                       // detiene y vuelve a 0
    bool isPlaying() const;
    double positionSeconds() const;
    void setPositionSeconds (double s);
    double lengthSeconds() const;
    void setTempo (double bpm);
    double tempo() const;

    // Previsualización (A/B de mezclas y masters): reproduce un archivo por el mismo dispositivo,
    // sin añadirlo al proyecto. Cambiar de archivo conserva la posición (comparación A/B).
    bool previewPlay (const std::string& path, double startSeconds);
    void previewStop();
    bool previewPlaying() const;
    double previewPosition() const;
    double previewLength() const;
    std::string previewPath() const;

    // Medición (llamar periódicamente desde el hilo de mensajes)
    Levels readLevels();
    void resetLoudness();                    // vacía las integradas y los máximos
    // Procesa toda la sesión en memoria (Tracktion Renderer::measureStatistics) y devuelve la
    // sonoridad del master y de cada pista: sin archivos. Bloqueante, como un render.
    MixMeasure measureMix();

    // Render offline del Edit completo (bloqueante; no usa el dispositivo)
    bool renderToWav (const std::string& path);

    // Procesa mensajes pendientes de JUCE (útil cuando el bucle de eventos no es el de Win32)
    static void pumpMessages (int milliseconds);

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
};

// Utilidades
std::string version();
std::string juceVersion();
// Escribe un WAV de 24 bits con una senoidal (señal de prueba sintética, identificada como tal)
bool writeTestTone (const std::string& path, double frequency, double seconds, double sampleRate, float amplitudeDb);
// Mide pico y RMS (dBFS) de un archivo de audio usando los lectores de JUCE
std::pair<float, float> measureFile (const std::string& path);

// Vocal Align (AF-67): escribe en `outPath` la toma `dubPath` con su tiempo ajustado a la voz guía
// `guidePath`. guideStart / dubStart: segundo del proyecto en que cae el principio de cada archivo.
// La salida tiene la misma duración, canales y frecuencia que la toma (WAV de 32 bits en coma
// flotante). strength 0–1; maxShiftMs: lo más que se mueve una sílaba. No usa el motor: puede ir en
// otro hilo.
struct AlignReport
{
    bool ok = false;
    std::string error;
    double meanShiftMs = 0.0, maxShiftMs = 0.0, seconds = 0.0;
};
AlignReport alignVoiceFiles (const std::string& guidePath, double guideStart, const std::string& dubPath, double dubStart,
                             const std::string& outPath, float strength, float maxShiftMs);

// Pitch Editor (AF-64): notas de una voz (tono cada 10 ms y notas con su mediana) y una copia con
// cada nota movida `shift` semitonos y enderezada `flatten` (0–1), sin cambiar el tiempo (TD-PSOLA).
// No usan el motor: pueden ir en otro hilo.
struct PitchNoteInfo
{
    double start = 0.0, end = 0.0;
    float midi = 0.0f, shift = 0.0f, flatten = 0.0f;
};
struct PitchAnalysis
{
    bool ok = false;
    std::string error;
    double hop = 0.01, seconds = 0.0;
    std::vector<float> curve;                 // MIDI cada `hop` s; 0 = sin voz
    std::vector<PitchNoteInfo> notes;
};
PitchAnalysis analyzePitchFile (const std::string& path);
std::string pitchEditFile (const std::string& path, const std::string& outPath, const std::vector<PitchNoteInfo>& notes);

} // namespace afo
