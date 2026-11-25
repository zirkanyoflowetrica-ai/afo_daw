// AllForOne — sintetizador de las pistas de Instrumento y Batería.
//
// Reproduce el diseño de sonido de PLANTILLA_DAW.html (osciladores → filtro → envolvente;
// batería con barridos, cuadradas y ruido filtrado), ahora dentro del motor: un plugin de
// Tracktion que toca las notas de un clip MIDI en el callback de audio. La misma DSP sirve
// para escuchar una nota suelta al pulsar (Synth::renderHit).
#pragma once

#include <array>
#include <atomic>
#include <cstdint>
#include <vector>

namespace afo::synth
{

// Parámetros de una pista (los mismos nombres que en la plantilla)
struct Params
{
    int mode = 0;           // 0 = instrumento, 1 = batería
    int wave = 0;           // preset de Instrumentos: 0..7 → triangle, saw, square, saw, sine, saw, sine, triangle; 8 = 808; 9 = analógico
    float vel = 70.0f;      // Velocidad 0..100
    float bri = 50.0f;      // Brillo 0..100 → lowpass 400 + bri·60 Hz
    bool sus = false;       // Sostenido: nota de 1,4 s en vez de 0,3 s
    float vol = 80.0f;      // Batería: volumen 0..100
    float tun = 50.0f;      // Batería: afinación 0..100 → ×2^((tun−50)/50)
    float rev = 0.0f;       // Instrumentos: reverb 0..100 (0 = seca)
    // 808 Lab (preset 8): monofónico; las notas que se pisan se deslizan en vez de volver a sonar
    float glide = 30.0f;    // 0..100 → deslizamiento de 0 a 300 ms entre notas que se pisan
    float drive = 30.0f;    // 0..100 → saturación (armónicos que se oyen en altavoces pequeños)
    float punch = 50.0f;    // 0..100 → la afinación arranca hasta 24 semitonos arriba y cae en 40 ms
    // Arpegiador (Instrumentos): las notas pulsadas suenan una tras otra, al tempo de la sesión
    int arp = 0;            // 0 apagado, 1 arriba, 2 abajo, 3 arriba y abajo, 4 al azar (repetible)
    int arpRate = 2;        // 0..3 → negras, corcheas, semicorcheas, fusas
    int arpOct = 1;         // 1..4 octavas que recorre
    float arpGate = 50.0f;  // 5..100 % del paso que suena cada nota
    // Drum Synth: ajustes de cada carril de la batería, 0..100 (50 = el golpe de fábrica)
    //   afinación ×2^((v−50)/50) · caída ×2^((v−50)/25) · tono (filtro / golpe de afinación / intervalo)
    //   · nivel (v/50)², 0 = mudo, 100 = +12 dB
    std::array<float, 8> dTun { 50, 50, 50, 50, 50, 50, 50, 50 }, dDec { 50, 50, 50, 50, 50, 50, 50, 50 },
                         dTone { 50, 50, 50, 50, 50, 50, 50, 50 }, dLvl { 50, 50, 50, 50, 50, 50, 50, 50 };
    // Drum Rack: paneo de cada pad (0 izquierda, 50 centro, 100 derecha) y grupo de corte (0 ninguno,
    // 1 A, 2 B): un golpe corta, con un fundido de 5 ms, lo que suena en los otros pads de su grupo
    std::array<float, 8> dPan { 50, 50, 50, 50, 50, 50, 50, 50 }, dChoke { 0, 0, 0, 0, 0, 0, 0, 0 };
    // Sinte analógico (preset 9): dos dientes de sierra desafinados y filtro paso bajo resonante con envolvente
    float anDet = 30.0f;    // 0..100 → ±0..25 cents entre los dos osciladores
    float anCut = 55.0f;    // 0..100 → corte 40 Hz · 2^(v·9/100) (sigue a medias la nota)
    float anRes = 30.0f;    // 0..100 → resonancia (100 = casi autooscila)
    float anEnv = 50.0f;    // 0..100 → la envolvente abre el filtro hasta 5 octavas y cae en 0,3 s
    float anAtk = 5.0f;     // 0..100 → ataque de 1 ms a 2 s
    float anRel = 30.0f;    // 0..100 → liberación de 10 ms a 3 s
    // Sinte de tablas (preset 10): 8 ondas por tabla, sin aliasing (una tabla por octava), leídas entre dos
    int wtTab = 0;          // 0 Básica (seno → triángulo → sierra → cuadrada), 1 Vocal (u o a e i), 2 Metálica, 3 Digital (pulso)
    float wtPos = 40.0f;    // 0..100 → posición en la tabla
    float wtEnv = 30.0f;    // 0..100 → barrido: la posición empieza más adelante y vuelve en 0,4 s
    float wtLfo = 0.0f;     // 0..100 → movimiento: la posición oscila ±35 % a 1 Hz
    float wtAtk = 5.0f;     // 0..100 → ataque de 1 ms a 2 s
    float wtRel = 30.0f;    // 0..100 → liberación de 10 ms a 3 s
    // Sampler (preset 11): el sonido cargado en la pista, afinado nota a nota desde su nota raíz
    int smRoot = 60;        // nota MIDI en la que el sonido suena tal cual
    float smStart = 0.0f;   // 0..100 % → punto de inicio dentro del sonido
    bool smLoop = false;    // mientras la nota sigue pulsada, repite desde el inicio del bucle hasta el final
    float smLoopAt = 50.0f; // 0..100 % → inicio del bucle (fundido de 10 ms en la unión)
    float smAtk = 2.0f;     // 0..100 → ataque de 1 ms a 2 s
    float smRel = 25.0f;    // 0..100 → liberación de 10 ms a 3 s
};

constexpr int bass808 = 8;              // índice del preset 808 en Instrumentos
constexpr int analog = 9;               // «Sinte analógico»
constexpr int wavetable = 10;           // «Sinte de tablas»
constexpr int sampler = 11;             // «Sampler»: el sonido cargado en la pista
constexpr int numPresets = 12;
constexpr int wtTables = 4;

// Construye las tablas de onda (unos 50 ms): se llama al crear el motor, no en el hilo de audio
void warmUp();

// Copia sin bloqueos entre el hilo de mensajes (escribe) y el de audio (lee)
struct AtomicParams
{
    std::atomic<int> mode { 0 }, wave { 0 };
    std::atomic<float> vel { 70 }, bri { 50 }, vol { 80 }, tun { 50 }, rev { 0 }, glide { 30 }, drive { 30 }, punch { 50 };
    std::atomic<bool> sus { false };
    std::atomic<int> arp { 0 }, arpRate { 2 }, arpOct { 1 };
    std::atomic<float> arpGate { 50 };
    std::array<std::atomic<float>, 8> dTun, dDec, dTone, dLvl, dPan, dChoke;
    std::atomic<float> anDet { 30 }, anCut { 55 }, anRes { 30 }, anEnv { 50 }, anAtk { 5 }, anRel { 30 };
    std::atomic<int> wtTab { 0 };
    std::atomic<float> wtPos { 40 }, wtEnv { 30 }, wtLfo { 0 }, wtAtk { 5 }, wtRel { 30 };
    std::atomic<int> smRoot { 60 };
    std::atomic<bool> smLoop { false };
    std::atomic<float> smStart { 0 }, smLoopAt { 50 }, smAtk { 2 }, smRel { 25 };
    AtomicParams()
    {
        for (size_t i = 0; i < 8; ++i) { dTun[i] = dDec[i] = dTone[i] = dLvl[i] = dPan[i] = 50.0f; dChoke[i] = 0.0f; }
    }
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
constexpr double maxInstSampleSeconds = 30.0;   // sonido del Sampler del Instrumento

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
    // 808: seno con golpe de afinación, saturación y deslizamiento hacia la nota siguiente
    bool is808 = false;
    double drive = 0, punchSemis = 0, glideFrom = 0, glideSamples = 0, glideT = 0;
    int pendingNote = -1, pendingWait = 0;  // deslizamiento que empieza dentro del bloque
    // Sinte analógico: dos sierras (PolyBLEP) y filtro de estado variable (TPT) con envolvente
    bool isAnalog = false;
    double detune = 1.0, cutBase = 1000, envOct = 0, res = 0;
    double ic1 = 0, ic2 = 0, fa1 = 0, fa2 = 0, fa3 = 0;
    int filtWait = 0;
    // Drum Rack: ganancia de cada canal (paneo con el centro a 1, como antes) y corte pendiente en el bloque
    float panL = 1.0f, panR = 1.0f;
    int chokeWait = -1;
    // Sinte de tablas: las 8 ondas de su tabla al nivel de armónicos que cabe bajo Nyquist para esta nota
    bool isWave = false;
    const float* wtData = nullptr;
    double wtPos = 0, wtSweep = 0, wtLfo = 0, wtCur = 0;
    // Sampler: lectura afinada del sonido de la pista, con bucle opcional (fundido en la unión)
    bool isSampler = false, smLoop = false;
    double loopStart = 0, loopEnd = 0, xfade = 0;

