@echo off
setlocal enabledelayedexpansion

set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"

echo [1/4] Running convert2.py...
python convert2.py Jeju_Worldaa.json map_work_changes.json Jeju_World.json
if errorlevel 1 (
    echo Error: convert2.py failed
    exit /b 1
)

echo [2/4] Recording current .umap timestamp...
set "BEFORE="
if exist "%UMAP%" (
    for %%F in ("%UMAP%") do set "BEFORE=%%~tF"
    echo   Before: !BEFORE!
) else (
    echo   .umap does not exist yet
)

echo [3/4] Running UAssetGUI fromjson...
start /B UAssetGUI.exe fromjson Jeju_World.json "%UMAP%" VER_UE5_5

echo   Waiting for .umap to be modified...
:wait_loop
timeout /t 1 /nobreak >nul
if not exist "%UMAP%" (
    echo   .umap not yet created, waiting...
    goto wait_loop
)
for %%F in ("%UMAP%") do set "AFTER=%%~tF"
if "!AFTER!"=="!BEFORE!" (
    echo   No change yet ^(!AFTER!^), waiting...
    goto wait_loop
)
echo   .umap modified: !AFTER!

echo [4/4] Running modp.bat MapChangeTest_P...
call modp.bat MapChangeTest_P
if errorlevel 1 (
    echo Error: modp.bat failed
    exit /b 1
)

echo Done.
endlocal
