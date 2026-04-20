@echo off
setlocal enabledelayedexpansion

set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"
set "GENDIR=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_"

echo [1/3] Rebuilding mod map (convert2 + UAssetGUI fromjson)...
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

echo [2b/3] Cloning real parking actor from vanilla cell into target cells...
for %%C in (0W5HFJERQNYIKT4TIFEZBU4PD) do (
    copy /Y "D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_\%%C.umap"  "%GENDIR%\%%C.umap"  >nul
    copy /Y "D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_\%%C.uexp"  "%GENDIR%\%%C.uexp"  >nul
    MTBPInjector\bin\Release\net8.0\MTBPInjector.exe clone-cross-cell ^
        --mappings "D:\MT\MotorTown718P1.usmap" ^
        --source-cell "D:\MT\Output\Exports\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_\0MYO9WO9JBZ10BIDLXVFRXAOG.umap" ^
        --source-actor "ParkingSpace_Large_01_UAID_2CF05D790A1CFFDB01_1915517403" ^
        --dst-cell "%GENDIR%\%%C.umap" ^
        --output "%GENDIR%\%%C.umap" ^
        --preload-bp "D:\MT\Output\Exports\MotorTown\Content\Objects\ParkingSpace\Interaction_ParkingSpace_Large.uasset" ^
        --x -39750.86 --y -196340.17 --z -21840.35
    if errorlevel 1 exit /b 1
)

echo [3/3] Packing + deploying...
call .\modp.bat MapChangeTest_P
endlocal
