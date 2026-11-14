@echo off
setlocal
rem Alternate launcher for environments where Explorer applies SmartScreen
rem to the unsigned/self-signed app executable. See docs/WINDOWS_SMARTSCREEN.md.
set "APP=%~dp0win-unpacked\Lumen Studio.exe"
if not exist "%APP%" set "APP=%~dp0..\release\win-unpacked\Lumen Studio.exe"
if not exist "%APP%" set "APP=%~dp0..\Lumen Studio.exe"
if not exist "%APP%" (
  echo Lumen Studio executable not found.
  pause
  exit /b 1
)
start "" "%APP%"
endlocal
