@echo off
title OMS & Evidence System Launcher

echo =======================================================
echo =         Starting All System Components...           =
echo =======================================================
echo.

:: 1. รัน Main Server (app.py) อยู่ข้างนอกสุด
echo [1/3] Launching Main Server...
START "OMS - Main Server" /D "%~dp0" python app.py

echo      Waiting 2 seconds...
timeout /t 2 >nul

:: 2. รัน Stock Manager (อยู่ในโฟลเดอร์ stock_manager)
echo [2/3] Launching Stock Manager...
START "OMS - Stock Manager" /D "%~dp0stock_manager" python stock_manager_app.py

echo      Waiting 2 seconds...
timeout /t 2 >nul

:: 3. รัน VDO Recorder (อยู่ในโฟลเดอร์ Desktop_Recorder)
echo [3/3] Launching VDO Recorder...
:: แก้ไขตำแหน่งโฟลเดอร์เป็น Desktop_Recorder
START "OMS - Recorder" /D "%~dp0Desktop_Recorder" python recorder_app.py

echo.
echo =======================================================
echo =  All programs launched!                             =
echo =  Check individual windows for any errors.           =
echo =======================================================

timeout /t 5 >nul
exit
