@echo off
setlocal

set "MODNAME=%~1"
set "PAKFILE=%MODNAME%.pak"
set "PAKDIR=D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks"

REM Recursively remove all .bak files in the current directory and subdirectories
echo Cleaning up old .bak files...
del /S /Q "*.bak"

REM Run repak
echo Packing "%MODNAME%"...
repak pack ".\%MODNAME%"
if errorlevel 1 (
    echo Error: repak failed!
    exit /b 1
)

REM Check if .pak file exists
if not exist "%PAKFILE%" (
    echo Error: "%PAKFILE%" not found after packing.
    exit /b 1
)

REM Copy to game directory
echo Copying "%PAKFILE%" to "%PAKDIR%"...
copy /Y "%PAKFILE%" "%PAKDIR%"
if errorlevel 1 (
    echo Error: Failed to copy the .pak file.
    exit /b 1
)

echo Done.
endlocal
