@echo off
setlocal enabledelayedexpansion

rem ============================================================================
rem  Configuration is read from `.env` (sibling of this file). Copy
rem  `.env.example` to `.env` once and edit the values for your machine.
rem  Process env vars still take priority over `.env`.
rem
rem  Required keys:
rem    MT_GAME_DIR      -- game install folder (Steam Browse local files).
rem                        Auto-detected from common Steam paths when unset.
rem    MTMI_MAPPINGS    -- absolute path to the .usmap mappings file.
rem
rem  Optional keys:
rem    MTMI_MAPPINGS_TAG    -- defaults to basename of MTMI_MAPPINGS.
rem    MTMI_GAME_CONTENT    -- override pre-extracted content dir; defaults
rem                            to <repo>/vanilla_extract/MotorTown/Content
rem                            populated by `python bootstrap_extract.py`.
rem    MTMI_REPO_ROOT       -- override repo root for ue.py.
rem    MTMI_COOKED_CONTENT  -- UE editor cooked output folder (optional).
rem ============================================================================
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
        set "_KEY=%%A"
        set "_VAL=%%B"
        if defined _KEY (
            rem trim leading spaces on key
            for /f "tokens=* delims= " %%K in ("!_KEY!") do set "_KEY=%%K"
            rem strip surrounding quotes from value
            if defined _VAL (
                if "!_VAL:~0,1!"=="\"" set "_VAL=!_VAL:~1,-1!"
                if "!_VAL:~0,1!"=="'"  set "_VAL=!_VAL:~1,-1!"
            )
            rem .env never overrides a value already set in the shell env
            if not defined !_KEY! set "!_KEY!=!_VAL!"
        )
    )
)
set "_KEY="
set "_VAL="

rem -- Auto-detect MT_GAME_DIR by probing common Steam install drives if
rem -- neither process env nor .env supplied it. Mirrors mt_paths.py.
if not defined MT_GAME_DIR (
    for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
        if not defined MT_GAME_DIR (
            if exist "%%D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" (
                set "MT_GAME_DIR=%%D:\SteamLibrary\steamapps\common\Motor Town"
            ) else if exist "%%D:\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" (
                set "MT_GAME_DIR=%%D:\Steam\steamapps\common\Motor Town"
            ) else if exist "%%D:\Program Files (x86)\Steam\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak" (
                set "MT_GAME_DIR=%%D:\Program Files (x86)\Steam\steamapps\common\Motor Town"
            )
        )
    )
)

rem -- Default the .usmap to the copy bundled in the repo's mappings\
rem -- folder when .env didn't set one, so a fresh clone needs zero config.
if not defined MTMI_MAPPINGS (
    for %%F in ("%~dp0mappings\*.usmap") do if not defined MTMI_MAPPINGS set "MTMI_MAPPINGS=%%F"
)

