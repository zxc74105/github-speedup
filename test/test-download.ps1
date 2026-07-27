Write-Host "=== OpenCode GitHub Speedup - 下载功能测试 ===" -ForegroundColor Cyan

# 需要先启动 github-speedup.exe
# 测试前请确保服务在运行: Start-Process -FilePath 'build/bin/github-speedup.exe' -WindowStyle Hidden

$base = "http://127.0.0.1:9090"
$testDir = "$env:TEMP\github-speedup-test"

# 1. 通过代理下载小文件
Write-Host "`n[1/4] 直接下载 - 通过 HTTP API 下载小文件" -ForegroundColor Yellow
try {
    $url = "https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt"
    $r = Invoke-WebRequest -Uri "$base/$url" -UseBasicParsing -TimeoutSec 30 -OutFile "$testDir\speedtest.txt"
    $size = (Get-Item "$testDir\speedtest.txt").Length
    Write-Host "  PASS: 已保存到 $testDir\speedtest.txt ($size bytes)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 2. Range 分块下载测试
Write-Host "`n[2/4] Range 分块 - 下载前 500 字节" -ForegroundColor Yellow
try {
    $url = "https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt"
    $r = Invoke-WebRequest -Uri "$base/$url" -UseBasicParsing -TimeoutSec 30 -Headers @{"Range"="bytes=0-499"}
    [io.file]::WriteAllBytes("$testDir\speedtest_part.bin", $r.Content)
    Write-Host "  PASS: HTTP $($r.StatusCode), 收到 $($r.RawContentLength) bytes" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 3. 状态查询（验证下载统计）
Write-Host "`n[3/4] 下载状态查询" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/api/status" -UseBasicParsing
    Write-Host "  PASS: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 4. 健康检查
Write-Host "`n[4/4] 服务健康检查" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/health" -UseBasicParsing
    Write-Host "  PASS: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

Write-Host "`n=== 下载功能测试完成 ===" -ForegroundColor Cyan
Write-Host "测试临时文件: $testDir" -ForegroundColor Gray
