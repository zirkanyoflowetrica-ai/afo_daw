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
#include <string>
#include <vector>

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
};

// Parámetros de una pista de Instrumento/Batería (ver AfoSynth.h)
struct SynthSettings
{
    int mode = 0;           // 0 = instrumento, 1 = batería
    int wave = 0;           // preset 0..7
    float vel = 70, bri = 50;
    bool sus = false;
    float vol = 80, tun = 50;
    float rev = 0;          // reverb 0..100 (instrumentos)
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

    // Pistas de Instrumento/Batería: sintetizador del motor que toca un clip MIDI
    TrackInfo addSynthTrack (const std::string& name, int mode);
    void setSynthSettings (int id, const SynthSettings&);
    // (tiempo en negras, nota MIDI); batería: nota 36 + carril. Devuelve la duración del clip en segundos.
    double setSynthNotes (int id, const std::vector<std::pair<double, int>>& notes, double lengthBeats);
    // Escucha de una nota o golpe suelto por el reproductor de escucha (no toca el transporte)
    bool auditionSynth (const SynthSettings&, int midiNote, double seconds);

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

} // namespace afo
