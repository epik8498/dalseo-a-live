$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "SUPERSONIC.lnk"
if (Test-Path $link) {
    Remove-Item $link -Force
    Write-Host "SUPERSONIC startup removed." -ForegroundColor Green
} else {
    Write-Host "SUPERSONIC startup shortcut not found."
}
