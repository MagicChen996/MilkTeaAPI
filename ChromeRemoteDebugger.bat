@echo off
netsh interface portproxy delete v4tov4 listenport=9222 listenaddress=0.0.0.0
start /b cmd /c call "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222  --user-data-dir=dev-mode-removeme --disk-cache-dir=null --overscroll-history-navigation=0 --disable-web-security -–allow-file-access-from-files "%~dp0/src/index.html"
timeout 5
netsh interface portproxy add v4tov4 listenport=9222 connectaddress=127.0.0.1 connectport=9222 listenaddress=0.0.0.0
cls
echo ============================================
echo  Chrome started with following configuration:
echo ============================================
echo    * No-Caching
echo    * Developer Profile
echo    * Disabled TouchHistory
echo    * Disabled Web-Security 
echo    * Allowed XHR Localfile Access 
echo    * Forwarded Remote-Debug Port
echo ============================================
ipconfig | findstr "IPv4"
echo    Remote-Debug Port: 9222
echo ============================================
echo Dont close Chrome manually
echo Press any Button to terminate Chrome Network Debug Session
echo ============================================
pause
netsh interface portproxy delete v4tov4 listenport=9222 listenaddress=0.0.0.0
taskkill /F /IM Chrome.exe /T