rem -- Defaults / auto-derivations.
if not defined MTMI_MAPPINGS_TAG (
    for %%F in ("%MTMI_MAPPINGS%") do set "MTMI_MAPPINGS_TAG=%%~nF"
)
if not defined MTMI_REPO_ROOT set "MTMI_REPO_ROOT=%~dp0"
if not defined MTMI_COOKED_CONTENT set "MTMI_COOKED_CONTENT="
if not defined MTMI_GAME_CONTENT set "MTMI_GAME_CONTENT=%~dp0vanilla_extract\MotorTown\Content"
rem Drop foliage that ended up below sea level, at BUILD time. Editor-space Z
rem (the number you read in the viewport). Non-destructive: your level keeps
rem the instances, they just don't ship. CULL_MESHES empty = cull nothing.
rem FEATHER fades the cut out above ZMAX so the treeline isn't a straight cut.
if not defined MTMI_FOLIAGE_CULL_MESHES  set "MTMI_FOLIAGE_CULL_MESHES="
if not defined MTMI_FOLIAGE_CULL_ZMAX    set "MTMI_FOLIAGE_CULL_ZMAX="
if not defined MTMI_FOLIAGE_CULL_FEATHER set "MTMI_FOLIAGE_CULL_FEATHER=0"
rem Foliage that must never pop in. WP streams cells by distance, so a solid
rem rock can appear right in front of a moving vehicle. Meshes matching these
rem substrings ship as persistent-level StaticMeshActors instead (always
rem loaded, ~2 UObjects each) rather than as streamed cell foliage. Keep the
rem list to small hazardous sets; it does not scale to grass.
if not defined MTMI_FOLIAGE_AS_ACTORS set "MTMI_FOLIAGE_AS_ACTORS=Rock"
rem Swap a whole mesh set without repainting the level: comma-separated
rem from=to substring rewrites on /Game asset paths. Used for the seasonal
rem tree sets (NatureGreen = green, Nature = winter). Per-mesh safe: a mesh
rem with no counterpart in the target folder keeps its original path, so the
rem merged grass clumps (no winter version) still resolve.
if not defined MTMI_MESH_REMAP set "MTMI_MESH_REMAP="
rem Instance cull distances used when the editor exported 0. In UE 0 means
rem NEVER CULL, which at millions of instances draws every tree in the
rem streaming radius at full detail -- foliage to the horizon and the frame
rem rate with it. Foliage types sit at 0 by default, so 0 is treated as
rem "unset". A non-zero value from the editor always wins.
if not defined MTMI_FOLIAGE_CULL_START set "MTMI_FOLIAGE_CULL_START=0"
if not defined MTMI_FOLIAGE_CULL_END   set "MTMI_FOLIAGE_CULL_END=0"
rem Per-mesh cull overrides "substr:start:end,...". Grass carries the
rem geometry (merged Clump meshes are 16/64/256/1024 blades EACH), so it is
rem pulled in hard while trees keep their distance.
if not defined MTMI_FOLIAGE_CULL_OVERRIDES set "MTMI_FOLIAGE_CULL_OVERRIDES="
rem Volumetric fog reach, in uu, written onto Jeju's ExponentialHeightFog.
rem This is the froxel grid depth: fog is only integrated within this distance
rem of the camera, and NOTHING outside it can be voxelized -- not the height
rem fog, not a Volume-domain fog mesh, at any quality setting. Vanilla ships
rem 15000 (150 m), which is shorter than the distance from Galati Port to our
rem fog meshes. Cost is flat: GridSizeZ stays at 128 slices, each just covers
rem more depth, so the trade is softer fog gradients, not frame time.
rem Set to 0 to leave the map's own value alone.
if not defined MTMI_FOG_DISTANCE set "MTMI_FOG_DISTANCE=60000"
rem Float properties written onto Jeju's ExponentialHeightFogComponent,
rem "Name=Value,Name=Value". This drives the game's OWN fog, which is the one
rem fog system here known to render -- three mesh-based attempts were invisible
rem while an ordinary mesh at the same coordinates was not (see
rem fog_placements.json). GLOBAL: there is one height fog per scene and the
rem renderer only ever reads the first, so this changes Jeju's weather too.
rem   FogDensity        overall thickness. Vanilla leaves it at the 0.02 default.
rem   FogHeightFalloff  how fast it thins with altitude. Vanilla 0.75 keeps it
rem                     in the valleys; the island sits ~200 m up, so it needs
rem                     a much lower value to reach at all.
rem   StartDistance     metres before fog begins. Vanilla 10000 = 100 m.
rem   FogMaxOpacity     1.0 lets it go fully opaque.
rem Set empty to leave the fog exactly as the game ships it.
rem EMPTY: the island uses LocalFogVolume actors (static_meshes_parts/fog_volumes.json),
rem which are BOUNDED. Setting anything here changes Jeju's weather too, because a
rem scene has one height fog and the renderer only reads ExponentialFogs[0].
if not defined MTMI_FOG_PROPS set "MTMI_FOG_PROPS="
rem Substitute a different mesh for every injected mesh whose asset path
rem contains MTMI_DEBUG_MESH_FOR, scaling it by MTMI_DEBUG_MESH_SCALE on top of
rem whatever scale the entry already carries.
rem
rem This is how the island's fog is drawn. A Volume-domain material has to be
rem voxelized into the volumetric fog grid to be seen, and that never happened
rem in game however correct the asset was (see TODO section 4). An ordinary
rem additive Surface material needs none of that -- it draws on the same path
rem as the other 14,280 meshes, which demonstrably works. SM_Particle_Smoke_01a
rem carries vanilla Mat_Gradient_01, Surface + BLEND_Additive, so it is a soft
rem glow card the game already renders for its own FX. Its bounding sphere is
rem 12.8 uu against SM_Fog_01's 373, hence the ~29x on top of the scene's 10x.
if not defined MTMI_DEBUG_MESH_FOR set "MTMI_DEBUG_MESH_FOR=SM_Fog"
rem OFF. The fog is done with the game's own height fog now, so the scene's
rem meshes ship exactly as authored. Set MTMI_DEBUG_MESH to a mesh path to
rem substitute again, e.g. to check whether an actor is reaching the world.
if not defined MTMI_DEBUG_MESH set "MTMI_DEBUG_MESH="
if not defined MTMI_DEBUG_MESH_SCALE set "MTMI_DEBUG_MESH_SCALE=1"
rem World Partition streaming radius, in uu. Vanilla MainGrid is 25600
rem (256 m) over 12800 cells -- fine for sparse vanilla content, but once
rem every cell carries foliage a whole cell of trees appears ~256 m ahead of
rem you. Raising it keeps cells resident further out. Resident cell count
rem grows with the SQUARE of this, so raise it in steps and watch memory.
rem Empty = leave the map's own value alone.
if not defined MTMI_WP_LOADING_RANGE set "MTMI_WP_LOADING_RANGE="
if not defined MTMI_GAME_PAKDIR  if defined MT_GAME_DIR set "MTMI_GAME_PAKDIR=%MT_GAME_DIR%\MotorTown\Content\Paks"

