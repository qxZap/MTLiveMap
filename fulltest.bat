@echo off
setlocal enabledelayedexpansion

echo [1/5] Cleaning mod _Generated_ folder...
if exist "MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_" (
    rd /s /q "MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_"
)

echo [2/5] Importing meshes...
python import_meshes.py
if errorlevel 1 exit /b 1

echo [3/5] Building main map (dealerships + meshes)...
python convert2.py Jeju_Worldaa.json map_work_changes.json Jeju_World.json
if errorlevel 1 exit /b 1

echo [4/5] Converting main map JSON to umap...
set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"
set "BEFORE="
if exist "%UMAP%" (
    for %%F in ("%UMAP%") do set "BEFORE=%%~tF"
)
start /B UAssetGUI.exe fromjson Jeju_World.json "%UMAP%" VER_UE5_5 MotorTown718T9x
echo   Waiting for umap...
:wait_main
timeout /t 1 /nobreak >nul
if not exist "%UMAP%" (
    echo   .umap not yet created, waiting...
    goto wait_main
)
for %%F in ("%UMAP%") do set "AFTER=%%~tF"
if "!AFTER!"=="!BEFORE!" (
    echo   No change yet, waiting...
    goto wait_main
)
echo   umap ready.

echo [5/5] Packing and deploying...
call modp.bat MapChangeTest_P
if errorlevel 1 (
    echo Error: modp.bat failed
    exit /b 1
)

echo Done.
endlocal
