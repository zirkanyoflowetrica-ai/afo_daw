// Pruebas nativas mínimas del motor (sin dispositivo de audio: usan render offline).
#include "AfoEngine.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

/** Escribe un WAV en coma flotante de 64 bits, como los que exportan muchos DAW.
    JUCE no los lee (acepta hasta 32 bits): AllForOne registra su propio lector. */
static bool write_float64_wav (const std::string& path, double seconds, double freq, double amp,
                               unsigned channels = 2, unsigned rate = 48000)
{
    const auto frames = (uint32_t) (seconds * rate);
    const uint32_t bytes = frames * channels * 8;
    std::ofstream f (path, std::ios::binary);
    if (! f) return false;
    auto u32 = [&f] (uint32_t v) { f.write (reinterpret_cast<const char*> (&v), 4); };
    auto u16 = [&f] (uint16_t v) { f.write (reinterpret_cast<const char*> (&v), 2); };
    f.write ("RIFF", 4); u32 (36 + bytes); f.write ("WAVEfmt ", 8);
    u32 (16); u16 (3); u16 ((uint16_t) channels); u32 (rate);
    u32 (rate * channels * 8); u16 ((uint16_t) (channels * 8)); u16 (64);
    f.write ("data", 4); u32 (bytes);
    std::vector<double> frame (channels);
    for (uint32_t i = 0; i < frames; ++i)
    {
        const double v = amp * std::sin (2.0 * 3.14159265358979323846 * freq * i / rate);
        for (unsigned c = 0; c < channels; ++c) frame[c] = v;
        f.write (reinterpret_cast<const char*> (frame.data()), (std::streamsize) channels * 8);
    }
    return f.good();
}

static int failures = 0;
static bool juce_file_size_ok (const std::string& p)
{
    // 2 s estéreo 24 bits a 44.1/48 kHz: menos de 1 MB. Un archivo con datos añadidos sería mayor.
    return std::filesystem::file_size (p) < 1000000;
}
#define CHECK(cond, msg) do { if (cond) std::printf ("[OK]   %s\n", msg); else { std::printf ("[FAIL] %s\n", msg); ++failures; } } while (0)

