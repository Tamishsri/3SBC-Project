@echo off
echo ============================================
echo   Launching Chrome with Debug Port 9222
echo ============================================
echo.
echo This will open Chrome with remote debugging enabled.
echo The ATS Form Filler will connect to this session.
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug-profile"
echo Chrome launched! You can now run the form filler.
echo.
pause
