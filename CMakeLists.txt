# AllForOne — motor de audio nativo (C++20, JUCE + Tracktion Engine) y extensión Python afo_audio
cmake_minimum_required(VERSION 3.22)
project(AllForOneNative VERSION 0.2.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(AFO_BUILD_TESTS "Compilar las pruebas nativas" ON)

# Dependencias con versiones fijadas (cmake/deps.cmake)
include(cmake/deps.cmake)

# --- Biblioteca estática del motor ------------------------------------------
add_library(afo_engine STATIC native/src/AfoEngine.cpp)
target_include_directories(afo_engine PUBLIC native/src)
target_compile_definitions(afo_engine PUBLIC AFO_VERSION="${PROJECT_VERSION}")
# JUCE/Tracktion son PRIVADOS: AfoEngine.h no los expone (pimpl), así sus fuentes se
# compilan una sola vez dentro de afo_engine y no en cada objetivo que lo enlaza.
target_compile_definitions(afo_engine
    PRIVATE
        JUCE_USE_CURL=0
        JUCE_WEB_BROWSER=0
        JUCE_MODAL_LOOPS_PERMITTED=1
        JUCE_STRICT_REFCOUNTEDPOINTER=1
        JUCE_PLUGINHOST_VST3=1
        JUCE_DISPLAY_SPLASH_SCREEN=0
        JUCE_STANDALONE_APPLICATION=0
        TRACKTION_ENABLE_TIMESTRETCH_SOUNDTOUCH=1)
if (WIN32)
    target_compile_definitions(afo_engine PRIVATE JUCE_ASIO=0 JUCE_WASAPI=1 JUCE_DIRECTSOUND=1 NOMINMAX)
endif()
target_link_libraries(afo_engine
    PRIVATE
        tracktion::tracktion_core
        tracktion::tracktion_engine
        tracktion::tracktion_graph
        juce::juce_audio_devices
        juce::juce_audio_processors
        juce::juce_audio_utils)
if (UNIX AND NOT APPLE)
    target_link_libraries(afo_engine PUBLIC atomic)
endif()
if (MSVC)
    target_compile_options(afo_engine PRIVATE /bigobj /utf-8 /MP)
endif()

# --- Extensión Python afo_audio (.pyd en Windows) ----------------------------
pybind11_add_module(afo_audio native/bindings/afo_audio_module.cpp)
target_link_libraries(afo_audio PRIVATE afo_engine)
set(AFO_NATIVE_OUT "${CMAKE_SOURCE_DIR}/app/allforone/_native")
set_target_properties(afo_audio PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${AFO_NATIVE_OUT}"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${AFO_NATIVE_OUT}"
    LIBRARY_OUTPUT_DIRECTORY_DEBUG "${AFO_NATIVE_OUT}"
    RUNTIME_OUTPUT_DIRECTORY "${AFO_NATIVE_OUT}"
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${AFO_NATIVE_OUT}")

# --- Pruebas nativas ----------------------------------------------------------
if (AFO_BUILD_TESTS)
    enable_testing()
    add_executable(afo_engine_tests native/tests/engine_tests.cpp)
    target_link_libraries(afo_engine_tests PRIVATE afo_engine)
    add_test(NAME afo_engine_tests COMMAND afo_engine_tests "${CMAKE_BINARY_DIR}/test_out")
endif()