rem -- Validate the required values. mt_paths.py runs its own validation
rem -- on every Python step; this bat-side check is just so the user
rem -- sees an immediate error rather than waiting for the first python.
set "VALIDATION_FAILED=0"
if not defined MT_GAME_DIR (
    echo.
    echo [build] ERROR: MT_GAME_DIR is not set and could not be auto-detected.
    echo            Edit .env and set it to your Motor Town install folder.
    echo            Right-click Motor Town in Steam -^> Manage -^> Browse local
    echo            files, then copy the path one level above the MotorTown
    echo            subfolder ^(the folder containing MotorTown\Content\Paks\^).
    set "VALIDATION_FAILED=1"
)
if not exist "%MTMI_MAPPINGS%" (
    echo.
    echo [build] ERROR: MTMI_MAPPINGS does not point at a .usmap file.
    echo            Looking for "%MTMI_MAPPINGS%" — not found.
    echo            Generate or download a .usmap matching your MT install
    echo            ^(UnrealMappingsDumper / Dumper-7^) and set the path in .env.
    set "VALIDATION_FAILED=1"
)
if defined MTMI_GAME_PAKDIR (
    if not exist "%MTMI_GAME_PAKDIR%" (
        echo.
        echo [build] ERROR: MTMI_GAME_PAKDIR does not point at the game's Paks folder.
        echo            Looking for "%MTMI_GAME_PAKDIR%" — not found.
        set "VALIDATION_FAILED=1"
    )
)
if "%VALIDATION_FAILED%"=="1" (
    echo.
    echo Aborting — fix the paths above before re-running. See README.md.
    exit /b 2
)

rem ----- Mod identity. ONE name, set in .env as MTMI_MOD_NAME, that the
rem ----- staging folder, the deployed pak and every path below derive from.
rem ----- Rename the folder to match and nothing else needs touching.
if not defined MTMI_MOD_NAME set "MTMI_MOD_NAME=MapChangeTest_P"
set "MODCONTENT=%MTMI_MOD_NAME%\MotorTown\Content"
set "DEPLOYED=%MTMI_GAME_PAKDIR%\zzzz_%MTMI_MOD_NAME%.pak"
set "UMAP=%MODCONTENT%\Maps\Jeju\Jeju_World.umap"
set "GENDIR=%MODCONTENT%\Maps\Jeju\Jeju_World\_Generated_"
set "INJECTOR=MTBPInjector\bin\Release\net8.0\MTBPInjector.exe"
set "VANILLA_MAP=%MTMI_GAME_CONTENT%\Maps\Jeju\Jeju_World.umap"

rem ----- Intermediate / scratch artifacts live in a temp work dir, NOT the
rem ----- repo. Keeps the checkout clean. MTMI_WORK_DIR overrides; default
rem ----- is %TEMP%\MTMapInjector (matches mt_paths.WORK_DIR).
if not defined MTMI_WORK_DIR set "MTMI_WORK_DIR=%TEMP%\MTMapInjector"
if not exist "%MTMI_WORK_DIR%" mkdir "%MTMI_WORK_DIR%"
set "CACHE_JSON=%MTMI_WORK_DIR%\Jeju_World_vanilla.json"
set "MAP_WORK_JSON=%MTMI_WORK_DIR%\map_work_changes.json"
set "PATCHED_MAP_JSON=%MTMI_WORK_DIR%\Jeju_World_patched.json"
rem Vanilla map + WP-cell registrations, BEFORE static meshes are injected.
rem Cell registration must run on the SMALL map: it re-serializes whatever
rem map it's handed, and doing that after a 3.4M-mesh injection costs 32 GB
rem of RAM (76k exports -> 6.8M). Injecting into this file instead keeps the
rem peak at the injection itself.
set "CELLS_MAP=%MTMI_WORK_DIR%\Jeju_World_cells.umap"

