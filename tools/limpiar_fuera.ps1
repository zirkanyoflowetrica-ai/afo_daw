<#
  AllForOne - elimina lo que versiones anteriores de los scripts crearon FUERA de E:\AFO.
  Solo borra rutas conocidas de AllForOne y solo si se crearon a partir del 2026-11-07 21:50
  (inicio de esta etapa del proyecto); lo anterior se respeta y se informa.
  Registro: logs\limpieza_*.log
#>
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir ("limpieza_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")) | Out-Null
$Since = Get-Date '2026-11-07 21:50'
$Desktop = [Environment]::GetFolderPath('Desktop')
$targets = @(
    "$env:LOCALAPPDATA\Programs\AllForOne",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\AllForOne.lnk",
    "$Desktop\AllForOne.lnk",
    "$env:LOCALAPPDATA\AllForOne",
    "$env:APPDATA\AllForOne",
    "$env:APPDATA\AllForOneCheck",
    "$env:APPDATA\AllForOneTests",
    "$env:LOCALAPPDATA\Nuitka",
    "$env:TEMP\AllForOne",
    "$env:TEMP\AllForOneCheck",
    "$env:TEMP\AllForOneTests"
)
$targets += @(Get-ChildItem $env:TEMP -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like 'AllForOne_portable_*' -or $_.Name -like 'afo_*' -or $_.Name -like 'pytest-of-*' } | ForEach-Object { $_.FullName })
foreach ($t in $targets) {
    if (-not (Test-Path -LiteralPath $t)) { continue }
    $item = Get-Item -LiteralPath $t -Force
    if ($item.CreationTime -lt $Since) {
        Write-Host "  [SE CONSERVA] $t (creado $($item.CreationTime), anterior a AllForOne 0.1)"
        continue
    }
    Remove-Item -LiteralPath $t -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $t) { Write-Host "  [NO SE PUDO] $t" } else { Write-Host "  [ELIMINADO] $t" }
}
Write-Host "Limpieza terminada."
Stop-Transcript | Out-Null
exit 0
