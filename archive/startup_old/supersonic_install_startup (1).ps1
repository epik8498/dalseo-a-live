$ErrorActionPreference = "Stop"
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $base "supersonic_start.bat"

if (-not (Test-Path $bat)) {
    Write-Host "supersonic_start.bat not found." -ForegroundColor Red
    exit 1
}

$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "SUPERSONIC.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($link)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $base
$sc.WindowStyle = 7
$sc.Description = "SUPERSONIC startup"
$sc.Save()

Write-Host ""
Write-Host "SUPERSONIC startup registration complete." -ForegroundColor Green
Write-Host $link