rem ---- Per-step gating. Each step can be skipped independently. Set STEP_X
rem ---- to "0" to skip that step. --skip-* flips it; --only-* runs just that
rem ---- step (convenience for iterating on a single slow stage).
set "STEP_BUILD=1"
set "STEP_CLEAN=1"
set "STEP_MESHES=1"
set "STEP_CONVERT=1"
set "STEP_FOLIAGE=1"
set "STEP_ACTORS=1"
set "STEP_PACK=1"
set "PULL_MAP=0"
rem --skip-cargo sets this; clone_bp_actors + verify_build read it to fully
rem ignore cargo (no Cargos_01 built/shipped, no safety-DP injection, no
rem cargo integrity checks). Inherited by child python processes.
set "MTMI_SKIP_CARGO="
rem --skip-cache-mesh sets this; import_meshes reuses already-copied cooked
rem meshes instead of re-copying. Default (unset) ALWAYS copies fresh from
rem cooked output, since cooked content can change at any time.
set "MTMI_SKIP_CACHE_MESH="
rem Foliage NEVER ships as StaticMeshActors any more - one actor per instance
rem costs >=2 UObjects against UE's hard 2,162,688 cap and crashes on load at
rem real density. It ships as instanced IFA cells in step [4] instead, so the
rem mesh stage always drops the fol_* shards. --skip-foliage turns off BOTH
rem (no foliage at all in the build).
set "MTMI_SKIP_FOLIAGE=1"

:parse_args
if "%~1"=="" goto after_args
if /i "%~1"=="--help"         goto usage
if /i "%~1"=="-h"             goto usage
if /i "%~1"=="--pull-map"     set "PULL_MAP=1"     & shift & goto parse_args
if /i "%~1"=="--skip-build"   set "STEP_BUILD=0"   & shift & goto parse_args
if /i "%~1"=="--skip-clean"   set "STEP_CLEAN=0"   & shift & goto parse_args
if /i "%~1"=="--skip-meshes"  set "STEP_MESHES=0"  & shift & goto parse_args
if /i "%~1"=="--skip-convert" set "STEP_CONVERT=0" & shift & goto parse_args
if /i "%~1"=="--skip-foliage-cells" set "STEP_FOLIAGE=0" & shift & goto parse_args
if /i "%~1"=="--skip-actors"  set "STEP_ACTORS=0"  & shift & goto parse_args
if /i "%~1"=="--skip_actors"  set "STEP_ACTORS=0"  & shift & goto parse_args
if /i "%~1"=="--skip-pack"    set "STEP_PACK=0"    & shift & goto parse_args
if /i "%~1"=="--layer"        set "MTMI_LAYER=%~2" & shift & shift & goto parse_args
if /i "%~1"=="--skip-cargo"   set "MTMI_SKIP_CARGO=1" & shift & goto parse_args
if /i "%~1"=="--skip-cache-mesh" set "MTMI_SKIP_CACHE_MESH=1" & shift & goto parse_args
if /i "%~1"=="--skip-cache"   set "MTMI_SKIP_CACHE_MESH=1" & shift & goto parse_args
if /i "%~1"=="--skip-foliage" set "STEP_FOLIAGE=0"  & shift & goto parse_args
if /i "%~1"=="--only-build"   call :only build   & shift & goto parse_args
if /i "%~1"=="--only-clean"   call :only clean   & shift & goto parse_args
if /i "%~1"=="--only-meshes"  call :only meshes  & shift & goto parse_args
if /i "%~1"=="--only-convert" call :only convert & shift & goto parse_args
if /i "%~1"=="--only-foliage" call :only foliage & shift & goto parse_args
if /i "%~1"=="--only-actors"  call :only actors  & shift & goto parse_args
if /i "%~1"=="--only-pack"    call :only pack    & shift & goto parse_args
if /i "%~1"=="--only-vehicles" call :only vehicles & shift & goto parse_args
echo Unknown flag: %~1
goto usage

