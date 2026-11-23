@echo off
rem AllForOne - compila el motor de IA local (acestep.cpp: ACE-Step 1.5 en GGML con Vulkan).
rem Resultado: .cache\acestep.cpp\build-vk\ace-lm.exe, ace-synth.exe y las DLL de GGML.
rem package.ps1 los copia a EXE\motores\acestep. Requiere Visual Studio Build Tools (C++), CMake,
rem Ninja, Git y el Vulkan SDK de LunarG (https://vulkan.lunarg.com/sdk/home).
rem Uso: build_acestep.bat [carpeta del proyecto]   (por defecto, la que contiene tools\)
rem Version fijada: la que se probo con AllForOne (licencia MIT).
setlocal
set ACE_REPO=https://github.com/ServeurpersoCom/acestep.cpp.git
set ACE_COMMIT=973517b
set "ROOT=%~dp0.."
if not "%~1"=="" set "ROOT=%~1"
set SRC=%ROOT%\.cache\acestep.cpp

if not defined VULKAN_SDK (
    for /d %%d in (C:\VulkanSDK\*) do set VULKAN_SDK=%%d
)
if not defined VULKAN_SDK (
    echo [ERROR] Falta el Vulkan SDK: instalalo desde https://vulkan.lunarg.com/sdk/home
    exit /b 1
)
set PATH=%VULKAN_SDK%\Bin;%PATH%

if not exist "%SRC%\CMakeLists.txt" (
    git clone --recurse-submodules %ACE_REPO% "%SRC%" || exit /b 1
)
pushd "%SRC%"
git fetch --quiet origin
git checkout --quiet %ACE_COMMIT% || (popd & exit /b 1)
git submodule update --init --recursive --quiet || (popd & exit /b 1)

rem vswhere fuera de un for /f: los parentesis de "Program Files (x86)" lo rompen
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath > "%TEMP%\afo_vs_path.txt"
set /p VS=<"%TEMP%\afo_vs_path.txt"
if not defined VS (
    echo [ERROR] Falta Visual Studio Build Tools con C++
    popd
    exit /b 1
)
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || (popd & exit /b 1)

cmake -S . -B build-vk -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DGGML_NATIVE=OFF || (popd & exit /b 1)
cmake --build build-vk -j %NUMBER_OF_PROCESSORS% --target ace-lm ace-synth || (popd & exit /b 1)
popd
echo [OK] Motor de IA compilado en %SRC%\build-vk
exit /b 0
