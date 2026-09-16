$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "SUPERSONIC 자동실행.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "SUPERSONIC 자동실행 등록을 해제했습니다." -ForegroundColor Green
} else {
    Write-Host "등록된 SUPERSONIC 자동실행 바로가기가 없습니다."
}