:only
set "STEP_BUILD=0"
set "STEP_CLEAN=0"
set "STEP_MESHES=0"
set "STEP_CONVERT=0"
set "STEP_FOLIAGE=0"
set "STEP_ACTORS=0"
set "STEP_PACK=0"
if /i "%~1"=="build"   set "STEP_BUILD=1"
if /i "%~1"=="clean"   set "STEP_CLEAN=1"
if /i "%~1"=="meshes"  set "STEP_MESHES=1"
if /i "%~1"=="convert" set "STEP_CONVERT=1"
if /i "%~1"=="foliage" set "STEP_FOLIAGE=1"
if /i "%~1"=="actors"  set "STEP_ACTORS=1"
if /i "%~1"=="pack"    set "STEP_PACK=1"
rem vehicles: the 5b/5b2 blocks are not step-guarded, so they run
rem regardless; this just turns the world-building steps off and keeps
rem the injector build and the pack, which is everything a vehicles-only
rem change needs. Seconds instead of a twelve-minute full build.
if /i "%~1"=="vehicles" set "STEP_BUILD=1" & set "STEP_PACK=1"
exit /b 0

:usage
echo build.bat [options]
echo.
echo   --pull-map       Cache vanilla Jeju_World.umap -^> %CACHE_JSON% and exit.
echo                    Source: %VANILLA_MAP%
echo.
echo   --skip-build     Skip MTBPInjector rebuild
echo   --skip-clean     Skip mod _Generated_ + DC/Actors cleanup
echo   --skip-meshes    Skip import_meshes.py
echo   --skip-convert   Skip the static-mesh injection (step 5)
echo   --skip-foliage-cells  Skip step 4 ^(foliage IFA cells^)
echo   --only-vehicles  Rebuild ONLY vehicles.json changes, then pack.
echo   --skip-actors    Skip clone_bp_actors.py (WP cells, step 3). The
echo                    injection then runs straight off the vanilla map.
echo   --skip-pack      Skip modp.bat pack/deploy
echo   --skip-cargo     Fully ignore cargo: no Cargos_01 built/shipped, no
echo                    safety-DP injection, no cargo integrity checks
echo   --skip-cache-mesh Reuse already-copied cooked meshes instead of
echo                    re-copying (faster; default always copies fresh)
echo   --skip-foliage   No foliage at all in this build.
echo.
echo   --only-^<stage^>   Run only that stage. Stages: build, clean, meshes,
echo                    convert, foliage, actors, pack
endlocal
exit /b 0

:after_args

rem ----- Build LAYER. A layer decides which other mods this build may see.
rem mt_paths resolves vanilla assets through the installed paks, so a mod that
rem overrides Cargos or Vehicles silently becomes our baseline -- right when
rem building the layer FOR that mod, wrong for the plain release. mods.py turns
rem a layer name into the pak exclusions and the mod identity.
if defined MTMI_LAYER (
    for /f "usebackq delims=" %%i in (`python mods.py --layer %MTMI_LAYER%`) do set "MTMI_EXCLUDE_PAKS=%%i"
    for /f "usebackq delims=" %%i in (`python mods.py --layer %MTMI_LAYER% --mod-name`) do set "MTMI_MOD_NAME=%%i"
    if errorlevel 1 (
        echo   layer "%MTMI_LAYER%" could not be resolved -- see mods.json
        exit /b 1
    )
    rem EVERY path derived from the mod name has to be recomputed, not just the
    rem staging root. UMAP and GENDIR are set near the top from the default name,
    rem so a layer that only re-set MODCONTENT wrote its map into the BASE
    rem folder -- silently overwriting the base build's map with one built while
    rem another mod was visible, and shipping a layer pak with no map at all.
    set "MODCONTENT=!MTMI_MOD_NAME!\MotorTown\Content"
    set "UMAP=!MODCONTENT!\Maps\Jeju\Jeju_World.umap"
    set "GENDIR=!MODCONTENT!\Maps\Jeju\Jeju_World\_Generated_"
    set "DEPLOYED=%MTMI_GAME_PAKDIR%\zzzz_!MTMI_MOD_NAME!.pak"
    echo   layer !MTMI_LAYER!: building !MTMI_MOD_NAME!, hiding !MTMI_EXCLUDE_PAKS!

    rem A compat layer patches DATA. It must not build the island: it mounts
    rem after the base pak, so any cell it ships wins, and one built with
    rem foliage skipped took the base build's foliage down with it. Skipping
    rem the map steps also turns a 20-minute 900 MB build into a short one.
    for /f "usebackq delims=" %%i in (`python mods.py --layer %MTMI_LAYER% --delta`) do set "MTMI_DELTA=%%i"
    if "!MTMI_DELTA!"=="1" (
        set "STEP_MESHES=0"
        set "STEP_CONVERT=0"
        set "STEP_FOLIAGE=0"
        echo   layer !MTMI_LAYER! is a delta: data only, no map
    )
)

