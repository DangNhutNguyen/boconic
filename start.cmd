@echo off
setlocal EnableDelayedExpansion

title Boconic Platform - Orchestrator

echo ==============================================================================
echo                      BOCONIC PLATFORM - KHOI DONG HE THONG
echo ==============================================================================

if "%1"=="docker" goto start_docker
if "%1"=="--docker" goto start_docker
if "%1"=="-d" goto start_docker

if not exist ".env" (
    echo [!] Tep .env chua ton tai. Dang tao tu dong tu .env.example...
    copy ".env.example" ".env" >nul
    echo [OK] Da tao tep .env thanh cong.
)

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [i] Su dung Python tu .venv: !PYTHON_EXE!
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    echo [i] Su dung Python tu venv: !PYTHON_EXE!
) else (
    set "PYTHON_EXE=python"
    echo [i] Su dung Python he thong
)

echo.
echo [*] Dang kiem tra va dong bo co so du lieu (Migrations and RBAC Setup)...
%PYTHON_EXE% scripts\setup.py
if errorlevel 1 (
    echo [!] Setup co canh bao hoac loi, van tiep tuc khoi dong dich vu...
)

echo.
echo ==============================================================================
echo               DANG KHOI CHAY TAT CA DICH VU BOCONIC...
echo ==============================================================================

echo [1/3] Khoi chay FastAPI Backend va Admin Console (Port 8000)...
start "Boconic - Web API va Admin Console" cmd /k "%PYTHON_EXE% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/3] Khoi chay Telegram Bot Gateway...
start "Boconic - Telegram Bot" cmd /k "%PYTHON_EXE% -m app.bot.main"

echo [3/3] Khoi chay Background Job Worker...
start "Boconic - Background Worker" cmd /k "%PYTHON_EXE% -m app.jobs.worker"

echo.
echo ==============================================================================
echo                         HE THONG DA SAN SANG!
echo ==============================================================================
echo  - Admin Web Console : http://127.0.0.1:8000/admin
echo    Tai khoan mac dinh : admin
echo    Mat khau mac dinh : Boconic@2026
echo.
echo  - API Documentation : http://127.0.0.1:8000/docs
echo  - Health Probe      : http://127.0.0.1:8000/health/live
echo  - Telegram Bot      : Dang chay polling (xem cua so Telegram Bot)
echo  - Job Worker        : Dang chay xu ly outbox (xem cua so Background Worker)
echo ==============================================================================
echo.
echo Go 'stop' va nhan Enter ben duoi de tat tat ca cac cua so dich vu,
echo hoac dong truc tiep tung cua so khi ban hoan tat.
echo.

:loop
set "USER_INPUT="
set /p "USER_INPUT=Boconic> "
if /i "%USER_INPUT%"=="stop" goto stop_all
if /i "%USER_INPUT%"=="exit" goto stop_all
if /i "%USER_INPUT%"=="quit" goto stop_all
goto loop

:stop_all
echo.
echo [*] Dang dung tat ca cac tien trinh Boconic...
taskkill /fi "WINDOWTITLE eq Boconic - Web API*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Boconic - Telegram Bot*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq Boconic - Background Worker*" /f >nul 2>&1
echo [OK] Da tat tat ca cac dich vu Boconic.
timeout /t 2 >nul
exit /b 0

:start_docker
echo [*] Dang khoi chay Boconic bang Docker Compose...
docker compose up -d
echo [OK] Cac container Docker da duoc khoi dong o che do background.
echo     Xem logs bang lenh: docker compose logs -f
exit /b 0
