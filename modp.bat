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
rem PAKDIR derived from MTMI_GAME_PAKDIR (preferred) or MT_GAME_DIR. Both
rem normally come from .env via build.bat. When running modp.bat
rem standalone we read .env directly so the deploy target stays in one
rem place — no hardcoded paths.
setlocal enabledelayedexpansion
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
        set "_K=%%A"
        set "_V=%%B"
        if defined _K (
            for /f "tokens=* delims= " %%K in ("!_K!") do set "_K=%%K"
            if defined _V (
                if "!_V:~0,1!"=="\"" set "_V=!_V:~1,-1!"
                if "!_V:~0,1!"=="'"  set "_V=!_V:~1,-1!"
            )
            if not defined !_K! set "!_K!=!_V!"
        )
    )
)
set "_K="
set "_V="
rem Auto-detect MT_GAME_DIR by probing common Steam drives when .env didn't
rem set it (mirrors build.bat and mt_paths) so standalone deploy works too.
if not defined MT_GAME_DIR if not defined MTMI_GAME_PAKDIR (
    for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
        if not defined MT_GAME_DIR (
            if exist "%%D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" set "MT_GAME_DIR=%%D:\SteamLibrary\steamapps\common\Motor Town"
            if exist "%%D:\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" set "MT_GAME_DIR=%%D:\Steam\steamapps\common\Motor Town"
            if exist "%%D:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" set "MT_GAME_DIR=%%D:\Program Files (x86)\Steam\steamapps\common\Motor Town"
        )
    )
)
if not defined MTMI_GAME_PAKDIR  if defined MT_GAME_DIR set "MTMI_GAME_PAKDIR=%MT_GAME_DIR%\MotorTown\Content\Paks"
set "PAKDIR=%MTMI_GAME_PAKDIR%"
if not defined PAKDIR set "PAKDIR="
if not exist "%PAKDIR%" (
    echo.
    echo [modp] ERROR: deploy target does not exist: "%PAKDIR%"
    echo        Edit .env and set MT_GAME_DIR ^(preferred^) or MTMI_GAME_PAKDIR
    echo        to your game's Paks folder. Browse the game in Steam —
    echo        Manage — Browse local files, drill into MotorTown\Content\Paks.
    exit /b 2
)

REM Recursively remove all .bak files in the current directory and subdirectories
echo Cleaning up old .bak files...
del /S /Q "*.bak"

REM Drop any prior pak from this mod (both pre- and post-rename names) so a
REM stale older pak from before the ZZZ_ rename can't shadow the new one.
if exist "%PAKDIR%\%PAKFILE%"   del /Q "%PAKDIR%\%PAKFILE%"
if exist "%PAKDIR%\%DEPLOY_PAK%" del /Q "%PAKDIR%\%DEPLOY_PAK%"

REM Run repak (prefer vendored tools\repak.exe; fall back to PATH).
set "REPAK=%~dp0tools\repak.exe"
if not exist "%REPAK%" set "REPAK=repak"
echo Packing "%MODNAME%"...
"%REPAK%" pack ".\%MODNAME%"
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
