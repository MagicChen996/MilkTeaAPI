@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo Starting MilkTea API...
echo Ensure browser is started with --remote-debugging-port=9222 and AI chat page is open.
python main.py
pause
