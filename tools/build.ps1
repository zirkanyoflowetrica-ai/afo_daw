<#
  AllForOne - configuracion, compilacion, pruebas y arranque (Windows 11 x64).
  Uso normal: doble clic en build_and_run.bat

  Parametros:
    -Run          Inicia AllForOne al terminar
    -SkipTests    No ejecuta pruebas
    -Clean        Borra build\win-release antes de compilar (las dependencias en .deps se conservan)
    -NoInstall    No ofrece instalar herramientas que falten (solo informa)

  Principios: no modifica el PATH global, no borra instalaciones previas, trabaja con rutas
  locales (.venv, .deps, build) y registra todo en logs\.
#>
param(
    [switch]$Run,
    [switch]$SkipTests,
    [switch]$Clean,
    [switch]$NoInstall
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogFile = Join-Path $LogDir "build_$Stamp.log"
Start-Transcript -Path $LogFile -Append | Out-Null

function Step($msg)  { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Yellow }
function Ok($msg)    { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "    [!]  $msg" -ForegroundColor DarkYellow }
function Fail($msg)  {
    Write-Host "    [ERROR] $msg" -ForegroundColor Red
    Write-Host "    Registro completo: $LogFile"
    Stop-Transcript | Out-Null
    exit 1
}
function Ask($question) {
    if ($NoInstall) { return $false }
    $a = Read-Host "    $question [s/N]"
    return ($a -match '^(s|si|y|yes)$')
}
# Ejecuta un programa externo enviando su salida (stdout+stderr) al registro y devuelve el codigo
function Run-Native($exe, [string[]]$argList) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $exe @argList 2>&1 | ForEach-Object { "$_" } | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return $code
}
function Invoke-Checked($exe, [string[]]$argList, $what) {
    $code = Run-Native $exe $argList
    if ($code -ne 0) { Fail "$what (codigo $code)" }
}
function Have-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }

Write-Host "AllForOne - build_and_run  ($Stamp)" -ForegroundColor Cyan
Write-Host "Carpeta del proyecto: $Root"

# ---------------------------------------------------------------------------
Step "1/9 Sistema"
$os = Get-CimInstance Win32_OperatingSystem
Ok "$($os.Caption) $($os.OSArchitecture) build $($os.BuildNumber)"
if (-not [Environment]::Is64BitOperatingSystem) { Fail "Se requiere Windows de 64 bits" }
$drive = (Get-Item $Root).PSDrive
$freeGB = [math]::Round((Get-PSDrive $drive.Name).Free / 1GB, 1)
if ($freeGB -lt 8) { Warn "Quedan $freeGB GB libres en $($drive.Name):. La primera compilacion necesita ~6-8 GB." } else { Ok "$freeGB GB libres" }

# ---------------------------------------------------------------------------
Step "2/9 Python 3.12 (o 3.13)"
function Find-Python {
    foreach ($v in @('3.12', '3.13')) {
        try {
            $p = & py "-$v" -c "import sys;print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p) { return $p.Trim() }
        } catch {}
    }
    foreach ($cand in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                        "$env:ProgramFiles\Python312\python.exe",
                        "$env:ProgramFiles\Python313\python.exe")) {
        if (Test-Path $cand) { return $cand }
    }
    return $null
}
$SysPython = Find-Python
if (-not $SysPython) {
    Warn "No se encontro Python 3.12/3.13."
    if ((Have-Winget) -and (Ask "Instalar Python 3.12 desde winget (python.org, solo para tu usuario, sin administrador)?")) {
        Invoke-Checked winget @('install','-e','--id','Python.Python.3.12','--scope','user','--accept-package-agreements','--accept-source-agreements') "Instalacion de Python"
        $SysPython = Find-Python
    }
    if (-not $SysPython) { Fail "Instala Python 3.12 x64 desde https://www.python.org/downloads/windows/ y vuelve a ejecutar." }
}
$pyver = & $SysPython -c "import sys,platform;print(sys.version.split()[0], platform.architecture()[0])"
Ok "$SysPython ($pyver)"
if ($pyver -notmatch '64bit') { Fail "Se requiere Python de 64 bits" }

