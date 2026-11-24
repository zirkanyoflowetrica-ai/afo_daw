# AllForOne - compila el separador de stems (demucs.cpp: Demucs v4 en C++17 + Eigen, licencia MIT).
# Resultado: .cache\demucs.cpp\build-msvc\demucs_mt.cpp.main.exe (+ vcomp140.dll de OpenMP).
# package.ps1 lo copia a EXE\motores\demucs\afo-demucs.exe. Los modelos ggml (htdemucs 6 fuentes)
# se descargan desde el programa a modelos\demucs.
# Requiere Visual Studio Build Tools (C++), CMake, Ninja y Git.
# Uso: powershell -File tools\build_demucs.ps1 [carpeta del proyecto]
param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
$Repo = 'https://github.com/sevagh/demucs.cpp'
$Commit = '4edae49'                      # versión probada con AllForOne
$Src = Join-Path $Root '.cache\demucs.cpp'
$Build = Join-Path $Src 'build-msvc'

if (-not (Test-Path (Join-Path $Src 'CMakeLists.txt'))) {
    git clone --quiet --recurse-submodules $Repo $Src
    if ($LASTEXITCODE) { throw "git clone falló" }
}
Push-Location $Src
git fetch --quiet origin 2>$null
git checkout --quiet -f $Commit
if ($LASTEXITCODE) { Pop-Location; throw "No existe la versión $Commit" }
git submodule update --init --recursive --quiet
Pop-Location

# Ajustes para MSVC (el original es para GCC/Clang en Linux): banderas, runtime /MD, OpenMP de MSVC
# en vez de OpenBLAS, CMake moderno, sin pruebas de gtest, y rutas de salida como texto.
function Set-Patch([string]$file, [string]$from, [string]$to) {
    $t = [IO.File]::ReadAllText($file)
    if ($t.Contains($to)) { return }
    if (-not $t.Contains($from)) { throw "No se pudo ajustar $file (no está: $from)" }
    [IO.File]::WriteAllText($file, $t.Replace($from, $to))
}
$cm = Join-Path $Src 'CMakeLists.txt'
Set-Patch $cm 'cmake_minimum_required(VERSION 3.0)' 'cmake_minimum_required(VERSION 3.10)'
Set-Patch $cm 'option(USE_OPENBLAS "Use OpenBLAS" ON)' 'option(USE_OPENBLAS "Use OpenBLAS" OFF)'
Set-Patch $cm 'set(CMAKE_CXX_FLAGS "-Wall -Wextra")' 'set(CMAKE_CXX_FLAGS "/EHsc /bigobj /utf-8 /W1 /D_USE_MATH_DEFINES /DNOMINMAX")'
Set-Patch $cm 'set(CMAKE_CXX_FLAGS_RELEASE "-Ofast -march=native -fno-unsafe-math-optimizations -freciprocal-math -fno-signed-zeros")' 'set(CMAKE_CXX_FLAGS_RELEASE "/MD /O2 /Oi /arch:AVX2 /fp:fast /openmp /DNDEBUG")'
$t = [IO.File]::ReadAllText($cm)
$i = $t.IndexOf('# add target to run cpp tests')
if ($i -ge 0) { [IO.File]::WriteAllText($cm, $t.Substring(0, $i)) }
$ny = Join-Path $Src 'vendor\libnyquist\CMakeLists.txt'
$t = [IO.File]::ReadAllText($ny)
[IO.File]::WriteAllText($ny, ($t -replace '(?i)cmake_minimum_required\s*\(\s*VERSION\s+[0-9.]+[^)]*\)', 'cmake_minimum_required(VERSION 3.10)'))
foreach ($f in @('cli-apps\demucs.cpp', 'cli-apps\demucs_mt.cpp')) {
    Set-Patch (Join-Path $Src $f) 'write_audio_file(target_waveform, p_target);' 'write_audio_file(target_waveform, p_target.string());'
}

# Entorno de Visual Studio
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "Falta Visual Studio Build Tools con C++" }
cmd /c "`"$(Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat')`" >nul 2>&1 && set" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($matches[1])" -Value $matches[2] }
}
cmake -S $Src -B $Build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=cl -DCMAKE_CXX_COMPILER=cl
if ($LASTEXITCODE) { throw "Configuración de CMake falló" }
cmake --build $Build --target demucs_mt.cpp.main
if ($LASTEXITCODE) { throw "Compilación falló" }

# OpenMP de MSVC (vcomp140.dll) junto al ejecutable: el programa instalado no depende de Visual Studio
$omp = Get-ChildItem (Join-Path $vs 'VC\Redist\MSVC') -Recurse -Filter vcomp140.dll -ErrorAction SilentlyContinue |
       Where-Object { $_.FullName -match '\\x64\\' -and $_.FullName -notmatch 'debug' } | Select-Object -First 1
if (-not $omp) { throw "No se encontró vcomp140.dll (x64) en Visual Studio" }
Copy-Item $omp.FullName $Build -Force
Write-Host "Listo: $Build\demucs_mt.cpp.main.exe"