if "%PULL_MAP%"=="1" (
    echo [%TIME%] Pulling vanilla map from extracted content...
    if not exist "%VANILLA_MAP%" (
        echo   ERROR: vanilla Jeju_World.umap not found at:
        echo   %VANILLA_MAP%
        echo   Extract the game's cooked content there first.
        exit /b 1
    )
    call :wait_write "%CACHE_JSON%" tojson "%VANILLA_MAP%" "%CACHE_JSON%" VER_UE5_5 %MTMI_MAPPINGS_TAG%
    if errorlevel 1 exit /b 1
    echo [%TIME%] Cached %CACHE_JSON%. You can now run build.bat normally.
    endlocal
    exit /b 0
)

if "%STEP_BUILD%"=="1" (
    echo [%TIME%] [0/7] Rebuilding MTBPInjector ^(no-op if up to date^)...
    pushd MTBPInjector
    dotnet build -c Release --nologo -v quiet
    if errorlevel 1 ( popd & exit /b 1 )
    popd
) else ( echo [%TIME%] [0/7] skipped )

rem ----- Clearance: fingerprint the game pak and (delta-)extract any
rem ----- stale or missing vanilla data. Fast no-op when current; loudly
rem ----- re-extracts after a game update. Cold clone bootstraps here.
echo [%TIME%] [clearance] Verifying vanilla data against the game pak...
rem MTMI_FULL_EXTRACT=1 unpacks the ENTIRE game pak (every asset, ~GBs) so any
rem UAssetAPI read — clone source actors and all their transitive references —
rem always resolves locally. Default is delta extraction of just the bundles
rem the pipeline needs (fast, small). Both are cached by pak fingerprint.
if "%MTMI_FULL_EXTRACT%"=="1" (
    python bootstrap_extract.py --full
) else (
    python bootstrap_extract.py --ensure
)
if errorlevel 1 (
    echo   ERROR: vanilla data extraction failed. See messages above.
    exit /b 1
)

if "%STEP_CLEAN%"=="1" (
    echo [%TIME%] [1/7] Cleaning mod _Generated_ + DC/Actors + DeliveryPoint folders...
    if exist "%GENDIR%" rd /s /q "%GENDIR%"
    mkdir "%GENDIR%"
    rem DC/Actors ships only scene-only placeholder assets — the BP-clone pass
    rem replaces them at runtime, so any stale copies from prior runs would
    rem render as the raw placeholder mesh in-game. Wipe the folder each run.
    if exist "%MODCONTENT%\DC\Actors" rd /s /q "%MODCONTENT%\DC\Actors"
    rem DeliveryPoint folder holds BOTH our mod-shipped BP classes (ModXXXX)
    rem AND any vanilla-DP overrides from past pipeline iterations (e.g.
    rem Storage_Fuel, Refinery_Fuel from the now-removed wholesale boost
    rem injection). The mod BPs are regenerated by prepare_mod_bp_class
    rem each run, so a full wipe here is safe — and prevents stale vanilla
    rem overrides from shipping in the new pak.
    if exist "%MODCONTENT%\Objects\Mission\Delivery\DeliveryPoint" rd /s /q "%MODCONTENT%\Objects\Mission\Delivery\DeliveryPoint"
    rem The cell-registered map is only valid while the _Generated_ cells it
    rem points at exist. We just wiped them, so drop it too — otherwise a
    rem later --skip-actors run would inject into a map referencing cells
    rem that are no longer shipped.
    if exist "%CELLS_MAP%" del /q "%CELLS_MAP%" "%MTMI_WORK_DIR%\Jeju_World_cells.uexp" 2>nul
) else ( echo [%TIME%] [1/7] skipped )

if "%STEP_MESHES%"=="1" (
    echo [%TIME%] [2/7] Importing meshes ^(static_meshes_parts shards -^> work dir, streamed^)...
    python import_meshes.py
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [2/7] skipped )

rem ---- ORDER MATTERS: cells BEFORE meshes. Both stages re-serialize the
rem ---- whole main map, so each one's cost is set by how big that map is
rem ---- when it runs. Registering 11 WP cells is a tiny mutation, but doing
rem ---- it AFTER a full-density foliage injection means re-serializing 6.8M
rem ---- exports to do it — 32 GB of RAM, and it only gets worse with
rem ---- density. Run it on the 76k-export vanilla map instead, then inject
rem ---- meshes into that result. Same output; peak memory is now just the
rem ---- injection's own, which is the one cost we can't avoid.
if "%STEP_ACTORS%"=="1" (
    echo [%TIME%] [3/7] BP actors -^> WP cells ^(on the vanilla map, before meshes^)...
    if not exist "%VANILLA_MAP%" (
        echo   ERROR: vanilla Jeju_World.umap not found at:
        echo   %VANILLA_MAP%
        echo   Run: python bootstrap_extract.py
        exit /b 1
    )
    python clone_bp_actors.py ^
        --config "%MAP_WORK_JSON%" ^
        --gen-dir "%GENDIR%" ^
        --main-in "%VANILLA_MAP%" ^
        --main-out "%CELLS_MAP%"
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [3/7] skipped )

