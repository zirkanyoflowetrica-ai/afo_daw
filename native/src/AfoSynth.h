// AllForOne — sintetizador de las pistas de Instrumento y Batería.
//
// Reproduce el diseño de sonido de PLANTILLA_DAW.html (osciladores → filtro → envolvente;
// batería con barridos, cuadradas y ruido filtrado), ahora dentro del motor: un plugin de
// Tracktion que toca las notas de un clip MIDI en el callback de audio. La misma DSP sirve
// para escuchar una nota suelta al pulsar (Synth::renderHit).
#pragma once

#include <atomic>
#include <cstdint>

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
};

// Copia sin bloqueos entre el hilo de mensajes (escribe) y el de audio (lee)
struct AtomicParams
{
    std::atomic<int> mode { 0 }, wave { 0 };
    std::atomic<float> vel { 70 }, bri { 50 }, vol { 80 }, tun { 50 };
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

    void startNote (const Params&, int midiNote, double seconds, double sampleRate, int delaySamples);
    void startDrum (const Params&, int lane, double sampleRate, int delaySamples);
    float next() noexcept;  // una muestra (0 antes de empezar o al acabar)
};

constexpr int maxVoices = 64;
constexpr int firstDrumNote = 36;       // carril i de la batería = nota 36 + i
double noteSeconds (const Params&);     // duración de una nota del secuenciador (0,3 s o 1,4 s)

// Nota (mode 0) o golpe (mode 1) aislado, renderizado entero (para escucharlo al pulsar)
void renderHit (const Params&, int midiNote, double seconds, double sampleRate, float* out, int numSamples);
int hitLengthSamples (const Params&, int midiNote, double seconds, double sampleRate);

} // namespace afo::synth
