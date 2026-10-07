# Install Tracer Studio for the current user (Windows 10/11, no admin).
# Idempotent — re-run any time, in particular after moving the repo.
#
#   * venv + editable package  -> the tracer launcher exists
#   * tracer.cmd on your PATH  -> one easy command, anywhere
#   * Start Menu entry         -> "Tracer Studio" in the apps list
#   * *.tracer file association-> double-click a document to open it
#
# Run from the cloned repo:
#   powershell -ExecutionPolicy Bypass -File tools\install-windows.ps1
# Uninstall: tools\uninstall-windows.ps1 (repo and venv survive both).

$ErrorActionPreference = "Stop"
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BIN  = Join-Path $env:LOCALAPPDATA "Programs\Tracer\bin"

# 1. python environment (py launcher first; plain python as fallback)
$PY = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 --version *> $null
    if ($LASTEXITCODE -eq 0) { $PY = @("py", "-3") }
}
if (-not $PY -and (Get-Command python -ErrorAction SilentlyContinue)) {
    python --version *> $null
    if ($LASTEXITCODE -eq 0) { $PY = @("python") }
}
if (-not $PY) {
    Write-Host "No Python found. Install it with:" -ForegroundColor Red
    Write-Host "    winget install -e --id Python.Python.3.12"
    Write-Host "then re-run this script."
    exit 1
}
$VENV = Join-Path $ROOT ".venv"
if (-not (Test-Path (Join-Path $VENV "Scripts\python.exe"))) {
    if ($PY.Count -eq 1) { & $PY[0] -m venv $VENV }
    else                 { & $PY[0] $PY[1] -m venv $VENV }
}
$VENV_PY = Join-Path $VENV "Scripts\python.exe"
& $VENV_PY -m pip install --quiet --upgrade pip
& $VENV_PY -m pip install --quiet -e $ROOT
$VENV_PYW = Join-Path $VENV "Scripts\pythonw.exe"

# 2. the one easy command (pythonw: no console window flashes)
New-Item -ItemType Directory -Force -Path $BIN | Out-Null
# written with explicit \r\n so git's line-ending policy can't break it
$cmd = "@echo off`r`n`"$VENV_PYW`" -m tracer %*`r`n"
[IO.File]::WriteAllText((Join-Path $BIN "tracer.cmd"), $cmd)
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $BIN) {
    [Environment]::SetEnvironmentVariable(
        "Path", "$BIN;$userPath", "User")
    Write-Host "Added $BIN to your PATH (new terminals pick it up)."
}

# 3. Start Menu entry — same pythonw road, no console
$lnk = Join-Path $env:APPDATA `
    "Microsoft\Windows\Start Menu\Programs\Tracer Studio.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $VENV_PYW
$s.Arguments  = "-m tracer"
$s.WorkingDirectory = $ROOT
$s.Description = "Tracer Studio - parametric CAD"
$s.Save()

# 4. .tracer double-click (HKCU — user-scoped, no admin)
$prog = "HKCU:\Software\Classes\TracerStudio.Document\shell\open\command"
New-Item -Force -Path $prog | Out-Null
Set-ItemProperty -Path $prog -Name "(Default)" `
    -Value "`"$VENV_PYW`" -m tracer `"%1`""
Set-ItemProperty -Path "HKCU:\Software\Classes\TracerStudio.Document" `
    -Name "(Default)" -Value "Tracer Studio Document"
New-Item -Force -Path "HKCU:\Software\Classes\.tracer" | Out-Null
Set-ItemProperty -Path "HKCU:\Software\Classes\.tracer" -Name "(Default)" `
    -Value "TracerStudio.Document"
Set-ItemProperty -Path "HKCU:\Software\Classes\.tracer" `
    -Name "Content Type" -Value "application/x-tracer"

Write-Host ""
Write-Host "Tracer Studio installed."
Write-Host "  command      : tracer            (tracer file.tracer opens it)"
Write-Host "  start menu   : 'Tracer Studio'"
Write-Host "  double-click : .tracer files open Tracer"
