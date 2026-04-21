@echo off
setlocal enabledelayedexpansion

set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"
set "GENDIR=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_"

echo [1/3] Rebuilding mod map (import_meshes + convert2 + UAssetGUI fromjson)...
python import_meshes.py
if errorlevel 1 exit /b 1
python convert2.py Jeju_Worldaa.json map_work_changes.json Jeju_World.json
if errorlevel 1 exit /b 1

set "BEFORE="
if exist "%UMAP%" for %%F in ("%UMAP%") do set "BEFORE=%%~tF"
start /B UAssetGUI.exe fromjson Jeju_World.json "%UMAP%" VER_UE5_5 MotorTown718P1
:wait_main
timeout /t 1 /nobreak >nul
if not exist "%UMAP%" goto wait_main
for %%F in ("%UMAP%") do set "AFTER=%%~tF"
if "!AFTER!"=="!BEFORE!" goto wait_main
echo   Main umap ready.

echo [2/3] Cleaning and recreating mod _Generated_ ...
if exist "%GENDIR%" rd /s /q "%GENDIR%"
mkdir "%GENDIR%"

echo [2b/3] Cloning BP actors from map_work_changes.json into auto-resolved WP cells...
python clone_bp_actors.py ^
    --config map_work_changes.json ^
    --gen-dir "%GENDIR%"
if errorlevel 1 exit /b 1

echo [3/3] Packing + deploying...
call .\modp.bat MapChangeTest_P
endlocal
