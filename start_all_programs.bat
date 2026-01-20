@echo off
title OMS & Evidence System Launcher

echo =======================================================
echo =         Starting All System Components...           =
echo =======================================================
echo.

echo [1/2] Launching Main Server...
:: รัน app.py จากโฟลเดอร์ปัจจุบันที่ไฟล์ .bat นี้อยู่
START "OMS - Main Server" /D "%~dp0" python app.py

echo      Waiting 3 seconds for the server to initialize...
timeout /t 3 >nul

echo.
echo [2/2] Launching Recorder App...
:: หาก recorder_app.py อยู่ในโฟลเดอร์หลักเหมือนกัน ให้แก้ตรงนี้ด้วยครับ
START "OMS - Desktop Recorder" /D "%~dp0" python recorder_app.py

echo.
echo =======================================================
echo =  All programs launched in new windows.              =
echo =  This launcher will now close.                      =
echo =======================================================

timeout /t 2 >nul
exit
