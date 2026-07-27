Write-Host "=== OpenCode GitHub Speedup - API 测试 ===" -ForegroundColor Cyan

# 1. 健康检查
Write-Host "`n[1/4] 健康检查 GET /health" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:9090/health" -UseBasicParsing
    if ($r.Content -match '"status":"ok"') {
        Write-Host "  PASS: $($r.Content)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: $($r.Content)" -ForegroundColor Red
    }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 2. 状态查询
Write-Host "`n[2/4] 服务状态 GET /api/status" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:9090/api/status" -UseBasicParsing
    Write-Host "  PASS: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 3. 代理下载（小文件）
Write-Host "`n[3/4] 代理下载 speedtest.txt" -ForegroundColor Yellow
try {
    $url = "https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt"
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:9090/$url" -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -eq 200 -and $r.RawContentLength -gt 0) {
        Write-Host "  PASS: HTTP $($r.StatusCode), Size: $($r.RawContentLength) bytes" -ForegroundColor Green
        Write-Host "  Body: $($r.Content)" -ForegroundColor Gray
    } else {
        Write-Host "  FAIL: HTTP $($r.StatusCode), Size: $($r.RawContentLength)" -ForegroundColor Red
    }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 4. 大文件 Range 下载（仅测试响应头）
Write-Host "`n[4/4] Range 请求测试 GET with Range header" -ForegroundColor Yellow
try {
    $url = "https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt"
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:9090/$url" -UseBasicParsing -TimeoutSec 30 -Headers @{"Range"="bytes=0-99"}
    if ($r.StatusCode -eq 206 -or $r.StatusCode -eq 200) {
        Write-Host "  PASS: HTTP $($r.StatusCode), Size: $($r.RawContentLength) bytes" -ForegroundColor Green
    } else {
        Write-Host "  FAIL: HTTP $($r.StatusCode)" -ForegroundColor Red
    }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

Write-Host "`n=== API 测试完成 ===" -ForegroundColor Cyan
