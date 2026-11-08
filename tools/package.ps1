<#
  AllForOne - genera la distribucion standalone para Windows (carpeta con AllForOne.exe).
  Uso normal: doble clic en package_windows.bat  (ejecuta antes build_and_run.bat al menos una vez)

  Resultado:
    dist\AllForOne\AllForOne.exe   (+ DLL, Qt WebEngine, plantilla, fuentes, afo_audio.pyd)
    dist\AllForOne-<version>-win64.zip
  Verificacion: copia la carpeta a %TEMP% y ejecuta AllForOne.exe --selftest con un entorno
  limpio (sin PYTHONPATH, sin .venv en el PATH) para demostrar que no depende de E:\AFO.
#>
param([switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Start-Transcript -Path (Join-Path $LogDir "package_$Stamp.log") -Append | Out-Null

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
    $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='AllForOne.exe' OR Name='QtWebEngineProcess.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -like "$Root\*" -or $_.CommandLine -like '*-m allforone*') }
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
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') -NoInstall
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
$Dist = Join-Path $Root 'dist'
$Out = Join-Path $Dist 'AllForOne'

Step "Nuitka standalone (AllForOne $Version)"
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
$env:PYTHONPATH = Join-Path $Root 'app'
$nargs = @('-m', 'nuitka',
    '--mode=standalone',
    '--assume-yes-for-downloads',
    '--enable-plugin=pyside6',
    '--include-package=allforone',
    "--include-data-dir=$Root\app\allforone\ui=allforone/ui",
    '--windows-console-mode=attach',
    '--output-filename=AllForOne.exe',
    '--company-name=AllForOne',
    '--product-name=AllForOne',
    "--file-version=$Version.0",
    "--product-version=$Version.0",
    '--file-description=AllForOne-DAW',
    "--output-dir=$Dist",
    "--report=$LogDir\nuitka_report_$Stamp.xml",
    "$Root\app\AllForOne.py")
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
Copy-Item (Join-Path $Root 'docs\INFORME_V0.1.md') $Out -ErrorAction SilentlyContinue

Step "Comprobaciones de la distribucion"
foreach ($rel in @('AllForOne.exe', 'allforone\ui\index.html', 'allforone\ui\afo_bridge.js', 'allforone\ui\fonts\space-grotesk-latin-wght-normal.woff2')) {
    if (-not (Test-Path (Join-Path $Out $rel))) { Fail "Falta $rel en la distribucion" }
}
if (-not (Get-ChildItem $Out -Recurse -Filter 'QtWebEngineProcess.exe')) { Fail "Falta QtWebEngineProcess.exe" }
if (-not (Get-ChildItem $Out -Recurse -Filter 'afo_audio*.pyd')) { Fail "Falta afo_audio*.pyd" }
Ok "Ejecutable, plantilla, fuentes, Qt WebEngine y afo_audio presentes"

Step "Autoprueba desde una copia fuera del proyecto, con entorno limpio"
$Portable = Join-Path $env:TEMP "AllForOne_portable_$Stamp"
Copy-Item $Out $Portable -Recurse
$report = Join-Path $LogDir "selftest_dist_$Stamp.json"
# Entorno limpio para el proceso hijo: sin PYTHONPATH/PYTHONHOME y PATH solo de Windows
$env:PYTHONPATH = ''; $env:PYTHONHOME = ''
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
$p = Start-Process -FilePath (Join-Path $Portable 'AllForOne.exe') `
        -ArgumentList @('--selftest', '--report', "`"$report`"", '--screenshot', "`"$LogDir\selftest_dist_$Stamp.png`"") `
        -WorkingDirectory $Portable -Wait -PassThru -NoNewWindow
if ($p.ExitCode -ne 0) { Fail "La autoprueba del ejecutable empaquetado fallo (ver $report)" }
Ok "AllForOne.exe paso la autoprueba desde $Portable"
Remove-Item -Recurse -Force $Portable -ErrorAction SilentlyContinue

Step "ZIP"
$zip = Join-Path $Dist "AllForOne-$Version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $Out -DestinationPath $zip
Ok "$zip"
Write-Host ""
Write-Host "Listo: $Out\AllForOne.exe" -ForegroundColor Cyan
Stop-Transcript | Out-Null
exit 0
