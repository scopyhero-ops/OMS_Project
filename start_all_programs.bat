@echo off
title OMS & Evidence System Launcher

echo =======================================================
echo =         Starting All System Components...           =
echo =======================================================
echo.

echo [1/2] Launching Main Server (in Server_App folder)...
:: คำสั่ง START จะเปิดหน้าต่างใหม่เพื่อรันเซิร์ฟเวอร์ โดยระบุให้ทำงานในโฟลเดอร์ Server_App
START "OMS - Main Server" /D "%~dp0Server_App" python app.py

echo      Waiting 3 seconds for the server to initialize...
timeout /t 3 >nul

echo.
echo [2/2] Launching Recorder App (in Desktop_Recorder folder)...
:: ใช้ START อีกครั้งเพื่อรันโปรแกรม Recorder ในโฟลเดอร์ที่ถูกต้อง
START "OMS - Desktop Recorder" /D "%~dp0Desktop_Recorder" python recorder_app.py

echo.
echo =======================================================
echo =  All programs launched in new windows.              =
echo =  This launcher will now close.                      =
echo =======================================================

:: หน่วงเวลา 2 วินาทีก่อนปิดหน้าต่างนี้ไป
timeout /t 2 >nul
exit