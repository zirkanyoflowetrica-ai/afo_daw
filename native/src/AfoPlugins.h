// AllForOne — plugins propios de Tracktion (solo los incluye AfoEngine.cpp).
//
//  * AfoSynthPlugin: sintetizador de las pistas de Instrumento/Batería. Toca el clip MIDI de su
//    pista con la DSP de AfoSynth y añade la reverb de JUCE (perilla Reverb de Instrumentos).
//  * AfoMasterPlugin: la sección master de «Mezcla final»: fader, saturación, tono (EQ inclinada),
//    limitador de JUCE y medida VU (RMS con balística de 300 ms). Se aplica también al exportar.
//
// Todo corre en el callback de audio; los parámetros llegan por atómicos desde el hilo de mensajes.
#pragma once

#include "AfoSynth.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <memory>
#include <vector>

namespace afo
{
namespace te = tracktion;

//==============================================================================
class AfoSynthPlugin : public te::Plugin
{
public:
    AfoSynthPlugin (te::PluginCreationInfo info) : te::Plugin (info) {}
    ~AfoSynthPlugin() override { notifyListenersOfDeletion(); }

    static const char* getPluginName() { return "AllForOne Synth"; }
    static constexpr const char* xmlTypeName = "afoSynth";
    juce::String getName() const override              { return getPluginName(); }
    juce::String getPluginType() override              { return xmlTypeName; }
    juce::String getShortName (int) override           { return "AFO Synth"; }
    juce::String getSelectableDescription() override   { return getName(); }
    bool producesAudioWhenNoAudioInput() override      { return true; }
    bool isSynth() override                            { return true; }
    bool takesMidiInput() override                     { return true; }
    int getNumOutputChannelsGivenInputs (int) override { return 2; }

    void initialise (const te::PluginInitialisationInfo& i) override
    {
        sampleRate = i.sampleRate;
        for (auto& v : voices) v.active = false;
        reverb.setSampleRate (sampleRate);
        reverb.reset();
    }
    void deinitialise() override {}

    void applyToBuffer (const te::PluginRenderContext& fc) override
    {
        if (fc.destBuffer == nullptr)
            return;
        const juce::ScopedNoDenormals noDenormals;
        auto& buf = *fc.destBuffer;
        const int n = fc.bufferNumSamples, start = fc.bufferStartSample;
        for (int c = 0; c < buf.getNumChannels(); ++c)
            buf.clear (c, start, n);

        const auto p = params.load();
        const bool held = heldNotes.load();
        const bool arpOn = p.mode == 0 && p.arp > 0;
        if (! arpOn) arpCount = 0;
        auto* midi = fc.bufferForMidiMessages;
        if (midi != nullptr && midi->isAllNotesOff)
        {
            for (auto& v : voices) v.active = false;
            arpCount = 0;
        }
        if (! arpOn)
        {
            if (midi != nullptr)
                for (auto& m : *midi)
                    playEvent (p, m, eventSample (m, n), held);
        }
        else
        {
            // Arpegiador: las notas del clip solo se apuntan; suenan de una en una en cada paso de
            // la rejilla del tempo (posición de la canción, así cada render es idéntico)
            const double stepLen = sampleRate * 60.0 / (juce::jlimit (20.0f, 400.0f, bpm.load()) * (double) (1 << juce::jlimit (0, 3, p.arpRate)));
            const bool rolling = fc.isPlaying || fc.isRendering;
            const double pos0 = rolling ? fc.editTime.getStart().inSeconds() * sampleRate : freePos;
            int ev = 0;
            const int numEv = midi != nullptr ? midi->size() : 0;
            for (auto k = (int64_t) std::ceil (pos0 / stepLen - 1e-9); ; ++k)
            {
                const int b = (int) std::ceil (k * stepLen - pos0 - 1e-6);
                if (b >= n) break;
                for (; ev < numEv && eventSample ((*midi)[ev], n) <= b; ++ev)
                    arpEvent (p, (*midi)[ev], eventSample ((*midi)[ev], n), held);
                arpExpire (sampleCount + juce::jmax (0, b));
                arpStep (p, juce::jmax (0, b), k, stepLen);
            }
            for (; ev < numEv; ++ev)
                arpEvent (p, (*midi)[ev], eventSample ((*midi)[ev], n), held);
            arpExpire (sampleCount + n);
            if (! rolling) freePos += n;
        }
        sampleCount += n;

        // Cada voz a su paneo (Drum Rack); en el centro, igual que en mono
        auto* l = buf.getWritePointer (0, start);
        auto* r = buf.getNumChannels() > 1 ? buf.getWritePointer (1, start) : nullptr;
        for (int i = 0; i < n; ++i)
        {
            float xl = 0.0f, xr = 0.0f;
            for (auto& v : voices)
                if (v.active)
                {
                    const float x = v.next();
                    xl += x * v.panL; xr += x * v.panR;
                }
            l[i] = xl;
            if (r != nullptr) r[i] = xr;
        }
        for (int c = 2; c < buf.getNumChannels(); ++c)
            buf.copyFrom (c, start, buf, 0, start, n);

        // Reverb (solo instrumentos): sala media, mezcla según la perilla (0 = seca)
        if (p.mode == 0 && p.rev > 0.5f && buf.getNumChannels() >= 2)
        {
            juce::Reverb::Parameters rp;
            rp.roomSize = 0.6f; rp.damping = 0.5f; rp.width = 1.0f;
            rp.wetLevel = 0.45f * p.rev / 100.0f; rp.dryLevel = 1.0f;
            reverb.setParameters (rp);
            reverb.processStereo (buf.getWritePointer (0, start), buf.getWritePointer (1, start), n);
        }
    }

