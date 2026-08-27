@echo off
title ATS Form Filler - Drop Folder Inbox Watcher
echo ======================================================================
echo   ATS FORM FILLER v2.7 - DROP-FOLDER INBOX WATCHER DAEMON
echo ======================================================================
echo.
if not exist "inbox" mkdir inbox
echo Drop any resume (.pdf, .txt, .json) into the 'inbox' directory.
echo The daemon will automatically parse and fill the active Chrome tab!
echo.
python src/main.py --watch-dir inbox --allow-generic --detect-captcha --generate-cover-letter
pause
