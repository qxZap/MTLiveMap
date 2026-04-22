@echo off
setlocal enabledelayedexpansion

set "UMAP=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World.umap"
set "GENDIR=MapChangeTest_P\MotorTown\Content\Maps\Jeju\Jeju_World\_Generated_"
set "INJECTOR=MTBPInjector\bin\Release\net8.0\MTBPInjector.exe"

echo [0/6] Rebuilding MTBPInjector (no-op if up to date)...
pushd MTBPInjector
dotnet build -c Release --nologo -v quiet
if errorlevel 1 ( popd & exit /b 1 )
popd

echo [1/6] Cleaning mod _Generated_ folder...
if exist "%GENDIR%" rd /s /q "%GENDIR%"
mkdir "%GENDIR%"

echo [2/6] Importing meshes (static_meshes.json -^> map_work_changes.json)...
python import_meshes.py
if errorlevel 1 exit /b 1

echo [3/6] Building main map JSON (dealerships + static meshes)...
python convert2.py Jeju_Worldaa.json map_work_changes.json Jeju_World.json
if errorlevel 1 exit /b 1

echo [4/6] UAssetGUI fromjson -^> Jeju_World.umap...
set "BEFORE="
if exist "%UMAP%" for %%F in ("%UMAP%") do set "BEFORE=%%~tF"
start /B UAssetGUI.exe fromjson Jeju_World.json "%UMAP%" VER_UE5_5 MotorTown718P1
:wait_main
timeout /t 1 /nobreak >nul
if not exist "%UMAP%" goto wait_main
for %%F in ("%UMAP%") do set "AFTER=%%~tF"
if "!AFTER!"=="!BEFORE!" goto wait_main
echo   Main umap ready.

echo [5/6] BP actors -^> WP cells (auto-register new cells for far coords)...
python clone_bp_actors.py ^
    --config map_work_changes.json ^
    --gen-dir "%GENDIR%" ^
    --main-in "%UMAP%" ^
    --main-out "%UMAP%"
if errorlevel 1 exit /b 1

echo [6/6] Packing and deploying...
call .\modp.bat MapChangeTest_P
if errorlevel 1 exit /b 1

echo Done.
endlocal