    synth::AtomicParams params;
    // true: el clip trae duraciones y velocidades propias (setSynthMidi); false: rejilla de 16 pasos
    std::atomic<bool> heldNotes { false };

    // Sampler de la batería: un golpe grabado por carril (nullptr = el sonido sintetizado).
    // Hilo de mensajes: setKit guarda el juego nuevo y lo publica con un atómico. Los juegos
    // anteriores se conservan hasta destruir el plugin (una voz puede estar leyendo uno), así el
    // hilo de audio nunca libera memoria.
    using Kit = std::array<std::shared_ptr<const synth::Sample>, synth::drumLanes>;
    void setKit (const Kit& k)
    {
        auto owned = std::make_unique<Kit> (k);
        kit.store (owned.get());
        kits.push_back (std::move (owned));
    }
    const synth::Sample* laneSample (int lane) const noexcept
    {
        const auto* k = kit.load();
        return (k != nullptr && lane >= 0 && lane < synth::drumLanes) ? (*k)[(size_t) lane].get() : nullptr;
    }
    // Sampler del Instrumento: su sonido va en el primer hueco del juego (las pistas de instrumento no tienen pads)
    const synth::Sample* instSample (const synth::Params& p) const noexcept
    {
        return p.mode == 0 && p.wave == synth::sampler ? laneSample (0) : nullptr;
    }

    std::atomic<float> bpm { 120.0f };      // tempo de la sesión (lo pone setTempo): rejilla del arpegiador

private:
    int eventSample (const juce::MidiMessage& m, int n) const
    {
        return juce::jlimit (0, juce::jmax (0, n - 1), juce::roundToInt (m.getTimeStamp() * sampleRate));
    }

    // Una nota del clip sin arpegiador
    void playEvent (const synth::Params& p, const juce::MidiMessage& m, int at, bool held)
    {
        if (m.isNoteOn() && p.mode == 0 && p.wave == synth::bass808 && note808 (p, m.getNoteNumber(), at, held))
            return;
        if (m.isNoteOn() && p.mode == 1)
            chokeGroup (p, m.getNoteNumber() - synth::firstDrumNote, at);
        if (m.isNoteOn())
        {
            auto& v = freeVoice();
            if (p.mode == 1)  v.startDrum (p, m.getNoteNumber() - synth::firstDrumNote, sampleRate, at,
                                           laneSample (m.getNoteNumber() - synth::firstDrumNote));
            else if (held)    v.startHeldNote (p, m.getNoteNumber(), (float) m.getVelocity(), sampleRate, at, instSample (p));
            else              v.startNote (p, m.getNoteNumber(), synth::noteSeconds (p), sampleRate, at, instSample (p));
            if (p.mode == 1 && held)
                v.g0 *= juce::jlimit (0.05, 1.27, m.getVelocity() / 100.0);
        }
        else if (m.isNoteOff() && held)
        {
            synth::Voice* best = nullptr;           // la más antigua de esa nota aún pulsada
            for (auto& v : voices)
                if (v.active && v.gated && ! v.released && v.offAt < 0 && v.note == m.getNoteNumber()
                    && (best == nullptr || v.t > best->t))
                    best = &v;
            if (best != nullptr) best->noteOff (at);
        }
    }

