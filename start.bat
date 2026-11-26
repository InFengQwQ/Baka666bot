@echo off
setlocal
cd /d "%~dp0"

REM Start NapCat, then the bot. NAPCAT_QQ in .env skips the QR code.

if not exist ".env" (
    echo Missing .env: copy .env.example to .env and fill SUPERUSERS.
    exit /b 1
)

if not exist "NapCat.Shell\napcat.bat" (
    echo Missing NapCat.Shell\napcat.bat.
    exit /b 1
)

set "assets_ok=1"
for %%F in (ManiaReplayMaster.jar ma2om.exe mp32ogg.exe ncm2mp3.exe ncm2ogg.exe DragUnzip.exe prontom.exe) do (
    if not exist "src\plugins\Malody_toolkit\tools\%%F" set "assets_ok="
)
if not defined assets_ok (
    echo [setup] Downloading runtime assets...
    uv run python scripts\fetch-assets.py
    if errorlevel 1 echo [setup] Asset download failed; /replayrd and conversion commands may be unavailable.
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
