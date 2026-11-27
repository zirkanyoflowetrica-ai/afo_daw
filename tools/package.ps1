<#
  AllForOne - genera el programa listo para usar en E:\AFO\EXE (carpeta portatil con AllForOne.exe).
  Uso normal: doble clic en package_windows.bat

  Resultado:
    EXE\AllForOne.exe            programa (+ DLL de Qt Quick, interfaz QML, mezclador, afo_audio.pyd)
    EXE\datos\                   tus datos (mezclas, ajustes, registros); se conservan al actualizar
    EXE\motores\acestep\         motor de IA local (ACE-Step con Vulkan, tools\build_acestep.bat)
    EXE\motores\llama\           motor de composicion MIDI (llama-server con Vulkan, tools\build_llama.bat)
    EXE\motores\demucs\          separador de stems (demucs.cpp, tools\build_demucs.ps1)
    EXE\modelos\acestep\ y midi\ modelos de IA que descargas desde el programa; se conservan al actualizar
    AllForOne.lnk                acceso directo en la raiz del proyecto
    release\AllForOne-<version>-win64.zip   para publicar (sin tus datos)
    release\AllForOne-<version>-Setup.exe   instalador (por usuario; los modelos se descargan desde la app)
  Todo queda dentro de la carpeta del proyecto: caches y temporales en .cache\.
  Verificacion: ejecuta AllForOne.exe --selftest desde una copia en .cache\tmp con un entorno
  limpio (sin PYTHONPATH ni .venv en el PATH) antes de instalarlo en EXE.
#>
# -SkipBuild: no compila ni prueba (ya lo hizo tools\package_partes.ps1). -Jobs: nucleos (0 = todos).
param([switch]$SkipBuild, [int]$Jobs = 0)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Start-Transcript -Path (Join-Path $LogDir "package_$Stamp.log") -Append | Out-Null
# Caches y temporales dentro del proyecto (nada en %TEMP% ni %LOCALAPPDATA%)
$Cache = Join-Path $Root '.cache'
foreach ($d in @('tmp', 'nuitka', 'pip', 'nuitka-out')) { New-Item -ItemType Directory -Force -Path (Join-Path $Cache $d) | Out-Null }
$env:TEMP = Join-Path $Cache 'tmp'; $env:TMP = $env:TEMP
$env:NUITKA_CACHE_DIR = Join-Path $Cache 'nuitka'
$env:PIP_CACHE_DIR = Join-Path $Cache 'pip'

function Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Yellow }
function Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Fail($m) { Write-Host "    [ERROR] $m" -ForegroundColor Red; Stop-Transcript | Out-Null; exit 1 }
function Run-Native($exe, [string[]]$argList) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $exe @argList 2>&1 | ForEach-Object { "$_" } | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return $code
}

# Cierra instancias de AllForOne lanzadas desde esta carpeta (bloquean afo_audio.pyd / dist)
function Stop-AllForOne {
    # Solo la aplicacion (AllForOne.exe o «python -m allforone»), nunca otros Python del proyecto:
    # el 23-11-2026 esto cerro una bateria de pytest a medias.
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='AllForOne.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and (($_.Name -eq 'AllForOne.exe' -and $_.ExecutablePath -like "$Root\*") -or
                       ($_.CommandLine -like '*-m allforone*' -and $_.CommandLine -notlike '*pytest*')) }
    foreach ($p in $procs) {
        Write-Host "    Cerrando AllForOne en ejecucion: PID $($p.ProcessId) $($p.ExecutablePath)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($procs) { Start-Sleep -Seconds 2 }
}
Stop-AllForOne
$Py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not $SkipBuild) {
    Step "Compilando y probando (build.ps1)"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') -NoInstall -Jobs $Jobs
    if ($LASTEXITCODE -ne 0) { Fail "build.ps1 fallo; revisa logs\" }
}
if (-not (Test-Path $Py)) { Fail "Falta .venv: ejecuta build_and_run.bat primero" }
$pyd = Get-ChildItem (Join-Path $Root 'app\allforone\_native') -Filter 'afo_audio*.pyd' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pyd) { Fail "Falta afo_audio.pyd: ejecuta build_and_run.bat primero" }

