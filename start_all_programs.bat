@echo off
title OMS & Evidence System Launcher

echo =======================================================
echo =         Starting All System Components...           =
echo =======================================================
echo.

echo [1/3] Launching Main Server...
:: รัน app.py จากโฟลเดอร์หลัก
START "OMS - Main Server" /D "%~dp0" python app.py

echo      Waiting 2 seconds...
timeout /t 2 >nul

echo.
echo [2/3] Launching Stock Manager...
:: รัน stock_manager_app.py ที่อยู่ในโฟลเดอร์ stock_manager
START "OMS - Stock Manager" /D "%~dp0stock_manager" python stock_manager_app.py

echo      Waiting 2 seconds...
timeout /t 2 >nul

echo.
echo [3/3] Launching Recorder App...
:: รัน recorder_app.py (ถ้าอยู่ในโฟลเดอร์หลัก)
START "OMS - Desktop Recorder" /D "%~dp0" python recorder_app.py

echo.
echo =======================================================
echo =  All programs launched in new windows.              =
echo =  This launcher will now close.                      =
echo =======================================================

timeout /t 2 >nul
exit
