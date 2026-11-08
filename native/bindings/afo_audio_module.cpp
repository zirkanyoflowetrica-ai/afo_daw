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
}

PYBIND11_MODULE (afo_audio, m)
{
    m.doc() = "AllForOne: motor de audio nativo (JUCE + Tracktion Engine)";
    m.attr("API_VERSION") = 1;

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
        .def (py::init<const std::string&>(), py::arg ("app_name") = "AllForOne")
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
                  d["master_l_db"] = l.masterL; d["master_r_db"] = l.masterR;
                  for (auto& [id, db] : l.tracks) tr[py::int_ (id)] = db;
                  d["tracks"] = tr;
                  return d;
              })
        .def ("render_to_wav", &afo::Engine::renderToWav, py::arg ("path"));
}
