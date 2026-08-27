@echo off
title ATS Form Filler - Live Dashboard
echo ======================================================================
echo   ATS FORM FILLER v2.7 - LIVE APPLICATION PIPELINE DASHBOARD
echo ======================================================================
echo.
echo Starting embedded Live Analytics Web Server on http://127.0.0.1:8080...
echo.
start "" http://127.0.0.1:8080
python src/main.py --serve-dashboard --dashboard-port 8080
pause
