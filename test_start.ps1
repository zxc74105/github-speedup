$proc = Start-Process -FilePath "D:\AI-Projects\github-speedup\build\bin\github-speedup.exe" -WindowStyle Hidden -PassThru -RedirectStandardOutput "D:\AI-Projects\github-speedup\build\bin\stdout.log" -RedirectStandardError "D:\AI-Projects\github-speedup\build\bin\stderr2.log"
Write-Host "Started PID: $($proc.Id)"
Start-Sleep -Seconds 3
Write-Host "Process exists: $($proc.HasExited)"
Get-Process -Id $proc.Id -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Responding
