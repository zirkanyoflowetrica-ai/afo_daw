<#
  AllForOne - empaquetado por partes (el mismo resultado que package_windows.bat, sin horas seguidas
  con el procesador al maximo).

  Partes: compilar el motor -> pruebas C++ -> cada archivo de tests\ por separado -> autoprueba ->
  Nuitka e instalacion en EXE (package.ps1 -SkipBuild). Entre parte y parte espera -Pausa segundos
  para que el equipo se enfrie, y compilador y Nuitka usan -Jobs nucleos (por defecto la mitad).

  Se puede retomar: cada parte terminada se apunta en .cache\paquete_partes.json. Si el equipo se
  apaga o una parte falla, vuelve a ejecutar el script y sigue desde la parte que faltaba (si el
  codigo cambio desde entonces, es decir otro commit o cambios sin guardar, empieza de cero).

  Uso:
    powershell -ExecutionPolicy Bypass -File tools\package_partes.ps1
    powershell -ExecutionPolicy Bypass -File tools\package_partes.ps1 -Jobs 4 -Pausa 60
    powershell -ExecutionPolicy Bypass -File tools\package_partes.ps1 -Reiniciar     # desde cero
#>
param(
    [int]$Jobs = [Math]::Max(1, [int]([Environment]::ProcessorCount / 2)),
    [int]$Pausa = 30,
    [switch]$Reiniciar
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
Start-Transcript -Path (Join-Path $LogDir "package_partes_$Stamp.log") -Append | Out-Null
$Cache = Join-Path $Root '.cache'
New-Item -ItemType Directory -Force -Path (Join-Path $Cache 'tmp') | Out-Null
$env:TEMP = Join-Path $Cache 'tmp'; $env:TMP = $env:TEMP
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$StateFile = Join-Path $Cache 'paquete_partes.json'

function Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Yellow }
function Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Fail($m) {
    Write-Host "    [ERROR] $m" -ForegroundColor Red
    Write-Host "    Corrige el fallo y vuelve a ejecutar el script: sigue desde esta parte." -ForegroundColor Red
    Stop-Transcript | Out-Null; exit 1
}
function Run-Native($exe, [string[]]$argList) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $exe @argList 2>&1 | ForEach-Object { "$_" } | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return $code
}

# Huella del codigo: commit + cambios sin guardar. Si cambia, lo ya probado no vale.
$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
$head = (& git rev-parse HEAD 2>$null | Out-String).Trim()
$dirty = (& git status --porcelain --untracked-files=no 2>$null | Out-String).Trim()
$ErrorActionPreference = $old
$sha = [Security.Cryptography.SHA1]::Create()
$print = $head + '|' + [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($dirty))).Replace('-', '')

$done = @()
if (-not $Reiniciar -and (Test-Path $StateFile)) {
    try {
        $st = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($st.huella -eq $print) { $done = @($st.hechas) }
        else { Write-Host "    El codigo cambio desde el ultimo intento: se empieza de cero." }
    } catch { Write-Host "    No se pudo leer $StateFile; se empieza de cero." }
}
function Save-State {
    [pscustomobject]@{ huella = $print; hechas = $script:done; fecha = (Get-Date).ToString('s') } |
        ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
}

$tests = Get-ChildItem (Join-Path $Root 'tests') -Filter 'test_*.py' | Sort-Object Name | ForEach-Object { $_.Name }
$parts = @('compilar', 'pruebas-c++') + ($tests | ForEach-Object { "pytest:$_" }) + @('autoprueba', 'empaquetar')
$left = @($parts | Where-Object { $done -notcontains $_ })
Step ("Empaquetado por partes: {0} de {1} hechas; {2} nucleos; {3} s de pausa entre partes" -f ($parts.Count - $left.Count), $parts.Count, $Jobs, $Pausa)

$first = $true
foreach ($part in $left) {
    if (-not $first -and $Pausa -gt 0) { Write-Host "    (pausa de $Pausa s para enfriar)"; Start-Sleep -Seconds $Pausa }
    $first = $false
    $n = $parts.IndexOf($part) + 1
    Step "[$n/$($parts.Count)] $part"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    switch -Wildcard ($part) {
        'compilar' {
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'build.ps1') -NoInstall -SkipTests -Yes -Jobs $Jobs
            if ($LASTEXITCODE -ne 0) { Fail "build.ps1 fallo; revisa logs\" }
        }
        'pruebas-c++' {
            Push-Location (Join-Path $Root 'build\win-release')
            $code = Run-Native (Join-Path $Root '.venv\Scripts\ctest.exe') @('--output-on-failure')
            Pop-Location
            if ($code -ne 0) { Fail "Pruebas nativas fallidas" }
        }
        'pytest:*' {
            $file = Join-Path $Root ('tests\' + $part.Substring(7))
            $env:PYTHONPATH = Join-Path $Root 'app'
            $code = Run-Native $Py @('-m', 'pytest', '-q', $file, '-p', 'no:cacheprovider')
            if ($code -eq 5) { Write-Host "    (sin pruebas que ejecutar en este archivo)" }
            elseif ($code -ne 0) { Fail "Pruebas fallidas en $($part.Substring(7))" }
        }
        'autoprueba' {
            $env:PYTHONPATH = Join-Path $Root 'app'
            $report = Join-Path $LogDir "selftest_$Stamp.json"
            $code = Run-Native $Py @('-m', 'allforone', '--selftest', '--report', $report, '--screenshot', (Join-Path $LogDir "selftest_$Stamp.png"))
            if ($code -ne 0) { Fail "Autoprueba integrada fallida (ver $report)" }
        }
        'empaquetar' {
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'package.ps1') -SkipBuild -Jobs $Jobs
            if ($LASTEXITCODE -ne 0) { Fail "package.ps1 fallo; revisa logs\" }
        }
    }
    Ok ("{0} ({1:N1} min)" -f $part, $sw.Elapsed.TotalMinutes)
    $done += $part
    Save-State
}
Remove-Item $StateFile -ErrorAction SilentlyContinue
Step "Listo: EXE\AllForOne.exe actualizado"
Stop-Transcript | Out-Null
