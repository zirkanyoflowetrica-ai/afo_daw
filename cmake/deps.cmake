# Dependencias nativas fijadas.
#  - Tracktion Engine v3.2.0 (etiqueta oficial).
#  - JUCE: el commit exacto que Tracktion Engine v3.2.0 fija como submódulo
#    (19edd538429c93d277bf95b55aaa7e3eb545f951, JUCE 8.0.6+19). Se descarga por HTTPS
#    porque el submódulo de Tracktion usa una URL SSH que falla sin claves.
#  - pybind11: el instalado en el entorno Python (requirements-build.txt, pybind11==3.1.0),
#    para que la extensión coincida con el intérprete.
#
# Para trabajar sin red se puede apuntar a copias locales:
#   -DFETCHCONTENT_SOURCE_DIR_JUCE=... -DFETCHCONTENT_SOURCE_DIR_TRACKTION=...
include(FetchContent)
set(FETCHCONTENT_QUIET OFF)

FetchContent_Declare(juce
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        19edd538429c93d277bf95b55aaa7e3eb545f951
    GIT_SHALLOW    FALSE)

FetchContent_Declare(tracktion
    GIT_REPOSITORY https://github.com/Tracktion/tracktion_engine.git
    GIT_TAG        v3.2.0
    GIT_SHALLOW    TRUE
    GIT_SUBMODULES ""
    SOURCE_SUBDIR  modules)   # solo los módulos (sin ejemplos ni el submódulo JUCE)

# ASIO SDK oficial de Steinberg (2.3.4, doble licencia: propietaria o GPLv3; AllForOne la usa bajo GPLv3,
# compatible con su AGPLv3). Solo se necesita la cabecera iasiodrv.h y lo que incluye (carpeta common/).
# Con el SDK los drivers ASIO del sistema aparecen en el panel de audio, incluidos ASIO4ALL y FlexASIO.
if (WIN32)
    FetchContent_Declare(asiosdk
        URL      https://download.steinberg.net/sdk_downloads/ASIO-SDK_2.3.4_2025-10-15.zip
        URL_HASH SHA256=d5ebf0c20dd2c5f43771fd0c1418f4b361bf52434ee670097cfa6b3a335e2eca
        DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
    FetchContent_MakeAvailable(asiosdk)
endif()

# JUCE primero: los módulos de Tracktion usan juce_add_modules()
FetchContent_MakeAvailable(juce)
FetchContent_MakeAvailable(tracktion)

# pybind11 desde el Python del proyecto
find_package(Python 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
if (NOT pybind11_DIR)
    execute_process(COMMAND "${Python_EXECUTABLE}" -m pybind11 --cmakedir
        OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _pb_res)
    if (NOT _pb_res EQUAL 0)
        message(FATAL_ERROR "pybind11 no está instalado en ${Python_EXECUTABLE}. Ejecuta build_and_run.bat.")
    endif()
endif()
find_package(pybind11 CONFIG REQUIRED)