set "CULLZ="
set "CULLF="
if defined MTMI_FOLIAGE_CULL_ZMAX    if not "%MTMI_FOLIAGE_CULL_ZMAX%"==""    set "CULLZ=--cull-zmax %MTMI_FOLIAGE_CULL_ZMAX%"
if defined MTMI_FOLIAGE_CULL_FEATHER if not "%MTMI_FOLIAGE_CULL_FEATHER%"=="" set "CULLF=--cull-feather %MTMI_FOLIAGE_CULL_FEATHER%"
if "%STEP_FOLIAGE%"=="1" (
    echo [%TIME%] [4/7] Foliage -^> instanced IFA cells...
    if defined MTMI_MESH_REMAP if not "%MTMI_MESH_REMAP%"=="" echo   mesh remap: %MTMI_MESH_REMAP%
    if not defined MTMI_MESH_REMAP echo   mesh remap: none ^(meshes ship exactly as painted^)
    rem MUST run HERE: after the cell stage, before the mesh injection. It
    rem registers its cells into %CELLS_MAP%, which step 5 then injects into
    rem and writes out. Run it after step 5 and the registrations never reach
    rem the shipped map.
    python inject_foliage_cells.py ^
        --main-in "%CELLS_MAP%" ^
        --main-out "%CELLS_MAP%" ^
        --gen-dir "%GENDIR%" ^
        --cull-meshes "%MTMI_FOLIAGE_CULL_MESHES%" %CULLZ% %CULLF%
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [4/7] skipped )

