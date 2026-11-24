// AllForOne — sintetizador de las pistas de Instrumento y Batería.
//
// Reproduce el diseño de sonido de PLANTILLA_DAW.html (osciladores → filtro → envolvente;
// batería con barridos, cuadradas y ruido filtrado), ahora dentro del motor: un plugin de
// Tracktion que toca las notas de un clip MIDI en el callback de audio. La misma DSP sirve
// para escuchar una nota suelta al pulsar (Synth::renderHit).
#pragma once

#include <atomic>
#include <cstdint>
#include <vector>

namespace afo::synth
{

// Parámetros de una pista (los mismos nombres que en la plantilla)
struct Params
{
    int mode = 0;           // 0 = instrumento, 1 = batería
    int wave = 0;           // preset de Instrumentos: 0..7 → triangle, saw, square, saw, sine, saw, sine, triangle
    float vel = 70.0f;      // Velocidad 0..100
    float bri = 50.0f;      // Brillo 0..100 → lowpass 400 + bri·60 Hz
    bool sus = false;       // Sostenido: nota de 1,4 s en vez de 0,3 s
    float vol = 80.0f;      // Batería: volumen 0..100
    float tun = 50.0f;      // Batería: afinación 0..100 → ×2^((tun−50)/50)
    float rev = 0.0f;       // Instrumentos: reverb 0..100 (0 = seca)
};

// Copia sin bloqueos entre el hilo de mensajes (escribe) y el de audio (lee)
struct AtomicParams
{
    std::atomic<int> mode { 0 }, wave { 0 };
    std::atomic<float> vel { 70 }, bri { 50 }, vol { 80 }, tun { 50 }, rev { 0 };
    std::atomic<bool> sus { false };
    void store (const Params& p);
    Params load() const;
};

// Biquad (BiquadFilterNode de Web Audio, coeficientes del Audio EQ Cookbook)
struct Biquad
{
    enum class Type { lowpass, highpass, bandpass };
    double b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0, z1 = 0, z2 = 0;
    void set (Type, double freq, double sampleRate);
    float process (float x) noexcept;
};

// Golpe grabado para un carril de la batería (sampler): mono, a su frecuencia de muestreo. Si un
// carril tiene uno, el pad suena con él (afinación = velocidad de lectura, Volumen = ganancia).
struct Sample
{
    std::vector<float> data;
    double sampleRate = 48000.0;
};
constexpr int drumLanes = 8;
constexpr double maxSampleSeconds = 10.0;

// Una nota o un golpe en curso
struct Voice
{
    bool active = false;
    int delay = 0;          // muestras hasta que empieza (posición dentro del bloque)
    int64_t t = 0;          // muestras desde que empezó
    int64_t length = 0;     // muestras hasta que se apaga
    int mode = 0, lane = 0, wave = 0;
    double sr = 48000, phase = 0, phase2 = 0, freq = 440, f0 = 0, f1 = 0, sweep = 0.15;
    double g0 = 0, decay = 0.3;
    uint32_t noise = 22222;
    Biquad filter;
    bool useFilter = false;
    // Notas con duración propia (MIDI importado o de la IA): suenan mientras están pulsadas
    bool gated = false, released = false;
    int note = -1;
    int64_t offAt = -1;                     // muestra (en t) en que llega el note-off
    double attack = 0.004, sustain = 0.3, releaseSec = 0.12, lastEnv = 0, relLevel = 0, relSec = 0;
    // Golpe grabado (sampler): lectura con interpolación lineal; `step` incluye la afinación
    const Sample* sample = nullptr;
    double spos = 0, sstep = 1;

    void startNote (const Params&, int midiNote, double seconds, double sampleRate, int delaySamples);
    // Nota que sigue al note-off: ataque, caída hasta el nivel de sostén del preset y release
    void startHeldNote (const Params&, int midiNote, float velocity, double sampleRate, int delaySamples);
    void startDrum (const Params&, int lane, double sampleRate, int delaySamples, const Sample* s = nullptr);
    void noteOff (int atSample) noexcept;   // posición dentro del bloque
    float next() noexcept;  // una muestra (0 antes de empezar o al acabar)
};

constexpr int maxVoices = 64;
constexpr int firstDrumNote = 36;       // carril i de la batería = nota 36 + i
double noteSeconds (const Params&);     // duración de una nota del secuenciador (0,3 s o 1,4 s)

// Nota (mode 0) o golpe (mode 1) aislado, renderizado entero (para escucharlo al pulsar)
void renderHit (const Params&, int midiNote, double seconds, double sampleRate, float* out, int numSamples,
                const Sample* s = nullptr);
int hitLengthSamples (const Params&, int midiNote, double seconds, double sampleRate, const Sample* s = nullptr);

} // namespace afo::synth
