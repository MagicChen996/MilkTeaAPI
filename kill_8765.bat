@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F
    echo Killed process PID %%a on port 8765
    goto :done
)
echo No process found on port 8765
:done
pause