# Nuitka necesita el compilador: importar vcvars64
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$VS = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath).Trim()
foreach ($line in (cmd /c "`"$VS\VC\Auxiliary\Build\vcvars64.bat`" >nul 2>&1 && set")) { if ($line -match '^([^=]+)=(.*)$') { Set-Item "env:$($matches[1])" $matches[2] } }

$Version = (& $Py -c "import sys; sys.path.insert(0, r'$Root\app'); import allforone; print(allforone.__version__)").Trim()
$Dist = Join-Path $Cache 'nuitka-out'
$Out = Join-Path $Dist 'AllForOne'
$Exe = Join-Path $Root 'EXE'

Step "Nuitka standalone (AllForOne $Version)"
foreach ($d in @($Out, (Join-Path $Dist 'AllForOne.dist'))) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
# Los modulos del Mezclador V4.2 se importan por su nombre (mixer_engine, scale_tuner...):
# se compilan como modulos de primer nivel desde su carpeta.
$MixerDir = Join-Path $Root 'app\allforone\mixer_v42'
$env:PYTHONPATH = (Join-Path $Root 'app') + ';' + $MixerDir
$mixerModules = Get-ChildItem $MixerDir -Filter '*.py' | ForEach-Object { "--include-module=$($_.BaseName)" }
$nargs = @('-m', 'nuitka',
    '--mode=standalone',
    '--assume-yes-for-downloads',
    '--enable-plugin=pyside6',
    '--include-package=allforone',
    "--include-data-dir=$Root\app\allforone\qml=allforone/qml",
    '--include-qt-plugins=qml',
    # librosa y numba van ademas como codigo Python en pylibs\ (ver mas abajo); Nuitka los sigue para
    # meter sus dependencias. Con numba de verdad (su JIT) en vez del modo sin JIT de Nuitka.
    '--module-parameter=numba-disable-jit=no',
    # librosa no se compila (el codigo compilado se salta pylibs); se meten a mano los modulos que importa
    '--nofollow-import-to=librosa',
    '--include-module=numba', '--include-package=llvmlite',   # numba (y lo que importa) ya no llega por librosa
    '--include-module=lazy_loader', '--include-module=decorator', '--include-module=joblib', '--include-module=pooch',
    '--include-module=soxr', '--include-module=msgpack', '--include-module=typing_extensions', '--include-module=soundfile',
    '--include-module=scipy.fft', '--include-module=scipy.interpolate', '--include-module=scipy.linalg',
    '--include-module=scipy.ndimage', '--include-module=scipy.optimize', '--include-module=scipy.signal',
    '--include-module=scipy.sparse', '--include-module=scipy.spatial', '--include-module=scipy.stats',
    '--include-module=sklearn.cluster', '--include-module=sklearn.decomposition',
    '--include-module=sklearn.feature_extraction', '--include-module=sklearn.neighbors',
    '--include-module=fractions', '--include-module=colorsys', '--include-module=html', '--include-module=glob',
    '--include-module=tomllib', '--include-module=inspect',
    # La interfaz es Qt Quick: nada de Chromium en la distribucion
    '--nofollow-import-to=PySide6.QtWebEngineCore', '--nofollow-import-to=PySide6.QtWebEngineWidgets',
    '--nofollow-import-to=PySide6.QtWebEngineQuick', '--nofollow-import-to=PySide6.QtWebChannel',
    '--nofollow-import-to=gradio', '--nofollow-import-to=torch', '--nofollow-import-to=transformers',
    '--nofollow-import-to=beat_this', '--nofollow-import-to=mdxnet_infer',
    "--windows-icon-from-ico=$Root\app\allforone\qml\assets\icon.ico",
    '--windows-console-mode=attach',
    '--output-filename=AllForOne.exe',
    '--company-name=AllForOne',
    '--product-name=AllForOne',
    "--file-version=$Version.0",
    "--product-version=$Version.0",
    '--file-description=AllForOne-DAW',
    "--output-dir=$Dist",
    "--report=$LogDir\nuitka_report_$Stamp.xml",
    "$Root\app\AllForOne.py") + $mixerModules
if ($Jobs -gt 0) { $nargs = @($nargs[0], $nargs[1], "--jobs=$Jobs") + $nargs[2..($nargs.Count - 1)] }
$sw = [Diagnostics.Stopwatch]::StartNew()
if ((Run-Native $Py $nargs) -ne 0) { Fail "Nuitka fallo" }
$built = Join-Path $Dist 'AllForOne.dist'
if (-not (Test-Path (Join-Path $built 'AllForOne.exe'))) { Fail "No se genero AllForOne.exe" }
Move-Item $built $Out
Remove-Item -Recurse -Force (Join-Path $Dist 'AllForOne.build') -ErrorAction SilentlyContinue
Ok ("Empaquetado en {0:N1} min" -f $sw.Elapsed.TotalMinutes)

# Avisos de licencia y documentacion junto al ejecutable
Copy-Item (Join-Path $Root 'THIRD_PARTY_NOTICES.md') $Out
Copy-Item (Join-Path $Root 'LICENSE') $Out -ErrorAction SilentlyContinue
Copy-Item (Join-Path $Root 'README.md') $Out -ErrorAction SilentlyContinue
# librosa y numba como codigo Python (main._source_packages los carga de aqui): numba compila funciones
# desde su bytecode, que el codigo compilado por Nuitka no tiene; sin esto el analisis (tempo, tonalidad,
# acordes, secciones) falla en el EXE. Se dejan compilados a .pyc para no hacerlo en cada arranque.
$PyLibs = Join-Path $Out 'pylibs'
$Site = Join-Path $Root '.venv\Lib\site-packages'
foreach ($pkg in @('librosa', 'numba')) {
    & robocopy (Join-Path $Site $pkg) (Join-Path $PyLibs $pkg) /E /XD __pycache__ tests /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "No se pudo copiar $pkg a pylibs" }
}
if ((Run-Native $Py @('-m', 'compileall', '-q', '-j', '0', $PyLibs)) -ne 0) { Fail "compileall de pylibs fallo" }
# Temas: cada carpeta de templates con un theme.json (copiar la carpeta = compartir el tema)
Copy-Item (Join-Path $Root 'templates') (Join-Path $Out 'templates') -Recurse
# Scripts del usuario (F8): los de ejemplo de scripts\ (menu Scripts; API afo)
Copy-Item (Join-Path $Root 'scripts') (Join-Path $Out 'scripts') -Recurse
# IA local: motor de ACE-Step (acestep.cpp con Vulkan) en motores\acestep. Los modelos no van en el
# paquete: se descargan desde el propio programa a modelos\acestep.
$Ace = Join-Path $Cache 'acestep.cpp\build-vk'
if (-not (Test-Path (Join-Path $Ace 'ace-synth.exe'))) {
    Step "Compilando el motor de IA (tools\build_acestep.bat)"
    if ((Run-Native 'cmd.exe' @('/c', (Join-Path $PSScriptRoot 'build_acestep.bat'))) -ne 0) { Fail "No se pudo compilar acestep.cpp" }
}
$AceOut = Join-Path $Out 'motores\acestep'
New-Item -ItemType Directory -Force -Path $AceOut | Out-Null
foreach ($f in @('ace-lm.exe', 'ace-synth.exe', 'ggml.dll', 'ggml-base.dll', 'ggml-cpu.dll', 'ggml-vulkan.dll')) {
    Copy-Item (Join-Path $Ace $f) $AceOut
}
Copy-Item (Join-Path $Cache 'acestep.cpp\LICENSE') (Join-Path $AceOut 'LICENSE-acestep.cpp.txt')
# Composicion MIDI con IA: llama-server de llama.cpp (Vulkan) en motores\llama; el modelo MIDI-LLM se
# descarga desde el programa a modelos\midi.
$Llama = Join-Path $Cache 'llama.cpp\build-vk\bin'
if (-not (Test-Path (Join-Path $Llama 'llama-server.exe'))) {
    Step "Compilando el motor de composicion MIDI (tools\build_llama.bat)"
    if ((Run-Native 'cmd.exe' @('/c', (Join-Path $PSScriptRoot 'build_llama.bat'))) -ne 0) { Fail "No se pudo compilar llama.cpp" }
}
$LlamaOut = Join-Path $Out 'motores\llama'
New-Item -ItemType Directory -Force -Path $LlamaOut | Out-Null
Get-ChildItem $Llama | Where-Object { $_.Name -eq 'llama-server.exe' -or $_.Extension -eq '.dll' } | Copy-Item -Destination $LlamaOut
Copy-Item (Join-Path $Cache 'llama.cpp\LICENSE') (Join-Path $LlamaOut 'LICENSE-llama.cpp.txt')
# Separador de stems: demucs.cpp (Demucs v4, CPU con OpenMP) en motores\demucs; el modelo ggml se
# descarga desde el programa a modelos\demucs.
$Dm = Join-Path $Cache 'demucs.cpp\build-msvc'
if (-not (Test-Path (Join-Path $Dm 'demucs_mt.cpp.main.exe'))) {
    Step "Compilando el separador de stems (tools\build_demucs.ps1)"
    if ((Run-Native 'powershell.exe' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'build_demucs.ps1'), $Root)) -ne 0) { Fail "No se pudo compilar demucs.cpp" }
}
$DmOut = Join-Path $Out 'motores\demucs'
New-Item -ItemType Directory -Force -Path $DmOut | Out-Null
Copy-Item (Join-Path $Dm 'demucs_mt.cpp.main.exe') (Join-Path $DmOut 'afo-demucs.exe')
Copy-Item (Join-Path $Dm 'vcomp140.dll') $DmOut
Copy-Item (Join-Path $Cache 'demucs.cpp\LICENSE') (Join-Path $DmOut 'LICENSE-demucs.cpp.txt')

Step "Comprobaciones de la distribucion"
foreach ($rel in @('AllForOne.exe', 'motores\acestep\ace-synth.exe', 'motores\acestep\ggml-vulkan.dll', 'motores\llama\llama-server.exe', 'motores\llama\ggml-vulkan.dll', 'motores\demucs\afo-demucs.exe', 'allforone\qml\Main.qml', 'allforone\qml\modules\FxBody.qml', 'allforone\qml\theme\qmldir', 'allforone\qml\assets\fonts\SpaceGrotesk-Bold.ttf', 'allforone\qml\assets\icon.ico', 'templates\Professional\theme.json')) {
    if (-not (Test-Path (Join-Path $Out $rel))) { Fail "Falta $rel en la distribucion" }
}
if (Get-ChildItem $Out -Recurse -Filter 'QtWebEngineProcess.exe') { Fail "La distribucion lleva Qt WebEngine (Chromium) y ya no lo usa" }
if (-not (Get-ChildItem $Out -Recurse -Filter 'afo_audio*.pyd')) { Fail "Falta afo_audio*.pyd" }
Ok "Ejecutable, interfaz QML, fuentes y afo_audio presentes; sin Chromium"

Step "Autoprueba desde una copia fuera del proyecto, con entorno limpio"
$Portable = Join-Path $Cache "tmp\AllForOne_portable_$Stamp"
Copy-Item $Out $Portable -Recurse
$report = Join-Path $LogDir "selftest_dist_$Stamp.json"
# Entorno limpio para el proceso hijo: sin PYTHONPATH/PYTHONHOME y PATH solo de Windows
$env:PYTHONPATH = ''; $env:PYTHONHOME = ''
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
$env:AFO_DATA_DIR = ''
$p = Start-Process -FilePath (Join-Path $Portable 'AllForOne.exe') `
        -ArgumentList @('--selftest', '--report', "`"$report`"", '--screenshot', "`"$LogDir\selftest_dist_$Stamp.png`"") `
        -WorkingDirectory $Portable -Wait -PassThru -NoNewWindow
if ($p.ExitCode -ne 0) { Fail "La autoprueba del ejecutable empaquetado fallo (ver $report)" }
Ok "AllForOne.exe paso la autoprueba desde $Portable"
Remove-Item -Recurse -Force $Portable -ErrorAction SilentlyContinue

Step "ZIP para publicar (sin datos del usuario)"
$Release = Join-Path $Root 'release'
New-Item -ItemType Directory -Force -Path $Release | Out-Null
$zip = Join-Path $Release "AllForOne-$Version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $Out -DestinationPath $zip
Ok "$zip"

Step "Instalador (Inno Setup): release\AllForOne-$Version-Setup.exe"
# Por usuario y sin administrador; los modelos de IA se descargan despues desde la app (installer\AllForOne.iss)
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($Iscc) {
    $code = Run-Native $Iscc @('/Q', "/DAppVersion=$Version", "/DSourceDir=$Out", "/DOutputDir=$Release",
                               (Join-Path $Root 'installer\AllForOne.iss'))
    if ($code -ne 0) { Fail "Inno Setup no pudo crear el instalador" }
    Ok (Join-Path $Release "AllForOne-$Version-Setup.exe")
} else {
    Write-Host "    [!]  Sin Inno Setup 6 no se crea el instalador (winget install JRSoftware.InnoSetup)" -ForegroundColor Yellow
}

Step "Instalar en $Exe (se conservan tus datos de EXE\datos)"
Stop-AllForOne
# Un motor de IA de EXE en uso (pruebas, otra copia) bloquearia el borrado a medias: parar antes de tocar nada
$busy = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -like "$Exe\*" }
if ($busy) {
    $list = ($busy | ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }) -join ', '
    Fail "Hay programas de $Exe en uso: $list. Espera a que terminen (por ejemplo, las pruebas) y vuelve a empaquetar; $Exe queda intacto."
}
$keep = Join-Path $Cache "tmp\datos_conservados_$Stamp"
if (Test-Path (Join-Path $Exe 'datos')) { Move-Item (Join-Path $Exe 'datos') $keep }
# Modelos de IA descargados (gigas): se conservan tal cual
$keepM = Join-Path $Cache "tmp\modelos_conservados_$Stamp"
if (Test-Path (Join-Path $Exe 'modelos')) { Move-Item (Join-Path $Exe 'modelos') $keepM }
# Temas que anadiste tu (los de fabrica se actualizan)
$keepT = Join-Path $Cache "tmp\temas_conservados_$Stamp"
if (Test-Path (Join-Path $Exe 'templates')) { Move-Item (Join-Path $Exe 'templates') $keepT }
# Scripts que escribiste tu (los de ejemplo se actualizan)
$keepS = Join-Path $Cache "tmp\scripts_conservados_$Stamp"
if (Test-Path (Join-Path $Exe 'scripts')) { Move-Item (Join-Path $Exe 'scripts') $keepS }
if (Test-Path $Exe) { Remove-Item -Recurse -Force $Exe }
Move-Item $Out $Exe
if (Test-Path $keep) { Move-Item $keep (Join-Path $Exe 'datos') }
if (Test-Path $keepM) { Move-Item $keepM (Join-Path $Exe 'modelos') }
if (Test-Path $keepT) {
    foreach ($t in Get-ChildItem $keepT -Directory) {
        $dest = Join-Path $Exe "templates\$($t.Name)"
        if (-not (Test-Path $dest)) { Move-Item $t.FullName $dest }
    }
    Remove-Item -Recurse -Force $keepT -ErrorAction SilentlyContinue
}
if (Test-Path $keepS) {
    foreach ($f in Get-ChildItem $keepS -File) {
        $dest = Join-Path $Exe "scripts\$($f.Name)"
        if (-not (Test-Path $dest)) { Move-Item $f.FullName $dest }
    }
    Remove-Item -Recurse -Force $keepS -ErrorAction SilentlyContinue
}
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $Root 'AllForOne.lnk'))
$lnk.TargetPath = Join-Path $Exe 'AllForOne.exe'
$lnk.WorkingDirectory = $Exe
$lnk.IconLocation = (Join-Path $Exe 'AllForOne.exe') + ',0'
$lnk.Description = 'AllForOne - DAW modular'
$lnk.Save()
Remove-Item -Recurse -Force (Join-Path $Cache 'tmp\*') -ErrorAction SilentlyContinue
Ok "Programa listo: $Exe\AllForOne.exe  (acceso directo: $Root\AllForOne.lnk)"
Write-Host ""
Write-Host "Listo: $Exe\AllForOne.exe" -ForegroundColor Cyan
Stop-Transcript | Out-Null
exit 0
