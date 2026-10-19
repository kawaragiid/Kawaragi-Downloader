@echo off
title Asisten Pemasangan Ekstensi Kawaragi Trigger
set "EXT_DIR=%~dp0"
if "%EXT_DIR:~-1%"=="\" set "EXT_DIR=%EXT_DIR:~0,-1%"

echo ========================================================
echo   PEMASANGAN EKSTENSI BROWSER KAWARAGI TRIGGER v2.0
echo ========================================================
echo.
echo [1/3] Menyalin lokasi folder ekstensi ke Clipboard...
echo|set /p="%EXT_DIR%"|clip
echo       Lokasi: %EXT_DIR%
echo.
echo [2/3] Membuka Windows Explorer pada folder Kawaragi-Trigger...
explorer /select,"%EXT_DIR%"
echo.
echo [3/3] Membuka halaman Ekstensi Browser...
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" "chrome://extensions"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" "chrome://extensions"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" "chrome://extensions"
) else if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" "edge://extensions"
)
echo.
echo CARA PASANG (10 DETIK):
echo 1. Aktifkan "Developer mode" (Mode Pengembang) di pojok kanan atas browser.
echo 2. Seret folder "Kawaragi-Trigger" dari Explorer ke jendela browser,
echo    ATAU klik "Load unpacked" lalu tekan Ctrl+V dan Enter!
echo.
pause