int main (int argc, char** argv)
{
    namespace fs = std::filesystem;
    const fs::path out = argc > 1 ? fs::path (argv[1]) : fs::temp_directory_path() / "afo_engine_tests";
    fs::create_directories (out);
    const auto tone = (out / "tone_440.wav").string();
    const auto render = (out / "render.wav").string();

    std::printf ("AllForOne engine %s | JUCE %s\n", afo::version().c_str(), afo::juceVersion().c_str());

    CHECK (afo::writeTestTone (tone, 440.0, 2.0, 48000.0, -12.0f), "escribe tono de prueba");
    auto [tonePeak, toneRms] = afo::measureFile (tone);
    std::printf ("       tono: pico %.2f dBFS, RMS %.2f dBFS\n", tonePeak, toneRms);
    CHECK (tonePeak > -12.5f && tonePeak < -11.5f, "pico del tono = -12 dBFS");

    {
        afo::Engine engine ("AllForOneTests", (out / "datos").string());
        auto dev = engine.deviceInfo();
        std::printf ("       dispositivo: '%s' (%s) abierto=%d sr=%.0f buf=%d\n",
                     dev.outputName.c_str(), dev.typeName.c_str(), (int) dev.open, dev.sampleRate, dev.bufferSize);

        auto t = engine.addAudioTrack (tone, "Tono de prueba");
        CHECK (t.id > 0 && t.lengthSeconds > 1.9 && t.lengthSeconds < 2.1, "crea pista de audio con clip de 2 s");
        CHECK (engine.lengthSeconds() > 1.9, "longitud del Edit");

        auto peaks = engine.trackPeaks (t.id, 100);
        CHECK (peaks.size() == 100 && peaks[50] > 0.2f, "picos de forma de onda reales");

        engine.setTempo (120.0);
        CHECK (std::abs (engine.tempo() - 120.0) < 0.01, "tempo");

        CHECK (std::abs (engine.masterGainDb()) < 0.01f, "master inicia en 0 dB");
        engine.setTrackGainDb (t.id, -6.0f);
        CHECK (engine.renderToWav (render), "render offline a WAV");
        auto [rp, rr] = afo::measureFile (render);
        std::printf ("       render (pista -6 dB): pico %.2f dBFS, RMS %.2f dBFS\n", rp, rr);
        CHECK (std::abs (rp - (tonePeak - 6.0f)) < 0.1f, "ganancia de pista exacta en el render (-12 -6 = -18 dBFS)");
        engine.setTrackGainDb (t.id, -3.0f);
        CHECK (engine.renderToWav (render), "render sobre un archivo existente");
        auto [rp2, rr2] = afo::measureFile (render);
        CHECK (std::abs (rp2 - (tonePeak - 3.0f)) < 0.1f, "el archivo existente se reemplaza (no se corrompe)");
        CHECK (afo::measureFile (render).first > -100.0f && juce_file_size_ok (render), "WAV reescrito válido");
        engine.setTrackGainDb (t.id, -6.0f);

        // Segunda pista a -20 dB: solo/mute deben decidir qué se exporta
        auto t2 = engine.addAudioTrack (tone, "Tono 2");
        engine.setTrackGainDb (t2.id, -20.0f);
        engine.setTrackSolo (t2.id, true);
        const auto solo = (out / "render_solo.wav").string();
        CHECK (engine.renderToWav (solo), "render con solo");
        auto [sp, sr] = afo::measureFile (solo);
        std::printf ("       render (solo pista 2): pico %.2f dBFS\n", sp);
        CHECK (std::abs (sp - (tonePeak - 20.0f)) < 0.1f, "solo exporta solo la pista solista");
        engine.setTrackSolo (t2.id, false);
        engine.setTrackMute (t.id, true);
        engine.setTrackMute (t2.id, true);
        CHECK (! engine.renderToWav ((out / "render_muted.wav").string()), "todo silenciado: no se exporta nada");
        CHECK (engine.removeTrack (t2.id), "elimina pista 2");

        CHECK (engine.previewPlay (tone, 0.5) || ! dev.open, "previsualización acepta el archivo");
        CHECK (engine.previewLength() > 1.9 || ! dev.open, "longitud de la previsualización");
        engine.previewStop();
        CHECK (! engine.previewPlaying(), "previsualización detenida");
        CHECK (engine.removeTrack (t.id), "elimina pista");
        CHECK (engine.tracks().empty(), "sin pistas tras eliminar");

        // --- WAV en coma flotante de 64 bits (el caso de los stems del usuario) ----------
        // JUCE lee hasta 32 bits y Tracktion necesita además un lector mapeado en memoria para
        // reproducir, así que estos archivos NO entran al motor: debe rechazarlos de inmediato y
        // con un mensaje claro, que es lo que dispara la conversión automática en engine_host.py.
        // (Se probó un lector propio de 64 bits: abre y mide bien, pero el render de Tracktion se
        //  queda esperando bloques para siempre. Un cuelgue es peor que una conversión de 1 s.)
        const auto f64 = (out / "stem_float64.wav").string();
        CHECK (write_float64_wav (f64, 2.0, 440.0, 0.25), "escribe WAV float de 64 bits");
        bool rejected = false;
        std::string why;
        const auto t0 = std::chrono::steady_clock::now();
        try { engine.addAudioTrack (f64, "Stem 64 bits"); }
        catch (const std::exception& e) { rejected = true; why = e.what(); }
        const auto ms = std::chrono::duration_cast<std::chrono::milliseconds> (std::chrono::steady_clock::now() - t0).count();
        std::printf ("       float64: rechazado en %lld ms -> %s\n", (long long) ms, why.c_str());
        CHECK (rejected && why.find ("no se puede leer el audio") != std::string::npos,
               "el motor rechaza el WAV de 64 bits con un error claro (no se cuelga)");
        CHECK (ms < 2000, "lo rechaza al momento, sin bloquearse");
        CHECK (engine.tracks().empty(), "una pista rechazada no deja restos");
    }

    std::printf ("%s (%d fallos)\n", failures ? "PRUEBAS NATIVAS FALLIDAS" : "PRUEBAS NATIVAS OK", failures);
    return failures ? 1 : 0;
}
