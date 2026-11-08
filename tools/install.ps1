<#
  AllForOne - instala la distribucion para el usuario actual (sin administrador).
  Copia dist\AllForOne a %LOCALAPPDATA%\Programs\AllForOne y crea accesos directos
  en el menu Inicio y en el escritorio. Desinstalar: tools\install.ps1 -Uninstall
#>
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root 'dist\AllForOne'
$Dest = Join-Path $env:LOCALAPPDATA 'Programs\AllForOne'
$StartMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AllForOne.lnk'
$Desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'AllForOne.lnk'
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir ("install_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")) | Out-Null

# Cerrar instancias instaladas en ejecucion
Get-CimInstance Win32_Process -Filter "Name='AllForOne.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$Dest\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

if ($Uninstall) {
    foreach ($p in @($StartMenu, $Desktop, $Dest)) { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
    Write-Host "AllForOne desinstalado (tus datos en $env:LOCALAPPDATA\AllForOne se conservan)."
    Stop-Transcript | Out-Null
    exit 0
}

if (-not (Test-Path (Join-Path $Src 'AllForOne.exe'))) {
    Write-Host "No existe dist\AllForOne\AllForOne.exe: ejecuta antes package_windows.bat" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}
Write-Host "Instalando en $Dest ..."
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
Copy-Item $Src $Dest -Recurse

$shell = New-Object -ComObject WScript.Shell
foreach ($lnk in @($StartMenu, $Desktop)) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $Dest 'AllForOne.exe'
    $s.WorkingDirectory = $Dest
    $s.Description = 'AllForOne - DAW modular'
    $s.Save()
}
foreach ($p in @((Join-Path $Dest 'AllForOne.exe'), $StartMenu, $Desktop)) {
    if (Test-Path $p) { Write-Host "    [OK] $p" } else { Write-Host "    [ERROR] falta $p"; Stop-Transcript | Out-Null; exit 1 }
}
Write-Host "Listo: accesos directos en el menu Inicio y el escritorio." -ForegroundColor Green
Stop-Transcript | Out-Null
exit 0