    // ---- Arpegiador -------------------------------------------------------------------------
    // Notas pulsadas: con duración propia (clip MIDI) hasta su note-off; las de la rejilla de 16
    // pasos no traen note-off y cuentan como pulsadas lo que dura su nota (0,3 s o 1,4 s).
    struct ArpNote { int note = 0; float vel = 100.0f; int64_t until = -1; };
    static constexpr int maxArpNotes = 32;
    std::array<ArpNote, maxArpNotes> arpNotes {};
    int arpCount = 0;
    int64_t arpCounter = 0;                 // pasos tocados desde que empezó el acorde
    int64_t sampleCount = 0;                // muestras procesadas (reloj propio para la rejilla)
    double freePos = 0.0;                   // posición de la rejilla con el transporte parado

    void arpEvent (const synth::Params& p, const juce::MidiMessage& m, int at, bool held)
    {
        const int note = m.getNoteNumber();
        if (m.isNoteOn())
        {
            for (int i = 0; i < arpCount; ++i)
                if (arpNotes[(size_t) i].note == note) { removeArpNote (i); break; }
            if (arpCount == 0) arpCounter = 0;          // acorde nuevo: empieza por su primera nota
            if (arpCount < maxArpNotes)
                arpNotes[(size_t) arpCount++] = { note, held ? (float) m.getVelocity() : 100.0f,
                                                  held ? -1 : sampleCount + at + (int64_t) (synth::noteSeconds (p) * sampleRate) };
        }
        else if (m.isNoteOff() && held)
        {
            for (int i = 0; i < arpCount; ++i)
                if (arpNotes[(size_t) i].note == note) { removeArpNote (i); break; }
        }
    }

    void removeArpNote (int i)
    {
        for (int j = i; j + 1 < arpCount; ++j) arpNotes[(size_t) j] = arpNotes[(size_t) j + 1];
        --arpCount;
    }

    void arpExpire (int64_t now)
    {
        for (int i = arpCount - 1; i >= 0; --i)
            if (arpNotes[(size_t) i].until >= 0 && arpNotes[(size_t) i].until <= now)
                removeArpNote (i);
    }

    // Paso k de la rejilla en la muestra `at` del bloque: suena la nota que toca del patrón
    void arpStep (const synth::Params& p, int at, int64_t k, double stepLen)
    {
        if (arpCount == 0) return;
        std::array<int, maxArpNotes> sorted {};
        std::array<float, maxArpNotes * 4> vel {};
        int count = 0;
        for (int i = 0; i < arpCount; ++i) { sorted[(size_t) count] = i; ++count; }
        std::sort (sorted.begin(), sorted.begin() + count,
                   [this] (int a, int b) { return arpNotes[(size_t) a].note < arpNotes[(size_t) b].note; });
        const int octaves = juce::jlimit (1, 4, p.arpOct);
        std::array<int, maxArpNotes * 4> pattern {};
        int len = 0;
        for (int o = 0; o < octaves; ++o)
            for (int i = 0; i < count; ++i)
            {
                const auto& a = arpNotes[(size_t) sorted[(size_t) i]];
                if (a.note + 12 * o > 127) continue;
                vel[(size_t) len] = a.vel;
                pattern[(size_t) len++] = a.note + 12 * o;
            }
        if (len == 0) return;
        const int64_t c = arpCounter++;
        int idx = 0;
        switch (p.arp)
        {
            case 2:  idx = len - 1 - (int) (c % len); break;                                   // abajo
            case 3:  if (len > 1) { const int per = 2 * len - 2, m = (int) (c % per); idx = m < len ? m : per - m; } break;
            case 4:  { auto h = (uint64_t) k * 0x9E3779B97F4A7C15ull; h ^= h >> 31; h *= 0xBF58476D1CE4E5B9ull; h ^= h >> 29;
                       idx = (int) (h % (uint64_t) len); } break;                               // al azar, repetible
            default: idx = (int) (c % len); break;                                              // arriba
        }
        const int note = pattern[(size_t) idx];
        const float v = vel[(size_t) idx];
        if (p.wave == synth::bass808)
            for (auto& o : voices)
                if (o.active && o.is808) o.choke();                                            // 808: una a la vez
        auto& voice = freeVoice();
        voice.startHeldNote (p, note, v, sampleRate, at, instSample (p));
        voice.offAt = juce::jmax ((int64_t) 1, (int64_t) (stepLen * juce::jlimit (5.0f, 100.0f, p.arpGate) / 100.0));
    }

