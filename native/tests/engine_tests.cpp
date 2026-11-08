// Pruebas nativas mínimas del motor (sin dispositivo de audio: usan render offline).
#include "AfoEngine.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

static int failures = 0;
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
        afo::Engine engine ("AllForOneTests");
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

        CHECK (engine.removeTrack (t.id), "elimina pista");
        CHECK (engine.tracks().empty(), "sin pistas tras eliminar");
    }

    std::printf ("%s (%d fallos)\n", failures ? "PRUEBAS NATIVAS FALLIDAS" : "PRUEBAS NATIVAS OK", failures);
    return failures ? 1 : 0;
}
