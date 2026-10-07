# Remove what tools/install-windows.ps1 installed (user-scoped; the
# repo and its .venv survive — delete the clone yourself if you want).
#   powershell -ExecutionPolicy Bypass -File tools\uninstall-windows.ps1

$ErrorActionPreference = "SilentlyContinue"
$BIN = Join-Path $env:LOCALAPPDATA "Programs\Tracer\bin"

Remove-Item -Force (Join-Path $BIN "tracer.cmd")
if ((Get-ChildItem $BIN | Measure-Object).Count -eq 0) {
    Remove-Item -Recurse -Force $BIN
    $root = Split-Path $BIN           # ...\Programs\Tracer
    if ((Get-ChildItem $root | Measure-Object).Count -eq 0) {
        Remove-Item -Recurse -Force $root
    }
}
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    $kept = ($userPath -split ";") | Where-Object { $_ -and $_ -ne $BIN }
    [Environment]::SetEnvironmentVariable("Path", ($kept -join ";"), "User")
}

Remove-Item -Force (Join-Path $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Tracer Studio.lnk")
Remove-Item -Recurse -Force "HKCU:\Software\Classes\TracerStudio.Document"
Remove-Item -Recurse -Force "HKCU:\Software\Classes\.tracer"

Write-Host "Tracer Studio uninstalled (files and venv untouched)."
