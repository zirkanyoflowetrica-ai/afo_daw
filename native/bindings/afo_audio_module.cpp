// afo_audio — extensión Python (pybind11) del motor nativo de AllForOne.
// API pensada para crecer sin romper la interfaz: dicts simples hacia Python.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "AfoEngine.h"

namespace py = pybind11;

namespace
{
py::dict toDict (const afo::TrackInfo& t)
{
    py::dict d;
    d["id"] = t.id;
    d["name"] = t.name;
    d["source_path"] = t.sourcePath;
    d["length_seconds"] = t.lengthSeconds;
    d["sample_rate"] = t.sampleRate;
    d["num_channels"] = t.numChannels;
    return d;
}

afo::SynthSettings settings (int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
{
    afo::SynthSettings s;
    s.mode = mode; s.wave = wave; s.vel = vel; s.bri = bri; s.sus = sus; s.vol = vol; s.tun = tun; s.rev = rev;
    return s;
}
}

PYBIND11_MODULE (afo_audio, m)
{
    m.doc() = "AllForOne: motor de audio nativo (JUCE + Tracktion Engine)";
    m.attr("API_VERSION") = 4;

    m.def ("version", &afo::version);
    m.def ("juce_version", &afo::juceVersion);
    m.def ("write_test_tone", &afo::writeTestTone,
           py::arg ("path"), py::arg ("frequency") = 440.0, py::arg ("seconds") = 4.0,
           py::arg ("sample_rate") = 48000.0, py::arg ("amplitude_db") = -12.0f,
           "Escribe un WAV 24 bits estéreo con una senoidal (señal de prueba sintética).");
    m.def ("measure_file", [] (const std::string& p)
           {
               auto [peak, rms] = afo::measureFile (p);
               py::dict d; d["peak_db"] = peak; d["rms_db"] = rms; return d;
           }, py::arg ("path"));
    m.def ("pump_messages", &afo::Engine::pumpMessages, py::arg ("milliseconds") = 0,
           "Procesa mensajes pendientes de JUCE. En Windows lo hace el bucle de Qt; úsese en otras plataformas.");

    py::class_<afo::Engine> (m, "Engine")
        .def (py::init<const std::string&, const std::string&>(), py::arg ("app_name") = "AllForOne", py::arg ("data_dir") = "")
        .def ("device_info", [] (const afo::Engine& e)
              {
                  auto i = e.deviceInfo();
                  py::dict d;
                  d["type"] = i.typeName; d["output"] = i.outputName; d["input"] = i.inputName;
                  d["sample_rate"] = i.sampleRate; d["buffer_size"] = i.bufferSize;
                  d["output_channels"] = i.numOutputChannels; d["input_channels"] = i.numInputChannels;
                  d["open"] = i.open; d["available_types"] = i.availableTypes;
                  return d;
              })
        .def ("add_audio_track", [] (afo::Engine& e, const std::string& path, const std::string& name)
              { return toDict (e.addAudioTrack (path, name)); }, py::arg ("path"), py::arg ("name") = "")
        .def ("remove_track", &afo::Engine::removeTrack)
        .def ("add_synth_track", [] (afo::Engine& e, const std::string& name, int mode)
              { return toDict (e.addSynthTrack (name, mode)); }, py::arg ("name"), py::arg ("mode") = 0)
        .def ("set_synth_settings", [] (afo::Engine& e, int id, int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
              { e.setSynthSettings (id, settings (mode, wave, vel, bri, sus, vol, tun, rev)); },
              py::arg ("track_id"), py::arg ("mode") = 0, py::arg ("wave") = 0, py::arg ("vel") = 70.0f, py::arg ("bri") = 50.0f,
              py::arg ("sus") = false, py::arg ("vol") = 80.0f, py::arg ("tun") = 50.0f, py::arg ("rev") = 0.0f)
        .def ("set_synth_notes", &afo::Engine::setSynthNotes, py::arg ("track_id"), py::arg ("notes"), py::arg ("length_beats") = 64.0)
        .def ("audition_synth", [] (afo::Engine& e, int note, double seconds, int mode, int wave, float vel, float bri, bool sus, float vol, float tun, float rev)
              { return e.auditionSynth (settings (mode, wave, vel, bri, sus, vol, tun, rev), note, seconds); },
              py::arg ("note"), py::arg ("seconds") = 0.4, py::arg ("mode") = 0, py::arg ("wave") = 0, py::arg ("vel") = 70.0f,
              py::arg ("bri") = 50.0f, py::arg ("sus") = false, py::arg ("vol") = 80.0f, py::arg ("tun") = 50.0f, py::arg ("rev") = 0.0f)
        .def ("set_master_processing", &afo::Engine::setMasterProcessing, py::arg ("drive"), py::arg ("tone"), py::arg ("limiter"))
        .def ("tracks", [] (const afo::Engine& e)
              { py::list l; for (auto& t : e.tracks()) l.append (toDict (t)); return l; })
        .def ("track_peaks", &afo::Engine::trackPeaks, py::arg ("track_id"), py::arg ("buckets") = 600)
        .def ("set_track_gain_db", &afo::Engine::setTrackGainDb)
        .def ("set_track_pan", &afo::Engine::setTrackPan)
        .def ("set_track_mute", &afo::Engine::setTrackMute)
        .def ("set_track_solo", &afo::Engine::setTrackSolo)
        .def ("set_master_gain_db", &afo::Engine::setMasterGainDb)
        .def ("master_gain_db", &afo::Engine::masterGainDb)
        .def ("play", &afo::Engine::play)
        .def ("pause", &afo::Engine::pause)
        .def ("stop", &afo::Engine::stop)
        .def ("is_playing", &afo::Engine::isPlaying)
        .def ("position_seconds", &afo::Engine::positionSeconds)
        .def ("set_position_seconds", &afo::Engine::setPositionSeconds)
        .def ("length_seconds", &afo::Engine::lengthSeconds)
        .def ("set_tempo", &afo::Engine::setTempo)
        .def ("tempo", &afo::Engine::tempo)
        .def ("read_levels", [] (afo::Engine& e)
              {
                  auto l = e.readLevels();
                  py::dict d, tr;
                  d["master_l_db"] = l.masterL; d["master_r_db"] = l.masterR; d["master_vu_db"] = l.masterVu;
                  for (auto& [id, db] : l.tracks) tr[py::int_ (id)] = db;
                  d["tracks"] = tr;
                  return d;
              })
        .def ("render_to_wav", &afo::Engine::renderToWav, py::arg ("path"), py::call_guard<py::gil_scoped_release>())
        .def ("preview_play", &afo::Engine::previewPlay, py::arg ("path"), py::arg ("start_seconds") = 0.0)
        .def ("preview_stop", &afo::Engine::previewStop)
        .def ("preview_playing", &afo::Engine::previewPlaying)
        .def ("preview_position", &afo::Engine::previewPosition)
        .def ("preview_length", &afo::Engine::previewLength)
        .def ("preview_path", &afo::Engine::previewPath);
}