# ---------------------------------------------------------------------------
Step "3/9 Git (para descargar JUCE y Tracktion Engine)"
$Git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $Git -and (Test-Path "$env:ProgramFiles\Git\cmd\git.exe")) { $Git = "$env:ProgramFiles\Git\cmd\git.exe" }
if (-not $Git) {
    Warn "Git no encontrado."
    if ((Have-Winget) -and (Ask "Instalar Git desde winget (git-scm.com)? Puede pedir permisos de administrador.")) {
        Invoke-Checked winget @('install','-e','--id','Git.Git','--accept-package-agreements','--accept-source-agreements') "Instalacion de Git"
        if (Test-Path "$env:ProgramFiles\Git\cmd\git.exe") { $Git = "$env:ProgramFiles\Git\cmd\git.exe" }
    }
    if (-not $Git) { Fail "Instala Git desde https://git-scm.com/download/win y vuelve a ejecutar." }
}
# Solo para este proceso (no se toca el PATH global)
$env:PATH = (Split-Path $Git) + ';' + $env:PATH
Ok (& $Git --version)

# ---------------------------------------------------------------------------
Step "4/9 Visual Studio Build Tools (MSVC x64 + Windows SDK)"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
function Find-VS {
    if (-not (Test-Path $vswhere)) { return $null }
    $p = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($p) { return $p.Trim() }
    return $null
}
$VS = Find-VS
if (-not $VS) {
    Warn "No se encontro MSVC (Visual Studio 2022 Build Tools con 'Desarrollo para el escritorio con C++')."
    if ((Have-Winget) -and (Ask "Instalar Visual Studio 2022 Build Tools con la carga C++ (~5 GB, requiere administrador)?")) {
        Invoke-Checked winget @('install','-e','--id','Microsoft.VisualStudio.2022.BuildTools','--accept-package-agreements','--accept-source-agreements',
            '--override','--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended') "Instalacion de Build Tools"
        $VS = Find-VS
    }
    if (-not $VS) { Fail "Instala 'Build Tools para Visual Studio 2022' con la carga 'Desarrollo para el escritorio con C++' (incluye Windows SDK)." }
}
$vcvars = Join-Path $VS 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $vcvars)) { Fail "No existe $vcvars" }
Ok "Visual Studio en $VS"
# Importar el entorno de vcvars64 en este proceso
$envDump = cmd /c "`"$vcvars`" >nul 2>&1 && set"
foreach ($line in $envDump) { if ($line -match '^([^=]+)=(.*)$') { Set-Item -Path "env:$($matches[1])" -Value $matches[2] } }
if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { Fail "cl.exe no disponible tras vcvars64" }
Ok "MSVC toolset $env:VCToolsVersion"
if ($env:WindowsSDKVersion) { Ok "Windows SDK $($env:WindowsSDKVersion.TrimEnd('\'))" } else { Warn "No se detecto WindowsSDKVersion" }

# ---------------------------------------------------------------------------
Step "5/9 Entorno Python local (.venv) y dependencias fijadas"
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path $Py)) {
    Invoke-Checked $SysPython @('-m','venv',$Venv) "Creacion de .venv"
    Ok "Creado .venv"
}
$reqFiles = @('requirements-app.txt','requirements-build.txt')
$hash = ($reqFiles | ForEach-Object { (Get-FileHash (Join-Path $Root $_) -Algorithm SHA256).Hash }) -join ''
$stampFile = Join-Path $Venv '.afo-req-hash'
if (-not (Test-Path $stampFile) -or (Get-Content $stampFile -Raw).Trim() -ne $hash) {
    Invoke-Checked $Py @('-m','pip','install','--upgrade','pip') "Actualizacion de pip"
    Invoke-Checked $Py @('-m','pip','install','-r',(Join-Path $Root 'requirements-build.txt')) "Instalacion de dependencias Python"
    Set-Content -Path $stampFile -Value $hash
    Ok "Dependencias instaladas"
} else { Ok "Dependencias ya instaladas (sin cambios en requirements)" }
$code = Run-Native $Py @('-c', "import PySide6, PySide6.QtWebEngineCore, pybind11, numpy, soundfile; print('    PySide6', PySide6.__version__, '| pybind11', pybind11.__version__, '| numpy', numpy.__version__)")
if ($code -ne 0) { Fail "Las dependencias de Python no se importan correctamente" }
$VenvScripts = Join-Path $Venv 'Scripts'
$CMake = Join-Path $VenvScripts 'cmake.exe'
$Ninja = Join-Path $VenvScripts 'ninja.exe'
Ok ((& $CMake --version | Select-Object -First 1) + " | ninja " + (& $Ninja --version))

# ---------------------------------------------------------------------------
Step "6/9 Configurar CMake (JUCE + Tracktion Engine fijados en cmake\deps.cmake)"
$Build = Join-Path $Root 'build\win-release'
if ($Clean -and (Test-Path $Build)) { Remove-Item -Recurse -Force $Build; Ok "build\win-release eliminado (-Clean)" }
$Deps = Join-Path $Root '.deps'
$cfgArgs = @('-S', $Root, '-B', $Build, '-G', 'Ninja',
             "-DCMAKE_MAKE_PROGRAM=$Ninja",
             '-DCMAKE_BUILD_TYPE=Release',
             "-DPython_EXECUTABLE=$Py",
             "-DFETCHCONTENT_BASE_DIR=$Deps")
if ((Test-Path (Join-Path $Deps 'juce-src\CMakeLists.txt')) -and (Test-Path (Join-Path $Deps 'tracktion-src\modules'))) {
    $cfgArgs += '-DFETCHCONTENT_UPDATES_DISCONNECTED=ON'
    Ok "Usando JUCE/Tracktion ya descargados en .deps"
} else { Warn "Primera vez: se descargaran JUCE (~commit 19edd53) y Tracktion Engine v3.2.0 (~600 MB)" }
Invoke-Checked $CMake $cfgArgs "Configuracion de CMake"

# ---------------------------------------------------------------------------
Step "7/9 Compilar motor C++ y extension afo_audio.pyd (la primera vez tarda 10-30 min)"
$sw = [Diagnostics.Stopwatch]::StartNew()
Invoke-Checked $CMake @('--build', $Build, '--config', 'Release') "Compilacion"
Ok ("Compilado en {0:N1} min" -f $sw.Elapsed.TotalMinutes)
$pyd = Get-ChildItem (Join-Path $Root 'app\allforone\_native') -Filter 'afo_audio*.pyd' | Select-Object -First 1
if (-not $pyd) { Fail "No se genero afo_audio*.pyd" }
Ok "$($pyd.FullName) ($([math]::Round($pyd.Length/1MB,1)) MB)"

# ---------------------------------------------------------------------------
Step "8/9 Verificacion"
$env:PYTHONPATH = Join-Path $Root 'app'
$code = Run-Native $Py @('-c', "from allforone._native import afo_audio as a; e=a.Engine('AllForOneCheck'); print('    afo_audio', a.version(), '| JUCE', a.juce_version()); print('    dispositivo:', e.device_info())")
if ($code -ne 0) { Fail "Python no puede importar/usar afo_audio" }
Ok "Python importa afo_audio y crea el motor"

if (-not $SkipTests) {
    $ctest = Join-Path $VenvScripts 'ctest.exe'
    Push-Location $Build
    $ct = Run-Native $ctest @('--output-on-failure')
    Pop-Location
    if ($ct -ne 0) { Fail "Pruebas nativas fallidas" } else { Ok "Pruebas nativas" }

    Invoke-Checked $Py @('-m','pytest','-q',(Join-Path $Root 'tests')) "Pruebas Python"
    Ok "Pruebas Python"

    $report = Join-Path $LogDir "selftest_$Stamp.json"
    $code = Run-Native $Py @('-m','allforone','--selftest','--report',$report,'--screenshot',(Join-Path $LogDir "selftest_$Stamp.png"))
    if ($code -ne 0) { Fail "Autoprueba integrada fallida (ver $report)" }
    Ok "Autoprueba integrada: $report"
} else { Warn "Pruebas omitidas (-SkipTests)" }

# ---------------------------------------------------------------------------
Step "9/9 Listo"
Ok "Para crear AllForOne.exe ejecuta package_windows.bat"
Stop-Transcript | Out-Null
if ($Run) {
    Write-Host "Iniciando AllForOne..." -ForegroundColor Cyan
    & $Py -m allforone
    exit $LASTEXITCODE
}
exit 0
