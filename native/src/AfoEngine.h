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

struct TrackInfo
{
    int id = 0;
    std::string name;
    std::string sourcePath;
    double lengthSeconds = 0.0;
    double sampleRate = 0.0;
    int numChannels = 0;
};

struct Levels
{
    float masterL = -100.0f, masterR = -100.0f;   // dBFS (pico desde la última lectura)
    std::map<int, float> tracks;                  // id -> dBFS (máx. de canales)
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

    // Pistas de audio
    TrackInfo addAudioTrack (const std::string& filePath, const std::string& name);
    bool removeTrack (int id);
    std::vector<TrackInfo> tracks() const;
    std::vector<float> trackPeaks (int id, int numBuckets) const;
    void setTrackGainDb (int id, float db);
    void setTrackPan (int id, float pan);              // -1..1
    void setTrackMute (int id, bool muted);
    void setTrackSolo (int id, bool solo);

    // Master
    void setMasterGainDb (float db);
    float masterGainDb() const;

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