    // 808 monofónico. Si la nota anterior sigue pulsada y hay deslizamiento, se desliza hasta la
    // nueva (true: no hace falta voz nueva). Si no, se corta con un fundido y suena la nueva.
    bool note808 (const synth::Params& p, int noteNumber, int at, bool held)
    {
        synth::Voice* last = nullptr;
        for (auto& v : voices)
            if (v.active && v.is808 && ! v.released && (last == nullptr || v.t < last->t))
                last = &v;
        if (last != nullptr && held && last->gated && last->offAt < 0 && p.glide > 0.5f)
        {
            last->glideTo (p, noteNumber, at);
            return true;
        }
        for (auto& v : voices)
            if (v.active && v.is808) v.choke();
        return false;
    }

    // Drum Rack: el golpe del pad `lane` corta lo que suena en los otros pads de su grupo
    void chokeGroup (const synth::Params& p, int lane, int at)
    {
        if (lane < 0 || lane >= synth::drumLanes) return;
        const int g = juce::roundToInt (p.dChoke[(size_t) lane]);
        if (g <= 0) return;
        for (auto& v : voices)
            if (v.active && v.mode == 1 && v.lane != lane && juce::roundToInt (p.dChoke[(size_t) v.lane]) == g)
                v.chokeAt (at);
    }

    std::atomic<const Kit*> kit { nullptr };
    std::vector<std::unique_ptr<Kit>> kits;

    synth::Voice& freeVoice()
    {
        synth::Voice* oldest = &voices[0];
        for (auto& v : voices)
        {
            if (! v.active) return v;
            if (v.t > oldest->t) oldest = &v;
        }
        return *oldest;                      // sin voces libres: se reutiliza la más antigua
    }

    double sampleRate = 48000.0;
    std::array<synth::Voice, synth::maxVoices> voices;
    juce::Reverb reverb;
};

//==============================================================================
// Limitador de seguridad del master: transparente por debajo del techo (ganancia exactamente 1),
// anticipación de 64 muestras para bajar antes de que llegue el pico, liberación de 100 ms.
struct PeakLimiter
{
    static constexpr int lookahead = 64;
    float ceiling = juce::Decibels::decibelsToGain (-1.0f);
    std::array<std::array<float, lookahead>, 2> delay {};
    int pos = 0, hold = 0;
    float target = 1.0f, gain = 1.0f, attack = 0.0f, release = 0.0f;

    void prepare (double sr)
    {
        for (auto& d : delay) d.fill (0.0f);
        pos = hold = 0; target = gain = 1.0f;
        attack = 1.0f - std::exp (-4.0f / (float) lookahead);          // llega antes de que salga el pico
        release = 1.0f - (float) std::exp (-1.0 / (0.1 * sr));
    }

    void process (float* l, float* r, int n, bool on, bool stereo) noexcept
    {
        for (int i = 0; i < n; ++i)
        {
            const float inL = l[i], inR = stereo ? r[i] : inL;
            const float peak = juce::jmax (std::abs (inL), std::abs (inR));
            if (on && peak > ceiling && ceiling / peak < target) { target = ceiling / peak; hold = lookahead; }
            else if (hold > 0) --hold;
            else target += (1.0f - target) * release;
            if (! on) target = 1.0f;
            gain += (target - gain) * (target < gain ? attack : release);
            if (gain > 0.99999f && target >= 1.0f) gain = 1.0f;
            float outL = delay[0][(size_t) pos] * gain, outR = delay[1][(size_t) pos] * gain;
            delay[0][(size_t) pos] = inL; delay[1][(size_t) pos] = inR;
            pos = (pos + 1) % lookahead;
            if (on) { outL = juce::jlimit (-ceiling, ceiling, outL); outR = juce::jlimit (-ceiling, ceiling, outR); }
            l[i] = outL;
            if (stereo) r[i] = outR;
        }
    }
};

//==============================================================================
class AfoMasterPlugin : public te::Plugin
{
public:
    AfoMasterPlugin (te::PluginCreationInfo info) : te::Plugin (info) {}
    ~AfoMasterPlugin() override { notifyListenersOfDeletion(); }

    static const char* getPluginName() { return "AllForOne Master"; }
    static constexpr const char* xmlTypeName = "afoMaster";
    juce::String getName() const override              { return getPluginName(); }
    juce::String getPluginType() override              { return xmlTypeName; }
    juce::String getShortName (int) override           { return "AFO Master"; }
    juce::String getSelectableDescription() override   { return getName(); }
    int getNumOutputChannelsGivenInputs (int n) override { return juce::jmax (2, n); }
    double getLatencySeconds() override { return PeakLimiter::lookahead / sampleRate; }   // Tracktion la compensa

