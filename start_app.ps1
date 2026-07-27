$proc = Start-Process -FilePath "D:\AI-Projects\github-speedup\build\bin\github-speedup.exe" -WindowStyle Hidden -PassThru -RedirectStandardError "D:\AI-Projects\github-speedup\build\bin\stderr.log"
Write-Host "Started PID: $($proc.Id)"
