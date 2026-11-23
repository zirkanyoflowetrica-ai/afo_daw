@echo off
rem AllForOne - compila el motor de MIDI con IA local (llama-server de llama.cpp, Vulkan).
rem Resultado: .cache\llama.cpp\build-vk\bin\llama-server.exe y las DLL de GGML.
rem package.ps1 los copia a EXE\motores\llama. Requiere Visual Studio Build Tools (C++), CMake,
rem Ninja, Git y el Vulkan SDK de LunarG (https://vulkan.lunarg.com/sdk/home).
rem Uso: build_llama.bat [carpeta del proyecto]   (por defecto, la que contiene tools\)
rem Version fijada: v1.0.0 (licencia MIT), la que se probo con AllForOne.
setlocal
set LLAMA_REPO=https://github.com/ggml-org/llama.cpp.git
set LLAMA_COMMIT=b1b770d90d94cad9e9ea5b993bdbc383a522fb28
set "ROOT=%~dp0.."
if not "%~1"=="" set "ROOT=%~1"
set SRC=%ROOT%\.cache\llama.cpp

if not defined VULKAN_SDK (
    for /d %%d in (C:\VulkanSDK\*) do set VULKAN_SDK=%%d
)
if not defined VULKAN_SDK (
    echo [ERROR] Falta el Vulkan SDK: instalalo desde https://vulkan.lunarg.com/sdk/home
    exit /b 1
)
set PATH=%VULKAN_SDK%\Bin;%PATH%

if not exist "%SRC%\CMakeLists.txt" (
    git clone --filter=blob:none %LLAMA_REPO% "%SRC%" || exit /b 1
)
pushd "%SRC%"
git fetch --quiet origin
git checkout --quiet %LLAMA_COMMIT% || (popd & exit /b 1)

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

cmake -S . -B build-vk -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF ^
      -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DBUILD_SHARED_LIBS=ON || (popd & exit /b 1)
cmake --build build-vk -j %NUMBER_OF_PROCESSORS% --target llama-server || (popd & exit /b 1)
popd
echo [OK] Motor de MIDI compilado en %SRC%\build-vk\bin
exit /b 0
