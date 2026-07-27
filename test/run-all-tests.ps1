param(
    [switch]$SkipStart,
    [switch]$SkipStop
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " OpenCode GitHub Speedup - 全量测试套件" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$root = "D:\AI-Projects\github-speedup"
$exe = "$root\build\bin\github-speedup.exe"

# 启动应用
if (-not $SkipStart) {
    Write-Host "`n[启动] 启动 github-speedup.exe..." -ForegroundColor Magenta
    $proc = Get-Process -Name "github-speedup" -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "  应用已在运行中 (PID: $($proc.Id))" -ForegroundColor Yellow
    } else {
        Start-Process -FilePath $exe -WindowStyle Hidden
        Start-Sleep -Seconds 8
        Write-Host "  应用已启动" -ForegroundColor Green
    }
}

# 健康检查
Write-Host "`n[检查] 等待服务就绪..." -ForegroundColor Magenta
$ready = $false
for ($i = 0; $i -lt 5; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:9090/health" -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Write-Host "  服务未就绪，退出测试" -ForegroundColor Red
    exit 1
}
Write-Host "  服务就绪" -ForegroundColor Green

# 运行各测试
$tests = @(
    @{Name="API 测试"; Script="$root\test\test-api.ps1"},
    @{Name="代理管理测试"; Script="$root\test\test-proxy.ps1"},
    @{Name="下载功能测试"; Script="$root\test\test-download.ps1"}
)

$results = @()
foreach ($t in $tests) {
    Write-Host "`n----------------------------------------" -ForegroundColor Cyan
    Write-Host " 运行: $($t.Name)" -ForegroundColor Cyan
    Write-Host "----------------------------------------" -ForegroundColor Cyan
    & $t.Script
    if ($LASTEXITCODE -eq 0) {
        $results += @{Name=$t.Name; Status="PASS"}
    } else {
        $results += @{Name=$t.Name; Status="FAIL"}
    }
}

# 清理
if (-not $SkipStop) {
    Write-Host "`n[清理] 停止应用..." -ForegroundColor Magenta
    Stop-Process -Name "github-speedup" -ErrorAction SilentlyContinue
    Write-Host "  已停止" -ForegroundColor Green
}

# 汇总
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " 测试结果汇总" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
$pass = 0; $fail = 0
foreach ($r in $results) {
    $color = if ($r.Status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "  [$($r.Status)] $($r.Name)" -ForegroundColor $color
    if ($r.Status -eq "PASS") { $pass++ } else { $fail++ }
}
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host " 通过: $pass / 失败: $fail / 总计: $($results.Count)" -ForegroundColor Cyan
if ($fail -eq 0) { Write-Host " 全部通过!" -ForegroundColor Green } else { Write-Host " 存在失败项" -ForegroundColor Red }