    void startNote (const Params&, int midiNote, double seconds, double sampleRate, int delaySamples,
                    const Sample* s = nullptr);
    // Nota que sigue al note-off: ataque, caída hasta el nivel de sostén del preset y release
    void startHeldNote (const Params&, int midiNote, float velocity, double sampleRate, int delaySamples,
                        const Sample* s = nullptr);
    void startDrum (const Params&, int lane, double sampleRate, int delaySamples, const Sample* s = nullptr);
    void noteOff (int atSample) noexcept;   // posición dentro del bloque
    // 808: la nota nueva pisa a esta (que sigue pulsada): se desliza hasta ella sin volver a empezar
    void glideTo (const Params&, int midiNote, int atSample) noexcept;
    // 808 monofónico: corta esta voz con un fundido de 5 ms (sin clic) para dejar sonar la nueva
    void choke() noexcept;
    // Grupo de corte: el golpe que corta llega en la muestra `atSample` del bloque
    void chokeAt (int atSample) noexcept;
    double currentHz() const noexcept;
    float next() noexcept;  // una muestra (0 antes de empezar o al acabar)
};

constexpr int maxVoices = 64;
constexpr int firstDrumNote = 36;       // carril i de la batería = nota 36 + i
double noteSeconds (const Params&);     // duración de una nota del secuenciador (0,3 s o 1,4 s)

// Nota (mode 0) o golpe (mode 1) aislado, renderizado entero (para escucharlo al pulsar)
void renderHit (const Params&, int midiNote, double seconds, double sampleRate, float* out, int numSamples,
                const Sample* s = nullptr);
int hitLengthSamples (const Params&, int midiNote, double seconds, double sampleRate, const Sample* s = nullptr);

// ---- Step Sequencer de la Batería ------------------------------------------------------------
// Cada paso encendido de un pad: fuerza (velocidad MIDI 1..127), probabilidad de sonar (1..100 %)
// y repeticiones dentro del paso (1..4, «ratchet»). Cada pad tiene su largo (1..16 pasos): con
// largos distintos los pads se desfasan (polimetría). La probabilidad se decide con una semilla:
// la misma semilla da siempre las mismas notas (al reproducir y al exportar).
struct Step { int lane = 0, step = 0, vel = 100, prob = 100, ratchet = 1; };
struct StepPattern
{
    std::vector<Step> steps;
    std::array<int, drumLanes> length { 16, 16, 16, 16, 16, 16, 16, 16 };
    std::vector<bool> bars;             // compases que suenan (vacío = todos)
    double swing = 0.0;                 // 0..1: las semicorcheas pares se retrasan hasta media semicorchea
    uint32_t seed = 0;
    int totalSteps = 256;               // semicorcheas del patrón (16 compases)
};
struct StepNote { double beat = 0, length = 0.25; int note = firstDrumNote, vel = 100; };
// Las notas del patrón, en negras, ordenadas por tiempo
std::vector<StepNote> expandSteps (const StepPattern&);

} // namespace afo::synth
