Write-Host "=== OpenCode GitHub Speedup - 代理管理测试 ===" -ForegroundColor Cyan

# 需要先启动 github-speedup.exe
# 若未启动，请先运行: Start-Process -FilePath 'build/bin/github-speedup.exe' -WindowStyle Hidden

$base = "http://127.0.0.1:9090"

# 1. 列出代理
Write-Host "`n[1/4] 获取代理列表 (Wails 绑定: GetProxies)" -ForegroundColor Yellow
Write-Host "  测试方式: 通过 /api/status 查看代理总数" -ForegroundColor Gray
try {
    $r = Invoke-WebRequest -Uri "$base/api/status" -UseBasicParsing
    $data = $r.Content | ConvertFrom-Json
    Write-Host "  PASS: 代理总数 $($data.totalProxies), 可用 $($data.availableProxies)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 2. 健康检查（确认服务正常）
Write-Host "`n[2/4] 服务健康检查" -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -Uri "$base/health" -UseBasicParsing
    Write-Host "  PASS: $($r.Content)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 3. 代理下载测试（走代理池自动选择）
Write-Host "`n[3/4] 通过代理下载文件" -ForegroundColor Yellow
try {
    $testUrl = "https://raw.githubusercontent.com/zxc74105/ceshi/main/speedtest.txt"
    $r = Invoke-WebRequest -Uri "$base/$testUrl" -UseBasicParsing -TimeoutSec 30
    $proxyHeader = $r.Headers["X-Proxy"]
    Write-Host "  PASS: HTTP $($r.StatusCode), Size: $($r.RawContentLength)" -ForegroundColor Green
    if ($proxyHeader) { Write-Host "  使用代理: $proxyHeader" -ForegroundColor Gray }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# 4. 导入/导出功能测试（验证 proxies.json 存在）
Write-Host "`n[4/4] 代理配置文件检查" -ForegroundColor Yellow
$files = @("proxies.json", "proxies-active.json")
foreach ($f in $files) {
    $path = "D:\AI-Projects\github-speedup\$f"
    if (Test-Path $path) {
        $size = (Get-Item $path).Length
        Write-Host "  PASS: $f 存在 ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "  WARN: $f 不存在" -ForegroundColor Yellow
    }
}

Write-Host "`n=== 代理管理测试完成 ===" -ForegroundColor Cyan
