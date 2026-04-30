@echo off
setlocal

set "MODNAME=%~1"
set "PAKFILE=%MODNAME%.pak"
rem Deployed pak gets a "zzzz_" lowercase prefix so UE's alphabetical
rem pak load order puts our changes (Cargos.uasset, Jeju_World.umap)
rem AFTER every other Cargos-overriding pak in the user's load order —
rem including ZZZ_qxZap_..._A.pak and zzProxysOversizeCargo_A.pak.
rem Empirically Cargos was being shadowed by zzProxys until our prefix
rem sorted strictly later. UE 5.5 pak sort is case-insensitive ASCII
rem ascending; "zzzz" beats "zzpr"/"zzqx" because at char 3 'z'>'p'/'q'.
set "DEPLOY_NAME=zzzz_%MODNAME%"
set "DEPLOY_PAK=%DEPLOY_NAME%.pak"
set "PAKDIR=D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks"

REM Recursively remove all .bak files in the current directory and subdirectories
echo Cleaning up old .bak files...
del /S /Q "*.bak"

REM Drop any prior pak from this mod (both pre- and post-rename names) so a
REM stale older pak from before the ZZZ_ rename can't shadow the new one.
if exist "%PAKDIR%\%PAKFILE%"   del /Q "%PAKDIR%\%PAKFILE%"
if exist "%PAKDIR%\%DEPLOY_PAK%" del /Q "%PAKDIR%\%DEPLOY_PAK%"

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

REM Copy to game directory under the ZZZ_-prefixed name.
echo Copying "%PAKFILE%" to "%PAKDIR%\%DEPLOY_PAK%"...
copy /Y "%PAKFILE%" "%PAKDIR%\%DEPLOY_PAK%" >nul
if errorlevel 1 (
    echo Error: Failed to copy the .pak file.
    exit /b 1
)

echo Done.
endlocal
