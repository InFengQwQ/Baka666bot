@echo off
setlocal
cd /d "%~dp0"

REM Starts NapCat, then the bot. Set NAPCAT_QQ in .env to reuse the saved
REM session instead of scanning the QR code each time.

if not exist ".env" (
    echo Missing .env: copy .env.example to .env and fill SUPERUSERS.
    exit /b 1
)

if not exist "NapCat.Shell\napcat.bat" (
    echo Missing NapCat.Shell\napcat.bat.
    exit /b 1
)

set "NAPCAT_QQ="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="NAPCAT_QQ" set "NAPCAT_QQ=%%B"
)

netstat -ano | findstr /c:":6099 " | findstr /c:"LISTENING" >nul
if not errorlevel 1 (
    echo NapCat is already listening on 6099.
    goto runbot
)

if defined NAPCAT_QQ (
    start "NapCat" "NapCat.Shell\napcat.bat" -q %NAPCAT_QQ%
) else (
    start "NapCat" "NapCat.Shell\napcat.bat"
)

:runbot
uv run bot.py
exit /b %errorlevel%