    // Parámetros (hilo de mensajes → audio)
    std::atomic<float> gainDb { 0.0f };      // fader master
    std::atomic<float> drive { 0.0f };       // Saturación 0..100
    std::atomic<float> tone { 50.0f };       // Tono 0..100 (50 = plano)
    std::atomic<bool> limiterOn { true };    // Limitador
    std::atomic<float> ceilingDb { -1.0f };  // techo del limitador (dBFS)
    // Medida (audio → hilo de mensajes)
    std::atomic<float> vuDb { -100.0f };     // RMS de L+R con constante de 300 ms

    void initialise (const te::PluginInitialisationInfo& i) override
    {
        sampleRate = i.sampleRate;
        gain.reset (sampleRate, 0.02);
        gain.setCurrentAndTargetValue (juce::Decibels::decibelsToGain (gainDb.load()));
        limiter.prepare (sampleRate);
        for (auto& f : lowShelf)  f.reset();
        for (auto& f : highShelf) f.reset();
        lastTone = -1.0f;
        vuEnergy = 0.0;
        vuCoef = 1.0 - std::exp (-1.0 / (0.3 * sampleRate));
    }
    void deinitialise() override {}

    void applyToBuffer (const te::PluginRenderContext& fc) override
    {
        if (fc.destBuffer == nullptr)
            return;
        const juce::ScopedNoDenormals noDenormals;
        auto& buf = *fc.destBuffer;
        const int n = fc.bufferNumSamples, start = fc.bufferStartSample;
        const int chans = juce::jmin (2, buf.getNumChannels());
        if (chans == 0 || n == 0)
            return;

        // 1. fader (suavizado, sin chasquidos)
        gain.setTargetValue (juce::Decibels::decibelsToGain (gainDb.load(), -100.0f));
        for (int i = 0; i < n; ++i)
        {
            const float g = gain.getNextValue();
            for (int c = 0; c < chans; ++c)
                buf.getWritePointer (c, start)[i] *= g;
        }

        // 2. saturación: tanh con ganancia unidad en señal baja (no sube el volumen, redondea picos)
        const float d = drive.load();
        if (d > 0.5f)
        {
            const float k = 1.0f + 3.0f * d / 100.0f;
            for (int c = 0; c < chans; ++c)
            {
                auto* x = buf.getWritePointer (c, start);
                for (int i = 0; i < n; ++i)
                    x[i] = std::tanh (k * x[i]) / k;
            }
        }

        // 3. tono: EQ inclinada alrededor de 1 kHz (±6 dB en los extremos)
        const float t = tone.load();
        if (std::abs (t - 50.0f) > 0.5f)
        {
            if (t != lastTone)
            {
                const float db = (t - 50.0f) / 50.0f * 6.0f;
                auto lo = juce::dsp::IIR::Coefficients<float>::makeLowShelf (sampleRate, 250.0, 0.7f, juce::Decibels::decibelsToGain (-db));
                auto hi = juce::dsp::IIR::Coefficients<float>::makeHighShelf (sampleRate, 4000.0, 0.7f, juce::Decibels::decibelsToGain (db));
                for (auto& f : lowShelf)  f.coefficients = lo;
                for (auto& f : highShelf) f.coefficients = hi;
                lastTone = t;
            }
            for (int c = 0; c < chans; ++c)
            {
                auto* x = buf.getWritePointer (c, start);
                for (int i = 0; i < n; ++i)
                    x[i] = highShelf[(size_t) c].processSample (lowShelf[(size_t) c].processSample (x[i]));
            }
        }

        // 4. limitador (siempre retrasa la señal lo mismo, activo o no: la latencia no cambia)
        limiter.ceiling = juce::Decibels::decibelsToGain (ceilingDb.load());
        limiter.process (buf.getWritePointer (0, start), buf.getWritePointer (chans > 1 ? 1 : 0, start), n,
                         limiterOn.load(), chans > 1);

        // 5. VU: energía media de L y R con constante de 300 ms
        const auto* l = buf.getReadPointer (0, start);
        const auto* r = buf.getReadPointer (chans > 1 ? 1 : 0, start);
        for (int i = 0; i < n; ++i)
            vuEnergy += vuCoef * (0.5 * ((double) l[i] * l[i] + (double) r[i] * r[i]) - vuEnergy);
        vuDb = (float) (10.0 * std::log10 (vuEnergy + 1e-12));
    }

private:
    double sampleRate = 48000.0;
    juce::SmoothedValue<float> gain { 1.0f };
    PeakLimiter limiter;
    std::array<juce::dsp::IIR::Filter<float>, 2> lowShelf, highShelf;
    float lastTone = -1.0f;
    double vuEnergy = 0.0, vuCoef = 0.0;
};

} // namespace afo
