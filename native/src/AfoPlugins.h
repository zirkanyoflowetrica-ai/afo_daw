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

#include <array>
#include <atomic>
#include <cmath>

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
        if (auto* midi = fc.bufferForMidiMessages)
        {
            if (midi->isAllNotesOff)
                for (auto& v : voices) v.active = false;
            for (auto& m : *midi)
                if (m.isNoteOn())
                {
                    const int at = juce::jlimit (0, juce::jmax (0, n - 1), juce::roundToInt (m.getTimeStamp() * sampleRate));
                    auto& v = freeVoice();
                    if (p.mode == 0) v.startNote (p, m.getNoteNumber(), synth::noteSeconds (p), sampleRate, at);
                    else             v.startDrum (p, m.getNoteNumber() - synth::firstDrumNote, sampleRate, at);
                }
        }

        auto* l = buf.getWritePointer (0, start);
        for (int i = 0; i < n; ++i)
        {
            float x = 0.0f;
            for (auto& v : voices)
                if (v.active) x += v.next();
            l[i] = x;
        }
        for (int c = 1; c < buf.getNumChannels(); ++c)
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

private:
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
