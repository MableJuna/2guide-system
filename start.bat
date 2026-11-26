@echo off
title Hoa Lo Smart Museum Gateway & AI Engine V4.0
color 0E
cd /d "%~dp0"

echo ===================================================================
echo   KHOI DONG HE THONG HOA LO SMART MUSEUM GATEWAY ^& AI ENGINE V4.0
echo ===================================================================
echo.

node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Node.js tren may tinh!
    echo Vui long cai dat Node.js tu: https://nodejs.org/
    pause
    exit /b
)

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren may tinh!
    echo Vui long cai dat Python 3.10+ tu: https://www.python.org/
    pause
    exit /b
)

echo [1/3] Dang khoi dong Hoa Lo Vietnamese-Pivot AI Engine (Port 4001)...
start cmd /k "title Hoa Lo AI Engine (Port 4001) && cd /d "%~dp0" && python ai_engine/web_server.py --host 127.0.0.1 --port 4001"

timeout /t 2 /nobreak >nul

echo [2/3] Dang khoi dong Smart Museum Web Gateway ^& Audio WAV Stream (Port 5000)...
start cmd /k "title Hoa Lo Web Gateway (Port 5000) && cd /d "%~dp0" && node server.js"

timeout /t 2 /nobreak >nul

echo [3/3] Dang mo Man Hinh Truc Quan tren Trinh Duyet Web...
start http://localhost:5000

echo.
echo ===================================================================
echo  He thong da khoi dong hoan tat:
echo   - Hoa Lo AI Engine  : http://127.0.0.1:4001/api/chat/ask
echo   - Web Gateway UI    : http://localhost:5000
echo   - IP LAN cho ESP32  : Xem truc tiep tren giao dien Web
echo ===================================================================
echo.
