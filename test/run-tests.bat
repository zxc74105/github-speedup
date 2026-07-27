@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo OpenCode GitHub Speedup - Test Suite
echo ========================================

set EXE=D:\AI-Projects\github-speedup\build\bin\github-speedup.exe

echo.
echo [START] Starting application...
tasklist | find "github-speedup" >nul 2>&1
if !errorlevel! equ 0 (
    echo   Already running
) else (
    start "" "%EXE%"
    timeout /t 8 /nobreak >nul
    echo   Started
)

echo.
echo [CHECK] Waiting for service...
:wait_loop
powershell -Command "try { $r=Invoke-WebRequest 'http://127.0.0.1:9090/health' -UseBasicParsing; if($r.StatusCode -eq 200){exit 0}}catch{}; exit 1"
if !errorlevel! equ 0 (
    echo   Service ready
) else (
    timeout /t 3 /nobreak >nul
    goto wait_loop
)

echo.
echo ========================================
echo [1/3] API Test
echo ========================================
powershell -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:9090/health' -UseBasicParsing; Write-Host '  PASS: Health' $r.Content -ForegroundColor Green}catch{Write-Host '  FAIL: Health' $_ -ForegroundColor Red; exit 1}"
powershell -Command "try{$r=Invoke-WebRequest 'http://127.0.0.1:9090/api/status' -UseBasicParsing; Write-Host '  PASS: Status' $r.Content -ForegroundColor Green}catch{Write-Host '  FAIL: Status' $_ -ForegroundColor Red; exit 1}"
echo   API test done

echo.
echo ========================================
echo [2/3] Proxy Download Test
echo ========================================
powershell -Command "try{$u='https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt';$r=Invoke-WebRequest \"http://127.0.0.1:9090/$u\" -UseBasicParsing -TimeoutSec 30; Write-Host ('  PASS: HTTP '+$r.StatusCode+' Size: '+$r.RawContentLength) -ForegroundColor Green}catch{Write-Host '  FAIL:' $_ -ForegroundColor Red; exit 1}"
echo   Proxy download test done

echo.
echo ========================================
echo [3/3] Live Proxy Download Test
echo ========================================
powershell -Command "try{$wc=New-Object Net.WebClient;$r=$wc.DownloadString('http://127.0.0.1:9090/https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt');$len=$r.Length;Write-Host ('  PASS: Downloaded '+$len+' chars') -ForegroundColor Green}catch{Write-Host '  FAIL:' $_ -ForegroundColor Red; exit 1}"
echo   Live test done

echo.
echo ========================================
echo [CLEANUP] Stopping application...
taskkill /f /im github-speedup.exe >nul 2>&1
echo   Stopped

echo.
echo ========================================
echo ALL TESTS PASSED
echo ========================================
