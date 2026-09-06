@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo      Diary Replica - Build Windows EXE
echo ========================================
echo.

PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -BuildExe -NoLaunch
set "BUILD_EXIT=%ERRORLEVEL%"

echo.
if not "%BUILD_EXIT%"=="0" (
    echo [FAILED] The EXE was not generated. Review the error above.
) else (
    echo [SUCCESS] EXE generated:
    echo %~dp0dist\DiaryReplica.exe
)
echo.
pause
exit /b %BUILD_EXIT%
