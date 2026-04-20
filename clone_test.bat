@echo off
setlocal

set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"

echo [1/3] Rebuilding mod map (convert2 + UAssetGUI fromjson)...
python convert2.py Jeju_Worldaa.json map_work_changes.json Jeju_World.json
if errorlevel 1 exit /b 1

set "BEFORE="
if exist "%UMAP%" (
    for %%F in ("%UMAP%") do set "BEFORE=%%~tF"
)
start /B UAssetGUI.exe fromjson Jeju_World.json "%UMAP%" VER_UE5_5 MotorTown718P1
:wait_main
timeout /t 1 /nobreak >nul
if not exist "%UMAP%" goto wait_main
for %%F in ("%UMAP%") do set "AFTER=%%~tF"
if "%AFTER%"=="%BEFORE%" goto wait_main
echo   Main umap ready.

echo [2/3] Cloning a vanilla PublicParkingSpace BP actor to target coords...
MTBPInjector\bin\Release\net8.0\MTBPInjector.exe clone-actor ^
    --main "%UMAP%" ^
    --output "%UMAP%" ^
    --mappings "D:\MT\MotorTown718P1.usmap" ^
    --source "AmbulanceSpawner_C_UAID_107C61471EBE6F7A02_1816131378" ^
    --x -39030.86 --y -196310.17 --z -18000 ^
    --pitch 0 --yaw 0 --roll 0 ^
    --count 100 --grid 10 --spacing 1000
if errorlevel 1 exit /b 1

echo [3/3] Packing + deploying...
call modp.bat MapChangeTest_P
endlocal
