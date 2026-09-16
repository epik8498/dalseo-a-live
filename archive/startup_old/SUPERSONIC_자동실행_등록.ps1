$ErrorActionPreference = "Stop"

$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $base "SUPERSONIC_자동실행.bat"
if (-not (Test-Path $bat)) {
    Write-Host "[오류] SUPERSONIC_자동실행.bat 파일이 같은 폴더에 없습니다." -ForegroundColor Red
    exit 1
}

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "SUPERSONIC 자동실행.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcutPath)
$sc.TargetPath = $bat
$sc.WorkingDirectory = $base
$sc.WindowStyle = 7
$sc.Description = "SUPERSONIC API + Collector 자동실행"
$sc.Save()

Write-Host ""
Write-Host "SUPERSONIC 자동실행 등록 완료" -ForegroundColor Green
Write-Host "등록 위치: $shortcutPath"
Write-Host "다음 Windows 로그인부터 API와 Collector가 자동 실행됩니다."
Write-Host ""
Write-Host "주의: Collector Chrome은 자동으로 열리며, 배민 로그인 세션이 만료된 경우 로그인할 때까지 대기합니다."