if "%STEP_CONVERT%"=="1" (
    echo [%TIME%] [5/7] Injecting dealers + static meshes into Jeju_World.umap ^(direct UAssetAPI, no JSON^)...
    rem Replaces the old convert2.py + UAssetGUI fromjson round-trip. MTBPInjector
    rem reads the .umap binary directly, streams the static-mesh sidecar shards
    rem (named in %MAP_WORK_JSON%'s _imported_shards marker), appends the actors,
    rem and writes the .umap binary — bypassing the multi-GB JSON that made
    rem UAssetGUI fromjson blow past 55 GB of RAM on a full foliage export.
    rem Source is step 3's cell-registered map; falls back to plain vanilla when
    rem the cell stage was skipped or had nothing to register.
    set "INJECT_SRC=%CELLS_MAP%"
    if not exist "%CELLS_MAP%" set "INJECT_SRC=%VANILLA_MAP%"
    if not exist "!INJECT_SRC!" (
        echo   ERROR: source Jeju_World.umap not found at:
        echo   !INJECT_SRC!
        echo   Run: python bootstrap_extract.py
        exit /b 1
    )
    echo   source: !INJECT_SRC!
    "%INJECTOR%" inject-static --main "!INJECT_SRC!" --output "%UMAP%" --mappings "%MTMI_MAPPINGS%" --config "%MAP_WORK_JSON%" --fog-distance %MTMI_FOG_DISTANCE% --fog-props "%MTMI_FOG_PROPS%" --fog-props-file "%~dp0static_meshes_parts\height_fog.json" --debug-mesh-for "%MTMI_DEBUG_MESH_FOR%" --debug-mesh "%MTMI_DEBUG_MESH%" --debug-mesh-scale %MTMI_DEBUG_MESH_SCALE%
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [5/7] skipped )

if not "%MTMI_SKIP_VEHICLES%"=="1" (
    echo [%TIME%] [5b] Unlocking hidden vehicles ^(mod-aware^)...
    python unlock_vehicles.py
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [5b] skipped ^(MTMI_SKIP_VEHICLES=1^) )

rem Custom vehicles declared in vehicles.json. AFTER the unlock pass on
rem purpose: unlock rebuilds each table from the copy the GAME loads, so a row
rem added before it would be thrown away. This layers on top of the tables the
rem unlock pass just wrote.
if not "%MTMI_SKIP_VEHICLES%"=="1" (
    echo [%TIME%] [5b2] Building custom vehicles from vehicles.json...
    python build_vehicles.py
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [5b2] skipped ^(MTMI_SKIP_VEHICLES=1^) )

rem Physical materials from materials.json. Same shape as vehicles: copy the
rem asset the GAME loads, patch it, ship our copy over the top.
if not "%MTMI_SKIP_MATERIALS%"=="1" (
    echo [%TIME%] [5b3] Patching physical materials from materials.json...
    python build_materials.py
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [5b3] skipped ^(MTMI_SKIP_MATERIALS=1^) )

if not "%MTMI_SKIP_CONFIG%"=="1" (
    echo [%TIME%] [5c] Merging console variables ^(mod-aware^)...
    python merge_config.py
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [5c] skipped ^(MTMI_SKIP_CONFIG=1^) )

rem The clean step wipes three folders and nothing else, so an asset painted
rem into the scene once and removed later keeps shipping forever -- the pak only
rem ever grows. This walks the package references out of the maps and data
rem assets and drops whatever nothing can reach. Delta layers skip it: they are
rem pruned to the data files anyway, and they ship no map to walk from.
if not "%MTMI_DELTA%"=="1" (
    echo [%TIME%] [5e] Dropping staged assets nothing references...
    python prune_unused_assets.py "%MODCONTENT%" --apply
    if errorlevel 1 exit /b 1
)

rem Step 3 writes a map on its way to producing the Mod* classes, so a delta
rem layer has one staged even with the map steps off. Strip it here rather
rem than trusting every step to have stayed in its lane.
if "%MTMI_DELTA%"=="1" (
    echo [%TIME%] [5d] Pruning !MTMI_MOD_NAME! to the delta...
    python prune_delta.py "%MODCONTENT%"
    if errorlevel 1 exit /b 1
)

if "%STEP_PACK%"=="1" (
    echo [%TIME%] [6/7] Packing and deploying...
    REM Verification runs AFTER deploy, so keep the last known-good pak to
    REM roll back to. Without this a failed check leaves the broken pak live.
    if exist "%DEPLOYED%" (
        copy /y "%DEPLOYED%" "%DEPLOYED%.lastgood" >nul
    )
    call .\modp.bat %MTMI_MOD_NAME%
    if errorlevel 1 exit /b 1
) else ( echo [%TIME%] [6/7] skipped )

if "%STEP_PACK%"=="1" (
    echo [%TIME%] [7/7] Verifying built mod integrity...
    python verify_build.py
    if errorlevel 1 (
        echo   INTEGRITY CHECK FAILED — rolling back to the last good pak.
        if exist "%DEPLOYED%.lastgood" (
            move /y "%DEPLOYED%.lastgood" "%DEPLOYED%" >nul
            echo   Restored the previous pak. The game is playable; this build is not deployed.
        ) else (
            echo   No previous pak to restore — the deployed pak is the failed one.
        )
        exit /b 1
    )
    if exist "%DEPLOYED%.lastgood" del "%DEPLOYED%.lastgood"
    REM Regenerate the economy page from what we just shipped, so the
    REM haul-this-there reference can never drift from the pak.
    python economy_report.py
) else ( echo [%TIME%] [7/7] skipped )

echo [%TIME%] Done.
endlocal
exit /b 0

rem ------------------------------------------------------------------
rem :wait_write <target-file> <UAssetGUI-verb> <UAssetGUI-args...>
rem Runs UAssetGUI.exe in the background and blocks until the target file
rem has been (re)written. Needed because UAssetGUI's fromjson/tojson paths
rem are asynchronous — the batch would otherwise race ahead with a stale
rem file. Extracted from inline labels because cmd doesn't allow labels
rem inside parenthesized blocks.
rem ------------------------------------------------------------------
:wait_write
rem Runs UAssetGUI synchronously (its CLI blocks until the file is written
rem and flushed) and verifies the target was produced. The old async
rem start /B + timeout-poll was fragile — under output redirection the
rem `timeout` command fails ("Input redirection is not supported") and the
rem loop busy-spins. A direct call has neither problem.
setlocal
set "TARGET=%~1"
shift
set "UAGUI=%~dp0tools\UAssetGUI.exe"
if not exist "%UAGUI%" set "UAGUI=UAssetGUI.exe"
"%UAGUI%" %1 %2 %3 %4 %5 %6 %7 %8 %9
if not exist "%TARGET%" (
    echo   ERROR: UAssetGUI did not produce "%TARGET%"
    endlocal & exit /b 1
)
endlocal
exit /b 0
