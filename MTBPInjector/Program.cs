using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UAssetAPI;
using UAssetAPI.ExportTypes;
using UAssetAPI.PropertyTypes.Objects;
using UAssetAPI.PropertyTypes.Structs;
using UAssetAPI.UnrealTypes;
using UAssetAPI.Unversioned;

namespace MTBPInjector;

internal static class Program
{
    private const EngineVersion EngineVer = EngineVersion.VER_UE5_5;

    public static int Main(string[] args)
    {
        if (args.Length == 0) { PrintHelp(); return 1; }

        try
        {
            return args[0] switch
            {
                "inject-cell"  => InjectCell(args.Skip(1).ToArray()),
                "inject-batch" => InjectBatch(args.Skip(1).ToArray()),
                "inject-main"  => InjectMain(args.Skip(1).ToArray()),
                "inject-static" => InjectStatic(args.Skip(1).ToArray()),
                "dump-extras"   => DumpExtras(args.Skip(1).ToArray()),
                "reencode-foliage" => ReencodeFoliage(args.Skip(1).ToArray()),
                "inject-foliage-probe" => InjectFoliageProbe(args.Skip(1).ToArray()),
                "make-foliage-cell" => MakeFoliageCell(args.Skip(1).ToArray()),
                "make-stringtable" => MakeStringTable(args.Skip(1).ToArray()),
                "clone-actor"  => CloneActor(args.Skip(1).ToArray()),
                "clone-cross-cell" => CloneCrossCell(args.Skip(1).ToArray()),
                "clone-batch"      => CloneBatch(args.Skip(1).ToArray()),
                "clone-super-batch"=> CloneSuperBatch(args.Skip(1).ToArray()),
                "inspect-cell" => InspectCell(args.Skip(1).ToArray()),
                "inspect-export" => InspectExport(args.Skip(1).ToArray()),
                "inspect-imports" => InspectImports(args.Skip(1).ToArray()),
                "inspect-by-class" => InspectByClass(args.Skip(1).ToArray()),
                "find-cell-wp" => FindCellWP(args.Skip(1).ToArray()),
                "find-cells-batch" => FindCellsBatch(args.Skip(1).ToArray()),
                "dump-level-extras" => DumpLevelExtras(args.Skip(1).ToArray()),
                "dump-streaming-grids" => DumpStreamingGridsCmd(args.Skip(1).ToArray()),
                "decode-layer-keys" => DecodeLayerKeys(args.Skip(1).ToArray()),
                "register-new-cell" => RegisterNewCell(args.Skip(1).ToArray()),
                "register-cells-batch" => RegisterCellsBatch(args.Skip(1).ToArray()),
                "register-and-clone" => RegisterAndClone(args.Skip(1).ToArray()),
                "mutate-bp-cdo" => MutateBpCdo(args.Skip(1).ToArray()),
                "mutate-cargos" => MutateCargos(args.Skip(1).ToArray()),
                "dump-cargo-row" => DumpCargoRow(args.Skip(1).ToArray()),
                "mesh-collision" => MeshCollision(args.Skip(1).ToArray()),
                "dump-cargo-weights" => DumpCargoWeights(args.Skip(1).ToArray()),
                "dump-table" => DumpTable(args.Skip(1).ToArray()),
                "set-worldmap" => SetWorldMap(args.Skip(1).ToArray()),
                "clone-vehicle-row" => CloneVehicleRow(args.Skip(1).ToArray()),
                "vehicle-awd" => VehicleAllWheelDrive(args.Skip(1).ToArray()),
                "vehicle-fuel-pump" => VehicleFuelPump(args.Skip(1).ToArray()),
                "vehicle-cargo-fuels" => VehicleCargoFuels(args.Skip(1).ToArray()),
                "unlock-vehicles" => UnlockVehicles(args.Skip(1).ToArray()),
                "dump-schema" => DumpSchema(args.Skip(1).ToArray()),
                "dump-enum" => DumpEnum(args.Skip(1).ToArray()),
                "dump-names" => DumpNames(args.Skip(1).ToArray()),
                "dump-mesh-bounds" => DumpMeshBounds(args.Skip(1).ToArray()),
                "set-export-prop" => SetExportProp(args.Skip(1).ToArray()),
                _ => Fail($"Unknown command: {args[0]}"),
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"FATAL: {ex.GetType().Name}: {ex.Message}");
            Console.Error.WriteLine(ex.StackTrace);
            return 2;
        }
    }

    private static int Fail(string msg) { Console.Error.WriteLine(msg); PrintHelp(); return 1; }

    private static void PrintHelp() => Console.WriteLine(
        "Usage:\n" +
        "  MTBPInjector inject-cell --cell <in.umap> --output <out.umap> --mappings <usmap>\n" +
        "                           --x N --y N --z N [--pitch N] [--yaw N] [--roll N]\n" +
        "                           --bp <BlueprintPath>\n" +
        "  MTBPInjector inject-batch --config <map_work_changes.json>\n" +
        "                            --mappings <usmap>\n" +
        "                            --game-content <path>\n" +
        "                            --mod-content <path>\n" +
        "  MTBPInjector inject-main --main <Jeju_World.umap> --output <out.umap>\n" +
        "                           --mappings <usmap> --config <map_work_changes.json>\n" +
        "                           --content-root <ContentDir>\n" +
        "  MTBPInjector inject-static --main <Jeju_World.umap> --output <out.umap>\n" +
        "                             --mappings <usmap> --config <map_work_changes.json>\n" +
        "        Injects dealerships + static meshes directly into the .umap binary\n" +
        "        (replaces convert2.py + UAssetGUI fromjson). Static meshes are\n" +
        "        streamed from the JSONL sidecar shards named in the config marker.\n" +
        "  MTBPInjector inspect-cell --cell <in.umap> --mappings <usmap>\n");

    private static Dictionary<string, string> ParseFlags(string[] args)
    {
        var d = new Dictionary<string, string>();
        int i = 0;
        while (i < args.Length)
        {
            if (!args[i].StartsWith("--")) throw new ArgumentException($"Bad flag: {args[i]}");
            var key = args[i].Substring(2);
            if (i + 1 < args.Length && !args[i + 1].StartsWith("--"))
            {
                d[key] = args[i + 1];
                i += 2;
            }
            else
            {
                d[key] = "true";
                i += 1;
            }
        }
        return d;
    }

    private static Usmap LoadMappings(string path) => new Usmap(path);

    // ----------------------------------------------------------------------
    // INSPECT
    // ----------------------------------------------------------------------
    private static int InspectCell(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        Console.WriteLine($"NameMap: {asset.GetNameMapIndexList().Count}");
        Console.WriteLine($"Imports: {asset.Imports.Count}");
        Console.WriteLine($"Exports: {asset.Exports.Count}");
        foreach (var (e, i) in asset.Exports.Select((e, i) => (e, i)))
        {
            var typeName = e.GetType().Name;
            Console.WriteLine($"  {i + 1}: {e.ObjectName} ({typeName})");
        }
        return 0;
    }

    // ----------------------------------------------------------------------
    // INJECT-CELL: add a parking actor to one cell, write output
    // ----------------------------------------------------------------------
    private static int InjectCell(string[] args)
    {
        var f = ParseFlags(args);
        var cellPath = f["cell"];
        var outPath = f["output"];
        var mappings = LoadMappings(f["mappings"]);

        var asset = new UAsset(cellPath, EngineVer, mappings);
        Console.WriteLine($"Loaded {cellPath}: {asset.Exports.Count} exports, {asset.Imports.Count} imports");

        var bpPath = f["bp"];
        var x = double.Parse(f["x"]);
        var y = double.Parse(f["y"]);
        var z = double.Parse(f["z"]);
        var pitch = f.GetValueOrDefault("pitch", "0") is var ps ? double.Parse(ps) : 0;
        var yaw   = f.GetValueOrDefault("yaw",   "0") is var ys ? double.Parse(ys) : 0;
        var roll  = f.GetValueOrDefault("roll",  "0") is var rs ? double.Parse(rs) : 0;
        var label = f.GetValueOrDefault("label", "ParkingLot_MOD");

        InjectParkingActor(asset, bpPath, x, y, z, pitch, yaw, roll, label);

        Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);
        asset.Write(outPath);
        Console.WriteLine($"Wrote {outPath}");
        return 0;
    }

    // ----------------------------------------------------------------------
    // INJECT-BATCH: read JSON, group by cell, inject + write
    // ----------------------------------------------------------------------
    private static int InjectBatch(string[] args)
    {
        var f = ParseFlags(args);
        var configJson = JObject.Parse(File.ReadAllText(f["config"]));
        var mappings = LoadMappings(f["mappings"]);
        var gameContent = f["game-content"];
        var modContent = f["mod-content"];
        var noInject = f.ContainsKey("no-inject");

        var bpEntries = new List<JObject>();
        var bpSection = configJson["blueprint_actors"] as JObject;
        if (bpSection != null)
            foreach (var group in bpSection.Properties())
                if (group.Value is JArray arr)
                    foreach (var e in arr) bpEntries.Add((JObject)e);

        if (bpEntries.Count == 0) { Console.WriteLine("No blueprint_actors entries."); return 0; }

        // Pre-load each referenced BP .uasset so its real schema is registered in mappings.
        var contentRoot = f.TryGetValue("content-root", out var cr) ? cr
            : DeriveContentRoot(gameContent);
        foreach (var bpPath in bpEntries.Select(e => (string)e["blueprint_path"]!).Distinct())
        {
            var bpUasset = ResolveBpUasset(contentRoot, bpPath);
            if (bpUasset == null)
            {
                Console.Error.WriteLine($"  Warning: BP .uasset not found for {bpPath} (expected under {contentRoot})");
                continue;
            }
            try
            {
                var _ = new UAsset(bpUasset, EngineVer, mappings);
                Console.WriteLine($"  Loaded BP schema from {bpUasset}");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"  Failed to load {bpUasset}: {ex.Message}");
            }
        }

        // Group by closest cell (simple approach — find cell whose center is closest)
        // Optional override: --target-cell <name> forces all entries into a specific cell.
        // Useful when we've identified the cell via WP bounds (find-cell-wp) and want
        // to bypass the bbox-scan heuristic.
        string? targetCellOverride = f.TryGetValue("target-cell", out var tc) ? tc : null;

        var byCell = new Dictionary<string, List<JObject>>();
        foreach (var entry in bpEntries)
        {
            var ex = (double)entry["X"]!;
            var ey = (double)entry["Y"]!;
            var cell = targetCellOverride ?? FindCellForCoords(gameContent, ex, ey);
            if (cell == null)
            {
                Console.Error.WriteLine($"  No cell found for ({ex:F0}, {ey:F0})");
                continue;
            }
            Console.WriteLine($"  ({ex:F0}, {ey:F0}) -> cell {cell}");
            if (!byCell.ContainsKey(cell)) byCell[cell] = new List<JObject>();
            byCell[cell].Add(entry);
        }

        Directory.CreateDirectory(modContent);
        foreach (var kv in byCell)
        {
            var cellName = kv.Key;
            var srcUmap = Path.Combine(gameContent, cellName + ".umap");
            var dstUmap = Path.Combine(modContent, cellName + ".umap");
            Console.WriteLine($"\n[cell {cellName}] {kv.Value.Count} parking actors");
            var asset = new UAsset(srcUmap, EngineVer, mappings);

            int idx = 0;
            if (!noInject)
            {
                foreach (var e in kv.Value)
                {
                    var x = (double)e["X"]!;
                    var y = (double)e["Y"]!;
                    var z = (double)e["Z"]!;
                    var pitch = e["Pitch"]?.Value<double>() ?? 0;
                    var yaw   = e["Yaw"]?.Value<double>()   ?? 0;
                    var roll  = e["Roll"]?.Value<double>()  ?? 0;
                    var bp = (string)e["blueprint_path"]!;
                    InjectParkingActor(asset, bp, x, y, z, pitch, yaw, roll, $"ParkingLot_MOD_{idx++}");
                }

                // Convert our newly-added NormalExports to RawExports by pre-serializing them
                // with the current mappings/schema context. This locks in the bytes, and stops
                // UAssetAPI from re-serializing them during asset.Write (which is where subtle
                // schema-context issues could creep in and break engine load).
                ConvertTrailingNormalExportsToRaw(asset, countJustAdded: idx * 5);
            }
            else
            {
                Console.WriteLine("  --no-inject: round-trip only (no parking actor added)");
            }

            asset.Write(dstUmap);
            Console.WriteLine($"  Wrote {dstUmap}");
            // Copy ubulk if exists
            var srcUbulk = Path.Combine(gameContent, cellName + ".ubulk");
            if (File.Exists(srcUbulk))
                File.Copy(srcUbulk, Path.Combine(modContent, cellName + ".ubulk"), true);
        }

        return 0;
    }

    private static string DumpStruct(UAssetAPI.PropertyTypes.Structs.StructPropertyData sp)
    {
        if (sp.Value == null || sp.Value.Count == 0) return $" <Struct {sp.StructType?.Value} empty>";
        var inner = sp.Value[0];
        return inner switch
        {
            UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp => $" = Vec({vp.Value.X},{vp.Value.Y},{vp.Value.Z})",
            UAssetAPI.PropertyTypes.Structs.RotatorPropertyData rp => $" = Rot(P{rp.Value.Pitch},Y{rp.Value.Yaw},R{rp.Value.Roll})",
            _ => $" <Struct {sp.StructType?.Value} fields={sp.Value.Count}>"
        };
    }

    private static void DumpField(PropertyData field, string indent, int maxDepth = 10)
    {
        if (maxDepth <= 0) { Console.WriteLine($"{indent}{field.Name}: <depth-limited>"); return; }
        switch (field)
        {
            case ArrayPropertyData ap:
                Console.WriteLine($"{indent}{field.Name}: [Array {ap.ArrayType} count={ap.Value?.Length ?? 0}]");
                if (ap.Value != null && ap.Value.Length > 0)
                {
                    // Three was fine for eyeballing; it is useless for reading
                    // geometry back out. A zone's TopViewLines is 16 points and
                    // the first three tell you nothing about its shape.
                    int cap = ArrayDumpLimit;
                    for (int i = 0; i < Math.Min(ap.Value.Length, cap); i++)
                    {
                        Console.WriteLine($"{indent}  [{i}]:");
                        DumpField(ap.Value[i], indent + "    ", maxDepth - 1);
                    }
                    if (ap.Value.Length > cap) Console.WriteLine($"{indent}  ... {ap.Value.Length - cap} more");
                }
                break;
            case UAssetAPI.PropertyTypes.Structs.StructPropertyData sp:
                Console.WriteLine($"{indent}{field.Name}: Struct {sp.StructType?.Value} ({sp.Value?.Count ?? 0} fields)");
                if (sp.Value != null)
                    foreach (var sub in sp.Value) DumpField(sub, indent + "  ", maxDepth - 1);
                break;
            case UAssetAPI.PropertyTypes.Objects.NamePropertyData np:
                Console.WriteLine($"{indent}{field.Name}: \"{np.Value}\""); break;
            case UAssetAPI.PropertyTypes.Objects.IntPropertyData ip:
                Console.WriteLine($"{indent}{field.Name}: {ip.Value}"); break;
            case UAssetAPI.PropertyTypes.Objects.Int64PropertyData i64:
                Console.WriteLine($"{indent}{field.Name}: {i64.Value}"); break;
            case UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp:
                Console.WriteLine($"{indent}{field.Name}: {fp.Value}"); break;
            case UAssetAPI.PropertyTypes.Objects.DoublePropertyData dp:
                Console.WriteLine($"{indent}{field.Name}: {dp.Value}"); break;
            case UAssetAPI.PropertyTypes.Objects.BoolPropertyData bp:
                Console.WriteLine($"{indent}{field.Name}: {bp.Value}"); break;
            case UAssetAPI.PropertyTypes.Objects.ObjectPropertyData op:
                Console.WriteLine($"{indent}{field.Name}: -> {op.Value?.Index}"); break;
            case UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData sop:
                Console.WriteLine($"{indent}{field.Name}: <SoftObject>"); break;
            case UAssetAPI.PropertyTypes.Objects.TextPropertyData tp:
                Console.WriteLine($"{indent}{field.Name}: Text hist={tp.HistoryType} flags={tp.Flags} ns={tp.Namespace} val={tp.Value} table={tp.TableId} cinv={tp.CultureInvariantString}");
                break;
            case UAssetAPI.PropertyTypes.Objects.StrPropertyData sp:
                Console.WriteLine($"{indent}{field.Name}: \"{sp.Value}\""); break;
            case UAssetAPI.PropertyTypes.Objects.MapPropertyData mp:
                Console.WriteLine($"{indent}{field.Name}: Map key={mp.KeyType} value={mp.ValueType} entries={mp.Value?.Count ?? 0}");
                if (mp.Value != null)
                {
                    int shown = 0;
                    foreach (var kv in mp.Value)
                    {
                        if (shown++ >= 3) { Console.WriteLine($"{indent}  ..."); break; }
                        Console.WriteLine($"{indent}  key:");
                        DumpField(kv.Key, indent + "    ", maxDepth - 1);
                        Console.WriteLine($"{indent}  val:");
                        DumpField(kv.Value, indent + "    ", maxDepth - 1);
                    }
                }
                break;
            case UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp:
                Console.WriteLine($"{indent}{field.Name}: ({vp.Value.X}, {vp.Value.Y}, {vp.Value.Z})"); break;
            default:
                Console.WriteLine($"{indent}{field.Name}: ({field.GetType().Name})"); break;
        }
    }

    // ----------------------------------------------------------------------
    // REGISTER-NEW-CELL: clone the 3 WP registration exports for a template
    // vanilla cell (cell, CellDataSpatialHash, WorldPartitionLevelStreaming)
    // with a new cell name + new Position/Extent, and append to the MainGrid
    // StreamingGrids[0].GridLevels[0]. Also copies the template's content
    // .umap file under _Generated_/<new-name>.umap so WP has something to
    // stream.
    // ----------------------------------------------------------------------
    private static int RegisterNewCell(string[] args)
    {
        var f = ParseFlags(args);
        string mainPath = f["main"];
        string outPath  = f["output"];
        var mappings = LoadMappings(f["mappings"]);
        var asset = new UAsset(mainPath, EngineVer, mappings);
        RegisterOneCell(asset, f);
        asset.Write(outPath);
        Console.WriteLine($"  Wrote {outPath}");
        return 0;
    }

    // Register N cells in a SINGLE Jeju_World load/save. Spec JSON is an array
    // of objects, each with the same keys as register-new-cell flags
    // (template-cell, new-cell-name, x, y, extent, grid, hier-level,
    // grid-levels-index, cells-dir, mod-cells-dir).
    private static int RegisterCellsBatch(string[] args)
    {
        var f = ParseFlags(args);
        string mainPath = f["main"];
        string outPath  = f["output"];
        string specPath = f["spec"];
        var mappings = LoadMappings(f["mappings"]);
        var asset = new UAsset(mainPath, EngineVer, mappings);
        var spec = Newtonsoft.Json.Linq.JArray.Parse(File.ReadAllText(specPath));
        int n = 0;
        foreach (var entry in spec)
        {
            var flags = new Dictionary<string, string>();
            foreach (var prop in ((Newtonsoft.Json.Linq.JObject)entry).Properties())
                flags[prop.Name] = prop.Value.ToString();
            RegisterOneCell(asset, flags);
            n++;
        }
        asset.Write(outPath);
        Console.WriteLine($"  Wrote {outPath} ({n} cells registered)");
        return 0;
    }

    // Body of register-new-cell, reusable against an already-loaded asset so
    // a batch command can register N cells in one save.
    private static void RegisterOneCell(UAsset asset, Dictionary<string, string> f)
    {
        string tplCell  = f["template-cell"];       // e.g. 0W5HFJERQNYIKT4TIFEZBU4PD
        string newCell  = f["new-cell-name"];       // e.g. MODCELLISLAND000000000000
        double tx = double.Parse(f["x"], System.Globalization.CultureInfo.InvariantCulture);
        double ty = double.Parse(f["y"], System.Globalization.CultureInfo.InvariantCulture);
        float extent = float.Parse(f.TryGetValue("extent", out var ex) ? ex : "6400", System.Globalization.CultureInfo.InvariantCulture);
        string gridName = f.TryGetValue("grid", out var gn) ? gn : "MainGrid";
        int hierLevel = int.Parse(f.TryGetValue("hier-level", out var hl) ? hl : "-1");
        int gridLevelsIndex = int.Parse(f.TryGetValue("grid-levels-index", out var gli) ? gli : "0");
        string cellsDir = f["cells-dir"]; // vanilla cells source, e.g. D:\MT\...\_Generated_
        string modCellsDir = f["mod-cells-dir"]; // output _Generated_ dir in mod

        // Find the 3 template exports by name
        int tplCellIdx = -1, tplLevelStreamIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var nm = asset.Exports[i].ObjectName.ToString();
            if (nm == tplCell) tplCellIdx = i;
            else if (nm == "WorldPartitionLevelStreaming_" + tplCell) tplLevelStreamIdx = i;
        }
        if (tplCellIdx < 0 || tplLevelStreamIdx < 0)
            throw new InvalidOperationException($"Template cell '{tplCell}' registration exports not found in main map");
        var tplCellExp = (NormalExport)asset.Exports[tplCellIdx];
        var tplLsExp = (NormalExport)asset.Exports[tplLevelStreamIdx];
        int tplRuntimeCellDataIdx = tplCellExp.Data.OfType<UAssetAPI.PropertyTypes.Objects.ObjectPropertyData>()
            .First(p => p.Name.ToString() == "RuntimeCellData").Value.Index - 1;
        var tplRcdExp = (NormalExport)asset.Exports[tplRuntimeCellDataIdx];

        Console.WriteLine($"Template: cell#{tplCellIdx+1} rcd#{tplRuntimeCellDataIdx+1} levelstream#{tplLevelStreamIdx+1}");

        // Pre-compute new export indices
        int newCellIdx      = asset.Exports.Count;     // 0-based
        int newRcdIdx       = asset.Exports.Count + 1;
        int newLsIdx        = asset.Exports.Count + 2;
        int newCellNum      = newCellIdx + 1;
        int newRcdNum       = newRcdIdx + 1;
        int newLsNum        = newLsIdx + 1;

        // Helper to deep-clone a NormalExport in place in the same asset.
        NormalExport Clone(NormalExport src, string newName)
        {
            EnsureName(asset, newName);
            var dst = new NormalExport
            {
                Asset = asset,
                Data = src.Data.Select(p => (PropertyData)p.Clone()).ToList(),
                ObjectGuid = src.ObjectGuid,
                SerializationControl = src.SerializationControl,
                Operation = src.Operation,
                HasLeadingFourNullBytes = src.HasLeadingFourNullBytes,
                ObjectName = FName.FromString(asset, newName),
                ClassIndex = new FPackageIndex(src.ClassIndex.Index),
                SuperIndex = new FPackageIndex(src.SuperIndex.Index),
                TemplateIndex = new FPackageIndex(src.TemplateIndex.Index),
                OuterIndex = new FPackageIndex(src.OuterIndex.Index),
                ObjectFlags = src.ObjectFlags,
                bForcedExport = src.bForcedExport,
                bNotForClient = src.bNotForClient,
                bNotForServer = src.bNotForServer,
                PackageGuid = src.PackageGuid,
                PackageFlags = src.PackageFlags,
                bNotAlwaysLoadedForEditorGame = src.bNotAlwaysLoadedForEditorGame,
                bIsAsset = src.bIsAsset,
                GeneratePublicHash = src.GeneratePublicHash,
                IsInheritedInstance = src.IsInheritedInstance,
                SerializationBeforeSerializationDependencies = new List<FPackageIndex>(src.SerializationBeforeSerializationDependencies),
                CreateBeforeSerializationDependencies = new List<FPackageIndex>(src.CreateBeforeSerializationDependencies),
                SerializationBeforeCreateDependencies = new List<FPackageIndex>(src.SerializationBeforeCreateDependencies),
                CreateBeforeCreateDependencies = new List<FPackageIndex>(src.CreateBeforeCreateDependencies),
                Extras = src.Extras != null ? (byte[])src.Extras.Clone() : null,
            };
            return dst;
        }

        // Clone the 3 exports
        var newCellExp = Clone(tplCellExp, newCell);
        var newRcdExp  = Clone(tplRcdExp, tplRcdExp.ObjectName.ToString()); // keep generic name for CellData
        var newLsExp   = Clone(tplLsExp,  "WorldPartitionLevelStreaming_" + newCell);

        // Fix cross-refs: cell.LevelStreaming -> newLs, cell.RuntimeCellData -> newRcd
        foreach (var p in newCellExp.Data)
        {
            if (p is UAssetAPI.PropertyTypes.Objects.ObjectPropertyData op && op.Value != null)
            {
                if (p.Name.ToString() == "LevelStreaming") op.Value = new FPackageIndex(newLsNum);
                if (p.Name.ToString() == "RuntimeCellData") op.Value = new FPackageIndex(newRcdNum);
            }
            // Regenerate CellGuid if present
            if (p is UAssetAPI.PropertyTypes.Structs.StructPropertyData sp && p.Name.ToString() == "CellGuid"
                && sp.Value.Count > 0 && sp.Value[0] is UAssetAPI.PropertyTypes.Structs.GuidPropertyData gp)
                gp.Value = Guid.NewGuid();
        }

        // Fix newLs: StreamingCell (weak) -> newCell, PackageNameToLoad to new path
        foreach (var p in newLsExp.Data)
        {
            if (p is UAssetAPI.PropertyTypes.Objects.WeakObjectPropertyData wop && p.Name.ToString() == "StreamingCell")
                wop.Value = new FPackageIndex(newCellNum);
            if (p is UAssetAPI.PropertyTypes.Objects.NamePropertyData np && p.Name.ToString() == "PackageNameToLoad")
            {
                string pkgName = $"/Game/Maps/Jeju/Jeju_World/_Generated_/{newCell}";
                EnsureName(asset, pkgName);
                np.Value = FName.FromString(asset, pkgName);
            }
            if (p is UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData sopd && p.Name.ToString() == "WorldAsset")
            {
                // Rewrite only the PackageName field of the existing soft path;
                // leave the rest (sub-path + asset name) alone so its internal
                // shape matches what UE expects for a WP cell WorldAsset ref.
                string newPkg = $"/Game/Maps/Jeju/Jeju_World/_Generated_/{newCell}";
                EnsureName(asset, newPkg);
                if (sopd.Value != null)
                {
                    var old = sopd.Value;
                    sopd.Value = new UAssetAPI.PropertyTypes.Objects.FSoftObjectPath(
                        FName.FromString(asset, newPkg),
                        old.AssetPath.AssetName,
                        old.SubPathString);
                }
            }
        }

        // Fix RCD: Position + Extent + ContentBounds + GridName + HierarchicalLevel.
        // Cell center aligned to grid (cell width = extent*2).
        double cellWidthR = extent * 2;
        double ccx = Math.Floor(tx / cellWidthR) * cellWidthR + extent;
        double ccy = Math.Floor(ty / cellWidthR) * cellWidthR + extent;
        foreach (var p in newRcdExp.Data)
        {
            if (p is UAssetAPI.PropertyTypes.Structs.StructPropertyData sp && p.Name.ToString() == "Position"
                && sp.Value.Count > 0 && sp.Value[0] is UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp)
            {
                vp.Value = new FVector(ccx, ccy, 0);
                Console.WriteLine($"  New cell Position=({ccx},{ccy},0) Extent={extent}");
            }
            if (p is UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp && p.Name.ToString() == "Extent") fp.Value = extent;
            // ContentBounds — WP uses this for the cell's streaming/cull bounds.
            // Left at the template's (origin) value, WP won't stream the cell at
            // the new location. Defaults to the cell's own grid region; callers
            // whose content reaches FURTHER than the cell (a foliage IFA spans a
            // 25600 tile while sitting on the 12800 lattice) pass the real AABB
            // via cb-*, otherwise the overhang gets culled at cell edges.
            if (p is UAssetAPI.PropertyTypes.Structs.StructPropertyData spc && p.Name.ToString() == "ContentBounds"
                && spc.Value.Count > 0 && spc.Value[0] is UAssetAPI.PropertyTypes.Structs.BoxPropertyData bpd)
            {
                double bx0 = ccx - extent, by0 = ccy - extent, bz0 = -100000;
                double bx1 = ccx + extent, by1 = ccy + extent, bz1 = 100000;
                if (f.TryGetValue("cb-min-x", out var cbx0))
                {
                    var ic = System.Globalization.CultureInfo.InvariantCulture;
                    bx0 = double.Parse(cbx0, ic);          by0 = double.Parse(f["cb-min-y"], ic);
                    bx1 = double.Parse(f["cb-max-x"], ic); by1 = double.Parse(f["cb-max-y"], ic);
                }
                bpd.Value = new UAssetAPI.UnrealTypes.TBox<FVector>(
                    new FVector(bx0, by0, bz0), new FVector(bx1, by1, bz1), 1);
                Console.WriteLine($"  New cell ContentBounds=({bx0}..{bx1}, {by0}..{by1})");
            }
            if (p is UAssetAPI.PropertyTypes.Objects.NamePropertyData np && p.Name.ToString() == "GridName")
            {
                EnsureName(asset, gridName);
                np.Value = FName.FromString(asset, gridName);
            }
            if (p is UAssetAPI.PropertyTypes.Objects.IntPropertyData ip && p.Name.ToString() == "HierarchicalLevel")
                ip.Value = hierLevel;
        }

        // Also patch RCD Extras: vanilla had "<Jeju_World_MainGrid_L-1_X_Y>\0" ish string+null.
        // Easiest: derive a fresh label and write count(=len+1)+string+null.
        double cellWidth2 = extent * 2;
        int gridX = (int)Math.Floor(tx / cellWidth2);
        int gridY = (int)Math.Floor(ty / cellWidth2);
        string rcdName = $"Jeju_World_{gridName}_L{hierLevel}_X{gridX}_Y{gridY}";
        newRcdExp.Extras = MakeCStringExtras(rcdName);

        // Cell's own Extras: similar "cell name" string
        newCellExp.Extras = tplCellExp.Extras != null ? (byte[])tplCellExp.Extras.Clone() : null;
        // LevelStreaming has no Extras normally

        // Fix OuterIndex of RCD to point at the new cell (was tplCellNum)
        newRcdExp.OuterIndex = new FPackageIndex(newCellNum);

        asset.Exports.Add(newCellExp);
        asset.Exports.Add(newRcdExp);
        asset.Exports.Add(newLsExp);

        // Append to StreamingGrids[0].GridLevels[gridLevelsIndex].LayerCells
        // + mapping entry key = (gridX + 524800) + gridY * 1024
        int hashIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var cls = asset.Exports[i].ClassIndex.IsImport() ? asset.Exports[i].ClassIndex.ToImport(asset).ObjectName.ToString() : "";
            if (cls == "WorldPartitionRuntimeSpatialHash") { hashIdx = i; break; }
        }
        if (hashIdx < 0) throw new InvalidOperationException("No RuntimeSpatialHash export");
        var hash = (NormalExport)asset.Exports[hashIdx];
        // Mark new cell export as dep of hash (CBSD chain)
        hash.CreateBeforeSerializationDependencies.Add(new FPackageIndex(newCellNum));

        var grids = hash.Data.OfType<ArrayPropertyData>().First(a => a.Name.ToString() == "StreamingGrids");
        int gridEntryIdx = -1;
        for (int i = 0; i < grids.Value.Length; i++)
        {
            var s = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)grids.Value[i];
            var gn2 = (UAssetAPI.PropertyTypes.Objects.NamePropertyData)s.Value.First(p => p.Name.ToString() == "GridName");
            if (gn2.Value.ToString() == gridName) { gridEntryIdx = i; break; }
        }
        if (gridEntryIdx < 0) throw new InvalidOperationException($"No grid '{gridName}'");
        var sgrid = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)grids.Value[gridEntryIdx];
        var gridLevels = (ArrayPropertyData)sgrid.Value.First(p => p.Name.ToString() == "GridLevels");
        var level0 = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)gridLevels.Value[gridLevelsIndex];
        var layerCells = (ArrayPropertyData)level0.Value.First(p => p.Name.ToString() == "LayerCells");
        var mapping = (UAssetAPI.PropertyTypes.Objects.MapPropertyData)level0.Value.First(p => p.Name.ToString() == "LayerCellsMapping");

        // Build a new LayerCell struct with GridCells array containing our new cell ref
        var tplLayerCell = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)layerCells.Value[0];
        var newLayerCell = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)tplLayerCell.Clone();
        var newGridCells = (ArrayPropertyData)newLayerCell.Value.First(p => p.Name.ToString() == "GridCells");
        // Replace value with one ObjectProperty -> newCellNum
        var tplObj = (UAssetAPI.PropertyTypes.Objects.ObjectPropertyData)newGridCells.Value[0];
        var newObj = (UAssetAPI.PropertyTypes.Objects.ObjectPropertyData)tplObj.Clone();
        newObj.Value = new FPackageIndex(newCellNum);
        newGridCells.Value = new PropertyData[] { newObj };

        var newLayerCellsArr = new PropertyData[layerCells.Value.Length + 1];
        Array.Copy(layerCells.Value, newLayerCellsArr, layerCells.Value.Length);
        int newLayerCellIdxInArr = layerCells.Value.Length;
        newLayerCellsArr[newLayerCellIdxInArr] = newLayerCell;
        layerCells.Value = newLayerCellsArr;

        // LayerCellsMapping: key = (gridX + 524800) + gridY * 1024; value = new LayerCells index
        long key = (gridX + 524800L) + (long)gridY * 1024L;
        var keyProp = new UAssetAPI.PropertyTypes.Objects.Int64PropertyData(FName.FromString(asset, "LayerCellsMapping")) { Value = key };
        var valProp = new UAssetAPI.PropertyTypes.Objects.IntPropertyData(FName.FromString(asset, "LayerCellsMapping")) { Value = newLayerCellIdxInArr };
        mapping.Value.Add(keyProp, valProp);
        Console.WriteLine($"  Registered cell in Grid '{gridName}' level[{gridLevelsIndex}] at grid=({gridX},{gridY}) key=0x{key:X16} layerIdx={newLayerCellIdxInArr}");

        // Also copy template cell content .umap + .uexp to new name in mod dir,
        // then rewrite its internal FolderName so UE's package identity matches
        // the new filename (otherwise streaming crashes with EXCEPTION_ACCESS_VIOLATION).
        string srcBase = Path.Combine(cellsDir, tplCell);
        string dstBase = Path.Combine(modCellsDir, newCell);
        Directory.CreateDirectory(modCellsDir);
        if (File.Exists(srcBase + ".umap")) File.Copy(srcBase + ".umap", dstBase + ".umap", true);
        if (File.Exists(srcBase + ".uexp")) File.Copy(srcBase + ".uexp", dstBase + ".uexp", true);
        // Raw byte-replace the template cell name with the new cell name in
        // both .umap and .uexp. Both names are 25 chars (our make_cell_name
        // produces 25-char base32-ish IDs), so the file layout is preserved
        // without UAssetAPI re-serialization (which corrupts offsets).
        if (newCell.Length != tplCell.Length)
            throw new InvalidOperationException(
                $"Cell name length mismatch: tpl '{tplCell}' ({tplCell.Length}) vs new '{newCell}' ({newCell.Length}). " +
                "Byte-replace requires equal length.");
        foreach (var ext in new[] { ".umap", ".uexp" })
        {
            var path = dstBase + ext;
            if (!File.Exists(path)) continue;
            var bytes = File.ReadAllBytes(path);
            var needle = System.Text.Encoding.ASCII.GetBytes(tplCell);
            var replace = System.Text.Encoding.ASCII.GetBytes(newCell);
            int hits = 0;
            for (int i = 0; i <= bytes.Length - needle.Length; i++)
            {
                bool ok = true;
                for (int j = 0; j < needle.Length; j++) if (bytes[i + j] != needle[j]) { ok = false; break; }
                if (ok) { Array.Copy(replace, 0, bytes, i, replace.Length); hits++; i += needle.Length - 1; }
            }
            File.WriteAllBytes(path, bytes);
            Console.WriteLine($"  {Path.GetFileName(path)}: replaced {hits} occurrence(s) of template name");
        }
    }

    // Stamp a scene component's transform. Location/rotation/scale are each
    // a struct wrapping one typed property, which is how UE serialises them
    // and what the mappings expect. Scale matters for fog volumes: the
    // component's scale IS the volume's radius.
    private static void AddTransform(UAsset asset, NormalExport comp,
                                     double x, double y, double z,
                                     double pitch, double yaw, double roll,
                                     double sx, double sy, double sz)
    {
        EnsureName(asset, "RelativeLocation");
        EnsureName(asset, "RelativeRotation");
        EnsureName(asset, "RelativeScale3D");
        EnsureName(asset, "Vector");
        EnsureName(asset, "Rotator");
        comp.Data.Add(new StructPropertyData(FName.FromString(asset, "RelativeLocation"),
                                             FName.FromString(asset, "Vector"))
        {
            Value = new List<PropertyData> {
                new VectorPropertyData(FName.FromString(asset, "RelativeLocation"))
                    { Value = new FVector(x, y, z) } }
        });
        if (pitch != 0 || yaw != 0 || roll != 0)
            comp.Data.Add(new StructPropertyData(FName.FromString(asset, "RelativeRotation"),
                                                 FName.FromString(asset, "Rotator"))
            {
                Value = new List<PropertyData> {
                    new RotatorPropertyData(FName.FromString(asset, "RelativeRotation"))
                        { Value = new FRotator(pitch, yaw, roll) } }
            });
        if (sx != 1 || sy != 1 || sz != 1)
            comp.Data.Add(new StructPropertyData(FName.FromString(asset, "RelativeScale3D"),
                                                 FName.FromString(asset, "Vector"))
            {
                Value = new List<PropertyData> {
                    new VectorPropertyData(FName.FromString(asset, "RelativeScale3D"))
                        { Value = new FVector(sx, sy, sz) } }
            });
    }

    // Set one scalar property on the first export of a given class. Written
    // for switching volumetric fog on at Jeju's ExponentialHeightFog, which
    // is a vanilla actor we do not clone -- we just need one bool flipped on
    // a component that already exists.
    //
    // Unversioned serialization only writes NON-default values, so a property
    // sitting at its default is simply absent from the export: the property
    // is added when missing rather than assumed present.
    //
    //   --cell <umap> --output <umap> --mappings <usmap>
    //   --class <ComponentClass> --prop <Name> --bool 1 | --float 1.5 | --int 3
    private static int SetExportProp(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        string cls = f["class"], prop = f["prop"];
        int changed = 0;
        foreach (var ex in asset.Exports)
        {
            if (ex.GetExportClassType()?.Value?.Value != cls) continue;
            if (ex is not NormalExport ne) continue;
            EnsureName(asset, prop);
            PropertyData? existing = null;
            foreach (var p in ne.Data)
                if (p.Name.ToString() == prop) { existing = p; break; }

            if (f.TryGetValue("bool", out var bv))
            {
                bool val = bv == "1" || bv.Equals("true", StringComparison.OrdinalIgnoreCase);
                if (existing is BoolPropertyData bp) bp.Value = val;
                else ne.Data.Add(new BoolPropertyData(FName.FromString(asset, prop)) { Value = val });
            }
            else if (f.TryGetValue("float", out var fv))
            {
                float val = float.Parse(fv);
                if (existing is FloatPropertyData fp) fp.Value = val;
                else ne.Data.Add(new FloatPropertyData(FName.FromString(asset, prop)) { Value = val });
            }
            else if (f.TryGetValue("int", out var iv))
            {
                int val = int.Parse(iv);
                if (existing is IntPropertyData ip) ip.Value = val;
                else ne.Data.Add(new IntPropertyData(FName.FromString(asset, prop)) { Value = val });
            }
            else { Console.Error.WriteLine("  need one of --bool/--float/--int"); return 1; }

            Console.WriteLine($"  {ex.ObjectName}.{prop} set "
                              + (existing == null ? "(property was absent — added)" : "(overwrote existing)"));
            changed++;
        }
        if (changed == 0) { Console.Error.WriteLine($"  no export of class '{cls}' found"); return 1; }
        asset.Write(f.GetValueOrDefault("output", f["cell"]));
        return 0;
    }

    // A StaticMesh's ExtendedBounds, which is where its pivot sits relative to
    // its geometry. A placeholder whose bounds origin is high above the pivot
    // places its actor that far below where the mesh appears to sit -- the
    // reason identically-placed delivery points land at different heights.
    //   --list <file of .uasset paths> --mappings <usmap>
    // Prints "<path>	<originZ>	<extentZ>".
    private static int DumpMeshBounds(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        foreach (var line in File.ReadAllLines(f["list"]))
        {
            var path = line.Trim();
            if (path.Length == 0) continue;
            double oz = 0, ez = 0;
            try
            {
                var asset = new UAsset(path, EngineVer, mappings);
                foreach (var ex in asset.Exports)
                {
                    if (ex is not NormalExport ne) continue;
                    foreach (var p in ne.Data)
                    {
                        if (p.Name.ToString() != "ExtendedBounds" || p is not StructPropertyData sp) continue;
                        foreach (var sub in sp.Value ?? new List<PropertyData>())
                        {
                            var n = sub.Name.ToString();
                            if (sub is StructPropertyData inner)
                                foreach (var v in inner.Value ?? new List<PropertyData>())
                                    if (v is VectorPropertyData vp)
                                    {
                                        if (n == "Origin") oz = vp.Value.Z;
                                        if (n == "BoxExtent") ez = vp.Value.Z;
                                    }
                            if (sub is VectorPropertyData dvp)
                            {
                                if (n == "Origin") oz = dvp.Value.Z;
                                if (n == "BoxExtent") ez = dvp.Value.Z;
                            }
                        }
                    }
                }
            }
            catch (Exception ex) { Console.Error.WriteLine($"  {path}: {ex.Message}"); }
            Console.WriteLine($"{path}	{oz}	{ez}");
        }
        return 0;
    }

    // What properties does a class have, according to the mappings? The
    // .usmap knows every class in the shipped build, including engine
    // classes with no asset anywhere, which is the only way to find out
    // what you can set on something like LocalFogVolumeComponent.

    // Print an enum's members from the .usmap.
    //
    // Cooked assets store enum values as byte indices and the member names
    // live only in the mappings, so "what can this field be set to" is not
    // answerable from an asset at all. dump-schema covers classes and structs
    // and says "no schema matching" for an enum, which reads like the enum
    // does not exist rather than like the wrong tool was used.

    // What an array actually CONTAINS, not just how many. "count=1" is the
    // answer to a question nobody asked -- reading an asset, the thing you
    // need is which enum members are in the set, or which actor the
    // ObjectProperty points at.
    private static string DescribeArray(UAssetAPI.PropertyTypes.Objects.ArrayPropertyData ap)
    {
        var v = ap.Value;
        string head = $" [Array {ap.ArrayType} count={v?.Length ?? 0}]";
        if (v == null || v.Length == 0 || v.Length > 8) return head;

        if (v.All(x => x is UAssetAPI.PropertyTypes.Objects.EnumPropertyData
                    || x is UAssetAPI.PropertyTypes.Objects.NamePropertyData))
            return head + " = " + string.Join(", ", v.Select(x =>
                x is UAssetAPI.PropertyTypes.Objects.EnumPropertyData e
                    ? e.Value.ToString()
                    : ((UAssetAPI.PropertyTypes.Objects.NamePropertyData)x).Value.ToString()));

        if (v.All(x => x is UAssetAPI.PropertyTypes.Objects.ObjectPropertyData))
            return head + " -> " + string.Join(", ", v.Select(x =>
                ((UAssetAPI.PropertyTypes.Objects.ObjectPropertyData)x).Value.Index));

        if (v.All(x => x is UAssetAPI.PropertyTypes.Structs.StructPropertyData))
            return head + " = {" + string.Join(" | ",
                v.Cast<UAssetAPI.PropertyTypes.Structs.StructPropertyData>().Select(sp =>
                    string.Join(",", (sp.Value ?? new System.Collections.Generic.List<PropertyData>())
                        .Select(q => q is UAssetAPI.PropertyTypes.Objects.EnumPropertyData qe ? qe.Value.ToString()
                                   : q is UAssetAPI.PropertyTypes.Objects.NamePropertyData qn ? qn.Value.ToString()
                                   : q.Name.ToString())))) + "}";
        return head;
    }


    // The package's name table, in order. RawExports keep the SOURCE map's
    // name INDICES in their byte-copied bodies, so if a rewrite reorders this
    // table every byte-copied actor starts reading different names -- which is
    // invisible until something like a string-table lookup resolves to the
    // wrong FName and the UI shows a missing entry.
    private static int DumpNames(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        var map = asset.GetNameMapIndexList();
        Console.WriteLine($"# {map.Count} names");
        for (int i = 0; i < map.Count; i++)
            Console.WriteLine($"{i}	{map[i]}");
        return 0;
    }

    private static int DumpEnum(string[] args)
    {
        var f = ParseFlags(args);
        var maps = LoadMappings(f["mappings"]);

        void Print(string name)
        {
            Console.WriteLine($"== {name} ==");
            foreach (var v in maps.EnumMap[name].Values.OrderBy(v => v.Key))
                Console.WriteLine($"   {v.Key,3} = {v.Value}");
        }

        // --member finds the enum that CONTAINS a value. That is the common
        // direction when reading an asset: it shows "Tanker_FuelPump" and
        // never names the type the value belongs to.
        if (f.TryGetValue("member", out var mem))
        {
            foreach (var kv in maps.EnumMap)
                if (kv.Value.Values.Any(v => string.Equals(v.Value, mem, StringComparison.OrdinalIgnoreCase)))
                { Print(kv.Key); return 0; }
            Console.Error.WriteLine($"  no enum contains a member named '{mem}'");
            return 1;
        }

        string want = f["enum"];
        var hit = maps.EnumMap.Keys.FirstOrDefault(k => k == want)
               ?? maps.EnumMap.Keys.FirstOrDefault(k => k.EndsWith("." + want, StringComparison.Ordinal))
               ?? maps.EnumMap.Keys.FirstOrDefault(k => k.Contains(want, StringComparison.OrdinalIgnoreCase));
        if (hit == null)
        {
            Console.Error.WriteLine($"  no enum matching '{want}'");
            return 1;
        }
        Print(hit);
        return 0;
    }


    //   --mappings <usmap> --class <Name> [--all]
    private static int DumpSchema(string[] args)
    {
        var f = ParseFlags(args);
        var maps = LoadMappings(f["mappings"]);
        string want = f.GetValueOrDefault("class", "");
        int shown = 0;
        foreach (var kv in maps.Schemas)
        {
            if (!string.IsNullOrEmpty(want)
                && !kv.Key.Contains(want, StringComparison.OrdinalIgnoreCase)) continue;
            var s = kv.Value;
            Console.WriteLine($"== {kv.Key} (super={s.SuperType}, {s.PropCount} props) ==");
            foreach (var p in s.Properties)
                Console.WriteLine($"   [{p.Value.SchemaIndex}] {p.Value.Name} : {p.Value.PropertyData?.Type}");
            shown++;
            if (shown >= 6 && !f.ContainsKey("all")) break;
        }
        if (shown == 0) Console.Error.WriteLine($"  no schema matching '{want}'");
        return 0;
    }

    // Un-hide every vehicle in a Vehicles* DataTable and drop the role and
    // part restrictions, so a player can buy and fit anything the game
    // actually ships. Port of DoubleEconomy/VehicleBulk/run.py, with the
    // same rules:
    //   bHidden / bDisabled  -> false        (deprecated stock becomes stock)
    //   was hidden           -> bIsRaceCar   (marks what used to be locked)
    //   taxi / limo / bus    -> true         (no role gating)
    //   Not*PartTypes        -> emptied      (fit any part)
    //   CompanyAIConditionUsageMultiplier[Offroad] -> tunable
    // Police vehicles are deliberately LEFT ALONE: they stay unbuyable, and
    // the map hands them out through spawn points instead.
    //
    //   --uasset <in> --output <out> --mappings <usmap>
    //   [--ai-mult 0.25] [--ai-mult-offroad 0.4] [--include-police]
    private static int UnlockVehicles(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        float aiMult = float.Parse(f.GetValueOrDefault("ai-mult", "0.25"));
        float aiOff = float.Parse(f.GetValueOrDefault("ai-mult-offroad", "0.4"));
        bool inclPolice = f.ContainsKey("include-police");

        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport"); return 1; }

        int unlocked = 0, touched = 0, police = 0;
        foreach (var row in table.Table.Data)
        {
            // Police detection: the gameplay tag is authoritative, the name
            // is the fallback for rows whose container we cannot read.
            bool isPolice = row.Name.ToString()
                .Contains("Police", StringComparison.OrdinalIgnoreCase);
            foreach (var p in row.Value)
            {
                if (p.Name.ToString() != "GameplayTags" || p is not StructPropertyData sp) continue;
                foreach (var sub in sp.Value ?? new List<PropertyData>())
                    if ((sub.RawValue?.ToString() ?? "").Contains("Police",
                            StringComparison.OrdinalIgnoreCase)) isPolice = true;
            }
            if (isPolice && !inclPolice) { police++; continue; }

            bool wasLocked = false;
            foreach (var p in row.Value)
            {
                var n = p.Name.ToString();
                if ((n == "bHidden" || n == "bDisabled") && p is BoolPropertyData b && b.Value)
                    wasLocked = true;
            }
            foreach (var p in row.Value)
            {
                switch (p.Name.ToString())
                {
                    case "bHidden":
                    case "bDisabled":
                        if (p is BoolPropertyData off) off.Value = false;
                        break;
                    case "bIsTaxiable":
                    case "bIsLimoable":
                    case "bIsBusable":
                        if (p is BoolPropertyData on) on.Value = true;
                        break;
                    case "bIsRaceCar":
                        if (wasLocked && p is BoolPropertyData rc) rc.Value = true;
                        break;
                    case "NotSupportedPartTypes":
                    case "NotOptionalPartTypes":
                    case "NotOptionalPartSlots":
                        if (p is ArrayPropertyData ap) ap.Value = Array.Empty<PropertyData>();
                        break;
                    case "CompanyAIConditionUsageMultiplier":
                        if (p is FloatPropertyData f1) f1.Value = aiMult;
                        break;
                    case "CompanyAIConditionUsageMultiplierOffroad":
                        if (p is FloatPropertyData f2) f2.Value = aiOff;
                        break;
                }
            }
            touched++;
            if (wasLocked) { unlocked++; Console.WriteLine($"    unlocked {row.Name}"); }
        }
        asset.Write(f["output"]);
        Console.WriteLine($"  {Path.GetFileName(f["uasset"])}: {touched} row(s) opened up, "
                          + $"{unlocked} previously locked, {police} police left alone");
        return 0;
    }

    // Row names plus chosen scalar fields from any DataTable. Generic
    // counterpart to dump-cargo-row: that one dumps a single row in full,
    // this walks the whole table so you can diff it against something else.
    //   --uasset <X.uasset> --mappings <usmap> [--fields A,B,C]
    // Prints "<row>\t<A>\t<B>..." — soft-object fields print their path.

    // Shared deep clone for property trees. The original lived as a local
    // function inside mutate-cargos; row cloning needs the same thing.
    private static PropertyData DeepCloneProp(PropertyData p)
    {
        var c = (PropertyData)p.Clone();
        if (c is StructPropertyData scp && scp.Value != null)
            scp.Value = scp.Value.Select(DeepCloneProp).ToList();
        else if (c is ArrayPropertyData acp && acp.Value != null)
            acp.Value = acp.Value.Select(DeepCloneProp).ToArray();
        else if (c is MapPropertyData mcp && mcp.Value != null)
        {
            var newMap = new UAssetAPI.UnrealTypes.TMap<PropertyData, PropertyData>();
            foreach (var kv in mcp.Value)
                newMap.Add(DeepCloneProp(kv.Key), DeepCloneProp(kv.Value));
            mcp.Value = newMap;
        }
        return c;
    }

    // Clone one vehicle DataTable row into a new row, applying field overrides
    // and repointing VehicleClass at a mod-shipped class. The row NAME is
    // free-form -- unlike a BP class name, which byte-rename forces to the
    // source's length -- so Spawn_<new_id> can be spelled however you like.
    private static int CloneVehicleRow(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        string baseRow = f["base"], newRow = f["new-id"];
        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport"); return 1; }

        StructPropertyData? src = null;
        foreach (var row in table.Table.Data)
            if (row.Name.ToString() == baseRow) { src = row; break; }
        if (src == null) { Console.Error.WriteLine($"  base row '{baseRow}' not found"); return 1; }
        // REPLACE, never skip. The mod's own table is the input on any build
        // after the first, so skipping an existing row means every later edit
        // to vehicles.json is silently ignored -- a display name or a changed
        // Cost would never reach the game and the build would look fine.
        int existing = -1;
        for (int i = 0; i < table.Table.Data.Count; i++)
            if (table.Table.Data[i].Name.ToString() == newRow) { existing = i; break; }

        var clone = (StructPropertyData)DeepCloneProp(src);
        EnsureName(asset, newRow);
        clone.Name = FName.FromString(asset, newRow);

        // Repoint the class. Without this the new row drives the SAME actor as
        // the base and every modification to the cloned class is invisible.
        if (f.TryGetValue("class-path", out var clsPath) && !string.IsNullOrWhiteSpace(clsPath))
        {
            EnsureName(asset, clsPath);
            foreach (var pd in clone.Value)
                if (pd.Name.ToString() == "VehicleClass" && pd is SoftObjectPropertyData sop)
                {
                    sop.Value = new FSoftObjectPath(
                        new FTopLevelAssetPath(FName.FromString(asset, clsPath),
                                               FName.FromString(asset, clsPath[(clsPath.LastIndexOf('/') + 1)..] + "_C")),
                        new FString(""));
                    Console.WriteLine($"  VehicleClass -> {clsPath}");
                }
        }

        // Display name. VehicleName is a TextProperty pointing into a
        // StringTable ("Vista_VehicleName"), so a cloned row shows the BASE
        // car's name in the dealership. Rewriting it as CultureInvariant
        // inline text bypasses the table lookup entirely -- the same trick the
        // delivery point labels use on PointName. VehicleName2 is the
        // MTTextByTexts variant the newer UI reads; set both or the two
        // screens disagree.
        if (f.TryGetValue("display-name", out var disp) && !string.IsNullOrWhiteSpace(disp))
        {
            TextPropertyData InlineText(FName n) => new TextPropertyData(n)
            {
                HistoryType = TextHistoryType.None,
                CultureInvariantString = new FString(disp),
                Flags = ETextFlag.CultureInvariant,
            };
            EnsureName(asset, "VehicleName");
            EnsureName(asset, "Texts");
            EnsureName(asset, "TextProperty");
            bool named = false;
            for (int i = 0; i < clone.Value.Count; i++)
            {
                var pd = clone.Value[i];
                if (pd.Name.ToString() == "VehicleName")
                {
                    clone.Value[i] = InlineText(FName.FromString(asset, "VehicleName"));
                    named = true;
                }
                else if (pd.Name.ToString() == "VehicleName2" && pd is StructPropertyData vn2)
                {
                    foreach (var inner in vn2.Value ?? new List<PropertyData>())
                        if (inner is ArrayPropertyData ap && inner.Name.ToString() == "Texts")
                        {
                            ap.Value = new PropertyData[] { InlineText(FName.FromString(asset, "Texts")) };
                            ap.ArrayType = FName.FromString(asset, "TextProperty");
                            named = true;
                        }
                }
            }
            Console.WriteLine(named ? $"  display name -> \"{disp}\""
                                    : "  WARN: no VehicleName/VehicleName2 on the row");
        }

        // Field overrides, "Name=Value,Name=Value". Typed off whatever the row
        // already holds, so a float stays a float.
        foreach (var kv in (f.GetValueOrDefault("set", "") ?? "")
                     .Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            var bits = kv.Split('=', 2);
            if (bits.Length != 2) continue;
            string fn = bits[0].Trim(), fv = bits[1].Trim();
            bool hit = false;
            foreach (var pd in clone.Value)
            {
                if (pd.Name.ToString() != fn) continue;
                hit = true;
                switch (pd)
                {
                    case IntPropertyData ip when int.TryParse(fv, out var iv): ip.Value = iv; break;
                    case Int64PropertyData lp when long.TryParse(fv, out var lv): lp.Value = lv; break;
                    case FloatPropertyData fp when float.TryParse(fv, out var vv): fp.Value = vv; break;
                    case BoolPropertyData bp: bp.Value = fv is "1" or "true" or "True"; break;
                    default:
                        Console.Error.WriteLine($"  WARN: {fn} is {pd.GetType().Name} — not settable here");
                        break;
                }
                Console.WriteLine($"  {fn} = {fv}");
            }
            if (!hit) Console.Error.WriteLine($"  WARN: field '{fn}' not on row '{baseRow}' — ignored");
        }

        if (existing >= 0) table.Table.Data[existing] = clone;
        else table.Table.Data.Add(clone);
        asset.Write(f.GetValueOrDefault("output", f["uasset"]));
        Console.WriteLine($"  {(existing >= 0 ? "refreshed" : "cloned")} row {baseRow} -> {newRow} "
                          + $"({table.Table.Data.Count} rows total)");
        return 0;
    }

    // Rewire a cloned vehicle class's drivetrain.
    //
    // Three shapes, selected by flags:
    //
    //   (default)        SPOOL. Every wheel on the one differential the driven
    //                    pair already used. Adds no components.
    //   --each-set-awd   Front and rear each get their OWN differential. The
    //                    existing one becomes the rear; the front is cloned
    //                    from it so inertia and the data asset carry over.
    //   --center-diff    Adds a centre differential that front and rear both
    //                    feed. This is vanilla's shape: Neo has Wheel0/1 ->
    //                    DifferentialF, Wheel2/3 -> DifferentialR, F and R ->
    //                    DifferentialC.
    //
    // Adding a differential means adding a Blueprint component: a
    // <Name>_GEN_VARIABLE template, an SCS_Node pointing at it with a fresh
    // VariableGuid, and that node registered in SimpleConstructionScript's
    // RootNodes AND AllNodes. Miss either array and the component is never


    // Say which liquids a vehicle's tanker cargo space will ACCEPT.
    //
    // Two different gates, and both have to open. MTTankerFuelPumpComponent's
    // Slots decide what a vehicle can DISPENSE; AllowedFuelTypes on its cargo
    // space decides what it can RECEIVE. Give a tanker a Water pump slot and
    // nothing else and a hydrant still refuses it with "wrong fuel type",
    // because the tank has no opinion recorded and the class default does not
    // include water.
    //
    // The fire engine is the worked example: its cargo space carries exactly
    // one AllowedFuelTypes entry, Water, which is why it can be filled from a
    // hydrant and why nothing else can.
    private static int VehicleCargoFuels(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        var types = f.GetValueOrDefault("types", "Water").Split(',')
                     .Select(x => x.Trim()).Where(x => x.Length > 0).ToArray();
        string wantSpace = f.GetValueOrDefault("space-type", "Tanker");

        EnsureName(asset, "AllowedFuelTypes");
        EnsureName(asset, "EMTFuelType");
        // QUALIFIED here, "EMTFuelType::Water", not the bare "Water" the pump
        // slots take. The two are serialized differently and want opposite
        // spellings: a slot's FuelType is a byte index resolved against the
        // usmap's member list, so a qualified name there throws outright,
        // while AllowedFuelTypes is an array of FNames and vanilla writes
        // them qualified. Bare names here serialize fine and the game then
        // cannot resolve them, which it reports as "wrong fuel type" at the
        // pump -- a silent write, a wrong read, and nothing in between.
        foreach (var t in types) EnsureName(asset, "EMTFuelType::" + t);

        int touched = 0;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            // Only the cargo spaces of the requested kind. A vehicle can carry
            // several spaces and a box or a flatbed has no business accepting
            // a liquid.
            var st = ne.Data.FirstOrDefault(p => p.Name.ToString() == "CargoSpaceType");
            if (st is not EnumPropertyData ep || ep.Value.Value.Value != wantSpace) continue;

            var arr = new ArrayPropertyData(FName.FromString(asset, "AllowedFuelTypes"))
            { ArrayType = FName.FromString(asset, "EnumProperty") };
            arr.Value = types.Select(t => (PropertyData)new EnumPropertyData(
                FName.FromString(asset, "AllowedFuelTypes"))
            {
                EnumType = FName.FromString(asset, "EMTFuelType"),
                Value    = FName.FromString(asset, "EMTFuelType::" + t)
            }).ToArray();

            var cur = ne.Data.FirstOrDefault(p => p.Name.ToString() == "AllowedFuelTypes");
            if (cur != null) ne.Data.Remove(cur);
            ne.Data.Add(arr);
            touched++;
            Console.WriteLine($"  {ne.ObjectName}: AllowedFuelTypes = {string.Join(", ", types)}");
        }
        if (touched == 0)
        {
            // Not fatal. A vehicle can be a tanker in every way that matters
            // and still not say so here -- Kira_Tanker carries liquids in game
            // with no CargoSpaceType serialized at all, inheriting it from its
            // class. Failing the build over that would block the eight vehicles
            // this DID work on.
            Console.Error.WriteLine("  no cargo space with CargoSpaceType=" + wantSpace
                                  + " on " + Path.GetFileNameWithoutExtension(f["uasset"])
                                  + " - it may inherit one; left unchanged");
            return 0;
        }
        asset.Write(f.GetValueOrDefault("output", f["uasset"]));
        return 0;
    }


    // Give a vehicle the tanker fuel pump, so it can refuel others.
    //
    // What separates the Brutus fire engine from the 30ft tanker trailer is
    // one component: MTTankerFuelPumpComponent. bHasFuelPump on the DataTable
    // row only advertises it -- set that alone and nothing happens, because
    // the flag describes a component that has to exist on the Blueprint.
    //
    // The component builds its own interaction point at runtime from
    // InteractionMeshRelativeLocation, so no hatch mesh has to be modelled or
    // copied across. Slots is the only thing worth authoring: an array of
    // MTFuelPumpSlot carrying one FuelType each, which is how a tanker ends up
    // able to dispense more than one liquid. EMTFuelType has exactly two
    // members, Gasoline and Diesel -- water is not one of them, so a water
    // tanker cannot be built this way.
    private static int VehicleFuelPump(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        string varName = f.GetValueOrDefault("name", "MTTankerFuelPump");
        var fuels = f.GetValueOrDefault("fuel-types", "Diesel").Split(',')
                     .Select(x => x.Trim()).Where(x => x.Length > 0).ToArray();

        NormalExport scs = null, sampleNode = null, sampleTpl = null;
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            string n = ne.ObjectName.ToString();
            if (n == varName + "_GEN_VARIABLE")
            { Console.WriteLine("  " + varName + " already present - nothing to do"); return 0; }
            if (n.StartsWith("SimpleConstructionScript", StringComparison.Ordinal)) scs = ne;
            else if (n.StartsWith("SCS_Node", StringComparison.Ordinal)) sampleNode ??= ne;
            else if (n.EndsWith("_GEN_VARIABLE", StringComparison.Ordinal)) sampleTpl ??= ne;
        }
        if (scs == null || sampleNode == null || sampleTpl == null)
        {
            Console.Error.WriteLine("  need a SimpleConstructionScript, an SCS_Node and a "
                                  + "_GEN_VARIABLE to model the new component on");
            return 1;
        }

        // Imports for a C++ component class: the module package, the class and
        // its CDO, shaped exactly as the fire engine carries them.
        int pkg = FindOrAddImport(asset, "/Script/MotorTown", 0, "/Script/CoreUObject", "Package");
        int cls = FindOrAddImport(asset, "MTTankerFuelPumpComponent", pkg, "/Script/CoreUObject", "Class");
        int cdo = FindOrAddImport(asset, "Default__MTTankerFuelPumpComponent", pkg,
                                  "/Script/MotorTown", "MTTankerFuelPumpComponent");

        foreach (var nm in new[] { varName, varName + "_GEN_VARIABLE", "SCS_Node_" + varName,
                                   "Slots", "FuelType", "MTFuelPumpSlot", "EMTFuelType" })
            EnsureName(asset, nm);

        var slots = new ArrayPropertyData(FName.FromString(asset, "Slots"))
        { ArrayType = FName.FromString(asset, "StructProperty") };
        var items = new List<PropertyData>();
        foreach (var ft in fuels)
        {
            // The BARE member name, not "EMTFuelType::Diesel". Unversioned
            // enums serialise as a byte index that UAssetAPI resolves by
            // matching this string against the usmap's enum member list, and
            // the usmap stores members unqualified.
            EnsureName(asset, ft);
            items.Add(new StructPropertyData(FName.FromString(asset, "Slots"),
                                             FName.FromString(asset, "MTFuelPumpSlot"))
            {
                Value = new List<PropertyData> {
                    new EnumPropertyData(FName.FromString(asset, "FuelType")) {
                        EnumType = FName.FromString(asset, "EMTFuelType"),
                        Value    = FName.FromString(asset, ft) }
                }
            });
        }
        slots.Value = items.ToArray();

        // Template: an existing component's skeleton, so outer, flags and
        // extras are already right for this asset, re-pointed at the new class.
        var tpl = (NormalExport)CloneExport(sampleTpl, asset);
        tpl.ObjectName = FName.FromString(asset, varName + "_GEN_VARIABLE");
        tpl.ClassIndex = new FPackageIndex(cls);
        tpl.TemplateIndex = new FPackageIndex(cdo);
        // Must exist on BOTH sides. The skeleton is whatever component came
        // first in the asset, and a cosmetic one -- a blinker light -- is
        // marked bNotForServer, which would leave a dedicated server with no
        // pump at all while clients drew one. The fire engine's own pump
        // carries both flags false.
        tpl.bNotForServer = false;
        tpl.bNotForClient = false;
        // Extras must match the CLASS, not whichever component was cloned for
        // its skeleton. A scene or primitive component carries 16 bytes here; a
        // plain ActorComponent, which this is, carries 4. Inheriting 16 makes
        // the export header claim twelve bytes more than the loader reads and
        // the game dies on load with "Serial size mismatch: Got 46, Expected
        // 58" -- 58 - 46 being exactly that 16 - 4. Whether it happened at all
        // depended on which component sorted first in the asset, so it hit two
        // of nine vehicles and looked random. The fire engine's own pump
        // carries four zero bytes.
        tpl.Extras = new byte[4];
        tpl.Data = new List<PropertyData> { slots };
        if (f.TryGetValue("rel-x", out var rx))
        {
            EnsureName(asset, "InteractionMeshRelativeLocation");
            EnsureName(asset, "Vector");
            var ic = System.Globalization.CultureInfo.InvariantCulture;
            double X = double.Parse(rx, ic);
            double Y = double.Parse(f.GetValueOrDefault("rel-y", "0"), ic);
            double Z = double.Parse(f.GetValueOrDefault("rel-z", "0"), ic);
            tpl.Data.Add(new StructPropertyData(
                FName.FromString(asset, "InteractionMeshRelativeLocation"),
                FName.FromString(asset, "Vector"))
            {
                Value = new List<PropertyData> {
                    new VectorPropertyData(FName.FromString(asset, "InteractionMeshRelativeLocation"))
                        { Value = new FVector(X, Y, Z) } }
            });
            Console.WriteLine("  interaction point at (" + X + ", " + Y + ", " + Z + ")");
        }
        asset.Exports.Add(tpl);
        int tplIdx = asset.Exports.Count;

        var node = (NormalExport)CloneExport(sampleNode, asset);
        node.ObjectName = FName.FromString(asset, "SCS_Node_" + varName);
        node.bNotForServer = false;
        node.bNotForClient = false;
        node.Data = sampleNode.Data.Select(DeepCloneProp).ToList();
        foreach (var p in node.Data)
        {
            switch (p.Name.ToString())
            {
                case "ComponentTemplate" when p is ObjectPropertyData op:
                    op.Value = new FPackageIndex(tplIdx); break;
                case "ComponentClass" when p is ObjectPropertyData cp:
                    cp.Value = new FPackageIndex(cls); break;
                case "InternalVariableName" when p is NamePropertyData np:
                    np.Value = FName.FromString(asset, varName); break;
                case "VariableGuid" when p is StructPropertyData gp && gp.Value != null:
                    foreach (var g in gp.Value)
                        if (g is GuidPropertyData gd) gd.Value = Guid.NewGuid();
                    break;
                case "ChildNodes" when p is ArrayPropertyData cn:
                    cn.Value = Array.Empty<PropertyData>(); break;
            }
        }
        asset.Exports.Add(node);
        int nodeIdx = asset.Exports.Count;

        // BOTH arrays. RootNodes alone leaves the component unconstructed and
        // nothing warns about it.
        int reg = 0;
        foreach (var p in scs.Data)
            if (p is ArrayPropertyData ap
                && (p.Name.ToString() == "RootNodes" || p.Name.ToString() == "AllNodes"))
            {
                var list = (ap.Value ?? Array.Empty<PropertyData>()).ToList();
                list.Add(new ObjectPropertyData(ap.Name) { Value = new FPackageIndex(nodeIdx) });
                ap.Value = list.ToArray();
                reg++;
            }
        if (reg < 2)
        {
            Console.Error.WriteLine("  registered in " + reg + " of 2 node arrays - the component "
                                  + "would not be constructed; refusing to write");
            return 1;
        }


        // The pump also needs an INTERACTION, or nothing can use it.
        //
        // MTTankerFuelPumpComponent holds the fuel; MTInteractableComponent
        // with an InteractionParams entry of Tanker_FuelPump is what exposes
        // it. All three vanilla pump vehicles carry both -- Brutus_Tanker,
        // Brutus_FireEngine and Jemusi_Tanker -- and a tanker with the
        // component but no interaction is refused by a hydrant with "wrong
        // fuel type", which reads like a fuel problem and is not one.
        //
        // Mirrors vanilla's shape exactly, including bNotForServer, which is
        // TRUE here where it was false on the pump. Extras is 4 bytes, as for
        // any non-primitive component.
        // Reuse the vehicle's existing interactable when it has one. Most
        // trailers already carry an MTInteractable for the hitch, with no
        // InteractionParams at all -- adding a second component would leave
        // the pump exposed by neither, so the entry goes onto the one that is
        // already there.
        var haveInteractable = asset.Exports.OfType<NormalExport>()
            .FirstOrDefault(e => e.ObjectName.ToString() == "MTInteractable_GEN_VARIABLE");
        {
            foreach (var nm in new[] { "MTInteractable", "MTInteractable_GEN_VARIABLE",
                                       "SCS_Node_MTInteractable", "InteractionParams",
                                       "InteractionType", "MTInteractionParams",
                                       "bHideOnList", "Tanker_FuelPump" })
                EnsureName(asset, nm);

            int icls = FindOrAddImport(asset, "MTInteractableComponent", pkg,
                                       "/Script/CoreUObject", "Class");
            int icdo = FindOrAddImport(asset, "Default__MTInteractableComponent", pkg,
                                       "/Script/MotorTown", "MTInteractableComponent");

            var prm = new ArrayPropertyData(FName.FromString(asset, "InteractionParams"))
            { ArrayType = FName.FromString(asset, "StructProperty") };
            prm.Value = new PropertyData[] {
                new StructPropertyData(FName.FromString(asset, "InteractionParams"),
                                       FName.FromString(asset, "MTInteractionParams"))
                {
                    Value = new List<PropertyData> {
                        // BARE member name: this is a byte index inside a
                        // struct, the same serialization the pump slots use.
                        new EnumPropertyData(FName.FromString(asset, "InteractionType")) {
                            EnumType = FName.FromString(asset, "EMotorTownInteractableType"),
                            Value    = FName.FromString(asset, "Tanker_FuelPump") },
                        new BoolPropertyData(FName.FromString(asset, "bHideOnList")) { Value = false },
                    }
                }
            };

            if (haveInteractable != null)
            {
                var cur = haveInteractable.Data.FirstOrDefault(q => q.Name.ToString() == "InteractionParams");
                if (cur is ArrayPropertyData curArr)
                {
                    var merged = (curArr.Value ?? Array.Empty<PropertyData>()).ToList();
                    merged.AddRange(prm.Value);
                    curArr.Value = merged.ToArray();
                }
                else haveInteractable.Data.Add(prm);
                asset.Write(f.GetValueOrDefault("output", f["uasset"]));
                Console.WriteLine("  + Tanker_FuelPump on the existing MTInteractable");
                return 0;
            }

            var itpl = (NormalExport)CloneExport(sampleTpl, asset);
            itpl.ObjectName = FName.FromString(asset, "MTInteractable_GEN_VARIABLE");
            itpl.ClassIndex = new FPackageIndex(icls);
            itpl.TemplateIndex = new FPackageIndex(icdo);
            itpl.Data = new List<PropertyData> { prm };
            itpl.Extras = new byte[4];
            itpl.bNotForClient = false;
            itpl.bNotForServer = true;          // as vanilla has it
            asset.Exports.Add(itpl);
            int itplIdx = asset.Exports.Count;

            var inode = (NormalExport)CloneExport(sampleNode, asset);
            inode.ObjectName = FName.FromString(asset, "SCS_Node_MTInteractable");
            inode.Data = sampleNode.Data.Select(DeepCloneProp).ToList();
            inode.Extras = sampleNode.Extras != null ? (byte[])sampleNode.Extras.Clone() : null;
            foreach (var q in inode.Data)
            {
                switch (q.Name.ToString())
                {
                    case "ComponentTemplate" when q is ObjectPropertyData qo:
                        qo.Value = new FPackageIndex(itplIdx); break;
                    case "ComponentClass" when q is ObjectPropertyData qc:
                        qc.Value = new FPackageIndex(icls); break;
                    case "InternalVariableName" when q is NamePropertyData qn:
                        qn.Value = FName.FromString(asset, "MTInteractable"); break;
                    case "VariableGuid" when q is StructPropertyData qg && qg.Value != null:
                        foreach (var g in qg.Value)
                            if (g is GuidPropertyData gd2) gd2.Value = Guid.NewGuid();
                        break;
                    case "ChildNodes" when q is ArrayPropertyData qa:
                        qa.Value = Array.Empty<PropertyData>(); break;
                }
            }
            asset.Exports.Add(inode);
            int inodeIdx = asset.Exports.Count;

            int ireg = 0;
            foreach (var q in scs.Data)
                if (q is ArrayPropertyData qa2
                    && (q.Name.ToString() == "RootNodes" || q.Name.ToString() == "AllNodes"))
                {
                    var list = (qa2.Value ?? Array.Empty<PropertyData>()).ToList();
                    list.Add(new ObjectPropertyData(qa2.Name) { Value = new FPackageIndex(inodeIdx) });
                    qa2.Value = list.ToArray();
                    ireg++;
                }
            if (ireg < 2)
            {
                Console.Error.WriteLine("  interactable registered in " + ireg + " of 2 node arrays");
                return 1;
            }
            Console.WriteLine("  + MTInteractable (Tanker_FuelPump) so the pump can be used");
        }

        asset.Write(f.GetValueOrDefault("output", f["uasset"]));
        Console.WriteLine("  + " + varName + " (" + string.Join(", ", fuels) + ") on "
                        + Path.GetFileNameWithoutExtension(f["uasset"]));
        return 0;
    }


    // constructed and nothing warns.
    private static int VehicleAllWheelDrive(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        bool eachSet = f.ContainsKey("each-set-awd");
        bool centre  = f.ContainsKey("center-diff");

        var wheels = new List<NormalExport>();
        NormalExport diffTpl = null, diffNode = null, scs = null;
        string diffName = "";
        foreach (var e in asset.Exports)
        {
            if (e is not NormalExport ne) continue;
            string n = ne.ObjectName.ToString();
            if (n.StartsWith("Wheel", StringComparison.Ordinal))
            {
                wheels.Add(ne);
                foreach (var p in ne.Data)
                    if (p.Name.ToString() == "DifferentialComponentName" && p is NamePropertyData np)
                        diffName = np.Value.ToString();
            }
            else if (n.EndsWith("_GEN_VARIABLE", StringComparison.Ordinal)
                     && n.StartsWith("Differential", StringComparison.Ordinal)) diffTpl = ne;
            else if (n.StartsWith("SimpleConstructionScript", StringComparison.Ordinal)) scs = ne;
        }
        if (wheels.Count == 0) { Console.Error.WriteLine("  no Wheel* exports"); return 1; }
        if (string.IsNullOrEmpty(diffName))
        { Console.Error.WriteLine("  no wheel names a differential"); return 1; }
        foreach (var e in asset.Exports)
            if (e is NormalExport n2 && n2.ObjectName.ToString().StartsWith("SCS_Node", StringComparison.Ordinal))
                foreach (var p in n2.Data)
                    if (p.Name.ToString() == "InternalVariableName" && p is NamePropertyData ivn
                        && ivn.Value.ToString() == diffName) diffNode = n2;

        EnsureName(asset, "DifferentialComponentName");

        void PointWheels(IEnumerable<NormalExport> ws, string target)
        {
            EnsureName(asset, target);
            foreach (var w in ws)
            {
                var cur = w.Data.FirstOrDefault(p => p.Name.ToString() == "DifferentialComponentName");
                if (cur is NamePropertyData np) np.Value = FName.FromString(asset, target);
                else w.Data.Add(new NamePropertyData(FName.FromString(asset, "DifferentialComponentName"))
                { Value = FName.FromString(asset, target) });
                Console.WriteLine("  " + w.ObjectName + " -> " + target);
            }
        }

        if (!eachSet && !centre)
        {
            PointWheels(wheels, diffName);
            asset.Write(f.GetValueOrDefault("output", f["uasset"]));
            Console.WriteLine("  spool: " + wheels.Count + " wheel(s) on " + diffName);
            return 0;
        }

        if (diffTpl == null || diffNode == null || scs == null)
        {
            Console.Error.WriteLine("  need the differential template, its SCS node and the "
                                  + "construction script to add components - falling back to spool");
            PointWheels(wheels, diffName);
            asset.Write(f.GetValueOrDefault("output", f["uasset"]));
            return 0;
        }

        void SetStr(NormalExport ex, string prop, string val)
        {
            EnsureName(asset, prop);
            EnsureName(asset, val);
            var cur = ex.Data.FirstOrDefault(p => p.Name.ToString() == prop);
            if (cur is StrPropertyData sd) sd.Value = new FString(val);
            else ex.Data.Add(new StrPropertyData(FName.FromString(asset, prop)) { Value = new FString(val) });
        }

        void AddDifferential(string varName, string feedsInto)
        {
            EnsureName(asset, varName);
            EnsureName(asset, varName + "_GEN_VARIABLE");
            var tpl = (NormalExport)CloneExport(diffTpl, asset);
            tpl.ObjectName = FName.FromString(asset, varName + "_GEN_VARIABLE");
            tpl.Data = diffTpl.Data.Select(DeepCloneProp).ToList();
            if (feedsInto != null) SetStr(tpl, "DifferentialComponentName", feedsInto);
            asset.Exports.Add(tpl);
            int tplIdx = asset.Exports.Count;

            var node = (NormalExport)CloneExport(diffNode, asset);
            node.ObjectName = FName.FromString(asset, "SCS_Node_" + varName);
            node.Data = diffNode.Data.Select(DeepCloneProp).ToList();
            foreach (var p in node.Data)
            {
                if (p.Name.ToString() == "ComponentTemplate" && p is ObjectPropertyData op)
                    op.Value = new FPackageIndex(tplIdx);
                else if (p.Name.ToString() == "InternalVariableName" && p is NamePropertyData np)
                    np.Value = FName.FromString(asset, varName);
                else if (p.Name.ToString() == "VariableGuid" && p is StructPropertyData gp && gp.Value != null)
                    foreach (var g in gp.Value)
                        if (g is GuidPropertyData gd) gd.Value = Guid.NewGuid();
            }
            asset.Exports.Add(node);
            int nodeIdx = asset.Exports.Count;

            foreach (var p in scs.Data)
                if (p is ArrayPropertyData ap
                    && (p.Name.ToString() == "RootNodes" || p.Name.ToString() == "AllNodes"))
                {
                    var list = (ap.Value ?? Array.Empty<PropertyData>()).ToList();
                    list.Add(new ObjectPropertyData(ap.Name) { Value = new FPackageIndex(nodeIdx) });
                    ap.Value = list.ToArray();
                }
            Console.WriteLine("  + component " + varName + (feedsInto != null ? " -> " + feedsInto : ""));
        }

        string rear = "DifferentialR", front = "DifferentialF", cen = "DifferentialC";
        EnsureName(asset, rear);
        diffTpl.ObjectName = FName.FromString(asset, rear + "_GEN_VARIABLE");
        foreach (var p in diffNode.Data)
            if (p.Name.ToString() == "InternalVariableName" && p is NamePropertyData np)
                np.Value = FName.FromString(asset, rear);
        Console.WriteLine("  " + diffName + " renamed -> " + rear);

        if (centre)
        {
            AddDifferential(cen, null);
            SetStr(diffTpl, "DifferentialComponentName", cen);
        }
        AddDifferential(front, centre ? cen : null);

        int half = wheels.Count / 2;
        PointWheels(wheels.Take(half), front);
        PointWheels(wheels.Skip(half), rear);

        asset.Write(f.GetValueOrDefault("output", f["uasset"]));
        Console.WriteLine("  all-wheel drive: front/rear differentials"
                          + (centre ? " feeding a centre differential" : "")
                          + ", " + wheels.Count + " wheel(s)");
        return 0;
    }


    // Move the in-game world map's world rectangle.
    //
    // DataAsset/GameResource.uasset holds DriveMaps, an array of MTMap. Entry 0
    // is Jeju, and its WorldMap struct is what converts a world position into a
    // map pixel:
    //
    //     WorldMapTexture   the texture drawn
    //     WorldMapLocation  the world-space CENTRE  (-180000, 780000, 100000)
    //     WorldMapSize      the world-space SIZE    2200000  (22 km square)
    //
    // Centre and size, NOT four corners -- which is why searching every cooked
    // asset for min/max values found nothing. Those two reproduce the numbers
    // the original live map used exactly: -180000 +/- 1100000 gives
    // -1280000..920000, and 780000 +/- 1100000 gives -320000..1880000.
    //
    // Editing them is what lets a LARGER map texture line up: grow the texture
    // and move these to match, and every marker the game draws follows.
    private static int SetWorldMap(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        int index = int.Parse(f.GetValueOrDefault("index", "0"));
        string arrayName = f.GetValueOrDefault("array", "DriveMaps");

        ArrayPropertyData? maps = null;
        foreach (var e in asset.Exports)
            if (e is NormalExport ne)
                foreach (var p in ne.Data)
                    if (p is ArrayPropertyData ap && p.Name.ToString() == arrayName)
                        maps = ap;
        if (maps?.Value == null || maps.Value.Length <= index)
        { Console.Error.WriteLine($"  {arrayName}[{index}] not found"); return 1; }

        if (maps.Value[index] is not StructPropertyData entry || entry.Value == null)
        { Console.Error.WriteLine($"  {arrayName}[{index}] is not a struct"); return 1; }

        StructPropertyData? wm = null;
        foreach (var p in entry.Value)
            if (p is StructPropertyData sp && p.Name.ToString() == "WorldMap") wm = sp;
        if (wm?.Value == null)
        { Console.Error.WriteLine("  no WorldMap struct on that entry"); return 1; }

        // Read what is there first, so the log shows the move rather than just
        // the destination -- a wrong index would otherwise look like a success.
        foreach (var p in wm.Value)
        {
            if (p.Name.ToString() == "WorldMapSize" && p is FloatPropertyData fs)
                Console.WriteLine($"  current WorldMapSize   {fs.Value}");
            if (p.Name.ToString() == "WorldMapLocation" && p is StructPropertyData ls)
                foreach (var v in ls.Value ?? new List<PropertyData>())
                    if (v is VectorPropertyData vp)
                        Console.WriteLine($"  current WorldMapLocation ({vp.Value.X}, {vp.Value.Y}, {vp.Value.Z})");
        }

        bool changed = false;
        if (f.TryGetValue("size", out var szs) && float.TryParse(szs, out float sz))
        {
            EnsureName(asset, "WorldMapSize");
            var cur = wm.Value.FirstOrDefault(p => p.Name.ToString() == "WorldMapSize");
            if (cur is FloatPropertyData fp) fp.Value = sz;
            else wm.Value.Add(new FloatPropertyData(FName.FromString(asset, "WorldMapSize")) { Value = sz });
            Console.WriteLine($"  WorldMapSize -> {sz}");
            changed = true;
        }
        if (f.TryGetValue("center-x", out var cxs) && f.TryGetValue("center-y", out var cys)
            && double.TryParse(cxs, out double cx) && double.TryParse(cys, out double cy))
        {
            double cz = f.TryGetValue("center-z", out var czs) && double.TryParse(czs, out double z) ? z : 100000.0;
            EnsureName(asset, "WorldMapLocation");
            EnsureName(asset, "Vector");
            var cur = wm.Value.FirstOrDefault(p => p.Name.ToString() == "WorldMapLocation");
            if (cur is StructPropertyData sp2 && sp2.Value != null
                && sp2.Value.FirstOrDefault(v => v is VectorPropertyData) is VectorPropertyData vp2)
                vp2.Value = new FVector(cx, cy, cz);
            else
                wm.Value.Add(new StructPropertyData(FName.FromString(asset, "WorldMapLocation"),
                                                    FName.FromString(asset, "Vector"))
                {
                    Value = new List<PropertyData> {
                        new VectorPropertyData(FName.FromString(asset, "WorldMapLocation"))
                            { Value = new FVector(cx, cy, cz) } }
                });
            Console.WriteLine($"  WorldMapLocation -> ({cx}, {cy}, {cz})");
            changed = true;
        }
        if (!changed) { Console.Error.WriteLine("  nothing to set — pass --size and/or --center-x/--center-y"); return 1; }

        asset.Write(f.GetValueOrDefault("output", f["uasset"]));
        return 0;
    }

    private static int DumpTable(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport"); return 1; }
        var want = (f.GetValueOrDefault("fields", "") ?? "")
            .Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(s => s.Trim()).Where(s => s.Length > 0).ToList();

        // --row NAME: print every field on one row, name and value. The row
        // struct of a DataTable is often a BLUEPRINT struct (VehicleRow is),
        // and the .usmap holds C++ types only -- so dump-schema cannot list
        // its fields and there was no way to find out what a row even has
        // without guessing field names one at a time.
        if (f.TryGetValue("row", out var wantRow) && !string.IsNullOrWhiteSpace(wantRow))
        {
            foreach (var row in table.Table.Data)
            {
                if (row.Name.ToString() != wantRow) continue;
                Console.WriteLine($"=== row {row.Name} ({row.Value.Count} fields) ===");
                foreach (var p in row.Value)
                {
                    string val = p switch
                    {
                        SoftObjectPropertyData so => so.Value.AssetPath.PackageName.ToString(),
                        BoolPropertyData bp => bp.Value ? "true" : "false",
                        StructPropertyData sp2 => $"<struct {sp2.StructType}>",
                        ArrayPropertyData ap2 => $"[array {ap2.ArrayType} x{ap2.Value?.Length ?? 0}]",
                        _ => p.RawValue?.ToString() ?? "",
                    };
                    Console.WriteLine($"  {p.Name,-40} {p.GetType().Name,-24} {val}");
                }
                return 0;
            }
            Console.Error.WriteLine($"  row '{wantRow}' not found");
            return 1;
        }

        foreach (var row in table.Table.Data)
        {
            var cells = new List<string> { row.Name.ToString() };
            foreach (var name in want)
            {
                string val = "";
                foreach (var p in row.Value)
                {
                    if (p.Name.ToString() != name) continue;
                    val = p switch
                    {
                        SoftObjectPropertyData so => so.Value.AssetPath.PackageName.ToString(),
                        BoolPropertyData bp => bp.Value ? "1" : "0",
                        _ => p.RawValue?.ToString() ?? "",
                    };
                    break;
                }
                cells.Add(val.Replace('\t', ' '));
            }
            Console.WriteLine(string.Join("\t", cells));
        }
        return 0;
    }

    // Every cargo's WeightRange, for pricing by weight. import_cargo_data.py
    // cannot get this: the vendored UAssetGUI falls back to RawExport on the
    // current mappings, so the whole table is opaque to it. UAssetAPI here
    // parses it fine.
    //   --uasset <Cargos.uasset> --mappings <usmap>
    // Prints "<name>\t<weightMin>\t<weightMax>" per row.
    private static int DumpCargoWeights(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport"); return 1; }
        foreach (var row in table.Table.Data)
        {
            string wmin = "", wmax = "";
            foreach (var p in row.Value)
            {
                if (p.Name.ToString() != "WeightRange") continue;
                // WeightRange is a Vector2D property, not a struct with X/Y
                // children -- reach into the struct's single inner value.
                PropertyData? inner = p;
                if (p is StructPropertyData sp)
                    inner = (sp.Value != null && sp.Value.Count > 0) ? sp.Value[0] : null;
                if (inner is UAssetAPI.PropertyTypes.Structs.Vector2DPropertyData v2)
                {
                    wmin = v2.Value.X.ToString();
                    wmax = v2.Value.Y.ToString();
                }
            }
            Console.WriteLine($"{row.Name}\t{wmin}\t{wmax}");
        }
        return 0;
    }

    // Read collision off the COOKED mesh, which is the only copy that
    // matters at runtime. ue.py reads the same thing in the editor, but that
    // snapshot goes stale the moment you re-cook a mesh without re-exporting
    // the scene -- and a stale snapshot silently reverts a collision change
    // you just made. This reads the shipped .uasset instead, so re-cooking a
    // mesh is enough for the change to reach the game.
    //   --list <file with one .uasset disk path per line> --mappings <usmap>
    // Prints "<path>\t<profile>\t<prims>" per line. Profile is NoCollision,
    // the mesh's own named preset, or BlockAll.
    private static int MeshCollision(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        foreach (var line in File.ReadAllLines(f["list"]))
        {
            var path = line.Trim();
            if (path.Length == 0) continue;
            string profile = "";
            int prims = -1;
            try
            {
                var asset = new UAsset(path, EngineVer, mappings);
                foreach (var ex in asset.Exports)
                {
                    if (ex.GetExportClassType()?.Value?.Value != "BodySetup") continue;
                    if (ex is not NormalExport ne) continue;
                    string enabled = "", named = "";
                    foreach (var p in ne.Data)
                    {
                        if (p.Name.ToString() == "AggGeom" && p is StructPropertyData agg)
                        {
                            prims = 0;
                            foreach (var sub in agg.Value ?? new List<PropertyData>())
                                if (sub is ArrayPropertyData ap) prims += ap.Value?.Length ?? 0;
                        }
                        if (p.Name.ToString() != "DefaultInstance" || p is not StructPropertyData di) continue;
                        foreach (var sub in di.Value ?? new List<PropertyData>())
                        {
                            var n = sub.Name.ToString();
                            if (n == "CollisionEnabled") enabled = sub.RawValue?.ToString() ?? "";
                            if (n == "CollisionProfileName") named = sub.RawValue?.ToString() ?? "";
                        }
                    }
                    // The mesh having collision switched off beats any
                    // leftover primitive still sitting in AggGeom.
                    if (enabled.Contains("NoCollision")) profile = "NoCollision";
                    else if (named.Length > 0 && named != "None" && named != "Default"
                             && named != "Custom") profile = named;
                    else if (prims == 0) profile = "NoCollision";
                    else profile = "BlockAll";
                    break;
                }
            }
            catch (Exception ex) { Console.Error.WriteLine($"  mesh-collision: {path}: {ex.Message}"); }
            Console.WriteLine($"{path}\t{profile}\t{prims}");
        }
        return 0;
    }

    // Diagnostic: dump one row of a Cargos DataTable in detail. Use to
    // compare the field shape of a row produced by a working mod (e.g.
    // OversizedCargos) against our cloned row, to spot missing imports
    // / string-table refs / namespaces that explain blank UI labels.
    //   --uasset <Cargos.uasset> --row <RowName>  [--imports] [--names]
    //   --mappings <usmap>
    private static int DumpCargoRow(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["uasset"], EngineVer, LoadMappings(f["mappings"]));
        Console.WriteLine($"== {f["uasset"]} ==");
        Console.WriteLine($"NameMap entries: {asset.GetNameMapIndexList().Count}");
        Console.WriteLine($"Imports: {asset.Imports.Count}");
        if (f.ContainsKey("imports"))
            for (int i = 0; i < asset.Imports.Count; i++)
            {
                var im = asset.Imports[i];
                Console.WriteLine($"  -{i+1}: {im.ObjectName} (class={im.ClassName} pkg={im.ClassPackage} outer={im.OuterIndex.Index})");
            }
        if (f.ContainsKey("names"))
        {
            var names = asset.GetNameMapIndexList();
            for (int i = 0; i < names.Count; i++)
                Console.WriteLine($"  N{i}: {names[i]}");
        }
        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport"); return 1; }
        string rowName = f.GetValueOrDefault("row", "");
        StructPropertyData? row = null;
        if (string.IsNullOrEmpty(rowName) && table.Table.Data.Count > 0)
            row = table.Table.Data[0];
        else
            foreach (var r in table.Table.Data)
                if (string.Equals(r.Name.ToString(), rowName, StringComparison.OrdinalIgnoreCase))
                { row = r; break; }
        if (row == null) { Console.Error.WriteLine($"  Row '{rowName}' not found"); return 1; }
        Console.WriteLine($"-- Row '{row.Name}' ({row.Value.Count} fields) --");
        if (f.ContainsKey("rawtext"))
        {
            // Re-serialize the Name + Name2 properties using THIS asset's
            // context so we can byte-compare two assets without UAssetAPI's
            // dump abstraction hiding subtle differences (NameMap indices,
            // FString encoding, terminator length).
            foreach (var p in row.Value)
            {
                if (p.Name.ToString() != "Name" && p.Name.ToString() != "Name2") continue;
                using var ms = new MemoryStream();
                using var w = new AssetBinaryWriter(ms, asset);
                p.Write(w, true);
                var bytes = ms.ToArray();
                Console.WriteLine($"  {p.Name} ({bytes.Length} bytes):");
                for (int i = 0; i < bytes.Length; i += 16)
                {
                    int n = Math.Min(16, bytes.Length - i);
                    var hex = new System.Text.StringBuilder();
                    var asc = new System.Text.StringBuilder();
                    for (int j = 0; j < n; j++)
                    {
                        hex.Append(bytes[i + j].ToString("x2")).Append(' ');
                        byte b = bytes[i + j];
                        asc.Append(b >= 0x20 && b < 0x7f ? (char)b : '.');
                    }
                    Console.WriteLine($"    {i:x4}  {hex,-48}  {asc}");
                }
            }
            return 0;
        }
        if (f.ContainsKey("json"))
        {
            var settings = new JsonSerializerSettings
            {
                TypeNameHandling = TypeNameHandling.Auto,
                Formatting = Formatting.Indented
            };
            Console.WriteLine(JsonConvert.SerializeObject(row, settings));
        }
        else
        {
            foreach (var p in row.Value) DumpField(p, "  ");
        }
        return 0;
    }

    // Append boosted cargo rows to a copy of vanilla Cargos.uasset.
    // Each spec entry deep-clones a source row, renames it, and multiplies
    // PaymentPer1Km. The cloned rows ship in the mod's pak under the same
    // /Game/DataAsset/Cargos path so MT's mission system picks them up
    // alongside vanilla cargos. Spec format:
    //   [{"source":"CornPallet","target":"CornPallet_x2_5","payment_multiplier":2.5}]
    //
    // Args:
    //   --src-uasset <vanilla Cargos.uasset>
    //   --dst-uasset <mod   Cargos.uasset>
    //   --spec       <JSON array path>
    //   --mappings   <usmap>
    private static int MutateCargos(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        string srcPath = f["src-uasset"];
        string dstPath = f["dst-uasset"];
        var spec = JArray.Parse(File.ReadAllText(f["spec"]));

        var asset = new UAsset(srcPath, EngineVer, mappings);
        UAssetAPI.ExportTypes.DataTableExport? table = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.DataTableExport dte) { table = dte; break; }
        if (table == null) { Console.Error.WriteLine("  No DataTableExport in Cargos.uasset"); return 1; }

        // Index existing rows by name so we can both find sources and skip
        // duplicate target inserts (idempotent re-runs).
        var existingRows = new Dictionary<string, StructPropertyData>(StringComparer.OrdinalIgnoreCase);
        foreach (var r in table.Table.Data)
            existingRows[r.Name.ToString()] = r;

        // Recursive deep clone of PropertyData (UAssetAPI's Clone is shallow
        // for nested struct/array values).
        PropertyData DeepClone(PropertyData p)
        {
            var c = (PropertyData)p.Clone();
            if (c is StructPropertyData scp && scp.Value != null)
                scp.Value = scp.Value.Select(DeepClone).ToList();
            else if (c is ArrayPropertyData acp && acp.Value != null)
                acp.Value = acp.Value.Select(DeepClone).ToArray();
            else if (c is MapPropertyData mcp && mcp.Value != null)
            {
                var newMap = new UAssetAPI.UnrealTypes.TMap<PropertyData, PropertyData>();
                foreach (var kv in mcp.Value)
                    newMap.Add(DeepClone(kv.Key), DeepClone(kv.Value));
                mcp.Value = newMap;
            }
            return c;
        }

        // Reserved keys in a spec entry — anything ELSE on the entry is
        // treated as a row-field name to set verbatim. This lets the JSON
        // mirror the actual cargo row schema instead of inventing a
        // separate dialect for each setter.
        // The list used to be enumerated, so every new build-time-only key
        // (display_name, weight_kg, batch, base_payment ...) had to be added
        // here or it reached the setter and warned about a field that was
        // never meant to exist on the row. UE field names are PascalCase or
        // b+PascalCase and never contain an underscore, so the shape of the
        // key is the rule: snake_case is ours, PascalCase is the game's.
        // ("batch" has no underscore, hence the all-lowercase arm; UE's own
        // boolean fields like bUseDamage always carry a capital after the b.)
        static bool IsReservedKey(string k) => k.Contains('_') || k.ToLowerInvariant() == k;

        // Generic per-field setter. Looks up `fieldName` on the row and
        // assigns the JSON value into the matching property. Property-type
        // dispatch on the actual UAssetAPI class — Float/Int/Int64/Bool/
        // Name covers every editable cargo-row field. Unknown fields or
        // fields that resolve to a complex struct (Vector2D, GameplayTags,
        // ObjectProperty actor refs) are skipped with a warning so a typo
        // is never silently ignored AND can never crash the writer.
        bool SetField(StructPropertyData row, string fieldName, JToken value, string label)
        {
            foreach (var p in row.Value)
            {
                if (p.Name.ToString() != fieldName) continue;
                switch (p)
                {
                    case FloatPropertyData fp:
                        fp.Value = (float)value!;
                        Console.WriteLine($"  {fieldName}={fp.Value} {label}");
                        return true;
                    case Int64PropertyData i64:
                        i64.Value = (long)value!;
                        Console.WriteLine($"  {fieldName}={i64.Value} {label}");
                        return true;
                    case IntPropertyData ip:
                        // Warn if a fractional JSON value is being silently
                        // truncated to int — usually means the JSON has the
                        // wrong type for this field (e.g. 0.5 on an Int
                        // counter). Lossless casts (5, 5.0) stay quiet.
                        if (value!.Type == JTokenType.Float)
                        {
                            double dv = (double)value!;
                            if (dv != Math.Truncate(dv))
                                Console.Error.WriteLine($"  WARN: field '{fieldName}' on {label} is Int — JSON value {dv} truncated to {(int)dv}");
                        }
                        ip.Value = (int)value!;
                        Console.WriteLine($"  {fieldName}={ip.Value} {label}");
                        return true;
                    case BoolPropertyData bp:
                        bp.Value = (bool)value!;
                        Console.WriteLine($"  {fieldName}={bp.Value} {label}");
                        return true;
                    case NamePropertyData np:
                        EnsureName(asset, (string)value!);
                        np.Value = FName.FromString(asset, (string)value!);
                        Console.WriteLine($"  {fieldName}={np.Value} {label}");
                        return true;
                    default:
                        Console.Error.WriteLine($"  WARN: field '{fieldName}' on {label} is type {p.GetType().Name} — not supported by mutate-cargos generic setter");
                        return false;
                }
            }
            Console.Error.WriteLine($"  WARN: field '{fieldName}' not found on {label}");
            return false;
        }

        void SetDisplayName(StructPropertyData row, string sourceKey, string? tablePath = null)
        {
            EnsureName(asset, "Texts");
            EnsureName(asset, "TextProperty");
            // Reuse vanilla's StringTableEntry pointing at the source
            // cargo's key. Inline FText (None / Base history) renders
            // blank in MT's mission UI; shipping a modified vanilla
            // StringTable crashes on world load. Until a separate-path
            // StringTable is wired up, the boosted row shows the source
            // cargo's localized name (e.g. Fuelx5 -> "Fuel").
            string tp2 = string.IsNullOrWhiteSpace(tablePath)
                ? "/Game/DataAsset/StringTables/Cargo.Cargo" : tablePath!;
            EnsureName(asset, tp2);
            var tableId = FName.FromString(asset, tp2);
            // A StringTable id is only an FName — it creates NO package
            // dependency, so the table is never loaded and the text resolves
            // to nothing. Vanilla rows work because the engine already loads
            // /Game/DataAsset/StringTables/Cargo. Add the real package +
            // object import for our table so it loads with Cargos_01.
            if (!string.IsNullOrWhiteSpace(tablePath))
            {
                string pkg = tp2.Split('.')[0];
                string obj = pkg.Substring(pkg.LastIndexOf('/') + 1);
                int pkgImp = FindOrAddImport(asset, pkg, 0, "/Script/CoreUObject", "Package");
                int stImp = FindOrAddImport(asset, obj, pkgImp, "/Script/Engine", "StringTable");
                foreach (var ex in asset.Exports)
                {
                    if (ex is not UAssetAPI.ExportTypes.DataTableExport) continue;
                    var dep = new FPackageIndex(stImp);
                    if (!ex.CreateBeforeSerializationDependencies.Any(x => x.Index == stImp))
                        ex.CreateBeforeSerializationDependencies.Add(dep);
                }
            }
            foreach (var p in row.Value)
            {
                if (p.Name.ToString() == "Name" && p is TextPropertyData tp)
                {
                    tp.HistoryType = TextHistoryType.StringTableEntry;
                    tp.Flags = 0;
                    tp.Namespace = null;
                    tp.TableId = tableId;
                    tp.Value = new FString(sourceKey);
                    tp.CultureInvariantString = null;
                    tp.SourceFmt = null; tp.Arguments = null; tp.ArgumentsData = null;
                }
                else if (p.Name.ToString() == "Name2" && p is StructPropertyData sp && sp.Value != null)
                {
                    // Vanilla rows leave Name2.Texts empty — match that.
                    foreach (var inner in sp.Value)
                    {
                        if (inner is ArrayPropertyData ap && inner.Name.ToString() == "Texts")
                        {
                            ap.Value = Array.Empty<PropertyData>();
                            ap.ArrayType = FName.FromString(asset, "TextProperty");
                            break;
                        }
                    }
                }
            }
        }

        int added = 0, skipped = 0;
        foreach (var entry in spec.Cast<JObject>())
        {
            string copyFrom = (string)entry["copy_from"]!;
            string newId    = (string)entry["new_id"]!;
            string displaySource = (string?)entry["display_source"] ?? copyFrom;
            // display_name + display_table: use OUR StringTable and the new
            // cargo's own key, instead of borrowing the source cargo's label.
            string? displayTable = (string?)entry["display_table"];
            if (!string.IsNullOrWhiteSpace(displayTable)) displaySource = newId;
            if (!existingRows.TryGetValue(copyFrom, out var srcRow))
            {
                Console.Error.WriteLine($"  copy_from '{copyFrom}' not found in Cargos table — skipped");
                continue;
            }
            if (existingRows.ContainsKey(newId))
            {
                skipped++;
                continue;
            }
            var newRow = (StructPropertyData)DeepClone(srcRow);
            EnsureName(asset, newId);
            newRow.Name = FName.FromString(asset, newId);
            SetDisplayName(newRow, displaySource, displayTable);
            string label = $"+cargo {newId} (clone of {copyFrom})";
            Console.WriteLine($"  {label}");
            // Iterate every non-reserved key on the entry as a row-field
            // override. JSON keys must match the cargo row's UE field
            // names exactly (PaymentPer1Km, BasePayment, SpawnProbability,
            // PaymentSqrtRatio, bUseDamage, etc.) so the mod author writes
            // values that map 1:1 to a vanilla-cargo dump.
            foreach (var prop in entry.Properties())
            {
                if (IsReservedKey(prop.Name)) continue;
                SetField(newRow, prop.Name, prop.Value, newId);
            }
            table.Table.Data.Add(newRow);
            existingRows[newId] = newRow;
            added++;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(dstPath)!);
        asset.Write(dstPath);
        Console.WriteLine($"  Wrote {dstPath} ({added} new, {skipped} dedup)");
        return 0;
    }

    // Build a mod-shipped BP class from a vanilla BP source: load the source
    // (where UAssetAPI has its schema in mappings, so the CDO parses as
    // NormalExport), mutate the CDO's ProductionConfigs to the supplied
    // recipes, save, then byte-rename the source class name to the target
    // name in the saved bytes (preserves file offsets — both names must be
    // the same length).
    // Args:
    //   --src-uasset path to vanilla BP .uasset
    //   --dst-uasset path to write the mod BP .uasset (and matching .uexp)
    //   --src-class  e.g. "Farm_Corn_C"
    //   --dst-class  e.g. "ModFarmTr_C" (must be the same length as src,
    //                including the trailing _C)
    //   --recipes    path to JSON array of recipe specs
    //   --mappings   usmap
    // MT reads ProductionConfigs from the BP CDO only — instance overrides
    // are silently ignored, so this is the only path that actually changes
    // a delivery point's behavior.
    private static int MutateBpCdo(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        string srcUasset = f["src-uasset"];
        string dstUasset = f["dst-uasset"];
        string srcClass  = f["src-class"];
        string dstClass  = f["dst-class"];
        // Strip trailing _C for the byte-rename — we replace the bare class
        // name everywhere it appears, which catches "Farm_Corn", "Farm_Corn_C",
        // "Default__Farm_Corn_C", and the package-name string in references.
        string srcShort = srcClass.EndsWith("_C") ? srcClass[..^2] : srcClass;
        string dstShort = dstClass.EndsWith("_C") ? dstClass[..^2] : dstClass;
        if (srcShort.Length != dstShort.Length)
        {
            Console.Error.WriteLine($"  byte-rename needs equal length: '{srcShort}' ({srcShort.Length}) vs '{dstShort}' ({dstShort.Length})");
            return 1;
        }
        var recipes = (JArray)JToken.Parse(File.ReadAllText(f["recipes"]));

        var asset = new UAsset(srcUasset, EngineVer, mappings);
        string cdoName = "Default__" + srcClass;
        int cdoIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i].ObjectName.ToString() == cdoName) { cdoIdx = i; break; }
        if (cdoIdx < 0) { Console.Error.WriteLine($"  CDO {cdoName} not found in {srcUasset}"); return 1; }
        if (asset.Exports[cdoIdx] is not NormalExport cdo)
        { Console.Error.WriteLine("  CDO is not a NormalExport — schema missing for src-class?"); return 1; }

        var newProd = BuildProductionConfigs(recipes, asset);
        int existing = -1;
        for (int i = 0; i < cdo.Data.Count; i++)
            if (cdo.Data[i].Name.ToString() == "ProductionConfigs") { existing = i; break; }

        bool appendMode = f.ContainsKey("append-recipes");
        if (appendMode && existing >= 0
            && cdo.Data[existing] is ArrayPropertyData prevArr
            && prevArr.Value != null)
        {
            // Concatenate vanilla + new recipes so the modified DP keeps
            // its original recipes AND also accepts/produces the boosted
            // variants. Used when mod-overriding vanilla DPs to flow
            // boosted-clone cargos through their normal mission graph.
            var combined = new PropertyData[prevArr.Value.Length + newProd.Value.Length];
            Array.Copy(prevArr.Value, 0, combined, 0, prevArr.Value.Length);
            Array.Copy(newProd.Value, 0, combined, prevArr.Value.Length, newProd.Value.Length);
            // Re-number array entries (Name field is the index).
            for (int i = 0; i < combined.Length; i++)
                if (combined[i] is StructPropertyData spd)
                    spd.Name = FName.FromString(asset, i.ToString());
            prevArr.Value = combined;
            Console.WriteLine($"  Appended {newProd.Value.Length} recipe(s) to {cdoName} (kept {prevArr.Value.Length - newProd.Value.Length} vanilla)");
        }
        else if (existing >= 0)
        {
            cdo.Data[existing] = newProd;
            Console.WriteLine($"  Replaced ProductionConfigs on {cdoName}");
        }
        else
        {
            cdo.Data.Add(newProd);
            Console.WriteLine($"  Added ProductionConfigs to {cdoName}");
        }

        Directory.CreateDirectory(Path.GetDirectoryName(dstUasset)!);
        // Regenerate PackageGuid so multiple byte-clones of the same source
        // BP don't share an identity — UE's loader treats same-GUID
        // packages as duplicates and silently drops all but the first,
        // which is why a 2nd cloned delivery point would fail to spawn.
        // EXCEPTION: when we're shipping a mod-override of a vanilla DP
        // (src-class == dst-class), keep the original PackageGuid so the
        // pak override semantics stay intact.
        if (srcClass != dstClass)
            asset.PackageGuid = Guid.NewGuid();
        // Save to dst path first so UAssetAPI handles offsets cleanly. Then
        // byte-rename the source class in both .uasset and .uexp.
        asset.Write(dstUasset);
        var needle  = System.Text.Encoding.ASCII.GetBytes(srcShort);
        var replace = System.Text.Encoding.ASCII.GetBytes(dstShort);
        foreach (var ext in new[] { ".uasset", ".uexp" })
        {
            string p = Path.ChangeExtension(dstUasset, ext);
            if (!File.Exists(p)) continue;
            var bytes = File.ReadAllBytes(p);
            int hits = 0;
            for (int i = 0; i <= bytes.Length - needle.Length; i++)
            {
                bool ok = true;
                for (int j = 0; j < needle.Length; j++) if (bytes[i + j] != needle[j]) { ok = false; break; }
                if (ok) { Array.Copy(replace, 0, bytes, i, replace.Length); hits++; i += needle.Length - 1; }
            }
            File.WriteAllBytes(p, bytes);
            Console.WriteLine($"  {Path.GetFileName(p)}: byte-renamed {hits} occurrence(s) of '{srcShort}'");
        }
        return 0;
    }

    // Build a ProductionConfigs ArrayPropertyData for instance-level override
    // of MTDeliveryPoint's recipe table. Each recipe is a partial
    // MTProductionConfig — fields not specified fall back to struct defaults.
    private static ArrayPropertyData BuildProductionConfigs(JArray recipes, UAsset dst)
    {
        EnsureName(dst, "ProductionConfigs");
        EnsureName(dst, "MTProductionConfig");
        EnsureName(dst, "InputCargos");
        EnsureName(dst, "OutputCargos");
        EnsureName(dst, "InputCargoTypes");
        EnsureName(dst, "OutputCargoTypes");
        EnsureName(dst, "EDeliveryCargoType");
        EnsureName(dst, "ProductionSpeedMultiplier");
        EnsureName(dst, "ProductionTimeSeconds");
        EnsureName(dst, "StructProperty");
        EnsureName(dst, "NameProperty");
        EnsureName(dst, "IntProperty");
        EnsureName(dst, "EnumProperty");

        MapPropertyData BuildCargoMap(string fieldName, JObject entries)
        {
            var map = new MapPropertyData(FName.FromString(dst, fieldName))
            {
                KeyType   = FName.FromString(dst, "NameProperty"),
                ValueType = FName.FromString(dst, "IntProperty"),
            };
            foreach (var kv in entries)
            {
                EnsureName(dst, kv.Key);
                var k = new NamePropertyData(FName.FromString(dst, fieldName))
                    { Value = FName.FromString(dst, kv.Key) };
                var v = new IntPropertyData(FName.FromString(dst, fieldName))
                    { Value = (int)kv.Value! };
                map.Value.Add(k, v);
            }
            return map;
        }
        // Cargo-type filter: enum-keyed map. JSON form is either a flat
        // array ["LargePackage", "Log"] (count defaults to 1) or an object
        // {"LargePackage": 1, "Log": 2}.
        MapPropertyData BuildCargoTypeMap(string fieldName, JToken types)
        {
            var map = new MapPropertyData(FName.FromString(dst, fieldName))
            {
                KeyType   = FName.FromString(dst, "EnumProperty"),
                ValueType = FName.FromString(dst, "IntProperty"),
            };
            void Add(string typeName, int cnt)
            {
                string fq = "EDeliveryCargoType::" + typeName;
                EnsureName(dst, fq);
                var k = new EnumPropertyData(FName.FromString(dst, fieldName))
                    { Value = FName.FromString(dst, fq) };
                var v = new IntPropertyData(FName.FromString(dst, fieldName))
                    { Value = cnt };
                map.Value.Add(k, v);
            }
            if (types is JArray arr)
                foreach (var t in arr) Add((string)t!, 1);
            else if (types is JObject obj)
                foreach (var kv in obj) Add(kv.Key, (int)kv.Value!);
            return map;
        }

        var configs = new PropertyData[recipes.Count];
        for (int i = 0; i < recipes.Count; i++)
        {
            var r = (JObject)recipes[i];
            var cfg = new StructPropertyData(
                FName.FromString(dst, i.ToString()),
                FName.FromString(dst, "MTProductionConfig"))
            {
                Value = new List<PropertyData>(),
            };
            if (r["inputs"] is JObject ins && ins.Count > 0)
                cfg.Value.Add(BuildCargoMap("InputCargos", ins));
            if (r["outputs"] is JObject outs && outs.Count > 0)
                cfg.Value.Add(BuildCargoMap("OutputCargos", outs));
            if (r["input_types"] is JToken intypes && intypes.Type != JTokenType.Null)
                cfg.Value.Add(BuildCargoTypeMap("InputCargoTypes", intypes));
            if (r["output_types"] is JToken outtypes && outtypes.Type != JTokenType.Null)
                cfg.Value.Add(BuildCargoTypeMap("OutputCargoTypes", outtypes));
            if (r["speed"] != null)
                cfg.Value.Add(new FloatPropertyData(FName.FromString(dst, "ProductionSpeedMultiplier"))
                    { Value = (float)r["speed"]! });
            if (r["time_seconds"] != null)
                cfg.Value.Add(new FloatPropertyData(FName.FromString(dst, "ProductionTimeSeconds"))
                    { Value = (float)r["time_seconds"]! });
            configs[i] = cfg;
        }
        return new ArrayPropertyData(FName.FromString(dst, "ProductionConfigs"))
        {
            ArrayType = FName.FromString(dst, "StructProperty"),
            Value     = configs,
        };
    }

    private static byte[] MakeCStringExtras(string s)
    {
        var b = System.Text.Encoding.UTF8.GetBytes(s);
        var ms = new MemoryStream();
        var bw = new BinaryWriter(ms);
        bw.Write((uint)(b.Length + 1)); // count including null
        bw.Write(b);
        bw.Write((byte)0);
        return ms.ToArray();
    }

    // Decode the first few LayerCellsMapping keys + cross-reference the pointed
    // LayerCell's GridCells[0] -> RuntimeLevelStreamingCell -> RuntimeCellData
    // to extract Position, so we can reverse-engineer the int64 key packing.
    private static int DecodeLayerKeys(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        int hashIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var cls = asset.Exports[i].ClassIndex.IsImport() ? asset.Exports[i].ClassIndex.ToImport(asset).ObjectName.ToString() : "";
            if (cls == "WorldPartitionRuntimeSpatialHash") { hashIdx = i; break; }
        }
        var hash = (NormalExport)asset.Exports[hashIdx];
        var grids = hash.Data.OfType<ArrayPropertyData>().First(a => a.Name.ToString() == "StreamingGrids");
        int gridIdx = f.TryGetValue("grid", out var gs) ? int.Parse(gs) : 0;
        int levelIdx = f.TryGetValue("level", out var ls) ? int.Parse(ls) : 0;
        int limit = f.TryGetValue("limit", out var lim) ? int.Parse(lim) : 10;

        var sgrid = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)grids.Value[gridIdx];
        var gridName = ((UAssetAPI.PropertyTypes.Objects.NamePropertyData)sgrid.Value.First(p => p.Name.ToString() == "GridName")).Value.ToString();
        var cellSize = ((UAssetAPI.PropertyTypes.Objects.IntPropertyData)sgrid.Value.First(p => p.Name.ToString() == "CellSize")).Value;
        var gridLevels = (ArrayPropertyData)sgrid.Value.First(p => p.Name.ToString() == "GridLevels");
        var lvl = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)gridLevels.Value[levelIdx];
        var layerCells = (ArrayPropertyData)lvl.Value.First(p => p.Name.ToString() == "LayerCells");
        var mapping = (UAssetAPI.PropertyTypes.Objects.MapPropertyData)lvl.Value.First(p => p.Name.ToString() == "LayerCellsMapping");

        Console.WriteLine($"Grid={gridName} CellSize={cellSize} level={levelIdx} LayerCells={layerCells.Value.Length} mapEntries={mapping.Value.Count}");
        int shown = 0;
        foreach (var kv in mapping.Value)
        {
            if (shown++ >= limit) break;
            long key = ((UAssetAPI.PropertyTypes.Objects.Int64PropertyData)kv.Key).Value;
            int val = ((UAssetAPI.PropertyTypes.Objects.IntPropertyData)kv.Value).Value;
            // fetch the cell referenced via layerCells[val] -> GridCells[0] -> CellDataSpatialHash
            var layerCellStruct = (UAssetAPI.PropertyTypes.Structs.StructPropertyData)layerCells.Value[val];
            var gridCells = (ArrayPropertyData)layerCellStruct.Value.First(p => p.Name.ToString() == "GridCells");
            int cellExpIdx = ((UAssetAPI.PropertyTypes.Objects.ObjectPropertyData)gridCells.Value[0]).Value.Index;
            var cellExp = asset.Exports[cellExpIdx - 1];
            // RuntimeCellData object ref is on cellExp.Data
            double px = 0, py = 0, ext = 0;
            if (cellExp is NormalExport cne)
            {
                var rcd = cne.Data.OfType<UAssetAPI.PropertyTypes.Objects.ObjectPropertyData>().FirstOrDefault(p => p.Name.ToString() == "RuntimeCellData");
                if (rcd != null)
                {
                    var rcdExp = (NormalExport)asset.Exports[rcd.Value.Index - 1];
                    var pos = rcdExp.Data.OfType<UAssetAPI.PropertyTypes.Structs.StructPropertyData>().FirstOrDefault(p => p.Name.ToString() == "Position");
                    if (pos != null && pos.Value.Count > 0 && pos.Value[0] is UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp)
                    {
                        px = vp.Value.X; py = vp.Value.Y;
                    }
                    var extF = rcdExp.Data.OfType<UAssetAPI.PropertyTypes.Objects.FloatPropertyData>().FirstOrDefault(p => p.Name.ToString() == "Extent");
                    if (extF != null) ext = extF.Value;
                }
            }
            int gridX = (int)Math.Floor(px / (ext * 2));
            int gridY = (int)Math.Floor(py / (ext * 2));
            Console.WriteLine($"  key=0x{key:X16} ({key,20}) -> layerIdx={val,5}  pos=({px,12:F0},{py,12:F0}) ext={ext,6}  guessed grid=({gridX,4},{gridY,4})");
        }
        return 0;
    }

    private static int DumpStreamingGridsCmd(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        int hashIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var cls = asset.Exports[i].ClassIndex.IsImport() ? asset.Exports[i].ClassIndex.ToImport(asset).ObjectName.ToString() : "";
            if (cls == "WorldPartitionRuntimeSpatialHash") { hashIdx = i; break; }
        }
        if (hashIdx < 0) { Console.Error.WriteLine("No RuntimeSpatialHash"); return 1; }
        var hash = (NormalExport)asset.Exports[hashIdx];
        var grids = hash.Data.OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name.ToString() == "StreamingGrids");
        if (grids == null) { Console.Error.WriteLine("No StreamingGrids"); return 1; }
        Console.WriteLine($"StreamingGrids: Array of {grids.ArrayType?.Value}, count={grids.Value.Length}");
        for (int g = 0; g < grids.Value.Length; g++)
        {
            var sp = grids.Value[g] as UAssetAPI.PropertyTypes.Structs.StructPropertyData;
            if (sp == null) { Console.WriteLine($"  [{g}] ?? {grids.Value[g].GetType().Name}"); continue; }
            Console.WriteLine($"  [{g}] Struct {sp.StructType?.Value} ({sp.Value.Count} fields):");
            foreach (var field in sp.Value)
            {
                DumpField(field, "      ");
            }
        }
        return 0;
    }

    // ----------------------------------------------------------------------
    // CLONE-BATCH: load dst cell ONCE, clone N source actors into it (each
    // with its own source .umap + slot + target coords), save dst ONCE.
    // Avoids the integrity drift caused by N separate load/save cycles.
    //
    // --spec <json> with array of:
    //   { "source_umap": "...", "source_actor": "...",
    //     "x": N, "y": N, "z": N,
    //     "pitch": N?, "yaw": N?, "roll": N?,
    //     "slot": N?, "preload_bp": "..." | null, "label": "..." }
    // ----------------------------------------------------------------------
    // Fused: registers N new cells in Jeju_World.umap AND runs N clone-batches
    // on target cell .umaps — ONE mappings load for the entire BP phase
    // (mappings parse ~30s each was the last remaining redundancy in step 5).
    // Spec: {
    //   "main-in":  "<Jeju_World.umap path>",
    //   "main-out": "<Jeju_World.umap path>",
    //   "register": [ ...register-cells-batch spec... ],  // may be empty
    //   "clone":    [ ...clone-super-batch spec... ],     // may be empty
    // }
    // Set LoadingRange on one named streaming grid. Raising it makes WP keep
    // cells resident further out, which is the only lever for "see further" —
    // instance cull distance can't help when the whole cell is unloaded.
    // Costs memory: the resident cell count grows with the square of this.
    private static void SetGridLoadingRange(UAsset asset, string gridName, float range)
    {
        int hashIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var ci = asset.Exports[i].ClassIndex;
            var cls = ci.IsImport() ? ci.ToImport(asset).ObjectName.ToString() : "";
            if (cls == "WorldPartitionRuntimeSpatialHash") { hashIdx = i; break; }
        }
        if (hashIdx < 0) { Console.WriteLine("  loading-range: no RuntimeSpatialHash"); return; }
        var grids = ((NormalExport)asset.Exports[hashIdx]).Data
            .OfType<ArrayPropertyData>().FirstOrDefault(a => a.Name.ToString() == "StreamingGrids");
        if (grids == null) { Console.WriteLine("  loading-range: no StreamingGrids"); return; }
        foreach (var g in grids.Value)
        {
            if (g is not StructPropertyData sp) continue;
            var nameProp = sp.Value.OfType<NamePropertyData>().FirstOrDefault(p => p.Name.ToString() == "GridName");
            if (nameProp == null || nameProp.Value.ToString() != gridName) continue;
            var lr = sp.Value.OfType<FloatPropertyData>().FirstOrDefault(p => p.Name.ToString() == "LoadingRange");
            if (lr == null) { Console.WriteLine($"  loading-range: '{gridName}' has no LoadingRange"); return; }
            Console.WriteLine($"  LoadingRange '{gridName}': {lr.Value} -> {range}");
            lr.Value = range;
            return;
        }
        Console.WriteLine($"  loading-range: grid '{gridName}' not found");
    }

    private static int RegisterAndClone(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        var cfg = (JObject)JToken.Parse(File.ReadAllText(f["spec"]));
        string mainIn  = (string)cfg["main-in"]!;
        string mainOut = (string)cfg["main-out"]!;
        var reg = (JArray?)cfg["register"] ?? new JArray();
        var clo = (JArray?)cfg["clone"]    ?? new JArray();

        if (reg.Count > 0)
        {
            var asset = new UAsset(mainIn, EngineVer, mappings);
            // Optional: widen WP's streaming radius. Vanilla MainGrid is
            // LoadingRange=25600 (256 m) over CellSize=12800 — fine for
            // sparse vanilla content, far too short once every cell carries
            // foliage, because a cell's worth of trees appears ~256 m ahead
            // of a moving vehicle. Applied once here, on the small map.
            if (cfg["loading-range"] != null)
            {
                double lr = (double)cfg["loading-range"]!;
                if (lr > 0) SetGridLoadingRange(asset, "MainGrid", (float)lr);
            }
            foreach (var entry in reg)
            {
                var flags = new Dictionary<string, string>();
                foreach (var prop in ((JObject)entry).Properties())
                    flags[prop.Name] = prop.Value.ToString();
                RegisterOneCell(asset, flags);
            }
            asset.Write(mainOut);
            Console.WriteLine($"  Wrote {mainOut} ({reg.Count} cells registered)");
        }

        foreach (var job in clo)
        {
            string dstPath = (string)job["dst-cell"]!;
            string outPath = (string)job["output"]!;
            var specArr = (JArray)job["spec"]!;
            Console.WriteLine($"  -- cell {Path.GetFileName(dstPath)} ({specArr.Count} clone(s))");
            CloneBatchBody(mappings, specArr, dstPath, outPath);
        }
        return 0;
    }

    // Run clone-batch over MANY cells in one process. Input JSON is an array of
    // {dst-cell, output, spec} objects. The big MotorTown.usmap mappings file
    // is loaded once — subprocess startup + mappings parse was the dominant
    // cost of calling clone-batch N times.
    private static int CloneSuperBatch(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        var jobs = JArray.Parse(File.ReadAllText(f["spec"]));
        int n = 0;
        foreach (var job in jobs)
        {
            string dstPath = (string)job["dst-cell"]!;
            string outPath = (string)job["output"]!;
            var specArr = (JArray)job["spec"]!;
            Console.WriteLine($"  -- cell {Path.GetFileName(dstPath)} ({specArr.Count} clone(s))");
            CloneBatchBody(mappings, specArr, dstPath, outPath);
            n++;
        }
        Console.WriteLine($"clone-super-batch: processed {n} cell(s)");
        return 0;
    }

    private static int CloneBatch(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        string dstPath = f["dst-cell"];
        string outPath = f["output"];
        string specPath = f["spec"];
        var specArr = JArray.Parse(File.ReadAllText(specPath));
        return CloneBatchBody(mappings, specArr, dstPath, outPath);
    }

    private static int CloneBatchBody(Usmap mappings, JArray specArr, string dstPath, string outPath)
    {

        // Pre-load all BP .uasset files once into the shared mappings so
        // schema lookups succeed during cloning. preload_bp may be a single
        // path or semicolon-separated list (used when BP wrappers spawn
        // inner BPs via ChildActorComponents, both schemas must be loaded).
        var preloads = new HashSet<string>();
        foreach (var s in specArr)
        {
            var p = (string?)s["preload_bp"];
            if (string.IsNullOrEmpty(p)) continue;
            foreach (var path in p.Split(';'))
                if (!string.IsNullOrWhiteSpace(path)) preloads.Add(path);
        }
        foreach (var p in preloads)
        {
            try { _ = new UAsset(p, EngineVer, mappings); Console.WriteLine($"  Preloaded BP schema {Path.GetFileName(p)}"); }
            catch (Exception ex) { Console.Error.WriteLine($"  preload failed {p}: {ex.Message}"); }
        }

        var dst = new UAsset(dstPath, EngineVer, mappings);

        // Cache source assets (reload once per unique source file)
        var srcCache = new Dictionary<string, UAsset>();
        int dstLevelIdx = -1;
        for (int i = 0; i < dst.Exports.Count; i++)
            if (dst.Exports[i] is LevelExport) { dstLevelIdx = i; break; }
        if (dstLevelIdx < 0) throw new InvalidOperationException("No LevelExport in dst");
        int dstLevelNum = dstLevelIdx + 1;

        var replaceOps = new List<(int slot, int newActorNum)>();
        // Bus stops asking to be wired to a terminal -- resolved after the
        // loop, when every stop's export index is known.
        var busLinks = new List<(int actorNum, string terminal)>();

        for (int idx = 0; idx < specArr.Count; idx++)
        {
            var s = specArr[idx];
            string srcPath = (string)s["source_umap"]!;
            string srcActorName = (string)s["source_actor"]!;
            double tx = (double)s["x"]!;
            double ty = (double)s["y"]!;
            double tz = (double)s["z"]!;
            double? tsx = (double?)s["scale_x"];
            double? tsy = (double?)s["scale_y"];
            double? tsz = (double?)s["scale_z"];
            double? tPitch = (double?)s["pitch"];
            double? tYaw   = (double?)s["yaw"];
            double? tRoll  = (double?)s["roll"];

            if (!srcCache.TryGetValue(srcPath, out var src))
            {
                src = new UAsset(srcPath, EngineVer, mappings);
                srcCache[srcPath] = src;
            }

            // Locate source actor
            int srcIdx = -1;
            for (int i = 0; i < src.Exports.Count; i++)
                if (src.Exports[i].ObjectName.ToString().Contains(srcActorName)) { srcIdx = i; break; }
            if (srcIdx < 0)
            {
                Console.Error.WriteLine($"  [{idx}] source actor '{srcActorName}' not found");
                continue;
            }
            int srcActorNum = srcIdx + 1;
            var srcActor = src.Exports[srcIdx];

            // BFS: transitive closure of exports the clone brings along.
            // (a) direct children via OuterIndex, always.
            // (b) ObjectProperty refs into the source package — skipped when
            //     RECURSE_REFS is false; in that case the cloned ref becomes
            //     null (FPackageIndex 0) and UE respawns ChildActor targets
            //     from the class archetype at runtime.
            bool mainInject = (bool?)s["main_inject"] ?? false;
            // Main-inject mode: src and dst are the same package, so refs to
            // sibling actors (e.g. InputInventoryShare → other delivery
            // points) stay valid via pass-through in RemapIdx. Recursing
            // into them would duplicate them as new actors and conflict
            // with the originals.
            bool recurseRefs = !mainInject
                && !("1" == Environment.GetEnvironmentVariable("CLONE_NO_RECURSE_REFS"));
            var cloneSet = new List<int> { srcIdx };
            var seen = new HashSet<int> { srcIdx };
            void AddRefsFromProp(PropertyData p)
            {
                if (!recurseRefs) return;
                if (p is ObjectPropertyData op && op.Value != null)
                {
                    int idxRef = op.Value.Index;
                    if (idxRef > 0 && idxRef - 1 < src.Exports.Count && !seen.Contains(idxRef - 1))
                    {
                        var tgt = src.Exports[idxRef - 1];
                        // Never recurse into the Level itself or package-level stuff
                        if (tgt is LevelExport) return;
                        seen.Add(idxRef - 1);
                        cloneSet.Add(idxRef - 1);
                    }
                }
                else if (p is ArrayPropertyData ap && ap.Value != null)
                    foreach (var inner in ap.Value) AddRefsFromProp(inner);
                else if (p is StructPropertyData sp2 && sp2.Value != null)
                    foreach (var inner in sp2.Value) AddRefsFromProp(inner);
            }
            for (int qi = 0; qi < cloneSet.Count; qi++)
            {
                int srcExpZero = cloneSet[qi];
                // (a) direct children
                int srcExpOne = srcExpZero + 1;
                for (int i = 0; i < src.Exports.Count; i++)
                {
                    if (src.Exports[i].OuterIndex.Index == srcExpOne && !seen.Contains(i))
                    { seen.Add(i); cloneSet.Add(i); }
                }
                // (b) Property refs in Data (NormalExport only)
                if (src.Exports[srcExpZero] is NormalExport nexp)
                    foreach (var p in nexp.Data) AddRefsFromProp(p);
            }

            int newActorNum = dst.Exports.Count + 1;
            if ((string?)s["bus_link"] is string blTerm && blTerm.Length > 0)
                busLinks.Add((newActorNum, blTerm));
            // Assign new indices in cloneSet order. cloneSet[0] = actor.
            var idxMap = new Dictionary<int, int>();  // 1-based src -> 1-based dst
            for (int k = 0; k < cloneSet.Count; k++)
                idxMap[cloneSet[k] + 1] = newActorNum + k;
            // Legacy aliases used below
            var srcChildren = cloneSet.Skip(1).ToList();
            int[] newChildNums = Enumerable.Range(1, cloneSet.Count - 1).Select(k => newActorNum + k).ToArray();

            var importRemap = new Dictionary<int, int>();
            int RemapImport(int srcImportIdx1Based)
            {
                int zero = -srcImportIdx1Based - 1;
                if (importRemap.TryGetValue(zero, out var cached)) return cached;
                var simp = src.Imports[zero];
                int outer = simp.OuterIndex.Index;
                int mappedOuter = outer < 0 ? RemapImport(outer) : 0;
                string objName = simp.ObjectName.ToString();
                string className = simp.ClassName.ToString();
                string classPkg  = simp.ClassPackage.ToString();
                int dstIdx = -1;
                for (int i = 0; i < dst.Imports.Count; i++)
                {
                    var di = dst.Imports[i];
                    if (di.ObjectName.ToString() == objName && di.ClassName.ToString() == className && di.OuterIndex.Index == mappedOuter)
                    { dstIdx = -(i + 1); break; }
                }
                if (dstIdx == -1)
                {
                    EnsureName(dst, objName); EnsureName(dst, className); EnsureName(dst, classPkg);
                    dst.Imports.Add(new UAssetAPI.Import(classPkg, className, new FPackageIndex(mappedOuter), objName, simp.bImportOptional, dst));
                    dstIdx = -dst.Imports.Count;
                }
                importRemap[zero] = dstIdx;
                return dstIdx;
            }
            // For main-injection src and dst are the same package — imports
            // are identical so pass them through (avoids creating duplicate
            // import entries). Export refs still go through idxMap; refs to
            // sibling actors we didn't clone get nulled rather than pointing
            // at source-side runtime state.
            bool srcEqDst = ((bool?)s["main_inject"] ?? false);
            int RemapIdx(int i)
            {
                if (i == 0) return 0;
                if (i > 0)
                {
                    if (idxMap.TryGetValue(i, out var mapped)) return mapped;
                    if (i - 1 < src.Exports.Count && src.Exports[i - 1] is LevelExport) return dstLevelNum;
                    if (srcEqDst) return i;  // sibling persistent-level actor — keep ref valid
                    return 0;
                }
                if (srcEqDst) return i;
                return RemapImport(i);
            }
            // UAssetAPI's PropertyData.Clone() is MemberwiseClone → shallow.
            // For StructPropertyData the .Value List<PropertyData> is the SAME
            // reference as source's. If we later mutate refs inside those
            // structs (e.g. RemapPropRefs recursing through Array/Struct),
            // we corrupt the source and any subsequent clone of the same
            // source sees the mutated state. Recursive deep-clone fixes it.
            // Re-bind an FName to the destination package. Clone() keeps
            // FNames bound to the SOURCE asset (Asset + source NameMap
            // index); written into a DIFFERENT package (a WP cell) those
            // indices point at the wrong/out-of-range NameMap slot, which
            // the engine dereferences as a garbage pointer -> world-load
            // EXCEPTION_ACCESS_VIOLATION. Reading .Value (still src-bound)
            // yields the correct string; we rebuild the FName against dst,
            // which adds the string to dst's NameMap and fixes the index.
            FName RebaseName(FName f)
            {
                if (f == null || f.IsDummy) return f;
                string s;
                try { s = f.Value?.Value; } catch { return f; }
                if (string.IsNullOrEmpty(s)) return f;
                return new FName(dst, s, f.Number);
            }
            PropertyData DeepCloneProp(PropertyData p)
            {
                var c = (PropertyData)p.Clone();
                c.Name = RebaseName(c.Name);
                switch (c)
                {
                    case NamePropertyData npd:   npd.Value = RebaseName(npd.Value); break;
                    case EnumPropertyData epd:
                        epd.Value = RebaseName(epd.Value);
                        epd.EnumType = RebaseName(epd.EnumType);
                        epd.InnerType = RebaseName(epd.InnerType);
                        break;
                    case BytePropertyData bpd:
                        bpd.EnumType  = RebaseName(bpd.EnumType);
                        bpd.EnumValue = RebaseName(bpd.EnumValue);
                        break;
                    case StructPropertyData spd2: spd2.StructType = RebaseName(spd2.StructType); break;
                    case ArrayPropertyData apd:   apd.ArrayType   = RebaseName(apd.ArrayType);   break;
                    case MapPropertyData mpd:
                        mpd.KeyType   = RebaseName(mpd.KeyType);
                        mpd.ValueType = RebaseName(mpd.ValueType);
                        break;
                }
                if (c is StructPropertyData scp && scp.Value != null)
                    scp.Value = scp.Value.Select(DeepCloneProp).ToList();
                else if (c is ArrayPropertyData acp && acp.Value != null)
                    acp.Value = acp.Value.Select(DeepCloneProp).ToArray();
                else if (c is MapPropertyData mcp && mcp.Value != null)
                {
                    var nm = new UAssetAPI.UnrealTypes.TMap<PropertyData, PropertyData>();
                    foreach (var kv in mcp.Value) nm.Add(DeepCloneProp(kv.Key), DeepCloneProp(kv.Value));
                    mcp.Value = nm;
                }
                return c;
            }
            Export DeepClone(Export e)
            {
                Export d;
                if (e is NormalExport ne)
                {
                    d = new NormalExport
                    {
                        Data = ne.Data.Select(DeepCloneProp).ToList(),
                        ObjectGuid = ne.ObjectGuid,
                        SerializationControl = ne.SerializationControl,
                        Operation = ne.Operation,
                        HasLeadingFourNullBytes = ne.HasLeadingFourNullBytes,
                    };
                }
                else if (e is RawExport re)
                {
                    d = new RawExport { Data = re.Data != null ? (byte[])re.Data.Clone() : Array.Empty<byte>() };
                }
                else throw new InvalidOperationException($"Unsupported {e.GetType().Name}");
                d.Asset = dst;
                string objName = e.ObjectName.ToString();
                EnsureName(dst, objName);
                d.ObjectName = FName.FromString(dst, objName);
                d.ClassIndex    = new FPackageIndex(RemapIdx(e.ClassIndex.Index));
                d.SuperIndex    = new FPackageIndex(RemapIdx(e.SuperIndex.Index));
                d.TemplateIndex = new FPackageIndex(RemapIdx(e.TemplateIndex.Index));
                d.OuterIndex    = new FPackageIndex(RemapIdx(e.OuterIndex.Index));
                d.ObjectFlags = e.ObjectFlags;
                d.bForcedExport = e.bForcedExport;
                d.bNotForClient = e.bNotForClient; d.bNotForServer = e.bNotForServer;
                d.PackageGuid = e.PackageGuid; d.PackageFlags = e.PackageFlags;
                d.bNotAlwaysLoadedForEditorGame = e.bNotAlwaysLoadedForEditorGame;
                d.bIsAsset = e.bIsAsset; d.GeneratePublicHash = e.GeneratePublicHash;
                d.IsInheritedInstance = e.IsInheritedInstance;
                d.SerializationBeforeSerializationDependencies = e.SerializationBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIdx(x.Index))).ToList();
                d.CreateBeforeSerializationDependencies        = e.CreateBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIdx(x.Index))).ToList();
                d.SerializationBeforeCreateDependencies        = e.SerializationBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIdx(x.Index))).ToList();
                d.CreateBeforeCreateDependencies               = e.CreateBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIdx(x.Index))).ToList();
                d.Extras = e.Extras != null ? (byte[])e.Extras.Clone() : null;
                return d;
            }
            void RemapPropRefs(PropertyData p)
            {
                if (p is ObjectPropertyData op && op.Value != null)
                    op.Value = new FPackageIndex(RemapIdx(op.Value.Index));
                else if (p is ArrayPropertyData ap && ap.Value != null)
                    foreach (var inner in ap.Value) RemapPropRefs(inner);
                else if (p is StructPropertyData sp2 && sp2.Value != null)
                    foreach (var inner in sp2.Value) RemapPropRefs(inner);
            }

            // Clone every export in the closure. DeepClone preserves OuterIndex
            // via RemapIdx (which looks at idxMap); this works naturally for
            // both direct children (OuterIndex == srcActorNum -> newActorNum)
            // AND transitively-discovered refs whose Outer is PersistentLevel
            // or another cloned export.
            Export? newActor = null;
            for (int k = 0; k < cloneSet.Count; k++)
            {
                var cloned = DeepClone(src.Exports[cloneSet[k]]);
                if (k == 0)
                {
                    cloned.OuterIndex = new FPackageIndex(dstLevelNum);
                    newActor = cloned;
                    string label = (string?)s["label"] ?? $"{srcActor.ObjectName}_MOD";
                    int suffix = 0; string finalLabel = label;
                    while (dst.Exports.Any(e => e.ObjectName.ToString() == finalLabel))
                        finalLabel = $"{label}_{++suffix}";
                    cloned.ObjectName = FName.FromString(dst, finalLabel);
                    EnsureName(dst, finalLabel);
                }
                dst.Exports.Add(cloned);
            }

            // Optional: repoint the cloned actor at a NEW BP class shipped by
            // the mod (makes it a distinct delivery-point type rather than
            // another copy of the source's class). ClassIndex/TemplateIndex
            // are remapped to imports that resolve to /Game/<target_bp_path>.
            string? tgtPath  = (string?)s["target_bp_path"];
            string? tgtClass = (string?)s["target_bp_class"];
            // Hoisted so the child-component pass below can add the same arcs.
            int arcClsIdx = 0, arcTplIdx = 0;
            if (newActor != null && !string.IsNullOrEmpty(tgtPath) && !string.IsNullOrEmpty(tgtClass))
            {
                int srcClsZ = -srcActor.ClassIndex.Index - 1;
                int srcTplZ = -srcActor.TemplateIndex.Index - 1;
                var srcClsImp = src.Imports[srcClsZ];
                var srcTplImp = src.Imports[srcTplZ];
                int srcPkgZ  = -srcClsImp.OuterIndex.Index - 1;
                var srcPkgImp = src.Imports[srcPkgZ];

                // New package import (/Game/.../ModDrop_1)
                EnsureName(dst, tgtPath!);
                EnsureName(dst, srcPkgImp.ClassPackage.ToString());
                EnsureName(dst, srcPkgImp.ClassName.ToString());
                dst.Imports.Add(new UAssetAPI.Import(
                    srcPkgImp.ClassPackage.ToString(), srcPkgImp.ClassName.ToString(),
                    new FPackageIndex(0), tgtPath!, srcPkgImp.bImportOptional, dst));
                int newPkgIdx = -dst.Imports.Count;

                // New class import (ModDrop_1_C, outer = new package)
                EnsureName(dst, tgtClass!);
                EnsureName(dst, srcClsImp.ClassPackage.ToString());
                EnsureName(dst, srcClsImp.ClassName.ToString());
                dst.Imports.Add(new UAssetAPI.Import(
                    srcClsImp.ClassPackage.ToString(), srcClsImp.ClassName.ToString(),
                    new FPackageIndex(newPkgIdx), tgtClass!, srcClsImp.bImportOptional, dst));
                int newClsIdx = -dst.Imports.Count;

                // New template import (Default__ModDrop_1_C, classpkg = new path)
                string tplName = "Default__" + tgtClass;
                EnsureName(dst, tplName);
                dst.Imports.Add(new UAssetAPI.Import(
                    tgtPath!, tgtClass!,
                    new FPackageIndex(newPkgIdx), tplName, srcTplImp.bImportOptional, dst));
                int newTplIdx = -dst.Imports.Count;

                newActor.ClassIndex    = new FPackageIndex(newClsIdx);
                newActor.TemplateIndex = new FPackageIndex(newTplIdx);

                // EDL preload arcs. The cloned actor's dependency lists still
                // reference the SOURCE class/template imports (Farm_Corn_C),
                // remapped — but the actor's class is now Mod*_C. Without an
                // arc to the NEW class import, the event-driven loader may
                // create the actor before the rewritten BP package finishes
                // serializing -> LowLevelFatalError "request for <Class> but
                // it was still waiting for serialization" on world load.
                // (Latent bug; load-order luck masked it until the base-map
                // regen shifted ordering.) Add explicit arcs to the new class
                // + template imports so the BP package is always serialized
                // before the actor is created. The stale source-class arc is
                // left in place — harmless, that import still exists.
                newActor.SerializationBeforeCreateDependencies ??= new System.Collections.Generic.List<FPackageIndex>();
                if (!newActor.SerializationBeforeCreateDependencies.Any(d => d.Index == newClsIdx))
                    newActor.SerializationBeforeCreateDependencies.Add(new FPackageIndex(newClsIdx));
                if (!newActor.SerializationBeforeCreateDependencies.Any(d => d.Index == newTplIdx))
                    newActor.SerializationBeforeCreateDependencies.Add(new FPackageIndex(newTplIdx));
                arcClsIdx = newClsIdx;
                arcTplIdx = newTplIdx;
                Console.WriteLine($"  Rewrote actor class {srcClsImp.ObjectName} -> {tgtClass} ({tgtPath}) + EDL preload arc to new class");
            }
            // Remap prop refs on every newly-added export (they still hold
            // source-side FPackageIndex values until now).
            for (int k = 0; k < cloneSet.Count; k++)
            {
                int dstIdx = idxMap[cloneSet[k] + 1] - 1;
                if (dst.Exports[dstIdx] is NormalExport nc)
                    foreach (var p in nc.Data) RemapPropRefs(p);
            }

            // Normalize component Extras. Source-side Extras for primitive
            // components sometimes embed extra FPackageIndex values pointing
            // into the source package (observed 44-byte Extras with negative
            // import + positive export int32s). We can't safely remap those
            // bytes because we don't know the layout; since the engine
            // accepts the minimal SCS Extras pattern (16 bytes for primitives,
            // 4 bytes for scene-only components), force that shape on every
            // NON-actor cloned export so the dst has no dangling refs.
            // NO extra arcs on the child components. Adding them was tried
            // and made things worse rather than better.
            //
            // The reasoning was sound -- a component's archetype is the
            // like-named subobject of the class default object, so the CDO
            // must be serialized before the component is created, or the
            // load fatals with "had RF_NeedLoad when being set up as an
            // archetype". But the arcs did not deliver it. Vanilla children
            // carry SBCD=2, pointing at package-local EXPORTS; the added
            // pair pointed at IMPORTS and took them to 4, and the crash
            // simply moved to a different delivery point instead of going
            // away. Everything else was checked and matches vanilla exactly:
            // the cloned class package is arc-for-arc identical to its
            // source, it ships, the children have the same outers, and the
            // 688 CDO-subobject imports are the same on both sides.
            //
            // So the ordering problem is real and this is not the lever for
            // it. Removed rather than left in, because an arc table holding
            // index values the loader does not expect there is not a
            // harmless no-op to leave lying around while the real cause is
            // still open.

            for (int k = 1; k < cloneSet.Count; k++)  // skip k=0 (the actor itself)
            {
                int dstIdx = idxMap[cloneSet[k] + 1] - 1;
                var exp = dst.Exports[dstIdx];

                // Move the child's ARCHETYPE onto the new class's CDO.
                //
                // Rewriting the actor's class repointed the actor and left its
                // components behind: ConstructionSite2_MOD_1 became a
                // Mod979A7326D725B_C while its SceneComponent kept an archetype
                // whose outer was Default__ConstructionSite_C -- the vanilla
                // class. UE does not follow that stale import. It resolves the
                // archetype by NAME inside the actor's class, reaches
                // Default__Mod979A7326D725B_C:SceneComponent in a package
                // nothing forced to serialize, and fatals: "had RF_NeedLoad
                // when being set up as an archetype".
                //
                // This is why the earlier attempt failed. Arcs were added to
                // the class and template imports, which serializes the CDO but
                // not the CDO's SUBOBJECTS -- and the subobject is what the
                // archetype lookup lands on. The arc has to name the subobject
                // itself, which first requires an import for it to exist.
                if (arcTplIdx != 0 && exp.TemplateIndex.IsImport())
                {
                    var timp = dst.Imports[-exp.TemplateIndex.Index - 1];
                    if (timp.OuterIndex.IsImport() && timp.OuterIndex.Index != arcTplIdx
                        && dst.Imports[-timp.OuterIndex.Index - 1].ObjectName.ToString()
                               .StartsWith("Default__", StringComparison.Ordinal))
                    {
                        string subName = timp.ObjectName.ToString();
                        int subIdx = 0;
                        for (int q = 0; q < dst.Imports.Count; q++)
                            if (dst.Imports[q].OuterIndex.Index == arcTplIdx
                                && dst.Imports[q].ObjectName.ToString() == subName)
                            { subIdx = -(q + 1); break; }
                        if (subIdx == 0)
                        {
                            EnsureName(dst, subName);
                            EnsureName(dst, timp.ClassPackage.ToString());
                            EnsureName(dst, timp.ClassName.ToString());
                            dst.Imports.Add(new UAssetAPI.Import(
                                timp.ClassPackage.ToString(), timp.ClassName.ToString(),
                                new FPackageIndex(arcTplIdx), subName, timp.bImportOptional, dst));
                            subIdx = -dst.Imports.Count;
                        }
                        exp.TemplateIndex = new FPackageIndex(subIdx);
                        exp.SerializationBeforeCreateDependencies ??= new System.Collections.Generic.List<FPackageIndex>();
                        if (!exp.SerializationBeforeCreateDependencies.Any(d => d.Index == subIdx))
                            exp.SerializationBeforeCreateDependencies.Add(new FPackageIndex(subIdx));
                        Console.WriteLine($"    archetype: {subName} -> Default__{tgtClass}:{subName}");
                    }
                }

                if (exp is NormalExport ncn)
                {
                    // Inherited DefaultSubObjects (Box on a BP actor, Root etc.)
                    // use 4-byte extras — their source's Extras is already safe.
                    if (exp.IsInheritedInstance) continue;

                    // Keep the SOURCE's Extras whenever they carry nothing to
                    // remap. All-zero bytes hold no package indices, so copying
                    // them verbatim is exact -- and exact beats inferring a
                    // shape from a class name. BusStop_01's Box is a
                    // BoxComponent with FOUR zero bytes, not the sixteen the
                    // rule below assumes for anything primitive-shaped, and
                    // forcing sixteen made its export header claim twelve bytes
                    // more than the loader reads: "Serial size mismatch: Got
                    // 21, Expected 33". The normalization is still needed for
                    // the 44-byte extras that DO embed source-package indices;
                    // it just should not touch the ones that are plainly safe.
                    if (exp.Extras != null && exp.Extras.Length <= 16
                        && exp.Extras.All(b => b == 0))
                        continue;

                    string className = exp.ClassIndex.IsImport() ? exp.ClassIndex.ToImport(dst).ObjectName.ToString() : "";

                    // COMPONENTS ONLY. The 4-or-16 byte shape below is a fact
                    // about components, and applying it to anything else
                    // destroys data. A UModel keeps its entire BSP geometry in
                    // Extras -- 3610 bytes for a zone volume's box, with
                    // Data.Count=0 because UAssetAPI does not model UModel --
                    // so truncating it to 4 left the export declaring 10 bytes
                    // where the loader read 124, and the world load died on
                    // "Serial size mismatch: Got 124, Expected 10".
                    if (!className.EndsWith("Component", StringComparison.Ordinal))
                        continue;

                    bool isPrimitive = className.Contains("MeshComponent") || className == "BoxComponent"
                                       || className == "StaticMeshComponent" || className == "SkeletalMeshComponent"
                                       || className == "InstancedStaticMeshComponent";
                    if (isPrimitive)
                        ncn.Extras = new byte[] { 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0 };
                    else if (exp.Extras != null && exp.Extras.Length != 4)
                        ncn.Extras = new byte[] { 0, 0, 0, 0 };
                }
            }

            // Set location + rotation on the actor's ROOT component ONLY.
            //
            // The root component's RelativeLocation is the actor's world
            // position (the root has no parent, so relative == world). Every
            // OTHER scene component is attached beneath the root and carries a
            // SMALL relative offset; overwriting those with the absolute world
            // coord flings them ~1e6 units away from the actor and the meshes
            // render nowhere near the target — the "no actor at the gas
            // station" symptom. Simple actors (parking) only have a root with a
            // transform so the old set-on-every-child loop happened to work;
            // multi-component actors (FuelPump: 8 components) break.
            //
            // Resolve the root from the actor's RootComponent property (already
            // remapped to the new export index by RemapPropRefs above). Fall
            // back to a child named like a root, then — last resort — the old
            // behavior so we never silently skip positioning.
            int rootExportNum = -1;
            if (newActor is NormalExport rootProbe)
            {
                foreach (var p in rootProbe.Data)
                    if (p.Name.ToString() == "RootComponent"
                        && p is ObjectPropertyData rcop && rcop.Value != null && rcop.Value.IsExport())
                    { rootExportNum = rcop.Value.Index; break; }
            }
            if (rootExportNum < 0)
            {
                foreach (var n in newChildNums)
                {
                    string cn = dst.Exports[n - 1].ObjectName.ToString();
                    if (cn == "DefaultSceneRoot" || cn == "RootComponent" || cn == "Root" || cn == "Scene")
                    { rootExportNum = n; break; }
                }
            }
            void ApplyTransform(NormalExport nc)
            {
                bool setLoc = false, setRot = false, setScale = false;
                foreach (var p in nc.Data)
                {
                    // A zone is a unit box, sized entirely by scale: vanilla
                    // Gangjung is RelativeScale3D (1000, 1000, 500). Without
                    // this the clone inherits the source zone's footprint.
                    if (tsx != null && p.Name.ToString() == "RelativeScale3D"
                        && p is StructPropertyData ssc
                        && ssc.Value.Count > 0 && ssc.Value[0] is VectorPropertyData svp)
                    { svp.Value = new FVector(tsx.Value, tsy ?? tsx.Value, tsz ?? tsx.Value); setScale = true; }
                    if (p.Name.ToString() == "RelativeRotation" && p is StructPropertyData srot
                        && srot.Value.Count > 0 && srot.Value[0] is RotatorPropertyData rp)
                    { rp.Value = new FRotator(tPitch ?? rp.Value.Pitch, tYaw ?? rp.Value.Yaw, tRoll ?? rp.Value.Roll); setRot = true; }
                    if (p.Name.ToString() == "RelativeLocation" && p is StructPropertyData sloc
                        && sloc.Value.Count > 0 && sloc.Value[0] is VectorPropertyData vp)
                    { vp.Value = new FVector(tx, ty, tz); setLoc = true; }
                }
                // CREATE the property when the source didn't serialize one.
                // UE omits properties sitting at their default, so a source
                // actor whose root is at the origin has NO RelativeLocation to
                // overwrite — the clone then silently stays at (0,0,0) while
                // its map marker shows the intended spot. Every delivery point
                // landed at world origin this way.
                if (tsx != null && !setScale)
                {
                    EnsureName(dst, "RelativeScale3D");
                    EnsureName(dst, "Vector");
                    var svd = new VectorPropertyData(FName.FromString(dst, "RelativeScale3D"))
                    { Value = new FVector(tsx.Value, tsy ?? tsx.Value, tsz ?? tsx.Value) };
                    nc.Data.Add(new StructPropertyData(FName.FromString(dst, "RelativeScale3D"),
                                                       FName.FromString(dst, "Vector"))
                    { Value = new List<PropertyData> { svd } });
                    Console.WriteLine($"    (created RelativeScale3D on {nc.ObjectName} — source had none)");
                }
                if (!setLoc)
                {
                    EnsureName(dst, "RelativeLocation");
                    EnsureName(dst, "Vector");
                    var vpd = new VectorPropertyData(FName.FromString(dst, "RelativeLocation"))
                    { Value = new FVector(tx, ty, tz) };
                    var sp = new StructPropertyData(FName.FromString(dst, "RelativeLocation"),
                                                    FName.FromString(dst, "Vector"))
                    { Value = new List<PropertyData> { vpd } };
                    nc.Data.Add(sp);
                    Console.WriteLine($"    (created RelativeLocation on {nc.ObjectName} — source had none)");
                }
                if (!setRot && (tPitch.HasValue || tYaw.HasValue || tRoll.HasValue))
                {
                    EnsureName(dst, "RelativeRotation");
                    EnsureName(dst, "Rotator");
                    var rpd = new RotatorPropertyData(FName.FromString(dst, "RelativeRotation"))
                    { Value = new FRotator(tPitch ?? 0, tYaw ?? 0, tRoll ?? 0) };
                    var sp = new StructPropertyData(FName.FromString(dst, "RelativeRotation"),
                                                    FName.FromString(dst, "Rotator"))
                    { Value = new List<PropertyData> { rpd } };
                    nc.Data.Add(sp);
                }
            }
            if (rootExportNum > 0 && dst.Exports[rootExportNum - 1] is NormalExport rootNc)
            {
                ApplyTransform(rootNc);
                Console.WriteLine($"  Set transform on root component {rootNc.ObjectName} -> ({tx},{ty},{tz})");
            }
            else
            {
                // Couldn't identify a single root — apply to all (old behavior).
                Console.Error.WriteLine("  WARNING: no root component identified; setting transform on all children (may misplace nested components)");
                foreach (var n in newChildNums)
                    if (dst.Exports[n - 1] is NormalExport nc) ApplyTransform(nc);
            }
            // Regenerate FGuid in Extras
            if (newActor.Extras != null && newActor.Extras.Length >= 44)
            {
                int strlen = BitConverter.ToInt32(newActor.Extras, 4);
                if (strlen > 0 && 8 + strlen + 16 <= newActor.Extras.Length)
                    Guid.NewGuid().ToByteArray().CopyTo(newActor.Extras, 8 + strlen);
            }
            // Persistent-level actors carry their identity metadata directly
            // in Extras: count(1) + strlen + actor-label + FGuid(16) + pad(16).
            // Cell actors have empty Extras and use the level body's metadata
            // table instead.
            //
            // IMPORTANT: when the cloned source actor ALREADY has Extras (the
            // normal case for Jeju persistent actors — CornFarm_2, FuelPump2,
            // etc.), preserve it verbatim. DeepClone copied the source's exact
            // Extras (its byte length is precisely what the actor's class
            // deserializes) and the FGuid in it was already regenerated above.
            // Synthesizing a fresh blob of a DIFFERENT length here corrupts the
            // recomputed SerialSize: the engine reads the object's real bytes,
            // then trips on the leftover oversized Extras — "Serial size
            // mismatch: Got <real>, Expected <real+diff>" / ACCESS_VIOLATION on
            // world load (the FuelPump gas-station crash). Only synthesize when
            // the clone genuinely lacks metadata (a source whose identity lived
            // in the level body table, so its own Extras came through empty).
            if (mainInject && newActor != null
                && (newActor.Extras == null || newActor.Extras.Length == 0))
            {
                string label = newActor.ObjectName.ToString();
                var nameBytes = System.Text.Encoding.UTF8.GetBytes(label);
                var ms = new System.IO.MemoryStream();
                var bw = new System.IO.BinaryWriter(ms);
                bw.Write((uint)1);                       // count
                bw.Write((uint)(nameBytes.Length + 1));  // strlen incl. null
                bw.Write(nameBytes);
                bw.Write((byte)0);
                bw.Write(Guid.NewGuid().ToByteArray());  // FGuid (16)
                bw.Write(new byte[16]);                  // pad
                newActor.Extras = ms.ToArray();
                Console.WriteLine($"  Synthesized {newActor.Extras.Length}b actor-metadata Extras for {label} (clone had none)");
            }
            else if (mainInject && newActor != null)
            {
                Console.WriteLine($"  Preserved {newActor.Extras.Length}b vanilla actor-metadata Extras for {newActor.ObjectName}");
            }

            // Regenerate per-actor identity GUIDs so multiple clones don't
            // collide in MT's save-game / marker-registry tables. Vanilla
            // delivery points key save state + map markers by
            // DeliveryPointGuid; sharing one across clones means only one
            // actor "exists" to those subsystems.
            //
            // CRITICAL: GUIDs MUST be deterministic across deploys.
            // Random GUIDs caused the player's save (keyed by GUID-from-
            // first-run) to mismatch the GUID-from-second-run, crashing
            // load. Hash the actor's stable identity (target class name
            // when present, otherwise ObjectName) into the GUID.
            if (mainInject && newActor is NormalExport guidExp)
            {
                string seedKey = !string.IsNullOrEmpty(tgtClass)
                    ? tgtClass
                    : newActor.ObjectName.ToString();
                Guid SeedGuid(string subKey)
                {
                    using var sha = System.Security.Cryptography.SHA1.Create();
                    var bytes = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(
                        "MTLiveMap-DPGuid|" + seedKey + "|" + subKey));
                    var g = new byte[16];
                    Array.Copy(bytes, g, 16);
                    return new Guid(g);
                }
                guidExp.ObjectGuid = SeedGuid("ObjectGuid");
                int patched = 0;
                foreach (var p in guidExp.Data)
                {
                    string nm = p.Name.ToString();
                    if ((nm == "DeliveryPointGuid" || nm.EndsWith("Guid"))
                        && p is StructPropertyData spg
                        && spg.Value.Count > 0
                        && spg.Value[0] is UAssetAPI.PropertyTypes.Structs.GuidPropertyData gp)
                    {
                        gp.Value = SeedGuid(nm);
                        patched++;
                        Console.WriteLine($"  Regenerated {nm} GUID on {newActor.ObjectName} (deterministic)");
                    }
                }
                if (patched == 0)
                    Console.WriteLine($"  (no Guid struct properties found on actor — skipped GUID regen)");
            }

            // Optional in-game label override. The source actor's PointName
            // bytes inside its RawData carry the displayed name (e.g. vanilla
            // CornFarm_2 reads "NamwonCornFarm"). Byte-replace the matching
            // ASCII run with our custom label, zero-padded to the same length
            // — UE reads the FString to its declared length, displays up to
            // first null. Longer labels need full FString resize (TODO).
            // A zone identifies itself by ZoneKey, and MTZoneState is keyed
            // by it -- residents, NumResidents and BusTransportRate all hang
            // off that name. Cloning Gangjung's volume without renaming it
            // would give Arini a second volume claiming to BE Gangjung.
            string? zoneKey = (string?)s["zone_key"];
            if (!string.IsNullOrEmpty(zoneKey) && newActor is NormalExport zoneExp)
            {
                EnsureName(dst, zoneKey!);
                var zk = zoneExp.Data.FirstOrDefault(q => q.Name.ToString() == "ZoneKey");
                if (zk is NamePropertyData zkn)
                {
                    zkn.Value = FName.FromString(dst, zoneKey!);
                    Console.WriteLine($"  ZoneKey -> '{zoneKey}'");
                }
                else
                {
                    zoneExp.Data.Add(new NamePropertyData(FName.FromString(dst, "ZoneKey"))
                    { Value = FName.FromString(dst, zoneKey!) });
                    Console.WriteLine($"  ZoneKey -> '{zoneKey}' (created)");
                }
            }

            // The map outline is NOT the brush. TopViewLines is its own
            // world-space polygon, which is why a cloned zone kept drawing
            // Gangjung's shape over Arini however the volume was placed and
            // scaled. Redraw it as a rectangle around the zone's centre.
            double? outX = (double?)s["outline_x"];
            double? outY = (double?)s["outline_y"];
            if (outX != null && outY != null && newActor is NormalExport tvExp)
            {
                EnsureName(dst, "TopViewLines");
                EnsureName(dst, "Vector");
                EnsureName(dst, "StructProperty");
                // An explicit polygon wins over the rectangle. Vanilla zones are
                // irregular and tile against each other, so a plain box reads as
                // wrong next to them -- and the map label is drawn from this
                // outline, so shaping it is also how the label moves.
                var poly = s["outline_points"] as Newtonsoft.Json.Linq.JArray;
                var corners = poly != null && poly.Count >= 3
                    ? poly.Select(pt => (dx: (double)pt[0]! - tx, dy: (double)pt[1]! - ty)).ToArray()
                    : new (double dx, double dy)[] {
                        (-outX.Value, -outY.Value), ( outX.Value, -outY.Value),
                        ( outX.Value,  outY.Value), (-outX.Value,  outY.Value),
                    };
                // TopViewLines is SEGMENTS, stored as point PAIRS -- not a
                // polygon ring. Every vanilla zone has an even count (Jeju 8,
                // Gangjung 16, Gapa 24) and each pair's end is the next pair's
                // start, with the last closing back to the first. Writing four
                // corners as four points drew two opposite edges and left the
                // shape open down the middle.
                var edges = new List<(double dx, double dy)>();
                for (int c = 0; c < corners.Length; c++)
                {
                    edges.Add(corners[c]);
                    edges.Add(corners[(c + 1) % corners.Length]);
                }
                var pts = edges.Select(c => (PropertyData)new StructPropertyData(
                        FName.FromString(dst, "TopViewLines"), FName.FromString(dst, "Vector"))
                {
                    Value = new List<PropertyData> {
                        new VectorPropertyData(FName.FromString(dst, "TopViewLines"))
                        { Value = new FVector(tx + c.dx, ty + c.dy, tz) } }
                }).ToArray();

                var tvl = tvExp.Data.FirstOrDefault(q => q.Name.ToString() == "TopViewLines");
                if (tvl is ArrayPropertyData tva) { tva.Value = pts; }
                else
                {
                    tvExp.Data.Add(new ArrayPropertyData(FName.FromString(dst, "TopViewLines"))
                    { ArrayType = FName.FromString(dst, "StructProperty"), Value = pts });
                }
                Console.WriteLine($"  TopViewLines -> {corners.Length} corners / {pts.Length} points, "
                                + $"{outX.Value * 2 / 100000.0:0.#} x {outY.Value * 2 / 100000.0:0.#} km "
                                + $"around ({tx:0}, {ty:0})");
            }

            // Zone colour. Cloned from Gangjung, it drew in Gangjung's colour,
            // which is exactly wrong for telling two zones apart on a map.
            var zc = s["zone_color"] as Newtonsoft.Json.Linq.JArray;
            if (zc != null && zc.Count >= 3 && newActor is NormalExport zcExp)
            {
                EnsureName(dst, "ZoneColor");
                EnsureName(dst, "LinearColor");
                var lc = new LinearColorPropertyData(FName.FromString(dst, "ZoneColor"))
                {
                    Value = new FLinearColor((float)(double)zc[0]!, (float)(double)zc[1]!,
                                             (float)(double)zc[2]!,
                                             zc.Count > 3 ? (float)(double)zc[3]! : 1f)
                };
                var prior = zcExp.Data.FirstOrDefault(q => q.Name.ToString() == "ZoneColor");
                if (prior is StructPropertyData zsp) zsp.Value = new List<PropertyData> { lc };
                else
                    zcExp.Data.Add(new StructPropertyData(FName.FromString(dst, "ZoneColor"),
                                                         FName.FromString(dst, "LinearColor"))
                    { Value = new List<PropertyData> { lc } });
                Console.WriteLine($"  ZoneColor -> ({zc[0]}, {zc[1]}, {zc[2]})");
            }

            string? customLabel = (string?)s["actor_label"];
            if (!string.IsNullOrEmpty(customLabel) && newActor is NormalExport neLbl)
            {
                // NormalExport path: locate PointName (StructPropertyData of
                // type MTTextByTexts) and rewrite its Texts array to contain
                // a single TextProperty with HistoryType=None +
                // CultureInvariantString = our label. MoreTuning's trick —
                // bypasses the StringTable lookup and displays the inline
                // string verbatim.
                EnsureName(dst, "PointName");
                EnsureName(dst, "MTTextByTexts");
                EnsureName(dst, "Texts");
                EnsureName(dst, "TextProperty");
                TextPropertyData NewLabelText() => new TextPropertyData(FName.FromString(dst, "Texts"))
                {
                    HistoryType = TextHistoryType.None,
                    CultureInvariantString = new FString(customLabel),
                    Flags = ETextFlag.CultureInvariant,
                };

                // Unversioned serialization only writes properties whose value
                // differs from the class default, so WHICH name property a
                // vanilla instance carries varies by class: CornFarm_2 has both
                // MissionPointName and PointName, Warehouse_Ranch has only
                // PointName, and LogSupply_2 has only MissionPointName. Patching
                // one of them and warning about the other left every LogSupply
                // clone displaying its vanilla name in game. Patch whatever is
                // there, and synthesize PointName when it is absent, so the
                // label is a property of the framework and not of which
                // template a point happens to use.
                // A bus stop names itself with BusStopDisplayName, not with
                // any of the delivery-point properties. It also must NOT get a
                // synthesized PointName: MTBusStop has no such property, so the
                // fallback below would write a field the class never reads.
                StructPropertyData? pn = null;
                bool patchedAny = false, isBusStop = false;
                foreach (var p in neLbl.Data)
                {
                    string pnm = p.Name.ToString();
                    if (p is StructPropertyData sp && (pnm == "PointName" || pnm == "BusStopName"))
                    {
                        pn = sp;
                        if (pnm == "BusStopName") isBusStop = true;
                    }
                    else if (p is TextPropertyData mpn
                             && (pnm == "MissionPointName" || pnm == "BusStopDisplayName"
                                 || pnm == "AreaName"))
                    {
                        // Inline culture-invariant FText does not render in
                        // this MT build. Cargo rows went blank with it, and a
                        // bus stop shows "<MISSING STRING TABLE ENTRY>" -- so
                        // when a table is supplied, point at it instead. The
                        // delivery points keep the inline form: PointName is
                        // MoreTuning's trick and it does display.
                        string? lblTable = (string?)s["label_table"];
                        string? lblKey   = (string?)s["label_key"];
                        if (!string.IsNullOrEmpty(lblTable) && !string.IsNullOrEmpty(lblKey))
                        {
                            EnsureName(dst, lblTable!);
                            // A StringTable is only LOADED if some package
                            // imports it. TableId is an FName, not an object
                            // reference, so pointing text at a table imports
                            // nothing and the lookup finds an unloaded table:
                            // "<MISSING STRING TABLE ENTRY>", with the entry
                            // sitting right there in the shipped asset.
                            // Vanilla does exactly this -- Jeju_World carries
                            // /Game/DataAsset/StringTables/BusStop as a plain
                            // Package import that nothing references. Its
                            // presence is the load.
                            // Both halves, as vanilla has them: the package
                            // AND the StringTable object inside it. Jeju_World
                            // carries -6679 (package) and -10455 (the object,
                            // outered to it) for the vanilla BusStop table.
                            int dot = lblTable!.LastIndexOf('.');
                            string tblPkg = dot > 0 ? lblTable!.Substring(0, dot) : lblTable!;
                            string tblObj = dot > 0 ? lblTable!.Substring(dot + 1) : lblTable!;
                            int tblPkgIdx = FindOrAddImport(dst, tblPkg, 0,
                                                            "/Script/CoreUObject", "Package");
                            FindOrAddImport(dst, tblObj, tblPkgIdx,
                                            "/Script/Engine", "StringTable");
                            mpn.HistoryType = TextHistoryType.StringTableEntry;
                            mpn.Flags = 0;
                            mpn.Namespace = null;
                            mpn.TableId = FName.FromString(dst, lblTable!);
                            mpn.Value = new FString(lblKey!);
                            mpn.CultureInvariantString = null;
                            mpn.SourceFmt = null; mpn.Arguments = null; mpn.ArgumentsData = null;
                            Console.WriteLine($"  Patched {pnm} -> '{customLabel}' via {lblTable}[{lblKey}]");
                        }
                        else
                        {
                            mpn.HistoryType = TextHistoryType.None;
                            mpn.CultureInvariantString = new FString(customLabel);
                            mpn.Flags = ETextFlag.CultureInvariant;
                            Console.WriteLine($"  Patched {pnm} -> '{customLabel}'");
                        }
                        patchedAny = true;
                        if (pnm != "MissionPointName") isBusStop = true;   // no PointName synthesis
                    }
                }
                if (pn?.Value != null)
                {
                    foreach (var inner in pn.Value)
                    {
                        if (inner is ArrayPropertyData ap && inner.Name.ToString() == "Texts")
                        {
                            ap.Value = new PropertyData[] { NewLabelText() };
                            ap.ArrayType = FName.FromString(dst, "TextProperty");
                            Console.WriteLine($"  Patched PointName -> '{customLabel}'");
                            patchedAny = true;
                            break;
                        }
                    }
                }
                else if (!isBusStop)
                {
                    var texts = new ArrayPropertyData(FName.FromString(dst, "Texts"))
                    {
                        ArrayType = FName.FromString(dst, "TextProperty"),
                        Value = new PropertyData[] { NewLabelText() },
                    };
                    neLbl.Data.Add(new StructPropertyData(FName.FromString(dst, "PointName"))
                    {
                        StructType = FName.FromString(dst, "MTTextByTexts"),
                        Value = new List<PropertyData> { texts },
                    });
                    Console.WriteLine($"  Synthesized PointName -> '{customLabel}' (source had none)");
                    patchedAny = true;
                }
                if (!patchedAny)
                    Console.Error.WriteLine($"  actor_label: no name property could be written on {newActor.ObjectName}");
            }
            else if (!string.IsNullOrEmpty(customLabel) && newActor is RawExport rawAct
                && srcActor.Extras != null && srcActor.Extras.Length >= 8)
            {
                int strLen = BitConverter.ToInt32(srcActor.Extras, 4);
                if (strLen > 0 && 8 + strLen <= srcActor.Extras.Length)
                {
                    var srcLabelBytes = new byte[strLen - 1]; // drop null
                    Array.Copy(srcActor.Extras, 8, srcLabelBytes, 0, strLen - 1);
                    var newLabelBytes = System.Text.Encoding.ASCII.GetBytes(customLabel);
                    if (newLabelBytes.Length > srcLabelBytes.Length)
                    {
                        Console.Error.WriteLine(
                            $"  actor_label '{customLabel}' ({newLabelBytes.Length}) longer than source max ({srcLabelBytes.Length}) — skipped");
                    }
                    else
                    {
                        // Pad to match source label length so downstream
                        // bytes stay aligned.
                        var padded = new byte[srcLabelBytes.Length];
                        Array.Copy(newLabelBytes, padded, newLabelBytes.Length);
                        int pos = IndexOfSeq(rawAct.Data!, srcLabelBytes);
                        if (pos >= 0)
                        {
                            Array.Copy(padded, 0, rawAct.Data!, pos, padded.Length);
                            Console.WriteLine($"  Patched actor label '{System.Text.Encoding.ASCII.GetString(srcLabelBytes)}' -> '{customLabel}'");
                        }
                        else
                        {
                            Console.Error.WriteLine($"  actor_label: source label bytes not found in cloned RawData");
                        }
                        // Also rewrite the synthesized Extras so save-game
                        // metadata matches the displayed label.
                        if (newActor.Extras != null && newActor.Extras.Length >= 8)
                        {
                            int extStrLen = BitConverter.ToInt32(newActor.Extras, 4);
                            if (extStrLen > 0 && 8 + extStrLen <= newActor.Extras.Length)
                            {
                                var extPad = new byte[extStrLen - 1];
                                int copyN = Math.Min(newLabelBytes.Length, extPad.Length);
                                Array.Copy(newLabelBytes, extPad, copyN);
                                Array.Copy(extPad, 0, newActor.Extras, 8, extPad.Length);
                            }
                        }
                    }
                }
            }

            // Per-instance ProductionConfigs override. Spec field is a JSON
            // array of {inputs:{Name:Count}, outputs:{Name:Count}, speed:f,
            // time_seconds:f}. Whether MT honors instance overrides for this
            // BP property is an empirical question — first user of this code
            // path tells us.
            var recipes = (JArray?)s["production_recipes"];
            if (recipes != null && recipes.Count > 0 && newActor is NormalExport neAct)
            {
                neAct.Data.Add(BuildProductionConfigs(recipes, dst));
                Console.WriteLine($"  Added {recipes.Count} production_recipe override(s) on {newActor.ObjectName}");

                // MTDeliveryPoint exposes 51 properties and we had only ever
                // set ProductionConfigs, leaving every clone with whatever the
                // source corn farm happened to have. These three decide whether
                // the point can be traded with at all: a point that is neither
                // sender nor receiver, or that is not usable as a destination,
                // shows its map marker and then does nothing when you drive to
                // it -- exactly the "marker but no actor" symptom.
                foreach (var (prop, val) in new[] {
                             ("bIsSender", true), ("bIsReceiver", true),
                             ("bUseAsDestinationInteraction", true) })
                {
                    EnsureName(dst, prop);
                    bool already = false;
                    foreach (var p in neAct.Data)
                        if (p.Name.ToString() == prop && p is BoolPropertyData bp)
                        { bp.Value = val; already = true; break; }
                    if (!already)
                        neAct.Data.Add(new BoolPropertyData(FName.FromString(dst, prop)) { Value = val });
                }
                Console.WriteLine($"    set bIsSender / bIsReceiver / bUseAsDestinationInteraction on {newActor.ObjectName}");
                // Storage cap. A point that produces from thin air needs
                // somewhere to put the output: at MaxStorage 0 it makes nothing
                // and looks broken. Left unset the clone inherits the template
                // CDO's value, which varies wildly -- LogSupply_C says 20,
                // Farm_Corn_C does not set it at all.
                var capTok = s["output_storage_cap"];
                if (capTok != null && capTok.Type is JTokenType.Integer or JTokenType.Float)
                {
                    int cap = (int)capTok;
                    EnsureName(dst, "MaxStorage");
                    var cur = neAct.Data.FirstOrDefault(pp => pp.Name.ToString() == "MaxStorage");
                    if (cur is IntPropertyData ipd) ipd.Value = cap;
                    else neAct.Data.Add(new IntPropertyData(FName.FromString(dst, "MaxStorage")) { Value = cap });
                    Console.WriteLine($"    MaxStorage={cap} on {newActor.ObjectName}");
                }

            }

            // A DELIVERY POINT template is cloned for its map ICON and its
            // behaviour, never for the scenery its vanilla class happens to
            // carry (LiquidSupplier_C brings SM_Bld_Silo_Small_01, which is
            // why tanks appeared at every gas station). Dropping the cloned
            // child export does NOT remove it -- these are BP
            // construction-script components and UE rebuilds them from the
            // class at spawn -- so the only lever is a per-instance override.
            //
            // Opt-in, NOT default: fuel pumps, garages and parking spaces are
            // cloned precisely so their meshes show up. bp_registry sets this
            // for delivery points only.
            if ((bool?)s["hide_template_mesh"] == true)
            {
                int hidden = 0;
                foreach (var n in newChildNums)
                {
                    var child = dst.Exports[n - 1];
                    string ccls = child.ClassIndex.IsImport()
                        ? child.ClassIndex.ToImport(dst).ObjectName.ToString() : "";
                    if (ccls != "StaticMeshComponent" || child is not NormalExport cne) continue;
                    // "It is a StaticMeshComponent" is NOT the same question as
                    // "it is scenery". InteractionCube -- the volume the whole
                    // delivery point is interacted through -- is a
                    // StaticMeshComponent too, sharing the silo's class index
                    // exactly. Hiding it turned all 33 points into solid
                    // invisible blocks that could not be walked up to. Scenery
                    // follows UE's SM_ asset naming and functional components
                    // do not, so match on the name. Anything that fails the
                    // match just stays visible, which is the safe direction.
                    if (!child.ObjectName.ToString().StartsWith("SM_", StringComparison.Ordinal)) continue;

                    // Nulling StaticMesh is the whole fix on its own:
                    // UStaticMeshComponent::GetBodySetup() reads through the
                    // mesh, so no mesh means no geometry AND no collision, with
                    // no dependence on FBodyInstance profile fixup running in a
                    // cooked build. bVisible is belt and braces.
                    EnsureName(dst, "StaticMesh");
                    var sm = cne.Data.FirstOrDefault(p => p.Name.ToString() == "StaticMesh");
                    if (sm is ObjectPropertyData smo) smo.Value = new FPackageIndex(0);
                    else cne.Data.Add(new ObjectPropertyData(FName.FromString(dst, "StaticMesh"))
                    { Value = new FPackageIndex(0) });

                    EnsureName(dst, "bVisible");
                    var vis = cne.Data.FirstOrDefault(p => p.Name.ToString() == "bVisible");
                    if (vis is BoolPropertyData vbp) vbp.Value = false;
                    else cne.Data.Add(new BoolPropertyData(FName.FromString(dst, "bVisible")) { Value = false });
                    hidden++;
                }
                if (hidden > 0)
                    Console.WriteLine($"  Dropped {hidden} template scenery mesh(es) on {newActor.ObjectName}");
            }

            Console.WriteLine($"  [{idx}] cloned '{srcActorName}' -> #{newActorNum} ({srcChildren.Count} children, {dst.Imports.Count} imports total)");

            int? slot = (int?)s["slot"];
            if (slot.HasValue)
            {
                replaceOps.Add((slot.Value, newActorNum));
            }
            else
            {
                // An actor that never lands in the persistent level's Actors
                // array is NEVER SPAWNED, however perfect its export is. It
                // still registers its map marker, which is why the symptom
                // reads as "a marker with nothing underneath".
                //
                // This branch used to be `else if (... is LevelExport)`. The
                // first append converts the level export to a RawExport (see
                // AppendActorSlotInLevel), so from the second actor onward the
                // condition was false and every remaining actor fell through
                // with no slot and NO error: 2 nulls reused, 1 appended, 30
                // silently dropped out of 33 delivery points.
                int openSlot = -1;
                var reserved = new HashSet<int>(replaceOps.Select(o => o.slot));
                // Reusing an existing null is only possible while the level is
                // still typed; once it is raw we append, which works either way.
                if (dst.Exports[dstLevelIdx] is UAssetAPI.ExportTypes.LevelExport lvlForSlot)
                    for (int i = 0; i < lvlForSlot.Actors.Count; i++)
                        if (lvlForSlot.Actors[i].Index == 0 && !reserved.Contains(i))
                        { openSlot = i; break; }

                if (openSlot >= 0)
                {
                    replaceOps.Add((openSlot, newActorNum));
                    Console.WriteLine($"    [auto-slot] chose empty Actors[{openSlot}]");
                }
                else
                {
                    // Grows Actors.Count and the level body by 4 bytes.
                    int appendedSlot = AppendActorSlotInLevel(dst, dstPath, newActorNum);
                    if (appendedSlot >= 0)
                    {
                        if (dst.Exports[dstLevelIdx] is LevelExport typedLvlAdd)
                            typedLvlAdd.Actors.Add(new FPackageIndex(newActorNum));
                        Console.WriteLine($"    [auto-slot] appended new Actors[{appendedSlot}]");
                    }
                    else
                    {
                        Console.Error.WriteLine("    [auto-slot] WARNING: append failed; actor will NOT spawn");
                    }
                }
            }
        }

        // Apply Actors-list slot replacements ONCE at the end (single patch on the level body)
        if (replaceOps.Count > 0)
        {
            foreach (var (slot, idx2) in replaceOps)
                ReplaceActorSlotInLevel(dst, dstPath, slot, idx2);
        }

        // Null any Actor slot we didn't explicitly fill. ONLY for cells we
        // created from an L-1 template (whose unused slots reference unrelated
        // junk like container ships). Vanilla cells have real neighbors in
        // those slots — nulling would wipe legitimate actors.
        bool anyTemplateCell = specArr.Any(se => se["slot"] != null);
        if (anyTemplateCell && dst.Exports[dstLevelIdx] is UAssetAPI.ExportTypes.LevelExport lvl)
        {
            var used = new HashSet<int>(replaceOps.Select(o => o.slot));
            for (int i = 0; i < lvl.Actors.Count; i++)
            {
                if (used.Contains(i)) continue;
                int cur = lvl.Actors[i].Index;
                if (cur == 0) continue;
                ReplaceActorSlotInLevel(dst, dstPath, i, 0);
            }
        }

        // AdditionalDestinations: give a cloned stop somewhere to send people.
        //
        // A passenger's destination is chosen C++-side from the registered stop
        // pool, so stops dropped on an empty bridge hand out fares to the far
        // side of Jeju. This points each of them at the named terminal and at
        // its siblings, which is the only property in the game that says
        // anything about where a stop can send someone -- Ae-WolWarehouse is
        // the single vanilla user of it.
        //
        // ONE DIRECTION ONLY. The reverse (terminal -> our stops) would need a
        // property added to a vanilla actor, and vanilla actors survive the
        // build as byte-copied RawExports with no parsed property list to add
        // to. Ours are freshly built NormalExports, so they can point out but
        // nothing can point back.
        //
        // UNVERIFIED whether this RESTRICTS the destination pool or merely adds
        // to it. No vanilla stop uses it the way we are about to.
        if (busLinks.Count > 0)
        {
            EnsureName(dst, "AdditionalDestinations");
            EnsureName(dst, "ObjectProperty");
            var stopNums = busLinks.Select(b => b.actorNum).ToList();
            foreach (var (actorNum, terminal) in busLinks)
            {
                int termIdx = 0;
                for (int i = 0; i < dst.Exports.Count; i++)
                    if (dst.Exports[i].ObjectName.ToString() == terminal) { termIdx = i + 1; break; }
                if (termIdx == 0)
                {
                    Console.Error.WriteLine($"  bus_link: no actor named '{terminal}' in the map — stop #{actorNum} left unlinked");
                    continue;
                }
                if (dst.Exports[actorNum - 1] is not NormalExport stopExp)
                {
                    Console.Error.WriteLine($"  bus_link: stop #{actorNum} is not a NormalExport — left unlinked");
                    continue;
                }
                var targets = new List<int> { termIdx };
                targets.AddRange(stopNums.Where(n => n != actorNum));

                var arr = new ArrayPropertyData(FName.FromString(dst, "AdditionalDestinations"))
                { ArrayType = FName.FromString(dst, "ObjectProperty") };
                arr.Value = targets.Select(t => (PropertyData)new ObjectPropertyData(
                    FName.FromString(dst, "AdditionalDestinations"))
                { Value = new FPackageIndex(t) }).ToArray();

                var prior = stopExp.Data.FirstOrDefault(q => q.Name.ToString() == "AdditionalDestinations");
                if (prior != null) stopExp.Data.Remove(prior);
                stopExp.Data.Add(arr);
                Console.WriteLine($"  bus_link: stop #{actorNum} -> {terminal} (#{termIdx}) + {targets.Count - 1} sibling stop(s)");
            }
        }

        dst.Write(outPath);
        Console.WriteLine($"Wrote {outPath} ({dst.Exports.Count} exports, {dst.Imports.Count} imports)");
        return 0;
    }

    // ----------------------------------------------------------------------
    // CLONE-ACTOR: deep-copy an existing BP actor (+ its subobjects) to a new
    // location. Diagnostic: if a cloned real actor spawns, BP injection via
    // .umap patching works and our hand-crafted parking fields are wrong.
    // ----------------------------------------------------------------------
    private static int CloneActor(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        if (f.TryGetValue("preload-bp", out var preloadCsv))
        {
            foreach (var p in preloadCsv.Split(';'))
            {
                if (string.IsNullOrWhiteSpace(p)) continue;
                try { _ = new UAsset(p, EngineVer, mappings); Console.WriteLine($"  Preloaded BP schema from {p}"); }
                catch (Exception ex) { Console.Error.WriteLine($"  Failed BP load {p}: {ex.Message}"); }
            }
        }
        var asset = new UAsset(f["main"], EngineVer, mappings);
        var source = f["source"]; // name to match
        double tx = double.Parse(f["x"], System.Globalization.CultureInfo.InvariantCulture);
        double ty = double.Parse(f["y"], System.Globalization.CultureInfo.InvariantCulture);
        double tz = double.Parse(f["z"], System.Globalization.CultureInfo.InvariantCulture);
        double tp = f.TryGetValue("pitch", out var sp) ? double.Parse(sp, System.Globalization.CultureInfo.InvariantCulture) : 45;
        double ty_ = f.TryGetValue("yaw",  out var sy) ? double.Parse(sy, System.Globalization.CultureInfo.InvariantCulture) : 0;
        double tr = f.TryGetValue("roll",  out var sr) ? double.Parse(sr, System.Globalization.CultureInfo.InvariantCulture) : 30;

        // Find source actor by name pattern
        int srcIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var n = asset.Exports[i].ObjectName.ToString();
            if (n.Contains(source))
            {
                // Prefer actors whose OuterIndex points to PersistentLevel
                if (asset.Exports[i].OuterIndex.IsExport())
                {
                    var outerName = asset.Exports[i].OuterIndex.ToExport(asset).ObjectName.ToString();
                    if (outerName == "PersistentLevel") { srcIdx = i; break; }
                }
            }
        }
        if (srcIdx < 0) throw new InvalidOperationException($"No actor matching '{source}' with PersistentLevel outer found");

        var srcActor = asset.Exports[srcIdx];
        Console.WriteLine($"Source actor: #{srcIdx + 1} {srcActor.ObjectName} ({srcActor.GetType().Name})");

        // Find children whose OuterIndex points to srcActor (subobjects)
        int srcActorNum = srcIdx + 1;
        var srcChildren = new List<int>();
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            if (asset.Exports[i].OuterIndex.Index == srcActorNum) srcChildren.Add(i);
        }
        Console.WriteLine($"Children: {srcChildren.Count} (indices: {string.Join(",", srcChildren.Select(c => c + 1))})");

        // Grid multi-clone params
        int gridN    = f.TryGetValue("count",   out var gs) ? int.Parse(gs) : 1;
        int gridSide = f.TryGetValue("grid",    out var gg) ? int.Parse(gg) : (int)Math.Ceiling(Math.Sqrt(gridN));
        double pitch = f.TryGetValue("spacing", out var sp2) ? double.Parse(sp2, System.Globalization.CultureInfo.InvariantCulture) : 1000.0;
        var newActorNums = new List<int>();

        for (int n = 0; n < gridN; n++)
        {
            int gx = n % gridSide;
            int gy = n / gridSide;
            double ox = tx + gx * pitch;
            double oy = ty + gy * pitch;

            int newActorNum = asset.Exports.Count + 1;
            int[] newChildNums = srcChildren.Select((_, ix) => newActorNum + 1 + ix).ToArray();

            var clonedActor = CloneExport(srcActor, asset);
            clonedActor.ObjectName = FName.FromString(asset, $"{srcActor.ObjectName}_CLONE_MOD_{n}");
            EnsureName(asset, clonedActor.ObjectName.ToString());
            asset.Exports.Add(clonedActor);

            for (int i = 0; i < srcChildren.Count; i++)
            {
                var srcChild = asset.Exports[srcChildren[i]];
                var clonedChild = CloneExport(srcChild, asset);
                clonedChild.OuterIndex = new FPackageIndex(newActorNum);
                RemapDeps(clonedChild, srcActorNum, newActorNum, srcChildren, newChildNums);
                asset.Exports.Add(clonedChild);
            }
            RemapDeps(clonedActor, srcActorNum, newActorNum, srcChildren, newChildNums);

            if (clonedActor is NormalExport na)
            {
                foreach (var p in na.Data)
                {
                    if (p is ObjectPropertyData op && op.Value != null)
                    {
                        int idx = op.Value.Index;
                        int repl = RemapIndex(idx, srcActorNum, newActorNum, srcChildren, newChildNums);
                        if (repl != idx) op.Value = new FPackageIndex(repl);
                    }
                    if (p is ArrayPropertyData ap && ap.Value != null)
                    {
                        foreach (var inner in ap.Value)
                        {
                            if (inner is ObjectPropertyData iop && iop.Value != null)
                            {
                                int idx2 = iop.Value.Index;
                                int repl2 = RemapIndex(idx2, srcActorNum, newActorNum, srcChildren, newChildNums);
                                if (repl2 != idx2) iop.Value = new FPackageIndex(repl2);
                            }
                        }
                    }
                }
            }

            for (int i = 0; i < newChildNums.Length; i++)
            {
                var clonedChild = asset.Exports[newChildNums[i] - 1];
                if (clonedChild is NormalExport cne)
                {
                    foreach (var p in cne.Data)
                    {
                        if (p.Name.ToString() == "RelativeLocation" && p is StructPropertyData sloc
                            && sloc.Value.Count > 0 && sloc.Value[0] is VectorPropertyData vp)
                            vp.Value = new FVector(ox, oy, tz);
                        if (p.Name.ToString() == "RelativeRotation" && p is StructPropertyData srot
                            && srot.Value.Count > 0 && srot.Value[0] is RotatorPropertyData rp)
                            rp.Value = new FRotator(tp, ty_, tr);
                    }
                }
            }
            newActorNums.Add(newActorNum);
        }
        Console.WriteLine($"Cloned {gridN} actor(s). First #{newActorNums.First()}, last #{newActorNums.Last()}");

        PatchLevelExportAsRaw(asset, f["main"], newActorNums);

        Console.WriteLine($"Writing {f["output"]}");
        asset.Write(f["output"]);
        return 0;
    }

    private static int RemapIndex(int idx, int srcActor, int newActor, List<int> srcChildren, int[] newChildren)
    {
        if (idx == srcActor) return newActor;
        int pos = srcChildren.IndexOf(idx - 1);
        if (pos >= 0) return newChildren[pos];
        return idx;
    }

    private static void RemapDeps(Export exp, int srcActor, int newActor, List<int> srcChildren, int[] newChildren)
    {
        void Remap(List<FPackageIndex> list)
        {
            for (int i = 0; i < list.Count; i++)
            {
                int idx = list[i].Index;
                int repl = RemapIndex(idx, srcActor, newActor, srcChildren, newChildren);
                if (repl != idx) list[i] = new FPackageIndex(repl);
            }
        }
        Remap(exp.CreateBeforeSerializationDependencies);
        Remap(exp.SerializationBeforeCreateDependencies);
        Remap(exp.CreateBeforeCreateDependencies);
        Remap(exp.SerializationBeforeSerializationDependencies);
    }

    private static Export CloneExport(Export src, UAsset asset)
    {
        // Preserve parsed type (NormalExport) so property modifications (e.g. RelativeLocation)
        // still work on the clone. For RawExport sources, deep-copy the Data bytes.
        Export dst;
        if (src is NormalExport sne)
        {
            var cloneNe = new NormalExport
            {
                Data = sne.Data.Select(p => (PropertyData)p.Clone()).ToList(),
                ObjectGuid = sne.ObjectGuid,
                SerializationControl = sne.SerializationControl,
                Operation = sne.Operation,
                HasLeadingFourNullBytes = sne.HasLeadingFourNullBytes,
            };
            if (src is LevelExport) throw new InvalidOperationException("Cannot clone LevelExport via this path");
            dst = cloneNe;
        }
        else if (src is RawExport sre)
        {
            dst = new RawExport { Data = sre.Data != null ? (byte[])sre.Data.Clone() : Array.Empty<byte>() };
        }
        else
        {
            throw new InvalidOperationException($"Unsupported export type to clone: {src.GetType().Name}");
        }
        dst.Asset = asset;
        dst.ObjectName = src.ObjectName;
        dst.ClassIndex = src.ClassIndex;
        dst.SuperIndex = src.SuperIndex;
        dst.TemplateIndex = src.TemplateIndex;
        dst.OuterIndex = src.OuterIndex;
        dst.ObjectFlags = src.ObjectFlags;
        dst.bForcedExport = src.bForcedExport;
        dst.bNotForClient = src.bNotForClient;
        dst.bNotForServer = src.bNotForServer;
        dst.PackageGuid = src.PackageGuid;
        dst.PackageFlags = src.PackageFlags;
        dst.bNotAlwaysLoadedForEditorGame = src.bNotAlwaysLoadedForEditorGame;
        dst.bIsAsset = src.bIsAsset;
        dst.GeneratePublicHash = src.GeneratePublicHash;
        dst.IsInheritedInstance = src.IsInheritedInstance;
        dst.SerializationBeforeSerializationDependencies = new List<FPackageIndex>(src.SerializationBeforeSerializationDependencies);
        dst.CreateBeforeSerializationDependencies = new List<FPackageIndex>(src.CreateBeforeSerializationDependencies);
        dst.SerializationBeforeCreateDependencies = new List<FPackageIndex>(src.SerializationBeforeCreateDependencies);
        dst.CreateBeforeCreateDependencies = new List<FPackageIndex>(src.CreateBeforeCreateDependencies);
        dst.Extras = src.Extras != null ? (byte[])src.Extras.Clone() : null;
        // Actors' Extras have the layout: count(4) + strlen(4) + name+null + FGuid(16) + pad(16).
        // Clone must have its OWN FGuid, otherwise WP dedupes against the source.
        if (dst.Extras != null && dst.Extras.Length >= 44 && src.OuterIndex.IsExport()
            && src.OuterIndex.ToExport(asset) is LevelExport)
        {
            int count = BitConverter.ToInt32(dst.Extras, 0);
            int strlen = BitConverter.ToInt32(dst.Extras, 4);
            if (count == 1 && strlen > 0 && 8 + strlen + 16 <= dst.Extras.Length)
            {
                int guidOff = 8 + strlen;
                Guid.NewGuid().ToByteArray().CopyTo(dst.Extras, guidOff);
                Console.WriteLine($"  Regenerated FGuid in Extras for {dst.ObjectName}");
            }
        }
        return dst;
    }

    // Read the raw bytes of PersistentLevel's export body from disk, then
    // attempt to parse it step-by-step so we can see what follows NavListEnd.
    private static int DumpLevelExtras(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        int lvlIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { lvlIdx = i; break; }
        if (lvlIdx < 0) { Console.Error.WriteLine("No LevelExport"); return 1; }
        var lvl = (LevelExport)asset.Exports[lvlIdx];
        Console.WriteLine($"PersistentLevel #{lvlIdx + 1}  SerialOffset={lvl.SerialOffset} SerialSize={lvl.SerialSize}");
        Console.WriteLine($"  Actors.Count={lvl.Actors.Count}  ModelComps.Count={lvl.ModelComponents.Count}");
        Console.WriteLine($"  Extras.Length={lvl.Extras?.Length ?? 0}");

        // Read combined file bytes
        string mainPath = f["main"];
        string uexpPath = Path.ChangeExtension(mainPath, ".uexp");
        byte[] umapBytes = File.ReadAllBytes(mainPath);
        byte[] uexpBytes = File.Exists(uexpPath) ? File.ReadAllBytes(uexpPath) : Array.Empty<byte>();

        byte[] body = new byte[lvl.SerialSize];
        if (lvl.SerialOffset >= umapBytes.Length)
        {
            long start = lvl.SerialOffset - umapBytes.Length;
            Array.Copy(uexpBytes, start, body, 0, (int)lvl.SerialSize);
        }
        else
        {
            Array.Copy(umapBytes, lvl.SerialOffset, body, 0, (int)lvl.SerialSize);
        }

        // Use URL marker (int32 7 + "unreal\0") to locate the Actors list end.
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(body, marker);
        Console.WriteLine($"  URL marker at offset {urlOff}");
        if (urlOff < 0) return 0;
        int actorsCountOff = urlOff - 4 - lvl.Actors.Count * 4;
        Console.WriteLine($"  Computed Actors.Count offset: {actorsCountOff} (value={BitConverter.ToInt32(body, actorsCountOff)})");
        int afterActors = urlOff;
        Console.WriteLine($"  After Actors list: offset {afterActors} / {body.Length}");

        // Skip URL: Protocol (FString), Host (FString), Map (FString), Portal (FString), Op count+entries, Port int32, Valid int32
        int cur = afterActors;
        cur = SkipFString(body, cur, out var proto); Console.WriteLine($"    URL.Protocol=\"{proto}\"  ->{cur}");
        cur = SkipFString(body, cur, out var host);  Console.WriteLine($"    URL.Host=\"{host}\"       ->{cur}");
        cur = SkipFString(body, cur, out var map);   Console.WriteLine($"    URL.Map=\"{map}\"         ->{cur}");
        cur = SkipFString(body, cur, out var portal);Console.WriteLine($"    URL.Portal=\"{portal}\"   ->{cur}");
        int opCount = BitConverter.ToInt32(body, cur); cur += 4;
        for (int i = 0; i < opCount; i++) { cur = SkipFString(body, cur, out _); }
        cur += 8; // Port + Valid
        Console.WriteLine($"  After URL: offset {cur}");

        // Skip Model (FPackageIndex) + ModelComponents count + entries
        cur += 4;
        int mcCount = BitConverter.ToInt32(body, cur); cur += 4;
        Console.WriteLine($"  ModelComponents.Count={mcCount}");
        cur += mcCount * 4;
        cur += 4; // LevelScriptActor
        cur += 4; // NavListStart
        cur += 4; // NavListEnd
        Console.WriteLine($"  After NavListEnd: offset {cur}");
        Console.WriteLine($"  Remaining bytes (Extras per UAssetAPI): {body.Length - cur}");

        // Dump first 256 bytes after NavListEnd as hex + try to interpret counts
        int len = Math.Min(256, body.Length - cur);
        Console.WriteLine("  First bytes (hex):");
        for (int i = 0; i < len; i += 16)
        {
            Console.Write($"    {cur + i:X8}  ");
            for (int j = 0; j < 16 && i + j < len; j++)
                Console.Write($"{body[cur + i + j]:X2} ");
            Console.WriteLine();
        }
        // Probe: interpret the next 4 bytes as int32 — is it a count matching actors.Count or similar?
        for (int off = 0; off < Math.Min(64, body.Length - cur); off += 4)
        {
            int v = BitConverter.ToInt32(body, cur + off);
            if (v > 0 && v < 100_000)
                Console.WriteLine($"    int32@+{off}: {v}  (matches Actors? {v == lvl.Actors.Count})");
        }
        return 0;
    }

    private static int SkipFString(byte[] data, int pos, out string s)
    {
        int len = BitConverter.ToInt32(data, pos); pos += 4;
        if (len == 0) { s = ""; return pos; }
        if (len > 0) { s = System.Text.Encoding.ASCII.GetString(data, pos, len - 1); pos += len; }
        else { int bytes = (-len) * 2; s = System.Text.Encoding.Unicode.GetString(data, pos, bytes - 2); pos += bytes; }
        return pos;
    }

    // Scan all WorldPartitionRuntimeCellDataSpatialHash exports. For each,
    // read Position + Extent + GridName + HierarchicalLevel, then find the
    // cell that would contain target coords.
    // Load the cell bbox table once. Used by both single find-cell-wp and the
    // batch variant — parsing the big Jeju_World export list takes seconds, so
    // resolving N points should share one pass.
    private static List<(int idx, string name, FVector pos, double extent, string grid, int level, string cellOwner)>
        LoadCellBBoxes(UAsset asset)
    {
        var results = new List<(int idx, string name, FVector pos, double extent, string grid, int level, string cellOwner)>();
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            if (e is not NormalExport ne) continue;
            string cls = e.ClassIndex.IsImport() ? e.ClassIndex.ToImport(asset).ObjectName.ToString() : "";
            if (cls != "WorldPartitionRuntimeCellDataSpatialHash") continue;
            FVector pos = new(0, 0, 0);
            double extent = 0;
            string grid = "";
            int level = -1;
            foreach (var p in ne.Data)
            {
                if (p.Name.ToString() == "Position" && p is UAssetAPI.PropertyTypes.Structs.StructPropertyData sp &&
                    sp.Value.Count > 0 && sp.Value[0] is UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp)
                    pos = vp.Value;
                if (p.Name.ToString() == "Extent" && p is UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp)
                    extent = fp.Value;
                if (p.Name.ToString() == "GridName" && p is UAssetAPI.PropertyTypes.Objects.NamePropertyData np)
                    grid = np.Value.ToString();
                if (p.Name.ToString() == "HierarchicalLevel" && p is UAssetAPI.PropertyTypes.Objects.IntPropertyData ip)
                    level = ip.Value;
            }
            string owner = e.OuterIndex.IsExport() ? e.OuterIndex.ToExport(asset).ObjectName.ToString() : "";
            results.Add((i + 1, e.ObjectName.ToString(), pos, extent, grid, level, owner));
        }
        return results;
    }

    // Resolve many XY points against the WP cell bbox table in one load. Spec
    // is a JSON array of {x, y}; output is a JSON array aligned by index with
    // {containing:[{name, grid, level, owner}, ...]} per entry.
    private static int FindCellsBatch(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        var results = LoadCellBBoxes(asset);
        var points = JArray.Parse(File.ReadAllText(f["spec"]));
        var outArr = new JArray();
        foreach (var pt in points)
        {
            double px = (double)pt["x"]!;
            double py = (double)pt["y"]!;
            var cont = new JArray();
            foreach (var r in results)
            {
                if (px < r.pos.X - r.extent || px > r.pos.X + r.extent) continue;
                if (py < r.pos.Y - r.extent || py > r.pos.Y + r.extent) continue;
                cont.Add(new JObject {
                    ["name"] = r.name, ["grid"] = r.grid,
                    ["level"] = r.level, ["owner"] = r.cellOwner,
                });
            }
            outArr.Add(new JObject { ["containing"] = cont });
        }
        File.WriteAllText(f["output"], outArr.ToString());
        Console.WriteLine($"find-cells-batch: resolved {points.Count} point(s) against {results.Count} cells");
        return 0;
    }

    private static int FindCellWP(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        double tx = double.Parse(f["x"], System.Globalization.CultureInfo.InvariantCulture);
        double ty = double.Parse(f["y"], System.Globalization.CultureInfo.InvariantCulture);

        var results = LoadCellBBoxes(asset);
        Console.WriteLine($"Total cell-data exports: {results.Count}");

        // Find cells whose bbox contains target (2D, XY)
        var containing = results.Where(r =>
            tx >= r.pos.X - r.extent && tx <= r.pos.X + r.extent &&
            ty >= r.pos.Y - r.extent && ty <= r.pos.Y + r.extent).ToList();
        Console.WriteLine($"Cells containing ({tx}, {ty}): {containing.Count}");
        foreach (var c in containing.OrderBy(c => c.level))
            Console.WriteLine($"  #{c.idx} {c.name} grid={c.grid} L{c.level} pos=({c.pos.X},{c.pos.Y}) ext={c.extent} owner={c.cellOwner}");

        // Also print cells whose center is closest (nearest fallback)
        var nearest = results.Where(r => r.level <= 0)
            .OrderBy(r => Math.Pow(r.pos.X - tx, 2) + Math.Pow(r.pos.Y - ty, 2)).Take(10).ToList();
        Console.WriteLine("\nNearest 10 LEAF cells (L<=0) by center distance:");
        foreach (var c in nearest)
            Console.WriteLine($"  pos=({c.pos.X},{c.pos.Y}) ext={c.extent} L{c.level} grid={c.grid} owner={c.cellOwner}");
        return 0;
    }

    private static int InspectByClass(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        var needle = f["class"];
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            string cls = e.ClassIndex.IsImport() ? e.ClassIndex.ToImport(asset).ObjectName.ToString() : "";
            if (cls.Contains(needle, StringComparison.OrdinalIgnoreCase))
                Console.WriteLine($"  {i + 1}: {e.ObjectName} ({cls}) outer={e.OuterIndex.Index}");
        }
        return 0;
    }

    private static int InspectImports(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        var filter = f.TryGetValue("filter", out var fn) ? fn : null;
        Console.WriteLine($"Total imports: {asset.Imports.Count}");
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var imp = asset.Imports[i];
            string line = $"  -{i + 1}: {imp.ObjectName} (class={imp.ClassName}, outer={imp.OuterIndex.Index})";
            if (filter != null && !line.ToLower().Contains(filter.ToLower())) continue;
            Console.WriteLine(line);
        }
        return 0;
    }

    // ----------------------------------------------------------------------
    // CLONE-CROSS-CELL: copy an actor from a source cell .umap into a
    // destination cell .umap (both must be under the same Jeju_World package
    // so their imports share the WP runtime hash / BP classes).
    // ----------------------------------------------------------------------
    private static int CloneCrossCell(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);

        string sourceCellPath = f["source-cell"];
        string dstCellPath    = f["dst-cell"];
        string dstOutPath     = f["output"];
        string sourceActorName = f["source-actor"];
        double tx = double.Parse(f["x"], System.Globalization.CultureInfo.InvariantCulture);
        double ty = double.Parse(f["y"], System.Globalization.CultureInfo.InvariantCulture);
        double tz = double.Parse(f["z"], System.Globalization.CultureInfo.InvariantCulture);

        // Pre-load the parking BP so schemas are available in both assets.
        if (f.TryGetValue("preload-bp", out var pl))
        {
            foreach (var p in pl.Split(';'))
                try { _ = new UAsset(p, EngineVer, mappings); } catch { }
        }

        var src = new UAsset(sourceCellPath, EngineVer, mappings);
        var dst = new UAsset(dstCellPath, EngineVer, mappings);

        // Find source actor
        int srcIdx = -1;
        for (int i = 0; i < src.Exports.Count; i++)
        {
            if (src.Exports[i].ObjectName.ToString().Contains(sourceActorName)) { srcIdx = i; break; }
        }
        if (srcIdx < 0) throw new InvalidOperationException($"No actor matching '{sourceActorName}' in source cell");
        var srcActor = src.Exports[srcIdx];
        int srcActorNum = srcIdx + 1;
        Console.WriteLine($"Source #{srcActorNum} {srcActor.ObjectName} ({srcActor.GetType().Name})");

        // Find direct children (OuterIndex == srcActor)
        var srcChildren = new List<int>();
        for (int i = 0; i < src.Exports.Count; i++)
            if (src.Exports[i].OuterIndex.Index == srcActorNum) srcChildren.Add(i);
        Console.WriteLine($"  children: {srcChildren.Count} ({string.Join(",", srcChildren.Select(c => c + 1))})");

        // Build import remap: for every import used by src exports we're cloning,
        // find or add the equivalent in dst.
        var importRemap = new Dictionary<int, int>(); // src -1-based idx → dst (negative FPackageIndex)

        int RemapImport(int srcImportIdx1Based)
        {
            // srcImportIdx1Based is negative in FPackageIndex; convert to 0-based import array idx
            int zeroIdx = -srcImportIdx1Based - 1;
            if (zeroIdx < 0 || zeroIdx >= src.Imports.Count)
                throw new InvalidOperationException($"Bad import idx {srcImportIdx1Based}");
            if (importRemap.TryGetValue(zeroIdx, out var already)) return already;

            var simp = src.Imports[zeroIdx];
            int outer = simp.OuterIndex.Index;
            int mappedOuter = 0;
            if (outer < 0) mappedOuter = RemapImport(outer);
            // find or add equivalent import in dst
            string objName = simp.ObjectName.ToString();
            string className = simp.ClassName.ToString();
            string classPkg = simp.ClassPackage.ToString();
            int dstIdx = -1;
            for (int i = 0; i < dst.Imports.Count; i++)
            {
                var di = dst.Imports[i];
                if (di.ObjectName.ToString() == objName &&
                    di.ClassName.ToString() == className &&
                    di.OuterIndex.Index == mappedOuter)
                { dstIdx = -(i + 1); break; }
            }
            if (dstIdx == -1)
            {
                EnsureName(dst, objName); EnsureName(dst, className); EnsureName(dst, classPkg);
                var newImp = new UAssetAPI.Import(classPkg, className, new FPackageIndex(mappedOuter),
                                                  objName, simp.bImportOptional, dst);
                dst.Imports.Add(newImp);
                dstIdx = -dst.Imports.Count;
            }
            importRemap[zeroIdx] = dstIdx;
            return dstIdx;
        }

        // Find dst LevelExport for outer chain
        int dstLevelIdx = -1;
        for (int i = 0; i < dst.Exports.Count; i++)
            if (dst.Exports[i] is LevelExport) { dstLevelIdx = i; break; }
        if (dstLevelIdx < 0) throw new InvalidOperationException("No LevelExport in dst");
        int dstLevelNum = dstLevelIdx + 1;

        // Pre-plan new export indices in dst
        int newActorNum = dst.Exports.Count + 1;
        int[] newChildNums = srcChildren.Select((_, i) => newActorNum + 1 + i).ToArray();

        // Remap any FPackageIndex in the CLONED scope: src-actor → new-actor, src-children → new-children,
        // src-import (negative) → remapped dst-import, PersistentLevel → dst PersistentLevel.
        int RemapIndex(int srcIdx)
        {
            if (srcIdx == 0) return 0;
            if (srcIdx > 0)
            {
                if (srcIdx == srcActorNum) return newActorNum;
                int pos = srcChildren.IndexOf(srcIdx - 1);
                if (pos >= 0) return newChildNums[pos];
                // Points to some other export in src (unexpected for simple cases).
                // Check if it's PersistentLevel -> remap to dst PersistentLevel
                if (srcIdx - 1 < src.Exports.Count &&
                    src.Exports[srcIdx - 1] is LevelExport) return dstLevelNum;
                return 0; // drop ref — safe default
            }
            // negative: import
            return RemapImport(srcIdx);
        }

        Export DeepClone(Export e)
        {
            Export d;
            if (e is NormalExport ne)
            {
                d = new NormalExport
                {
                    Data = ne.Data.Select(p => (PropertyData)p.Clone()).ToList(),
                    ObjectGuid = ne.ObjectGuid,
                    SerializationControl = ne.SerializationControl,
                    Operation = ne.Operation,
                    HasLeadingFourNullBytes = ne.HasLeadingFourNullBytes,
                };
            }
            else if (e is RawExport re)
            {
                d = new RawExport { Data = re.Data != null ? (byte[])re.Data.Clone() : Array.Empty<byte>() };
            }
            else throw new InvalidOperationException($"Unsupported {e.GetType().Name}");
            d.Asset = dst;
            string objName = e.ObjectName.ToString();
            EnsureName(dst, objName);
            d.ObjectName = FName.FromString(dst, objName);
            d.ClassIndex    = new FPackageIndex(RemapIndex(e.ClassIndex.Index));
            d.SuperIndex    = new FPackageIndex(RemapIndex(e.SuperIndex.Index));
            d.TemplateIndex = new FPackageIndex(RemapIndex(e.TemplateIndex.Index));
            d.OuterIndex    = new FPackageIndex(RemapIndex(e.OuterIndex.Index));
            d.ObjectFlags = e.ObjectFlags;
            d.bForcedExport = e.bForcedExport;
            d.bNotForClient = e.bNotForClient;
            d.bNotForServer = e.bNotForServer;
            d.PackageGuid = e.PackageGuid;
            d.PackageFlags = e.PackageFlags;
            d.bNotAlwaysLoadedForEditorGame = e.bNotAlwaysLoadedForEditorGame;
            d.bIsAsset = e.bIsAsset;
            d.GeneratePublicHash = e.GeneratePublicHash;
            d.IsInheritedInstance = e.IsInheritedInstance;
            d.SerializationBeforeSerializationDependencies = e.SerializationBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.CreateBeforeSerializationDependencies = e.CreateBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.SerializationBeforeCreateDependencies = e.SerializationBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.CreateBeforeCreateDependencies = e.CreateBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.Extras = e.Extras != null ? (byte[])e.Extras.Clone() : null;
            return d;
        }

        // Clone actor then children
        var newActor = DeepClone(srcActor);
        // OuterIndex should be dst PersistentLevel
        newActor.OuterIndex = new FPackageIndex(dstLevelNum);
        string label = f.TryGetValue("label", out var lb) ? lb : $"{srcActor.ObjectName}_MOD";
        // Ensure unique in dst
        int suffix = 0;
        string finalLabel = label;
        while (dst.Exports.Any(e => e.ObjectName.ToString() == finalLabel))
            finalLabel = $"{label}_{++suffix}";
        newActor.ObjectName = FName.FromString(dst, finalLabel);
        EnsureName(dst, newActor.ObjectName.ToString());
        dst.Exports.Add(newActor);

        foreach (var ci in srcChildren)
        {
            var clonedChild = DeepClone(src.Exports[ci]);
            clonedChild.OuterIndex = new FPackageIndex(newActorNum);
            dst.Exports.Add(clonedChild);
        }

        // Remap inside NormalExport.Data (ObjectProperty refs, Array of refs, structs)
        void RemapPropRefs(PropertyData p)
        {
            if (p is ObjectPropertyData op && op.Value != null)
                op.Value = new FPackageIndex(RemapIndex(op.Value.Index));
            else if (p is ArrayPropertyData ap && ap.Value != null)
                foreach (var inner in ap.Value) RemapPropRefs(inner);
            else if (p is StructPropertyData sp && sp.Value != null)
                foreach (var inner in sp.Value) RemapPropRefs(inner);
        }

        if (newActor is NormalExport nae) foreach (var p in nae.Data) RemapPropRefs(p);
        foreach (var n in newChildNums)
        {
            if (dst.Exports[n - 1] is NormalExport nc) foreach (var p in nc.Data) RemapPropRefs(p);
        }

        // Set location on cloned Root (direct child named "Root" or "Scene")
        foreach (var n in newChildNums)
        {
            if (dst.Exports[n - 1] is NormalExport nc)
            {
                foreach (var p in nc.Data)
                {
                    if (p.Name.ToString() == "RelativeLocation" && p is StructPropertyData sloc
                        && sloc.Value.Count > 0 && sloc.Value[0] is VectorPropertyData vp)
                    {
                        vp.Value = new FVector(tx, ty, tz);
                        Console.WriteLine($"  Set RelativeLocation on {nc.ObjectName} -> ({tx},{ty},{tz})");
                    }
                }
            }
        }

        // Regenerate FGuid in actor's Extras
        if (newActor.Extras != null && newActor.Extras.Length >= 44)
        {
            int strlen = BitConverter.ToInt32(newActor.Extras, 4);
            if (strlen > 0 && 8 + strlen + 16 <= newActor.Extras.Length)
                Guid.NewGuid().ToByteArray().CopyTo(newActor.Extras, 8 + strlen);
        }

        // Two modes:
        //   --replace-slot N : replace Actors list index N with our new actor.
        //                      Body size unchanged. Use when the template cell
        //                      already has the right per-actor metadata for N+1
        //                      actors and we want to reuse one of its slots.
        //   (default)        : append to Actors list. Only safe when UE's
        //                      per-actor metadata doesn't care about count.
        if (f.TryGetValue("replace-slot", out var rs) && int.TryParse(rs, out var slotIdx))
        {
            ReplaceActorSlotInLevel(dst, dstCellPath, slotIdx, newActorNum);
        }
        else
        {
            PatchLevelExportAsRaw(dst, dstCellPath, new List<int> { newActorNum });
        }

        Console.WriteLine($"Writing {dstOutPath}");
        dst.Write(dstOutPath);
        Console.WriteLine($"Cloned actor #{newActorNum}, {srcChildren.Count} children at #{newActorNum + 1}..{newActorNum + srcChildren.Count}");
        return 0;
    }

    // Replace the Nth entry in PersistentLevel.Actors with newActorIdx, keeping
    // the Actors list length (and therefore the body size + per-actor metadata
    // layout) unchanged.
    // Append a new entry to the level's Actors list. Grows the level body by
    // 4 bytes (one FPackageIndex), increments the int32 count. UAssetAPI's
    // main Write recalculates SerialOffsets for subsequent exports based on
    // the new body length so the package layout stays consistent.
    // Returns the new slot index, or -1 on failure.
    private static int AppendActorSlotInLevel(UAsset asset, string originalPath, int newActorIdx)
    {
        int lvlIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { lvlIdx = i; break; }
        if (lvlIdx < 0)
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].ObjectName.ToString() == "PersistentLevel") { lvlIdx = i; break; }
        if (lvlIdx < 0) { Console.Error.WriteLine("  No PersistentLevel"); return -1; }
        var lvl = asset.Exports[lvlIdx];

        byte[] bodyIn;
        if (lvl is RawExport alreadyRaw && alreadyRaw.Data != null && alreadyRaw.Data.Length > 0)
            bodyIn = alreadyRaw.Data;
        else
        {
            byte[] umapBytes = File.ReadAllBytes(originalPath);
            string uexpPath = Path.ChangeExtension(originalPath, ".uexp");
            byte[] uexpBytes = File.Exists(uexpPath) ? File.ReadAllBytes(uexpPath) : Array.Empty<byte>();
            long off = lvl.SerialOffset;
            long sz  = lvl.SerialSize;
            bodyIn = new byte[sz];
            if (off >= umapBytes.Length)
                Array.Copy(uexpBytes, off - umapBytes.Length, bodyIn, 0, sz);
            else
                Array.Copy(umapBytes, off, bodyIn, 0, sz);
        }

        int expected = (lvl is LevelExport tlvl) ? tlvl.Actors.Count : -1;
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(bodyIn, marker);
        if (urlOff < 0) { Console.Error.WriteLine("  URL marker not found"); return -1; }
        int countOff = -1, count = 0;
        if (expected >= 0)
        {
            int probe = urlOff - 4 - expected * 4;
            if (probe >= 4 && BitConverter.ToInt32(bodyIn, probe) == expected)
            { countOff = probe; count = expected; }
        }
        if (countOff < 0)
        {
            for (int probe = urlOff - 4; probe >= 4; probe -= 4)
            {
                int c = BitConverter.ToInt32(bodyIn, probe);
                if (c > 0 && probe + 4 + c * 4 == urlOff && c > count) { countOff = probe; count = c; }
            }
        }
        if (countOff < 0) { Console.Error.WriteLine("  Actors count not located"); return -1; }

        // Insert 4 bytes at urlOff for the new slot, bump count by 1.
        var bodyOut = new byte[bodyIn.Length + 4];
        Array.Copy(bodyIn, 0, bodyOut, 0, urlOff);
        BitConverter.GetBytes(newActorIdx).CopyTo(bodyOut, urlOff);
        Array.Copy(bodyIn, urlOff, bodyOut, urlOff + 4, bodyIn.Length - urlOff);
        BitConverter.GetBytes(count + 1).CopyTo(bodyOut, countOff);
        int newSlot = count;
        Console.WriteLine($"  Appended Actors[{newSlot}]: 0 -> {newActorIdx} (count {count} -> {count + 1})");

        if (lvl is RawExport raw)
        {
            raw.Data = bodyOut;
            raw.SerialSize = bodyOut.Length;
        }
        else
        {
            if (lvl is LevelExport typedLvl)
                typedLvl.Actors.Add(new FPackageIndex(newActorIdx));
            var newRaw = new RawExport { Data = bodyOut, Asset = asset };
            CopyExportHeader(from: lvl, to: newRaw);
            newRaw.Extras = Array.Empty<byte>();
            newRaw.SerialSize = bodyOut.Length;
            newRaw.CreateBeforeSerializationDependencies.Add(new FPackageIndex(newActorIdx));
            asset.Exports[lvlIdx] = newRaw;
        }
        return newSlot;
    }

    private static void ReplaceActorSlotInLevel(UAsset asset, string originalPath, int slotIdx, int newActorIdx)
    {
        int lvlIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { lvlIdx = i; break; }
        if (lvlIdx < 0)
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].ObjectName.ToString() == "PersistentLevel") { lvlIdx = i; break; }
        if (lvlIdx < 0) { Console.Error.WriteLine("  No PersistentLevel"); return; }
        var lvl = asset.Exports[lvlIdx];

        byte[] bodyIn;
        if (lvl is RawExport alreadyRaw && alreadyRaw.Data != null && alreadyRaw.Data.Length > 0)
            bodyIn = alreadyRaw.Data;
        else
        {
            string uexpPath = Path.ChangeExtension(originalPath, ".uexp");
            byte[] umapBytes = File.ReadAllBytes(originalPath);
            byte[] uexpBytes = File.Exists(uexpPath) ? File.ReadAllBytes(uexpPath) : Array.Empty<byte>();
            long off = lvl.SerialOffset;
            long sz  = lvl.SerialSize;
            bodyIn = new byte[sz];
            if (off >= umapBytes.Length)
                Array.Copy(uexpBytes, off - umapBytes.Length, bodyIn, 0, sz);
            else
                Array.Copy(umapBytes, off, bodyIn, 0, sz);
        }

        // Locate URL marker and count. Use the typed LevelExport's Actors.Count
        // as the expected value if available — prevents false positives where
        // other int32 fields in the body happen to satisfy the "count * 4 +
        // 4 == urlOff" equation.
        int expected = (lvl is LevelExport tlvl) ? tlvl.Actors.Count : -1;
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(bodyIn, marker);
        if (urlOff < 0) { Console.Error.WriteLine("  URL marker not found"); return; }
        int countOff = -1, count = 0;
        if (expected >= 0)
        {
            int probe = urlOff - 4 - expected * 4;
            if (probe >= 4 && BitConverter.ToInt32(bodyIn, probe) == expected)
            { countOff = probe; count = expected; }
        }
        if (countOff < 0)
        {
            for (int probe = urlOff - 4; probe >= 4; probe -= 4)
            {
                int c = BitConverter.ToInt32(bodyIn, probe);
                if (c > 0 && probe + 4 + c * 4 == urlOff && c > count) { countOff = probe; count = c; }
            }
        }
        if (countOff < 0 || slotIdx >= count)
        {
            Console.Error.WriteLine($"  Slot {slotIdx} out of range (count={count})");
            return;
        }

        // Actors list starts immediately after count. Slot N is at (countOff + 4 + N*4).
        int slotOff = countOff + 4 + slotIdx * 4;
        int oldVal = BitConverter.ToInt32(bodyIn, slotOff);
        BitConverter.GetBytes(newActorIdx).CopyTo(bodyIn, slotOff);
        Console.WriteLine($"  Replaced Actors[{slotIdx}]: {oldVal} -> {newActorIdx}");

        if (lvl is RawExport raw)
        {
            raw.Data = bodyIn;
        }
        else
        {
            var newRaw = new RawExport { Data = bodyIn, Asset = asset };
            CopyExportHeader(from: lvl, to: newRaw);
            newRaw.Extras = Array.Empty<byte>();
            newRaw.CreateBeforeSerializationDependencies.Add(new FPackageIndex(newActorIdx));
            asset.Exports[lvlIdx] = newRaw;
        }
    }

    private static int ArrayDumpLimit = 3;

    private static int InspectExport(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        var asset = new UAsset(f["cell"], EngineVer, mappings);
        var filter = f.TryGetValue("name", out var fn) ? fn : null;
        int limit = f.TryGetValue("limit", out var ls) ? int.Parse(ls) : 3;
        int idxFilter = f.TryGetValue("index", out var idxs) ? int.Parse(idxs) : -1;
        ArrayDumpLimit = f.TryGetValue("array-limit", out var als) ? int.Parse(als) : 3;
        int count = 0;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            if (idxFilter >= 0 && i + 1 != idxFilter) continue;
            if (filter != null && e.ObjectName.ToString() != filter) continue;
            Console.WriteLine($"\n=== Export {i + 1}: {e.ObjectName} ({e.GetType().Name}) ===");
            Console.WriteLine($"  ClassIndex={e.ClassIndex.Index} TemplateIndex={e.TemplateIndex.Index} OuterIndex={e.OuterIndex.Index}");
            Console.WriteLine($"  ObjectFlags={e.ObjectFlags} IsInherited={e.IsInheritedInstance}");
            Console.WriteLine($"  bIsAsset={e.bIsAsset} bForcedExport={e.bForcedExport} GeneratePublicHash={e.GeneratePublicHash}");
            Console.WriteLine($"  bNotForClient={e.bNotForClient} bNotForServer={e.bNotForServer} bNotAlwaysLoadedForEditorGame={e.bNotAlwaysLoadedForEditorGame}");
            Console.WriteLine($"  PackageFlags={e.PackageFlags} PackageGuid={e.PackageGuid}");
            Console.WriteLine($"  SerialSize={e.SerialSize} SerialOffset={e.SerialOffset}");
            Console.WriteLine($"  CBCD={e.CreateBeforeCreateDependencies.Count} CBSD={e.CreateBeforeSerializationDependencies.Count} SBCD={e.SerializationBeforeCreateDependencies.Count} SBSD={e.SerializationBeforeSerializationDependencies.Count}");
            Console.WriteLine($"  ExtrasLen={e.Extras?.Length ?? 0}{(e.Extras != null ? " bytes=" + BitConverter.ToString(e.Extras) : "")}");
            if (e is NormalExport ne)
            {
                Console.WriteLine($"  Data.Count={ne.Data.Count} ObjectGuid={ne.ObjectGuid}");
                bool deep = f.ContainsKey("deep");
                foreach (var p in ne.Data)
                {
                    if (deep)
                    {
                        DumpField(p, "    ");
                        continue;
                    }
                    string valStr = p switch
                    {
                        UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp => $" = ({vp.Value.X},{vp.Value.Y},{vp.Value.Z})",
                        UAssetAPI.PropertyTypes.Structs.RotatorPropertyData rp => $" = (P{rp.Value.Pitch},Y{rp.Value.Yaw},R{rp.Value.Roll})",
                        UAssetAPI.PropertyTypes.Objects.ObjectPropertyData op => $" -> {op.Value?.Index}",
                        UAssetAPI.PropertyTypes.Structs.StructPropertyData sp => DumpStruct(sp),
                        UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp => $" = {fp.Value}",
                        UAssetAPI.PropertyTypes.Objects.IntPropertyData ip => $" = {ip.Value}",
                        UAssetAPI.PropertyTypes.Objects.NamePropertyData np => $" = \"{np.Value}\"",
                        UAssetAPI.PropertyTypes.Objects.ArrayPropertyData ap => DescribeArray(ap),
                        // Enum / byte / bool / string printed nothing, so a dump
                        // could show that MaterialDomain EXISTS while hiding
                        // whether it says MD_Volume or MD_Surface -- which is the
                        // only part anyone ever wants to know.
                        UAssetAPI.PropertyTypes.Objects.EnumPropertyData ep => $" = {ep.Value}",
                        UAssetAPI.PropertyTypes.Objects.BytePropertyData byp => $" = {byp.EnumValue?.ToString() ?? byp.Value.ToString()}",
                        UAssetAPI.PropertyTypes.Objects.BoolPropertyData bop => $" = {bop.Value}",
                        UAssetAPI.PropertyTypes.Objects.StrPropertyData stp => $" = \"{stp.Value}\"",
                        UAssetAPI.PropertyTypes.Objects.Int64PropertyData i64p => $" = {i64p.Value}",
                        UAssetAPI.PropertyTypes.Objects.DoublePropertyData dp => $" = {dp.Value}",
                        UAssetAPI.PropertyTypes.Objects.UInt32PropertyData u32 => $" = {u32.Value}",
                        _ => ""
                    };
                    Console.WriteLine($"    prop: {p.Name} ({p.GetType().Name}){valStr}");
                }
            }
            if (e is RawExport re)
                Console.WriteLine($"  RawData.Length={re.Data?.Length ?? 0}");
            if (e is LevelExport lvl)
            {
                Console.WriteLine($"  LevelExport.Actors.Count={lvl.Actors.Count}");
                Console.WriteLine($"  first 10 actors: {string.Join(",", lvl.Actors.Take(10).Select(a => a.Index))}");
                Console.WriteLine($"  last 5 actors: {string.Join(",", lvl.Actors.Skip(Math.Max(0, lvl.Actors.Count-5)).Select(a => a.Index))}");
                int nullCount = lvl.Actors.Count(a => a.Index == 0);
                var nullIdxs = Enumerable.Range(0, lvl.Actors.Count).Where(i => lvl.Actors[i].Index == 0).Take(20).ToList();
                Console.WriteLine($"  null slots: {nullCount} (first 20 indices: {string.Join(",", nullIdxs)})");
                if (f.TryGetValue("contains", out var containsStr) && int.TryParse(containsStr, out var containsIdx))
                {
                    bool has = lvl.Actors.Any(a => a.Index == containsIdx);
                    Console.WriteLine($"  Actors contains #{containsIdx}: {has}");
                }
            }
            count++;
            if (count >= limit) break;
        }
        return 0;
    }

    // ----------------------------------------------------------------------
    // INJECT-MAIN: inject parking actors directly into Jeju_World.umap
    // using the same NormalExport → RawExport pre-serialize trick.
    // ----------------------------------------------------------------------
    private static int InjectMain(string[] args)
    {
        var f = ParseFlags(args);
        var mainPath  = f["main"];
        var outPath   = f["output"];
        var mappings  = LoadMappings(f["mappings"]);
        var noInject = f.ContainsKey("no-inject");
        var configJson = JObject.Parse(File.ReadAllText(f["config"]));
        var contentRoot = f.TryGetValue("content-root", out var cr) ? cr
            : throw new ArgumentException("--content-root required");

        var bpEntries = new List<JObject>();
        var bpSection = configJson["blueprint_actors"] as JObject;
        if (bpSection != null)
            foreach (var group in bpSection.Properties())
                if (group.Value is JArray arr)
                    foreach (var e in arr) bpEntries.Add((JObject)e);

        if (bpEntries.Count == 0) { Console.WriteLine("No blueprint_actors entries."); return 0; }

        // Pre-load referenced BP .uasset files so their real schemas are registered.
        foreach (var bpPath in bpEntries.Select(e => (string)e["blueprint_path"]!).Distinct())
        {
            var bpUasset = ResolveBpUasset(contentRoot, bpPath);
            if (bpUasset == null) { Console.Error.WriteLine($"  Warning: BP not found for {bpPath}"); continue; }
            try { _ = new UAsset(bpUasset, EngineVer, mappings); Console.WriteLine($"  Loaded BP schema from {bpUasset}"); }
            catch (Exception ex) { Console.Error.WriteLine($"  Failed BP load: {ex.Message}"); }
        }

        Console.WriteLine($"Loading main map: {mainPath}");
        var asset = new UAsset(mainPath, EngineVer, mappings);
        Console.WriteLine($"  {asset.Exports.Count} exports, {asset.Imports.Count} imports");

        int idx = 0;
        if (!noInject)
        {
            foreach (var e in bpEntries)
            {
                var x = (double)e["X"]!;
                var y = (double)e["Y"]!;
                var z = (double)e["Z"]!;
                var pitch = e["Pitch"]?.Value<double>() ?? 0;
                var yaw   = e["Yaw"]?.Value<double>()   ?? 0;
                var roll  = e["Roll"]?.Value<double>()  ?? 0;
                var bp    = (string)e["blueprint_path"]!;
                InjectParkingActor(asset, bp, x, y, z, pitch, yaw, roll, $"ParkingLot_MOD_{idx++}");
            }

            Console.WriteLine($"Pre-serializing {idx * 5} NormalExports to RawExport bytes...");
            ConvertTrailingNormalExportsToRaw(asset, countJustAdded: idx * 5);

            // Collect new actor export indices (only the actor itself, not components)
            // Actor is at offset 0 in each group of 5.
            var newActorIndices = new List<int>();
            int startIdx = asset.Exports.Count - idx * 5;
            for (int k = 0; k < idx; k++) newActorIndices.Add(startIdx + k * 5 + 1);
            PatchLevelExportAsRaw(asset, mainPath, newActorIndices);
        }
        else
        {
            Console.WriteLine("--no-inject: round-trip only");
        }

        Console.WriteLine($"Writing {outPath}");
        asset.Write(outPath);

        // Copy .uexp / .ubulk siblings if needed — UAsset.Write handles .uexp automatically
        var srcDir = Path.GetDirectoryName(mainPath)!;
        var dstDir = Path.GetDirectoryName(outPath)!;
        var baseName = Path.GetFileNameWithoutExtension(mainPath);
        var srcUbulk = Path.Combine(srcDir, baseName + ".ubulk");
        if (File.Exists(srcUbulk))
        {
            var dstUbulk = Path.Combine(dstDir, baseName + ".ubulk");
            if (!File.Exists(dstUbulk) || new FileInfo(srcUbulk).Length != new FileInfo(dstUbulk).Length)
                File.Copy(srcUbulk, dstUbulk, true);
        }
        Console.WriteLine("Done.");
        return 0;
    }

    // ----------------------------------------------------------------------
    // INJECT-STATIC: inject dealerships + static meshes straight into
    // Jeju_World.umap as RawExports, bypassing convert2.py + UAssetGUI
    // fromjson entirely. Static meshes are streamed from the JSONL sidecar
    // shards (import_meshes writes the marker into the config), so a 6M-entry
    // export never materializes as one giant JSON the way UAssetGUI choked on
    // (it was eating 55 GB). Mirrors convert2.py's exact RawExport byte layout.
    // ----------------------------------------------------------------------
    // ----------------------------------------------------------------------
    // FOLIAGE instance buffer (FStaticMeshInstanceData) codec.
    //
    // Layout (cooked UE5.5 FoliageInstancedStaticMeshComponent.Extras), all
    // little-endian, no .ubulk for these cells:
    //   [0:4]   int 0
    //   [4:8]   int numBlocks  (per-LOD/lightmap blocks; we emit 0)
    //   numBlocks * 34 bytes   (skipped when numBlocks==0)
    //   4 ints  1,0,1,1        (constant header)
    //   int 128 (transform stride)  +  int N (instance count)
    //   N * 128 bytes : per-instance FMatrix (16 doubles, row-major, row4 =
    //                   translation in instance-local space, last col 0,0,0,1)
    //   int 4  + int 0         (instance reorder array, empty)
    //   int 0                  (mid)
    //   int 64 + int K         (cluster tree: K FClusterNode, 64 bytes each)
    //   K * 64 bytes : FClusterNode (BoundMin 3f, FirstChild i, BoundMax 3f,
    //                   LastChild i, FirstInstance i, LastInstance i,
    //                   MinInstanceScale 3f, MaxInstanceScale 3f)
    //
    // We emit a single root leaf node covering all instances — a valid tree
    // that renders every instance (one cull cluster). Bounds padded so the
    // mesh extent never falls outside the node.
    // ----------------------------------------------------------------------
    private const double FOLIAGE_BOUND_PAD = 12000.0;

    // Read per-instance 4x4 double matrices out of an existing FISMC Extras.
    private static List<double[]> ReadInstanceMatrices(byte[] ex)
    {
        var list = new List<double[]>();
        int pos = -1, n = 0;
        for (int o = 0; o + 8 <= ex.Length; o += 4)
        {
            if (BitConverter.ToInt32(ex, o) == 128)
            {
                int c = BitConverter.ToInt32(ex, o + 4);
                if (c >= 0 && o + 8 + (long)c * 128 <= ex.Length) { pos = o; n = c; break; }
            }
        }
        if (pos < 0) return list;
        int t = pos + 8;
        for (int i = 0; i < n; i++)
        {
            var m = new double[16];
            for (int j = 0; j < 16; j++) m[j] = BitConverter.ToDouble(ex, t + i * 128 + j * 8);
            list.Add(m);
        }
        return list;
    }

    // Build a FISMC Extras buffer (numBlocks=0, single-node cluster tree).
    private static byte[] BuildFoliageExtras(List<double[]> mats)
    {
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        bw.Write(0);                          // [0:4]
        bw.Write(0);                          // numBlocks = 0
        bw.Write(1); bw.Write(0); bw.Write(1); bw.Write(1);  // const header
        bw.Write(128);                        // transform stride
        bw.Write(mats.Count);                 // N
        // bbox of translations + scale range, for the cluster node
        float minX = float.MaxValue, minY = float.MaxValue, minZ = float.MaxValue;
        float maxX = float.MinValue, maxY = float.MinValue, maxZ = float.MinValue;
        float sMin = float.MaxValue, sMax = float.MinValue;
        foreach (var m in mats)
        {
            for (int j = 0; j < 16; j++) bw.Write(m[j]);
            float x = (float)m[12], y = (float)m[13], z = (float)m[14];
            minX = Math.Min(minX, x); minY = Math.Min(minY, y); minZ = Math.Min(minZ, z);
            maxX = Math.Max(maxX, x); maxY = Math.Max(maxY, y); maxZ = Math.Max(maxZ, z);
            double s0 = Math.Sqrt(m[0]*m[0]+m[1]*m[1]+m[2]*m[2]);
            double s1 = Math.Sqrt(m[4]*m[4]+m[5]*m[5]+m[6]*m[6]);
            double s2 = Math.Sqrt(m[8]*m[8]+m[9]*m[9]+m[10]*m[10]);
            float smn = (float)Math.Min(s0, Math.Min(s1, s2));
            float smx = (float)Math.Max(s0, Math.Max(s1, s2));
            sMin = Math.Min(sMin, smn); sMax = Math.Max(sMax, smx);
        }
        if (mats.Count == 0) { minX = minY = minZ = maxX = maxY = maxZ = 0; sMin = sMax = 1; }
        // reorder (empty), mid, cluster tree (1 node)
        bw.Write(4); bw.Write(0);
        bw.Write(0);
        bw.Write(64); bw.Write(1);
        float p = (float)FOLIAGE_BOUND_PAD;
        bw.Write(minX - p); bw.Write(minY - p); bw.Write(minZ - p);  // BoundMin
        bw.Write(-1);                                                // FirstChild
        bw.Write(maxX + p); bw.Write(maxY + p); bw.Write(maxZ + p);  // BoundMax
        bw.Write(-1);                                                // LastChild
        bw.Write(0);                                                 // FirstInstance
        bw.Write(Math.Max(0, mats.Count - 1));                       // LastInstance
        bw.Write(sMin); bw.Write(sMin); bw.Write(sMin);              // MinInstanceScale
        bw.Write(sMax); bw.Write(sMax); bw.Write(sMax);              // MaxInstanceScale
        return ms.ToArray();
    }

    // Row-major 4x4 (translation in m[12..14]) from a UE FRotator + scale,
    // matching FRotationTranslationMatrix. Pitch=Y, Yaw=Z, Roll=X, degrees.
    private static double[] MakeInstanceMatrix(double px, double py, double pz,
                                               double pitch, double yaw, double roll,
                                               double sx, double sy, double sz)
    {
        const double D2R = Math.PI / 180.0;
        double SP = Math.Sin(pitch * D2R), CP = Math.Cos(pitch * D2R);
        double SY = Math.Sin(yaw   * D2R), CY = Math.Cos(yaw   * D2R);
        double SR = Math.Sin(roll  * D2R), CR = Math.Cos(roll  * D2R);
        var m = new double[16];
        m[0] = CP * CY * sx;
        m[1] = CP * SY * sx;
        m[2] = SP * sx;
        m[3] = 0;
        m[4] = (SR * SP * CY - CR * SY) * sy;
        m[5] = (SR * SP * SY + CR * CY) * sy;
        m[6] = (-SR * CP) * sy;
        m[7] = 0;
        m[8]  = (-(CR * SP * CY + SR * SY)) * sz;
        m[9]  = (CY * SR - CR * SP * SY) * sz;
        m[10] = (CR * CP) * sz;
        m[11] = 0;
        m[12] = px; m[13] = py; m[14] = pz; m[15] = 1;
        return m;
    }

    // Turn a copy of a minimal vanilla foliage cell into OUR foliage cell.
    //
    //   --cell <cell .umap>        modified in place unless --output given
    //   --tx/--ty/--tz <int>       actor-partition tile (grid is always 25600)
    //   --instances <jsonl>        one {"X","Y","Z","Pitch","Roll","Yaw","ScaleX",..}
    //                              per line, in WORLD coords
    //   [--mesh /Game/Path/SM_X.SM_X]   retarget the template's StaticMesh
    //   --mappings <usmap>
    //
    // The transform model (AGENTS.md "Foliage Instance Transform Model"):
    //     world = IFA root RelativeLocation + FISMC TISO + instance translation
    // We put the whole world offset on the root (at the tile CENTRE, exactly
    // as vanilla does), zero the TISO, and store instances relative to it.
    // Keeping ONE FISMC matters: the IFA's Extras carry the FoliageType->
    // component map, and we are not re-encoding that here.
    // Build a mod-owned StringTable so custom cargo can have its OWN display
    // name. Shipping a modified vanilla /Game/DataAsset/StringTables/Cargo
    // crashes on world load, so we clone it to a new package path, replace
    // the entries with ours, and point the cargo rows at that table instead.
    //   --src <vanilla Cargo.uasset> --output <ModCargo.uasset>
    //   --namespace <ns> --entries <json {key: display}> --mappings <usmap>
    private static int MakeStringTable(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["src"], EngineVer, LoadMappings(f["mappings"]));
        string ns = f.TryGetValue("namespace", out var n) ? n : "ModCargo";
        var entries = Newtonsoft.Json.Linq.JObject.Parse(File.ReadAllText(f["entries"]));

        UAssetAPI.ExportTypes.StringTableExport? ste = null;
        foreach (var e in asset.Exports)
            if (e is UAssetAPI.ExportTypes.StringTableExport t) { ste = t; break; }
        if (ste == null) { Console.Error.WriteLine("  no StringTableExport in source"); return 1; }

        // The export name IS the object name inside the package, and the
        // package path comes from the file location — both must be the new
        // name or the Text lookup ("<pkg>.<obj>") will not resolve.
        //
        // RENAME THE PACKAGE TOO. Cloning the vanilla table leaves the source
        // package path sitting in the name map, so the asset went out still
        // calling itself /Game/DataAsset/StringTables/BusStop while its table
        // had been cleared down to our handful of entries -- a mod-priority
        // copy of the vanilla table with every vanilla key gone. Renaming the
        // export alone was never enough; the package name is what the engine
        // reads the asset's identity from.
        string oldObj = ste.ObjectName.ToString();
        EnsureName(asset, ns);
        {
            var map = asset.GetNameMapIndexList();
            string? newPkg = null;
            for (int i = 0; i < map.Count; i++)
            {
                string v = map[i].Value;
                if (v.StartsWith("/", StringComparison.Ordinal)
                    && (v.EndsWith("/" + oldObj, StringComparison.Ordinal)))
                {
                    newPkg = v.Substring(0, v.Length - oldObj.Length) + ns;
                    asset.SetNameReference(i, new FString(newPkg));
                    Console.WriteLine($"  package {v} -> {newPkg}");
                }
            }
            // The summary carries the package path a SECOND time, in
            // FolderName, and that copy is the one UE reads the asset's
            // identity from. Renaming only the name-map entry left the header
            // still saying BusStop.
            if (newPkg != null) asset.FolderName = new FString(newPkg);
        }
        ste.ObjectName = FName.FromString(asset, ns);
        ste.Table.TableNamespace = new FString(ns);
        ste.Table.Clear();
        foreach (var prop in entries.Properties())
        {
            string key = prop.Name, val = prop.Value.ToString();
            EnsureName(asset, key); EnsureName(asset, val);
            ste.Table.Add(new FString(key), new FString(val));
        }
        asset.Write(f["output"]);
        Console.WriteLine($"  StringTable '{ns}': {entries.Count} entry(ies) -> {Path.GetFileName(f["output"])}");
        foreach (var prop in entries.Properties())
            Console.WriteLine($"      {prop.Name} = \"{prop.Value}\"");
        return 0;
    }

    private static int MakeFoliageCell(string[] args)
    {
        var f0 = ParseFlags(args);
        // --spec <json>: array of per-cell arg maps. Batched because the whole
        // map is ~27k cells and paying process start + mappings load per cell
        // would run for hours; loaded once here it is milliseconds each.
        if (f0.TryGetValue("spec", out var specPath))
        {
            var mappings = LoadMappings(f0["mappings"]);
            var jobs = Newtonsoft.Json.Linq.JArray.Parse(File.ReadAllText(specPath));
            int done = 0, failed = 0; long insts = 0;
            foreach (var j in jobs)
            {
                var o = (Newtonsoft.Json.Linq.JObject)j!;
                var one = new Dictionary<string, string>();
                foreach (var prop in o.Properties()) one[prop.Name] = prop.Value.ToString();
                try
                {
                    insts += MakeFoliageCellOne(one, mappings, quiet: true);
                    done++;
                }
                catch (Exception ex)
                {
                    failed++;
                    if (failed <= 5) Console.Error.WriteLine($"  cell {one.GetValueOrDefault("cell")}: {ex.Message}");
                }
                if (done % 2000 == 0 && done > 0) Console.WriteLine($"  ... {done}/{jobs.Count} cells, {insts:N0} instances");
            }
            Console.WriteLine($"  wrote {done} foliage cell(s), {insts:N0} instances" + (failed > 0 ? $", {failed} FAILED" : ""));
            return failed > 0 ? 1 : 0;
        }
        MakeFoliageCellOne(f0, LoadMappings(f0["mappings"]), quiet: false);
        return 0;
    }

    private static long MakeFoliageCellOne(Dictionary<string, string> f, Usmap mappings, bool quiet)
    {
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        string cellPath = f["cell"];
        string outPath = f.TryGetValue("output", out var op) ? op : cellPath;
        int tx = int.Parse(f["tx"]), ty = int.Parse(f["ty"]), tz = int.Parse(f["tz"]);
        const double G = 25600.0;
        double rx = (tx + 0.5) * G, ry = (ty + 0.5) * G, rz = (tz + 0.5) * G;

        var asset = new UAsset(cellPath, EngineVer, mappings);

        int ifaIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i].ObjectName.ToString().StartsWith("InstancedFoliageActor")) { ifaIdx = i; break; }
        if (ifaIdx < 0) throw new InvalidOperationException("no InstancedFoliageActor in cell");
        int ifaNum = ifaIdx + 1;

        string ifaName = $"InstancedFoliageActor_{(int)G}_{tx}_{ty}_{tz}";
        EnsureName(asset, ifaName);
        asset.Exports[ifaIdx].ObjectName = FName.FromString(asset, ifaName);

        // Root component: the whole world offset lives here.
        int roots = 0;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            if (e.OuterIndex.Index != ifaNum || e is not NormalExport ne) continue;
            if (!e.ObjectName.ToString().StartsWith("RootComponent")) continue;
            foreach (var p in ne.Data)
                if (p.Name.ToString() == "RelativeLocation" && p is StructPropertyData sp
                    && sp.Value.Count > 0 && sp.Value[0] is VectorPropertyData vp)
                { vp.Value = new FVector(rx, ry, rz); roots++; }
        }
        if (roots == 0) throw new InvalidOperationException("IFA has no RootComponent with RelativeLocation");

        // Instances -> matrices relative to the root.
        var mats = new List<double[]>();
        foreach (var line in File.ReadLines(f["instances"]))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var o = Newtonsoft.Json.Linq.JObject.Parse(line);
            double D(string k, double dflt = 0) => o[k]?.Value<double>() ?? dflt;
            mats.Add(MakeInstanceMatrix(
                D("X") - rx, D("Y") - ry, D("Z") - rz,
                D("Pitch"), D("Yaw"), D("Roll"),
                D("ScaleX", 1), D("ScaleY", 1), D("ScaleZ", 1)));
        }

        int fismc = 0, fismcIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            if (e.OuterIndex.Index != ifaNum) continue;
            if (!e.ObjectName.ToString().StartsWith("FoliageInstancedStaticMeshComponent")) continue;
            if (e is NormalExport ne)
                foreach (var p in ne.Data)
                    if (p.Name.ToString() == "TranslatedInstanceSpaceOrigin" && p is StructPropertyData sp
                        && sp.Value.Count > 0 && sp.Value[0] is VectorPropertyData vp)
                        vp.Value = new FVector(0, 0, 0);
            e.Extras = BuildFoliageExtras(mats);
            fismc++; fismcIdx = i;
        }
        if (fismc != 1 && !quiet)
            Console.WriteLine($"  WARNING: {fismc} FISMC(s) written — each got the SAME instances. " +
                              "Use a single-FISMC template until per-mesh grouping ships.");

        // Primary mesh: retarget just THIS component's StaticMesh, never every
        // import in the file — sibling FISMCs added below each carry their own.
        if (fismcIdx >= 0)
        {
            if (f.TryGetValue("mesh", out var meshPath))
            {
                RetargetStaticMeshImport(asset, asset.Exports[fismcIdx], meshPath);
                if (!quiet) Console.WriteLine($"  mesh -> {meshPath}");
            }
            ApplyComponentSettings(asset.Exports[fismcIdx], f, "");
            if (!quiet && f.TryGetValue("collision", out var prof))
                Console.WriteLine($"  collision -> {prof}");
        }

        // --extra <json>: [{"mesh":..., "instances":<jsonl>}, ...] — additional
        // mesh types for the SAME tile.
        //
        // They MUST live in this one cell. WP keys a runtime cell by its grid
        // coords: key = (gridX + 524800) + gridY*1024. Every mesh of a tile has
        // the same coords, so registering one cell per (tile, mesh) collides on
        // that key and the map keeps only the last — measured 2,164 of 27,613
        // cells reachable, ~8% of the foliage rendering.
        //
        // One extra IFA per mesh, not one IFA with N components: an IFA's Extras
        // carry a FoliageType->info map we have not reverse-engineered, so each
        // clone keeps the template's own self-consistent copy. Vanilla ships
        // cells with up to 4 IFAs, so this is a shape the engine already loads.
        long extraInst = 0; int extraIfas = 0;
        if (f.TryGetValue("extra", out var extraSpec) && !string.IsNullOrWhiteSpace(extraSpec))
        {
            int rootIdx = -1;
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].OuterIndex.Index == ifaNum
                    && asset.Exports[i].ObjectName.ToString().StartsWith("RootComponent")) { rootIdx = i; break; }
            int lvlIdx = -1;
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i] is LevelExport) { lvlIdx = i; break; }
            if (rootIdx < 0 || fismcIdx < 0 || lvlIdx < 0)
                throw new InvalidOperationException("template cell missing root/FISMC/level export");

            foreach (var jt in Newtonsoft.Json.Linq.JArray.Parse(extraSpec))
            {
                var eo = (Newtonsoft.Json.Linq.JObject)jt!;
                var emats = new List<double[]>();
                foreach (var line in File.ReadLines((string)eo["instances"]!))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var o = Newtonsoft.Json.Linq.JObject.Parse(line);
                    double D(string k, double dflt = 0) => o[k]?.Value<double>() ?? dflt;
                    emats.Add(MakeInstanceMatrix(
                        D("X") - rx, D("Y") - ry, D("Z") - rz,
                        D("Pitch"), D("Yaw"), D("Roll"),
                        D("ScaleX", 1), D("ScaleY", 1), D("ScaleZ", 1)));
                }
                if (emats.Count == 0) continue;

                int nIfa = asset.Exports.Count + 1;
                int nRoot = nIfa + 1;
                int nFis = nIfa + 2;

                Export Dup(Export src, string newName, int outer)
                {
                    var ne2 = (NormalExport)src;
                    var d = new NormalExport
                    {
                        Data = ne2.Data.Select(p => (PropertyData)p.Clone()).ToList(),
                        ObjectGuid = ne2.ObjectGuid,
                        SerializationControl = ne2.SerializationControl,
                        Operation = ne2.Operation,
                        HasLeadingFourNullBytes = ne2.HasLeadingFourNullBytes,
                        Asset = asset,
                    };
                    EnsureName(asset, newName);
                    d.ObjectName = FName.FromString(asset, newName);
                    d.ClassIndex = new FPackageIndex(src.ClassIndex.Index);
                    d.SuperIndex = new FPackageIndex(src.SuperIndex.Index);
                    d.TemplateIndex = new FPackageIndex(src.TemplateIndex.Index);
                    d.OuterIndex = new FPackageIndex(outer);
                    d.ObjectFlags = src.ObjectFlags;
                    d.bNotAlwaysLoadedForEditorGame = src.bNotAlwaysLoadedForEditorGame;
                    d.IsInheritedInstance = src.IsInheritedInstance;
                    d.SerializationBeforeSerializationDependencies = src.SerializationBeforeSerializationDependencies.ToList();
                    d.CreateBeforeSerializationDependencies = src.CreateBeforeSerializationDependencies.ToList();
                    d.SerializationBeforeCreateDependencies = src.SerializationBeforeCreateDependencies.ToList();
                    d.CreateBeforeCreateDependencies = src.CreateBeforeCreateDependencies.ToList();
                    d.Extras = src.Extras != null ? (byte[])src.Extras.Clone() : null;
                    return d;
                }

                var ifaC  = Dup(asset.Exports[ifaIdx],   $"{ifaName}_{extraIfas + 1}", lvlIdx + 1);
                var rootC = Dup(asset.Exports[rootIdx],  "RootComponent0", nIfa);
                var fisC  = Dup(asset.Exports[fismcIdx], "FoliageInstancedStaticMeshComponent_0", nIfa);
                asset.Exports.Add(ifaC); asset.Exports.Add(rootC); asset.Exports.Add(fisC);

                // Rewire the clone's internal object references onto itself.
                foreach (var p in ((NormalExport)ifaC).Data)
                {
                    if (p is ObjectPropertyData rc && p.Name.ToString() == "RootComponent")
                        rc.Value = new FPackageIndex(nRoot);
                    if (p is ArrayPropertyData ap && p.Name.ToString() == "InstanceComponents"
                        && ap.Value != null)
                        foreach (var it in ap.Value)
                            if (it is ObjectPropertyData ic) ic.Value = new FPackageIndex(nFis);
                }
                foreach (var p in ((NormalExport)fisC).Data)
                    if (p is ObjectPropertyData ap2 && p.Name.ToString() == "AttachParent")
                        ap2.Value = new FPackageIndex(nRoot);

                RetargetStaticMeshImport(asset, fisC, (string?)eo["mesh"]);
                var eflags = new Dictionary<string, string>();
                foreach (var prop in eo.Properties()) eflags[prop.Name] = prop.Value.ToString();
                ApplyComponentSettings(fisC, eflags, "");
                fisC.Extras = BuildFoliageExtras(emats);

                if (asset.Exports[lvlIdx] is LevelExport lx)
                {
                    lx.Actors.Add(new FPackageIndex(nIfa));
                    lx.CreateBeforeSerializationDependencies.Add(new FPackageIndex(nIfa));
                }
                extraIfas++; extraInst += emats.Count;
            }
        }

        asset.Write(outPath);
        if (!quiet)
            Console.WriteLine($"  {ifaName}: root=({rx},{ry},{rz}) instances={mats.Count + extraInst} "
                              + $"ifa={1 + extraIfas} -> {Path.GetFileName(outPath)}");
        return mats.Count + extraInst;
    }

    // Apply the component settings the EDITOR had for this mesh, exported by
    // ue.py into foliage_settings.json. Our cells are clones of a vanilla
    // foliage template, so any property not explicitly carried over keeps that
    // template's value — which is how every mesh ended up with the vanilla
    // tree's cull distances and BlockAll regardless of the user's FoliageType.
    private static void ApplyComponentSettings(Export fismc, Dictionary<string, string> f, string prefix)
    {
        if (f.TryGetValue(prefix + "collision", out var prof)) SetCollisionProfile(fismc, prof);
        SetIntProp(fismc, "InstanceStartCullDistance", f, prefix + "cull_start");
        SetIntProp(fismc, "InstanceEndCullDistance", f, prefix + "cull_end");
        if (f.TryGetValue(prefix + "materials", out var mats)) SetOverrideMaterials(fismc.Asset, fismc, mats);
    }

    // Set a FISMC's OverrideMaterials. The winter/season look is applied as a
    // per-component material override in the editor, NOT baked into the mesh
    // (the tree meshes still reference MI_Leaf_01_Summer_01). Our cells clone
    // a vanilla template that has no OverrideMaterials at all, so without
    // this the game falls back to the mesh's own material and the whole map
    // renders in the wrong season.
    private static void SetOverrideMaterials(UAsset asset, Export fismc, string? spec)
    {
        if (string.IsNullOrWhiteSpace(spec)) return;
        var mats = Newtonsoft.Json.Linq.JArray.Parse(spec);
        if (mats.Count == 0) return;

        var items = new List<PropertyData>();
        foreach (var m in mats)
        {
            var o = m as Newtonsoft.Json.Linq.JObject;
            string? path = (string?)o?["path"];
            if (string.IsNullOrWhiteSpace(path))
            {
                // A null slot means "use the mesh's own material" — must be
                // kept so later slots keep their index.
                items.Add(new ObjectPropertyData(FName.FromString(asset, "OverrideMaterials"))
                { Value = new FPackageIndex(0) });
                continue;
            }
            string cls = (string?)o?["class"] ?? "MaterialInstanceConstant";
            int lastSlash = path.LastIndexOf('/');
            int dot = path.IndexOf('.', lastSlash < 0 ? 0 : lastSlash);
            string pkgPath = dot >= 0 ? path.Substring(0, dot) : path;
            string matName = pkgPath.Substring(pkgPath.LastIndexOf('/') + 1);
            int pkg = FindOrAddImport(asset, pkgPath, 0, "/Script/CoreUObject", "Package");
            int mi = FindOrAddImport(asset, matName, pkg, "/Script/Engine", cls);
            items.Add(new ObjectPropertyData(FName.FromString(asset, "OverrideMaterials"))
            { Value = new FPackageIndex(mi) });
        }

        var ne = (NormalExport)fismc;
        EnsureName(asset, "OverrideMaterials");
        EnsureName(asset, "ObjectProperty");
        var arr = new ArrayPropertyData(FName.FromString(asset, "OverrideMaterials"))
        {
            ArrayType = FName.FromString(asset, "ObjectProperty"),
            Value = items.ToArray(),
        };
        for (int i = 0; i < ne.Data.Count; i++)
            if (ne.Data[i].Name.ToString() == "OverrideMaterials") { ne.Data[i] = arr; return; }
        ne.Data.Add(arr);
    }

    private static void SetIntProp(Export e, string propName, Dictionary<string, string> f, string key)
    {
        if (!f.TryGetValue(key, out var raw) || string.IsNullOrWhiteSpace(raw)) return;
        if (!int.TryParse(raw, out var v)) return;
        foreach (var p in ((NormalExport)e).Data)
            if (p is IntPropertyData ip && p.Name.ToString() == propName)
                ip.Value = v;
    }

    // Set one FISMC's collision profile (BodyInstance.CollisionProfileName).
    //
    // The template we clone is vanilla TREE foliage, so every component we
    // generate inherits BlockAll — grass included. Whether that actually
    // blocks depends on the cooked mesh having collision geometry, which is
    // why making grass drive-through used to need a mesh re-cook. Setting
    // NoCollision here decides it at the component instead, per mesh type,
    // with no re-cook: trees stay solid, ground cover doesn't.
    private static void SetCollisionProfile(Export fismc, string? profile)
    {
        if (string.IsNullOrWhiteSpace(profile)) return;
        foreach (var p in ((NormalExport)fismc).Data)
        {
            if (p is not StructPropertyData sp || p.Name.ToString() != "BodyInstance") continue;
            foreach (var inner in sp.Value)
                if (inner is NamePropertyData np && inner.Name.ToString() == "CollisionProfileName")
                    np.Value = FName.FromString(fismc.Asset, profile);
        }
    }

    // Point one FISMC's StaticMesh at `meshPath` by adding (or reusing) the
    // import pair for it. Per-component, so sibling FISMCs keep their own mesh.
    private static void RetargetStaticMeshImport(UAsset asset, Export fismc, string? meshPath)
    {
        if (string.IsNullOrWhiteSpace(meshPath)) return;
        int lastSlash = meshPath.LastIndexOf('/');
        int dot = meshPath.IndexOf('.', lastSlash < 0 ? 0 : lastSlash);
        string pkgPath = dot >= 0 ? meshPath.Substring(0, dot) : meshPath;
        string meshName = pkgPath.Substring(pkgPath.LastIndexOf('/') + 1);
        int pkg = FindOrAddImport(asset, pkgPath, 0, "/Script/CoreUObject", "Package");
        int mesh = FindOrAddImport(asset, meshName, pkg, "/Script/Engine", "StaticMesh");
        foreach (var p in ((NormalExport)fismc).Data)
            if (p is ObjectPropertyData op && p.Name.ToString() == "StaticMesh")
                op.Value = new FPackageIndex(mesh);
    }

    // Rewrite every FISMC in a cell through our codec (validates the codec:
    // same instances, our buffer). --zlift N raises every instance so the
    // effect is visible in-game (proves our buffer is what's rendering).
    private static int ReencodeFoliage(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        double zlift = f.TryGetValue("zlift", out var zl) ? double.Parse(zl) : 0;
        // --gridcount N: REPLACE each FISMC's instances with an ~NxN-ish grid
        // centered on its existing instances' centroid (world coords), spacing
        // --gspacing. Tests variable-N codec generation + render in-game.
        int gridCount = f.TryGetValue("gridcount", out var gc) ? int.Parse(gc) : 0;
        double gspacing = f.TryGetValue("gspacing", out var gs) ? double.Parse(gs) : 200;
        // --noop: load + write the cell UNCHANGED, to test whether
        // UAssetAPI's cell write is game-faithful (isolates write path from
        // the codec). If vanilla foliage in a no-op cell disappears, the cell
        // write itself is the problem (LevelExport.Write WP incompleteness).
        bool noop = f.ContainsKey("noop");
        if (noop)
        {
            asset.Write(f["output"]);
            Console.WriteLine($"no-op round-trip -> {Path.GetFileName(f["output"])}");
            return 0;
        }
        int comps = 0; long total = 0;
        double wcx = 0, wcy = 0, wcz = 0; long wc = 0;
        var fismcIdx = new HashSet<int>();
        for (int ei = 0; ei < asset.Exports.Count; ei++)
        {
            var e = asset.Exports[ei];
            if (!e.ObjectName.ToString().StartsWith("FoliageInstancedStaticMeshComponent")) continue;
            if (e.Extras == null || e.Extras.Length == 0) continue;
            // TranslatedInstanceSpaceOrigin — instances are stored relative to it.
            double ox = 0, oy = 0, oz = 0;
            if (e is NormalExport ne)
                foreach (var p in ne.Data)
                    if (p.Name.ToString() == "TranslatedInstanceSpaceOrigin" && p is StructPropertyData sp
                        && sp.Value.Count > 0 && sp.Value[0] is VectorPropertyData vp)
                    { ox = vp.Value.X; oy = vp.Value.Y; oz = vp.Value.Z; }
            var mats = ReadInstanceMatrices(e.Extras);
            foreach (var m in mats) { wcx += m[12] + ox; wcy += m[13] + oy; wcz += m[14] + oz; wc++; }
            if (gridCount > 0 && mats.Count > 0)
            {
                // grid center: explicit --gx/--gy/--gz, else centroid of existing
                double cx, cy, cz;
                if (f.ContainsKey("gx"))
                {
                    var inv = System.Globalization.CultureInfo.InvariantCulture;
                    cx = double.Parse(f["gx"], inv); cy = double.Parse(f["gy"], inv); cz = double.Parse(f["gz"], inv);
                }
                else
                {
                    cx = 0; cy = 0; cz = 0;
                    foreach (var m in mats) { cx += m[12]; cy += m[13]; cz += m[14]; }
                    cx /= mats.Count; cy /= mats.Count; cz /= mats.Count;
                }
                cz += zlift;
                int gzlayers = f.TryGetValue("zlayers", out var zlv2) ? int.Parse(zlv2) : 1;
                double gzstep = f.TryGetValue("zstep", out var zsv2) ? double.Parse(zsv2, System.Globalization.CultureInfo.InvariantCulture) : 2000;
                int side = (int)Math.Ceiling(Math.Sqrt(gridCount));
                var grid = new List<double[]>();
                for (int gl = 0; gl < gzlayers; gl++)
                    for (int gi = 0; gi < side; gi++)
                        for (int gj = 0; gj < side; gj++)
                        {
                            if (gi * side + gj >= gridCount) break;
                            var m = new double[16] { 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 };
                            m[12] = cx + (gi - side / 2.0) * gspacing;
                            m[13] = cy + (gj - side / 2.0) * gspacing;
                            m[14] = cz + gl * gzstep;
                            grid.Add(m);
                        }
                mats = grid;
            }
            else if (zlift != 0) foreach (var m in mats) m[14] += zlift;
            e.Extras = BuildFoliageExtras(mats);
            fismcIdx.Add(ei);
            comps++; total += mats.Count;
        }
        if (comps == 0) { Console.WriteLine("no foliage components"); return 0; }

        // --rawlevel: raw-preserve EVERY export except the modified FISMCs from
        // the source file's original bytes. UAssetAPI re-serialization of WP
        // cell content (level + complex BP/ChildActor exports) corrupts it and
        // the cell won't stream; verbatim bytes are safe. Only the FISMCs (whose
        // properties+Extras round-trip faithfully) get re-serialized.
        if (f.ContainsKey("rawlevel"))
            ConvertCellExportsToRawExcept(asset, f["cell"], fismcIdx);
        asset.Write(f["output"]);
        if (wc > 0)
            Console.WriteLine($"reencoded {comps} FISMC, {total} inst, worldCenter=({wcx/wc:F0},{wcy/wc:F0},{wcz/wc:F0}) -> {Path.GetFileName(f["output"])}");
        else
            Console.WriteLine($"reencoded {comps} FISMC (0 inst) -> {Path.GetFileName(f["output"])}");
        return 0;
    }

    // ----------------------------------------------------------------------
    // INJECT-FOLIAGE-PROBE: clone a vanilla InstancedFoliageActor + its
    // RootComponent + FISMC from a foliage cell into the persistent level of
    // the main map, swap the mesh, and rewrite the FISMC instance buffer to a
    // grid of `count` instances at (x,y,z). Cloned NormalExports are
    // pre-serialized to RawExport (NormalExport in the RawExport main map
    // crashes). Tests whether a persistent-level HISM renders at all.
    //   --main --output --mappings --source-cell --source-actor
    //   --mesh </Game/.../SM_X.SM_X> --count N --x --y --z [--spacing]
    // ----------------------------------------------------------------------
    private static int InjectFoliageProbe(string[] args)
    {
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        var dst = new UAsset(f["main"], EngineVer, mappings);
        var src = new UAsset(f["source-cell"], EngineVer, mappings);
        string srcActorName = f.TryGetValue("source-actor", out var sa) ? sa : "InstancedFoliageActor";
        string meshPath = f["mesh"];
        int count = f.TryGetValue("count", out var cc) ? int.Parse(cc) : 1000;
        double gx = double.Parse(f["x"], inv), gy = double.Parse(f["y"], inv), gz = double.Parse(f["z"], inv);
        double sp = f.TryGetValue("spacing", out var ss) ? double.Parse(ss, inv) : 200;

        // resolve mesh import (pkg path + export name), like inject-static
        int lastSlash = meshPath.LastIndexOf('/');
        int dot = meshPath.IndexOf('.', lastSlash < 0 ? 0 : lastSlash);
        string pkgPath = dot >= 0 ? meshPath.Substring(0, dot) : meshPath;
        string exportName = pkgPath.Substring(pkgPath.LastIndexOf('/') + 1);

        int srcIdx = -1;
        for (int i = 0; i < src.Exports.Count; i++)
            if (src.Exports[i].ObjectName.ToString().Contains(srcActorName)) { srcIdx = i; break; }
        if (srcIdx < 0) throw new InvalidOperationException($"No actor matching '{srcActorName}' in source cell");
        int srcActorNum = srcIdx + 1;
        var srcActor = src.Exports[srcIdx];
        var srcChildren = new List<int>();
        for (int i = 0; i < src.Exports.Count; i++)
            if (src.Exports[i].OuterIndex.Index == srcActorNum) srcChildren.Add(i);
        Console.WriteLine($"source IFA #{srcActorNum} {srcActor.ObjectName}, children={srcChildren.Count}");

        int dstLevelIdx = -1;
        for (int i = 0; i < dst.Exports.Count; i++)
            if (dst.Exports[i] is LevelExport) { dstLevelIdx = i; break; }
        if (dstLevelIdx < 0)
            for (int i = 0; i < dst.Exports.Count; i++)
                if (dst.Exports[i].ObjectName.ToString() == "PersistentLevel") { dstLevelIdx = i; break; }
        if (dstLevelIdx < 0) throw new InvalidOperationException("No PersistentLevel in main map");
        int dstLevelNum = dstLevelIdx + 1;

        var importRemap = new Dictionary<int, int>();
        int RemapImport(int srcImp)
        {
            int z = -srcImp - 1;
            if (importRemap.TryGetValue(z, out var a)) return a;
            var si = src.Imports[z];
            int outer = si.OuterIndex.Index;
            int mappedOuter = outer < 0 ? RemapImport(outer) : 0;
            string on = si.ObjectName.ToString(), cn = si.ClassName.ToString(), cp = si.ClassPackage.ToString();
            int di = 0; bool found = false;
            for (int i = 0; i < dst.Imports.Count; i++)
            {
                var d = dst.Imports[i];
                if (d.ObjectName.ToString() == on && d.ClassName.ToString() == cn && d.OuterIndex.Index == mappedOuter)
                { di = -(i + 1); found = true; break; }
            }
            if (!found)
            {
                EnsureName(dst, on); EnsureName(dst, cn); EnsureName(dst, cp);
                dst.Imports.Add(new UAssetAPI.Import(cp, cn, new FPackageIndex(mappedOuter), on, si.bImportOptional, dst));
                di = -dst.Imports.Count;
            }
            importRemap[z] = di;
            return di;
        }

        int newActorNum = dst.Exports.Count + 1;
        int[] newChildNums = srcChildren.Select((_, i) => newActorNum + 1 + i).ToArray();
        int RemapIndex(int s)
        {
            if (s == 0) return 0;
            if (s > 0)
            {
                if (s == srcActorNum) return newActorNum;
                int pos = srcChildren.IndexOf(s - 1);
                if (pos >= 0) return newChildNums[pos];
                if (s - 1 < src.Exports.Count && src.Exports[s - 1] is LevelExport) return dstLevelNum;
                return 0;
            }
            return RemapImport(s);
        }
        Export DeepClone(Export e)
        {
            Export d = e is NormalExport ne
                ? new NormalExport { Data = ne.Data.Select(p => (PropertyData)p.Clone()).ToList(), ObjectGuid = ne.ObjectGuid, SerializationControl = ne.SerializationControl, Operation = ne.Operation, HasLeadingFourNullBytes = ne.HasLeadingFourNullBytes }
                : new RawExport { Data = ((RawExport)e).Data != null ? (byte[])((RawExport)e).Data.Clone() : Array.Empty<byte>() };
            d.Asset = dst;
            EnsureName(dst, e.ObjectName.ToString());
            d.ObjectName = FName.FromString(dst, e.ObjectName.ToString());
            d.ClassIndex = new FPackageIndex(RemapIndex(e.ClassIndex.Index));
            d.SuperIndex = new FPackageIndex(RemapIndex(e.SuperIndex.Index));
            d.TemplateIndex = new FPackageIndex(RemapIndex(e.TemplateIndex.Index));
            d.OuterIndex = new FPackageIndex(RemapIndex(e.OuterIndex.Index));
            d.ObjectFlags = e.ObjectFlags;
            d.bNotAlwaysLoadedForEditorGame = e.bNotAlwaysLoadedForEditorGame;
            d.IsInheritedInstance = e.IsInheritedInstance;
            d.SerializationBeforeSerializationDependencies = e.SerializationBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.CreateBeforeSerializationDependencies = e.CreateBeforeSerializationDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.SerializationBeforeCreateDependencies = e.SerializationBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.CreateBeforeCreateDependencies = e.CreateBeforeCreateDependencies.Select(x => new FPackageIndex(RemapIndex(x.Index))).ToList();
            d.Extras = e.Extras != null ? (byte[])e.Extras.Clone() : null;
            return d;
        }

        var newActor = DeepClone(srcActor);
        newActor.OuterIndex = new FPackageIndex(dstLevelNum);
        string label = $"{srcActor.ObjectName}_FOL";
        int suf = 0; string fl = label;
        while (dst.Exports.Any(e => e.ObjectName.ToString() == fl)) fl = $"{label}_{++suf}";
        EnsureName(dst, fl); newActor.ObjectName = FName.FromString(dst, fl);
        dst.Exports.Add(newActor);
        foreach (var ci in srcChildren)
        {
            var ccx = DeepClone(src.Exports[ci]);
            ccx.OuterIndex = new FPackageIndex(newActorNum);
            dst.Exports.Add(ccx);
        }

        void RemapPropRefs(PropertyData p)
        {
            if (p is ObjectPropertyData op && op.Value != null) op.Value = new FPackageIndex(RemapIndex(op.Value.Index));
            else if (p is ArrayPropertyData ap && ap.Value != null) foreach (var x in ap.Value) RemapPropRefs(x);
            else if (p is StructPropertyData sp2 && sp2.Value != null) foreach (var x in sp2.Value) RemapPropRefs(x);
        }
        if (newActor is NormalExport na) foreach (var p in na.Data) RemapPropRefs(p);
        foreach (var n in newChildNums)
            if (dst.Exports[n - 1] is NormalExport nc) foreach (var p in nc.Data) RemapPropRefs(p);

        // mesh import + grid
        int meshPkg = FindOrAddImport(dst, pkgPath, 0, "/Script/CoreUObject", "Package");
        int meshImp = FindOrAddImport(dst, exportName, meshPkg, "/Script/Engine", "StaticMesh");
        // Optional Z-layering: repeat the X-Y grid at `zlayers` heights (step
        // `zstep`) starting at gz. Lets a probe span unknown terrain height so
        // it's visible regardless of where the ground is.
        int zlayers = f.TryGetValue("zlayers", out var zlv) ? int.Parse(zlv) : 1;
        double zstep = f.TryGetValue("zstep", out var zsv) ? double.Parse(zsv, inv) : 2000;
        var mats = new List<double[]>();
        int side = (int)Math.Ceiling(Math.Sqrt(count));
        for (int L = 0; L < zlayers; L++)
            for (int gi = 0; gi < side; gi++)
                for (int gj = 0; gj < side; gj++)
                {
                    if (gi * side + gj >= count) break;
                    var m = new double[16] { 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 };
                    m[12] = gx + (gi - side / 2.0) * sp;
                    m[13] = gy + (gj - side / 2.0) * sp;
                    m[14] = gz + L * zstep;
                    mats.Add(m);
                }

        int fismc = 0;
        foreach (var n in newChildNums)
        {
            var e = dst.Exports[n - 1];
            if (!e.ObjectName.ToString().StartsWith("FoliageInstancedStaticMeshComponent")) continue;
            if (e is NormalExport fc)
            {
                foreach (var p in fc.Data)
                {
                    if (p.Name.ToString() == "StaticMesh" && p is ObjectPropertyData op) op.Value = new FPackageIndex(meshImp);
                    if (p.Name.ToString() == "TranslatedInstanceSpaceOrigin" && p is StructPropertyData spd && spd.Value.Count > 0 && spd.Value[0] is VectorPropertyData vp) vp.Value = new FVector(gx, gy, gz);
                }
                fc.Extras = BuildFoliageExtras(mats);
                fismc++;
            }
        }
        if (fismc == 0) { Console.Error.WriteLine("no FISMC child found in source"); return 1; }

        // regenerate IFA GUID in Extras (count + strlen + name + GUID + pad)
        if (newActor.Extras != null && newActor.Extras.Length >= 44)
        {
            int cnt = BitConverter.ToInt32(newActor.Extras, 0);
            int strlen = BitConverter.ToInt32(newActor.Extras, 4);
            if (cnt == 1 && strlen > 0 && 8 + strlen + 16 <= newActor.Extras.Length)
                Guid.NewGuid().ToByteArray().CopyTo(newActor.Extras, 8 + strlen);
        }

        ConvertTrailingNormalExportsToRaw(dst, 1 + srcChildren.Count);

        if (dst.Exports[dstLevelIdx] is LevelExport lvl)
        {
            lvl.Actors.Add(new FPackageIndex(newActorNum));
            lvl.CreateBeforeSerializationDependencies.Add(new FPackageIndex(newActorNum));
        }

        var outDir = Path.GetDirectoryName(f["output"]);
        if (!string.IsNullOrEmpty(outDir)) Directory.CreateDirectory(outDir);
        dst.Write(f["output"]);
        Console.WriteLine($"foliage probe: IFA #{newActorNum} ({fl}), {mats.Count} instances of {exportName} at ({gx},{gy},{gz}) -> {Path.GetFileName(f["output"])}");
        return 0;
    }

    // Replace EVERY export except those in keepIdx with a RawExport holding its
    // ORIGINAL serialized bytes (read from the source file). asset.Write then
    // only re-serializes the kept exports (the modified FISMCs), leaving the
    // level, IFA, ChildActors, materials, etc. byte-perfect — UAssetAPI's
    // re-serialization of UE5.5 WP cell content (level + complex BP actors)
    // corrupts them, which breaks cell streaming. Verbatim is safe.
    private static void ConvertCellExportsToRawExcept(UAsset asset, string cellPath, HashSet<int> keepIdx)
    {
        string uexp = Path.ChangeExtension(cellPath, ".uexp");
        byte[] umapB = File.ReadAllBytes(cellPath);
        byte[] uexpB = File.Exists(uexp) ? File.ReadAllBytes(uexp) : Array.Empty<byte>();
        int converted = 0;
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            if (keepIdx.Contains(i)) continue;
            var e = asset.Exports[i];
            if (e is RawExport) continue;
            long off = e.SerialOffset, sz = e.SerialSize;
            if (sz <= 0) continue;
            var body = new byte[sz];
            if (off >= umapB.Length) Array.Copy(uexpB, off - umapB.Length, body, 0, (int)sz);
            else Array.Copy(umapB, off, body, 0, (int)sz);
            var raw = new RawExport { Data = body, Asset = asset };
            CopyExportHeader(from: e, to: raw);
            raw.Extras = Array.Empty<byte>();
            asset.Exports[i] = raw;
            converted++;
        }
        Console.WriteLine($"  raw-preserved {converted} export(s); re-serialized only {keepIdx.Count} FISMC(s)");
    }

    // Dump a named export's raw Extras (and key props) for instance-buffer
    // reverse-engineering. --cell <umap> --name <export> --out <file> --mappings <usmap>
    private static int DumpExtras(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["cell"], EngineVer, LoadMappings(f["mappings"]));
        var name = f["name"];
        foreach (var e in asset.Exports)
        {
            if (e.ObjectName.ToString() != name) continue;
            var ex = e.Extras ?? Array.Empty<byte>();
            File.WriteAllBytes(f["out"], ex);
            int meshRef = 0;
            if (e is NormalExport ne)
                foreach (var p in ne.Data)
                    if (p.Name.ToString() == "StaticMesh" && p is ObjectPropertyData op)
                        meshRef = op.Value?.Index ?? 0;
            Console.WriteLine($"{name}: Extras={ex.Length} bytes, StaticMesh={meshRef} -> {f["out"]}");
            return 0;
        }
        Console.Error.WriteLine($"export '{name}' not found");
        return 1;
    }

    private static int InjectStatic(string[] args)
    {
        var f = ParseFlags(args);
        var mainPath = f["main"];
        var outPath  = f["output"];
        var mappings = LoadMappings(f["mappings"]);
        // --roundtrip: load + write the vanilla map with ZERO injection, to
        // test whether UAssetAPI's read/write of this UE5.5 WP map is itself
        // game-faithful (isolates the write path from the injected actors).
        bool roundtrip = f.ContainsKey("roundtrip");
        var config = roundtrip && !f.ContainsKey("config")
            ? new JObject()
            : JObject.Parse(File.ReadAllText(f["config"]));

        Console.WriteLine($"Loading main map: {mainPath}");
        var asset = new UAsset(mainPath, EngineVer, mappings);
        Console.WriteLine($"  {asset.Exports.Count} exports, {asset.Imports.Count} imports");
        if (roundtrip) Console.WriteLine("  --roundtrip: writing back with NO injection");

        int levelIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { levelIdx = i; break; }
        if (levelIdx < 0)
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].ObjectName.ToString() == "PersistentLevel") { levelIdx = i; break; }
        if (levelIdx < 0) throw new InvalidOperationException("No PersistentLevel found");
        int levelNum = levelIdx + 1;

        var newActorNums = new List<int>();
        void AddRaw(RawExport e)
        {
            asset.Exports.Add(e);
            asset.DependsMap?.Add(Array.Empty<int>());   // shared singleton — cheap
        }

        int enginePkg = FindOrAddImport(asset, "/Script/Engine", 0, "/Script/CoreUObject", "Package");

        // -------------------- DEALERSHIPS --------------------
        int nDealers = 0;
        if (config["dealerships"] is JObject dealerSection)
        {
            int mtPkg        = FindOrAddImport(asset, "/Script/MotorTown", 0, "/Script/CoreUObject", "Package");
            int dealerClass  = FindOrAddImport(asset, "MTDealerVehicleSpawnPoint", mtPkg, "/Script/CoreUObject", "Class");
            int defaultDealer= FindOrAddImport(asset, "Default__MTDealerVehicleSpawnPoint", mtPkg, "/Script/MotorTown", "MTDealerVehicleSpawnPoint");
            int sceneClass   = FindOrAddImport(asset, "SceneComponent", enginePkg, "/Script/CoreUObject", "Class");
            int rootsceneTpl = FindOrAddImport(asset, "RootScene", defaultDealer, "/Script/Engine", "SceneComponent");
            EnsureName(asset, "MTDealerVehicleSpawnPoint_MOD");
            EnsureName(asset, "RootScene");

            var vehCache = new Dictionary<string, int>();
            foreach (var grp in dealerSection.Properties())
            {
                if (grp.Value is not JArray arr) continue;
                foreach (var tok in arr)
                {
                    if (tok is not JObject e) continue;
                    string? vehPath = (string?)e["vehicle_path"];
                    if (string.IsNullOrEmpty(vehPath)) continue;
                    // The class name comes from the PACKAGE, never from
                    // vehicle_key. A key is a DataTable row name, and most
                    // rows are not named after their asset: row
                    // Trailer_Cotra_20_3L is asset Cotra_20_3L, row Bus is
                    // AirCity, row Police_01 is Police. Keying the class off
                    // the row imports a class that exists in no package, so
                    // the spawner references nothing and spawns nothing --
                    // silently, with a clean build log. vehicle_key stays as
                    // the actor label only.
                    string assetName = vehPath[(vehPath.LastIndexOf('/') + 1)..];
                    string? vehKey = (string?)e["vehicle_key"];
                    if (string.IsNullOrEmpty(vehKey)) vehKey = assetName;
                    if (!vehCache.TryGetValue(vehPath, out int vehImp))
                    {
                        int vp = FindOrAddImport(asset, vehPath, 0, "/Script/CoreUObject", "Package");
                        vehImp = FindOrAddImport(asset, assetName + "_C", vp, "/Script/Engine", "BlueprintGeneratedClass");
                        vehCache[vehPath] = vehImp;
                    }
                    double x = (double?)e["X"] ?? 0, y = (double?)e["Y"] ?? 0, z = (double?)e["Z"] ?? 0;
                    double pitch = (double?)e["Pitch"] ?? 0, yaw = (double?)e["Yaw"] ?? 0, roll = (double?)e["Roll"] ?? 0;
                    int actorNum = asset.Exports.Count + 1;
                    int compNum  = asset.Exports.Count + 2;
                    AddRaw(NewRaw(asset, BuildDealerActorData(vehImp, compNum, vehKey),
                        $"MTDealerVehicleSpawnPoint_MOD_{nDealers}", levelNum, dealerClass, defaultDealer,
                        EObjectFlags.RF_Transactional, false,
                        cbsd: new[] { vehImp, compNum }, sbcd: new[] { dealerClass, defaultDealer, rootsceneTpl }, cbcd: new[] { levelNum }));
                    AddRaw(NewRaw(asset, BuildDealerRootScene(x, y, z, pitch, yaw, roll),
                        "RootScene", actorNum, sceneClass, rootsceneTpl,
                        EObjectFlags.RF_Transactional | EObjectFlags.RF_DefaultSubObject, true,
                        cbsd: null, sbcd: new[] { sceneClass, rootsceneTpl }, cbcd: new[] { actorNum }));
                    newActorNums.Add(actorNum);
                    nDealers++;
                }
            }
            Console.WriteLine($"Injected {nDealers} dealer spawn points");
        }

        // -------------------- LOCAL FOG VOLUMES --------------------
        // ALocalFogVolume is an engine class present in MT's build (it is in
        // the .usmap) that the game never places. Authored in the editor and
        // exported by ue.py, rebuilt here as a real actor + component pair.
        // Built as NormalExports so UAssetAPI writes the unversioned property
        // headers from the mappings -- hand-rolling those bytes for a class
        // we have never shipped is how you get a silently broken actor.
        var fogArr = config["fog_volumes"] as JArray;
        int nFog = 0;
        if (fogArr != null && fogArr.Count > 0)
        {
            int fogPkg   = FindOrAddImport(asset, "/Script/Engine", 0, "/Script/CoreUObject", "Package");
            int fogCls   = FindOrAddImport(asset, "LocalFogVolume", fogPkg, "/Script/CoreUObject", "Class");
            int fogCompC = FindOrAddImport(asset, "LocalFogVolumeComponent", fogPkg, "/Script/CoreUObject", "Class");
            // ARCHETYPES. Every real actor in Jeju points TemplateIndex at its
            // CDO and its component at the CDO's subobject -- ExponentialHeightFog_1
            // is TemplateIndex=-1729 (Default__ExponentialHeightFog) with
            // HeightFogComponent0 at -1730. The first cut of this left both at 0,
            // so UE had no archetype to construct from and the actor did nothing.
            // That, not r.SupportLocalFogVolumes, is why the 12 Aug attempt was
            // invisible and got deleted.
            int fogDflt  = FindOrAddImport(asset, "Default__LocalFogVolume", fogPkg, "/Script/Engine", "LocalFogVolume");
            int fogCompT = FindOrAddImport(asset, "LocalFogVolumeComponent", fogDflt, "/Script/Engine", "LocalFogVolumeComponent");
            foreach (var tok in fogArr)
            {
                if (tok is not JObject e) continue;
                double x = (double?)e["X"] ?? 0, y = (double?)e["Y"] ?? 0, z = (double?)e["Z"] ?? 0;
                double pitch = (double?)e["Pitch"] ?? 0, yaw = (double?)e["Yaw"] ?? 0, roll = (double?)e["Roll"] ?? 0;
                double sx = (double?)e["ScaleX"] ?? 1, sy = (double?)e["ScaleY"] ?? 1, sz = (double?)e["ScaleZ"] ?? 1;
                string label = (string?)e["name"] ?? $"LocalFogVolume_{nFog}";

                int actorNum = asset.Exports.Count + 1;
                int compNum  = asset.Exports.Count + 2;

                EnsureName(asset, "LocalFogVolumeVolume");
                EnsureName(asset, "RootComponent");
                var actorEx = new NormalExport(asset, Array.Empty<byte>())
                {
                    ObjectName = FName.FromString(asset, label),
                    OuterIndex = new FPackageIndex(levelNum),
                    ClassIndex = new FPackageIndex(fogCls),
                    TemplateIndex = new FPackageIndex(fogDflt),
                    SuperIndex = new FPackageIndex(0),
                    ObjectFlags = EObjectFlags.RF_Transactional,
                    Data = new List<PropertyData>(),
                    // Every actor export in a cooked level carries trailing
                    // metadata -- count, label, FGuid, padding. A real cooked
                    // LocalFogVolume_0 has 55 bytes of it; ours had none, so the
                    // loader read the following export's bytes as this one's
                    // metadata. MakeActorExtras emits exactly that layout.
                    Extras = MakeActorExtras(label),
                    bNotAlwaysLoadedForEditorGame = true,
                };
                actorEx.Data.Add(new ObjectPropertyData(FName.FromString(asset, "LocalFogVolumeVolume"))
                    { Value = new FPackageIndex(compNum) });
                actorEx.Data.Add(new ObjectPropertyData(FName.FromString(asset, "RootComponent"))
                    { Value = new FPackageIndex(compNum) });
                actorEx.CreateBeforeSerializationDependencies.Add(new FPackageIndex(compNum));
                actorEx.CreateBeforeCreateDependencies.Add(new FPackageIndex(levelNum));
                // Reference actor reports SBCD=3: its class, its CDO, and the
                // component class it instantiates.
                actorEx.SerializationBeforeCreateDependencies.Add(new FPackageIndex(fogCls));
                actorEx.SerializationBeforeCreateDependencies.Add(new FPackageIndex(fogDflt));
                actorEx.SerializationBeforeCreateDependencies.Add(new FPackageIndex(fogCompC));
                asset.Exports.Add(actorEx);

                var compEx = new NormalExport(asset, Array.Empty<byte>())
                {
                    ObjectName = FName.FromString(asset, "LocalFogVolumeComponent"),
                    OuterIndex = new FPackageIndex(actorNum),
                    ClassIndex = new FPackageIndex(fogCompC),
                    TemplateIndex = new FPackageIndex(fogCompT),
                    SuperIndex = new FPackageIndex(0),
                    ObjectFlags = EObjectFlags.RF_Transactional | EObjectFlags.RF_DefaultSubObject,
                    // The real HeightFogComponent0 reports IsInherited=True: it is
                    // the class's own subobject, not a fresh object of ours.
                    IsInheritedInstance = true,
                    Data = new List<PropertyData>(),
                    // Reference component carries 4 zero bytes here, not zero
                    // bytes. Same reason as the actor's blob.
                    Extras = new byte[4],
                    bNotAlwaysLoadedForEditorGame = true,
                };
                void F(string n, double? v, double dflt)
                {
                    EnsureName(asset, n);
                    compEx.Data.Add(new FloatPropertyData(FName.FromString(asset, n))
                        { Value = (float)(v ?? dflt) });
                }
                F("RadialFogExtinction", (double?)e["RadialFogExtinction"], 1.0);
                F("HeightFogExtinction", (double?)e["HeightFogExtinction"], 1.0);
                F("HeightFogFalloff",    (double?)e["HeightFogFalloff"], 1.0);
                F("HeightFogOffset",     (double?)e["HeightFogOffset"], 0.0);
                F("FogPhaseG",           (double?)e["FogPhaseG"], 0.0);
                // Colours. ue.py exports FogAlbedo and FogEmissive as [r,g,b,a]
                // and the injector used to drop them, so a fog tinted in the
                // editor arrived white. The reference component writes
                // FogEmissive as a LinearColor struct, same shape as the Vector
                // properties above.
                void C(string n, JToken? tok)
                {
                    if (tok is not JArray arr || arr.Count < 3) return;
                    EnsureName(asset, n);
                    EnsureName(asset, "LinearColor");
                    compEx.Data.Add(new StructPropertyData(FName.FromString(asset, n),
                                                           FName.FromString(asset, "LinearColor"))
                    {
                        Value = new List<PropertyData> {
                            new LinearColorPropertyData(FName.FromString(asset, n))
                            {
                                Value = new FLinearColor(
                                    (float)arr[0], (float)arr[1], (float)arr[2],
                                    arr.Count > 3 ? (float)arr[3] : 1.0f)
                            } }
                    });
                }
                C("FogAlbedo",   e["FogAlbedo"]);
                C("FogEmissive", e["FogEmissive"]);

                int prio = (int?)e["FogSortPriority"] ?? 0;
                if (prio != 0)
                {
                    EnsureName(asset, "FogSortPriority");
                    compEx.Data.Add(new IntPropertyData(FName.FromString(asset, "FogSortPriority")) { Value = prio });
                }
                AddTransform(asset, compEx, x, y, z, pitch, yaw, roll, sx, sy, sz);
                compEx.CreateBeforeCreateDependencies.Add(new FPackageIndex(actorNum));
                compEx.SerializationBeforeCreateDependencies.Add(new FPackageIndex(fogCompC));
                compEx.SerializationBeforeCreateDependencies.Add(new FPackageIndex(fogCompT));
                asset.Exports.Add(compEx);

                newActorNums.Add(actorNum);
                nFog++;
                Console.WriteLine($"  fog '{label}' at ({x:F0},{y:F0},{z:F0}) scale {sx:F1} "
                                  + $"radial={(double?)e["RadialFogExtinction"] ?? 1.0}");
            }
            Console.WriteLine($"Injected {nFog} local fog volume(s)");
        }

        // -------------------- STATIC MESHES (streamed) --------------------
        long nMeshes = 0;
        var marker = (config["static_meshes"] as JObject)?["_imported_shards"] as JObject;
        if (marker != null)
        {
            string dir     = (string)marker["dir"]!;
            string? prefix = (string?)marker["prefix"];
            int smaClass   = FindOrAddImport(asset, "StaticMeshActor", enginePkg, "/Script/CoreUObject", "Class");
            int defaultSma = FindOrAddImport(asset, "Default__StaticMeshActor", enginePkg, "/Script/Engine", "StaticMeshActor");
            int smcClass   = FindOrAddImport(asset, "StaticMeshComponent", enginePkg, "/Script/CoreUObject", "Class");
            int smc0Tpl    = FindOrAddImport(asset, "StaticMeshComponent0", defaultSma, "/Script/Engine", "StaticMeshComponent");
            EnsureName(asset, "StaticMeshActor_MOD");
            EnsureName(asset, "StaticMeshComponent0");

            // Diagnostic: substitute a KNOWN-VISIBLE mesh for entries whose
            // asset path contains --debug-mesh-for. A Volume-domain material
            // draws nothing as a surface, so an invisible fog blob and an actor
            // that never spawned look identical in game; a solid shape at the
            // right coordinates tells them apart.
            //
            // This swaps the MESH rather than overriding the material, because
            // the swap happens before the import is created and the entry then
            // flows through the same path all 14,280 meshes already use. The
            // material-override version wrote four extra bytes into a
            // reverse-engineered raw component blob and crashed the game at
            // startup.
            string? debugMeshFor = f.GetValueOrDefault("debug-mesh-for");
            string? debugMeshPath = f.GetValueOrDefault("debug-mesh");
            bool debugMesh = !string.IsNullOrEmpty(debugMeshFor) && !string.IsNullOrWhiteSpace(debugMeshPath);
            // The replacement mesh is almost never the same size as the one it
            // replaces -- SM_Particle_Smoke_01a has a 12.8 uu bounding sphere
            // against SM_Fog_01's 373 -- so the substitution is useless without
            // a scale multiplier on top of whatever the entry already carries.
            double debugMeshScale = 1.0;
            if (f.TryGetValue("debug-mesh-scale", out var dms) && double.TryParse(dms, out double dmsv) && dmsv > 0)
                debugMeshScale = dmsv;
            if (debugMesh)
                Console.WriteLine($"  substituting mesh '{debugMeshPath}' x{debugMeshScale:G} for entries matching '{debugMeshFor}'");

            var meshCache = new Dictionary<string, int>();
            foreach (var entry in IterShardEntries(dir, prefix))
            {
                string assetPath = (string)entry["asset_path"]!;
                bool substituted = debugMesh && assetPath.Contains(debugMeshFor!, StringComparison.OrdinalIgnoreCase);
                if (substituted)
                {
                    Console.WriteLine($"    mesh: {assetPath} -> {debugMeshPath}");
                    assetPath = debugMeshPath!;
                }
                // resolve_mesh_path: strip "<pkg>.<obj>" suffix
                int lastSlash = assetPath.LastIndexOf('/');
                int dot = assetPath.IndexOf('.', lastSlash < 0 ? 0 : lastSlash);
                string pkgPath = dot >= 0 ? assetPath.Substring(0, dot) : assetPath;
                string? exportName = (string?)entry["asset_key"];
                if (string.IsNullOrEmpty(exportName)) exportName = pkgPath[(pkgPath.LastIndexOf('/') + 1)..];
                if (!meshCache.TryGetValue(pkgPath, out int meshImp))
                {
                    int mp = FindOrAddImport(asset, pkgPath, 0, "/Script/CoreUObject", "Package");
                    meshImp = FindOrAddImport(asset, exportName, mp, "/Script/Engine", "StaticMesh");
                    meshCache[pkgPath] = meshImp;
                }
                double x = (double?)entry["X"] ?? 0, y = (double?)entry["Y"] ?? 0, z = (double?)entry["Z"] ?? 0;
                double pitch = (double?)entry["Pitch"] ?? 0, yaw = (double?)entry["Yaw"] ?? 0, roll = (double?)entry["Roll"] ?? 0;
                double sx = (double?)entry["ScaleX"] ?? 1.0, sy = (double?)entry["ScaleY"] ?? 1.0, sz = (double?)entry["ScaleZ"] ?? 1.0;
                if (substituted) { sx *= debugMeshScale; sy *= debugMeshScale; sz *= debugMeshScale; }
                int actorNum = asset.Exports.Count + 1;
                int compNum  = asset.Exports.Count + 2;
                AddRaw(NewRaw(asset, BuildSmaActorData(compNum, exportName),
                    $"StaticMeshActor_MOD_{nMeshes}", levelNum, smaClass, defaultSma,
                    EObjectFlags.RF_Transactional, false,
                    cbsd: new[] { compNum }, sbcd: new[] { smaClass, defaultSma, smc0Tpl }, cbcd: new[] { levelNum }));
                AddRaw(NewRaw(asset, BuildSmcData(meshImp, x, y, z, pitch, yaw, roll, sx, sy, sz),
                    "StaticMeshComponent0", actorNum, smcClass, smc0Tpl,
                    EObjectFlags.RF_Transactional | EObjectFlags.RF_DefaultSubObject, true,
                    cbsd: new[] { meshImp }, sbcd: new[] { smcClass, smc0Tpl }, cbcd: new[] { actorNum }));
                newActorNums.Add(actorNum);
                nMeshes++;
                if (nMeshes % 500000 == 0) Console.WriteLine($"  ... {nMeshes} meshes built");
            }
            Console.WriteLine($"Injected {nMeshes} static mesh actors (streamed from {dir})");
        }

        if (newActorNums.Count == 0 && !roundtrip) { Console.WriteLine("Nothing to inject."); return 0; }

        if (newActorNums.Count > 0)
        {
            // Add actors the TYPED way (lvl.Actors.Add) — a no-op UAssetAPI
            // round-trip of this map loads in-game, so UAssetAPI's typed
            // LevelExport write is faithful here; reuse it. Converting the
            // level to a raw binary-patched export (PatchLevelExportAsRaw)
            // crashed world load, so it's only the fallback for a non-typed
            // level. Each actor also goes into the level's CBSD preload arcs.
            if (asset.Exports[levelIdx] is LevelExport lvlExp)
            {
                Console.WriteLine($"Adding {newActorNums.Count} actors to typed LevelExport.Actors ...");
                foreach (var n in newActorNums)
                {
                    lvlExp.Actors.Add(new FPackageIndex(n));
                    lvlExp.CreateBeforeSerializationDependencies.Add(new FPackageIndex(n));
                }
            }
            else
            {
                Console.WriteLine($"Patching PersistentLevel actor list (+{newActorNums.Count}, raw fallback) ...");
                PatchLevelExportAsRaw(asset, mainPath, newActorNums);
            }
        }

        // Volumetric fog reach. The froxel grid the fog is integrated in only
        // extends VolumetricFogDistance from the camera, and Jeju ships 15000
        // uu = 150 m. That is the ONE hard numeric limit on whether a
        // Volume-domain fog mesh can be seen: our blobs have a 37 m radius and
        // sit 160-270 m from Galati Port, so from most of the approach they are
        // outside the grid entirely and cannot be voxelized at any quality
        // setting. Widening it costs nothing per frame -- GridSizeZ stays at
        // 128 slices, they just each cover more depth -- so the fog gets a
        // window you can actually drive into. Done here because this step
        // already has the 100k-export map open; a standalone pass would mean
        // another parse and write of the largest asset in the game.
        // Arbitrary float properties on the height fog, "Name=Value,Name=Value".
        // This is the ONE fog system in this game known to render: it is the
        // game's own, it is already on, and Jeju's fog is drawn by it every
        // frame. Three separate attempts at mesh-based fog were invisible while
        // an ordinary mesh at the identical coordinates was not, so rather than
        // keep hunting for a mesh that draws, drive the fog that already does.
        // Trade-off: an ExponentialHeightFog is GLOBAL. There is exactly one
        // per scene -- ShouldRenderVolumetricFog only ever reads
        // ExponentialFogs[0] -- so tuning it changes Jeju's weather too.
        var fogPropsFile = f.GetValueOrDefault("fog-props-file");
        bool haveFogFile = !string.IsNullOrWhiteSpace(fogPropsFile) && File.Exists(fogPropsFile);
        if ((f.TryGetValue("fog-props", out var fogProps) && !string.IsNullOrWhiteSpace(fogProps))
            || haveFogFile)
        {
            var wanted = new List<(string name, float val)>();
            foreach (var kv in (fogProps ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries))
            {
                var bits = kv.Split('=', 2);
                if (bits.Length == 2 && float.TryParse(bits[1].Trim(),
                        System.Globalization.NumberStyles.Float,
                        System.Globalization.CultureInfo.InvariantCulture, out float v))
                    wanted.Add((bits[0].Trim(), v));
                else
                    Console.Error.WriteLine($"  WARNING: bad --fog-props entry '{kv}' — skipped");
            }
            // height_fog.json, written by ue.py from the fog you tuned in the
            // viewport, wins over the flag: the editor is the place you can
            // actually see what you are doing, so it is the source of truth.
            if (haveFogFile)
            {
                try
                {
                    var jo = JObject.Parse(File.ReadAllText(fogPropsFile!));
                    int n = 0;
                    foreach (var prop in jo.Properties())
                    {
                        if (prop.Value.Type is JTokenType.Float or JTokenType.Integer)
                        {
                            wanted.RemoveAll(w => w.name == prop.Name);
                            wanted.Add((prop.Name, (float)prop.Value));
                            n++;
                        }
                    }
                    Console.WriteLine($"  fog: {n} value(s) from {Path.GetFileName(fogPropsFile)} (editor wins over --fog-props)");
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"  WARNING: could not read {fogPropsFile}: {ex.Message}");
                }
            }
            foreach (var ex in asset.Exports)
            {
                if (ex.GetExportClassType()?.Value?.Value != "ExponentialHeightFogComponent") continue;
                if (ex is not NormalExport hfcp) continue;
                foreach (var (name, val) in wanted)
                {
                    EnsureName(asset, name);
                    var cur = hfcp.Data.FirstOrDefault(p => p.Name.ToString() == name);
                    float was = cur is FloatPropertyData cfp ? cfp.Value : float.NaN;
                    if (cur is FloatPropertyData fpx) fpx.Value = val;
                    else hfcp.Data.Add(new FloatPropertyData(FName.FromString(asset, name)) { Value = val });
                    Console.WriteLine($"  {ex.ObjectName}.{name} {(float.IsNaN(was) ? "(default)" : was.ToString())} -> {val}");
                }
            }
        }

        if (f.TryGetValue("fog-distance", out var fogDistStr)
            && float.TryParse(fogDistStr, out float fogDist) && fogDist > 0)
        {
            int patched = 0;
            foreach (var ex in asset.Exports)
            {
                if (ex.GetExportClassType()?.Value?.Value != "ExponentialHeightFogComponent") continue;
                if (ex is not NormalExport hfc) continue;
                EnsureName(asset, "VolumetricFogDistance");
                var existing = hfc.Data.FirstOrDefault(p => p.Name.ToString() == "VolumetricFogDistance");
                float was = existing is FloatPropertyData efp ? efp.Value : float.NaN;
                if (existing is FloatPropertyData fp2) fp2.Value = fogDist;
                else hfc.Data.Add(new FloatPropertyData(FName.FromString(asset, "VolumetricFogDistance")) { Value = fogDist });
                // Volumetric fog off means no voxelization at all, whatever the
                // distance, so pin it while we are here.
                EnsureName(asset, "bEnableVolumetricFog");
                var vf = hfc.Data.FirstOrDefault(p => p.Name.ToString() == "bEnableVolumetricFog");
                if (vf is BoolPropertyData vbp) vbp.Value = true;
                else hfc.Data.Add(new BoolPropertyData(FName.FromString(asset, "bEnableVolumetricFog")) { Value = true });
                Console.WriteLine($"  {ex.ObjectName}.VolumetricFogDistance {was} -> {fogDist} "
                                  + $"({fogDist / 100:F0} m), bEnableVolumetricFog=true");
                patched++;
            }
            if (patched == 0)
                Console.Error.WriteLine("  WARNING: --fog-distance given but no ExponentialHeightFogComponent found");
        }

        var outDir = Path.GetDirectoryName(outPath);
        if (!string.IsNullOrEmpty(outDir)) Directory.CreateDirectory(outDir);
        Console.WriteLine($"Writing {outPath} ({asset.Exports.Count} exports, {asset.Imports.Count} imports) ...");
        asset.Write(outPath);

        // NO .ubulk copy. We ship the map under its vanilla path, so the
        // engine resolves Jeju_World.ubulk out of the base game pak — an
        // identical copy in our pak just cost 4.8 GB of pak (95% of it).
        // Cell clones are different: they get a NEW name, so their .ubulk
        // must be copied (see the cell paths above).
        var staleUbulk = Path.Combine(outDir!, Path.GetFileNameWithoutExtension(mainPath) + ".ubulk");
        if (File.Exists(staleUbulk))
        {
            File.Delete(staleUbulk);
            Console.WriteLine("  dropped vanilla .ubulk copy from the mod tree (base pak provides it)");
        }
        Console.WriteLine($"Done. dealers={nDealers} meshes={nMeshes} totalExports={asset.Exports.Count}");
        return 0;
    }

    // Build a RawExport with the standard header fields + dependency arcs.
    private static RawExport NewRaw(UAsset asset, byte[] data, string name, int outer,
        int classIdx, int templateIdx, EObjectFlags flags, bool inherited,
        int[]? cbsd, int[]? sbcd, int[]? cbcd)
    {
        List<FPackageIndex> Mk(int[]? a) => a == null
            ? new List<FPackageIndex>()
            : a.Select(n => new FPackageIndex(n)).ToList();
        return new RawExport
        {
            Data = data,
            Asset = asset,
            ObjectName = FName.FromString(asset, name),
            ClassIndex = new FPackageIndex(classIdx),
            SuperIndex = new FPackageIndex(0),
            TemplateIndex = new FPackageIndex(templateIdx),
            OuterIndex = new FPackageIndex(outer),
            ObjectFlags = flags,
            IsInheritedInstance = inherited,
            bNotAlwaysLoadedForEditorGame = true,
            Extras = Array.Empty<byte>(),
            SerializationBeforeSerializationDependencies = new List<FPackageIndex>(),
            CreateBeforeSerializationDependencies = Mk(cbsd),
            SerializationBeforeCreateDependencies = Mk(sbcd),
            CreateBeforeCreateDependencies = Mk(cbcd),
        };
    }

    // Stream JSONL shard entries (mesh_*.jsonl) one at a time, bounded memory.
    private static IEnumerable<JObject> IterShardEntries(string dir, string? prefix)
    {
        var pat = prefix != null ? prefix + "_*.jsonl" : "*.jsonl";
        foreach (var path in Directory.GetFiles(dir, pat).OrderBy(p => p, StringComparer.Ordinal))
        {
            using var sr = new StreamReader(path);
            string? line;
            while ((line = sr.ReadLine()) != null)
            {
                if (line.Length == 0) continue;
                yield return JObject.Parse(line);
            }
        }
    }

    // ---- RawExport binary builders (byte-for-byte from convert2.py) -------

    private static byte[] BuildSmaActorData(int compRef, string label)
    {
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        bw.Write(new byte[] { 0x00, 0x02, 0x3c, 0x03 }); // SMA_ACTOR_HEADER
        bw.Write(compRef);                               // SMC ref
        bw.Write(compRef);                               // RootComponent
        bw.Write(0);                                     // zero padding
        bw.Write(MakeActorExtras(label));                // label + GUID + pad
        return ms.ToArray();
    }

    private static byte[] BuildSmcData(int meshImpRef, double x, double y, double z,
        double pitch, double yaw, double roll, double sx, double sy, double sz)
    {
        bool hasScale = !(sx == 1.0 && sy == 1.0 && sz == 1.0);
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        // header fragments: [4,5] [42,43] [49,50] tail num=3 (no scale) / num=4 (scale)
        bw.Write((ushort)0x0204);
        bw.Write((ushort)0x0224);
        bw.Write((ushort)0x0205);
        bw.Write((ushort)(hasScale ? 0x076E : 0x056E));
        bw.Write(meshImpRef);          // StaticMesh ref
        bw.Write(2);                   // Mobility = Movable
        // OverrideMaterials, ALWAYS empty. Writing a populated array here --
        // count 1 plus an object ref -- crashed the game on startup. This is a
        // reverse-engineered unversioned layout whose trailing fields were
        // never fully identified, so inserting four bytes is not safe, and the
        // import's class has to match the material asset's real class too. If
        // a material override is ever genuinely needed, build the component as
        // a typed NormalExport instead of extending this blob.
        bw.Write(0);                   // OverrideMaterials (empty)
        bw.Write(0);                   // padding
        bw.Write(100000.0f);           // CachedMaxDrawDistance
        bw.Write(x); bw.Write(y); bw.Write(z);
        bw.Write(pitch); bw.Write(yaw); bw.Write(roll);
        if (hasScale) { bw.Write(sx); bw.Write(sy); bw.Write(sz); }
        bw.Write(new byte[12]);        // tail zeros
        bw.Write(1); bw.Write(0);      // footer
        return ms.ToArray();
    }

    private static byte[] BuildDealerActorData(int vehicleClassRef, int sceneCompRef, string label)
    {
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        bw.Write(new byte[] { 0x00, 0x02, 0x02, 0x02, 0x03, 0x02, 0x39, 0x03 }); // DEALER_ACTOR_HEADER
        bw.Write(vehicleClassRef);
        bw.Write(vehicleClassRef);
        bw.Write(sceneCompRef);
        bw.Write(sceneCompRef);
        bw.Write(0);
        bw.Write(MakeActorExtras(label));
        return ms.ToArray();
    }

    private static byte[] BuildDealerRootScene(double x, double y, double z,
        double pitch, double yaw, double roll)
    {
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        bw.Write(new byte[] { 0x05, 0x05 });  // DEALER_ROOTSCENE_HEADER
        bw.Write(x); bw.Write(y); bw.Write(z);
        bw.Write(pitch); bw.Write(yaw); bw.Write(roll);
        bw.Write(new byte[8]);
        return ms.ToArray();
    }

    // ----------------------------------------------------------------------
    // Core injection: add parking actor + 4 components to a UAsset (sub-level)
    // ----------------------------------------------------------------------
    private static void InjectParkingActor(UAsset asset, string bpPath,
                                          double x, double y, double z,
                                          double pitch, double yaw, double roll,
                                          string label)
    {
        // Derive class name from path: /Game/.../Foo -> Foo_C
        var bpClass = bpPath.Substring(bpPath.LastIndexOf('/') + 1) + "_C";

        // Fallback stub if the BP's real schema wasn't pre-loaded.
        if (asset.Mappings != null && asset.Mappings.Schemas != null
            && !asset.Mappings.Schemas.ContainsKey(bpClass))
        {
            RegisterStubSchema(asset, bpClass, bpPath, "Actor",
                "BoxComponent", "MTInteractable", "InteractionCube");
        }

        // Create / find imports
        var pkgImp = FindOrAddImport(asset, bpPath, 0, "/Script/CoreUObject", "Package");
        var clsImp = FindOrAddImport(asset, bpClass, pkgImp, "/Script/Engine", "BlueprintGeneratedClass");
        var defaultImp = FindOrAddImport(asset, $"Default__{bpClass}", pkgImp, bpPath, bpClass);
        var rootImp = FindOrAddImport(asset, "Root", defaultImp, "/Script/Engine", "SceneComponent");
        var boxImp = FindOrAddImport(asset, "Box", defaultImp, "/Script/Engine", "BoxComponent");
        var mtImp  = FindOrAddImport(asset, "MTInteractable_GEN_VARIABLE", defaultImp,
                                     "/Script/MotorTown", "MTInteractableComponent");
        var cubeImp = FindOrAddImport(asset, "InteractionCube_GEN_VARIABLE", defaultImp,
                                      "/Script/Engine", "StaticMeshComponent");

        var enginePkgImp = FindOrAddImport(asset, "/Script/Engine", 0,
                                           "/Script/CoreUObject", "Package");
        var sceneClsImp = FindOrAddImport(asset, "SceneComponent", enginePkgImp,
                                          "/Script/CoreUObject", "Class");
        var boxClsImp = FindOrAddImport(asset, "BoxComponent", enginePkgImp,
                                        "/Script/CoreUObject", "Class");
        var mtPkgImp = FindOrAddImport(asset, "/Script/MotorTown", 0,
                                       "/Script/CoreUObject", "Package");
        var mtClsImp = FindOrAddImport(asset, "MTInteractableComponent", mtPkgImp,
                                       "/Script/CoreUObject", "Class");
        var smcClsImp = FindOrAddImport(asset, "StaticMeshComponent", enginePkgImp,
                                        "/Script/CoreUObject", "Class");

        // Find PersistentLevel
        int levelIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { levelIdx = i; break; }
        if (levelIdx < 0)
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].ObjectName.ToString() == "PersistentLevel") { levelIdx = i; break; }
        if (levelIdx < 0) throw new InvalidOperationException("No PersistentLevel found");
        var level = asset.Exports[levelIdx];
        int levelNum = levelIdx + 1;

        // Pre-compute new export numbers
        int actorNum = asset.Exports.Count + 1;
        int rootNum = actorNum + 1;
        int boxNum  = actorNum + 2;
        int mtNum   = actorNum + 3;
        int cubeNum = actorNum + 4;

        EnsureName(asset, label);
        EnsureName(asset, "Root");
        EnsureName(asset, "Box");
        EnsureName(asset, "MTInteractable");
        EnsureName(asset, "InteractionCube");

        // Actor export
        var actor = new NormalExport()
        {
            ObjectName = FName.FromString(asset, label),
            ClassIndex = new FPackageIndex(clsImp),
            TemplateIndex = new FPackageIndex(defaultImp),
            OuterIndex = new FPackageIndex(levelNum),
            ObjectFlags = EObjectFlags.RF_Transactional,
            CreateBeforeSerializationDependencies = new List<FPackageIndex> {
                new(rootNum), new(boxNum), new(mtNum), new(cubeNum) },
            SerializationBeforeCreateDependencies = new List<FPackageIndex> {
                new(clsImp), new(defaultImp), new(rootImp), new(boxImp), new(mtImp), new(cubeImp) },
            CreateBeforeCreateDependencies = new List<FPackageIndex> { new(levelNum) },
            bNotAlwaysLoadedForEditorGame = true,
            Data = new List<PropertyData>
            {
                ObjProp(asset, "BoxComponent", boxNum),
                ObjProp(asset, "MTInteractable", mtNum),
                ObjProp(asset, "InteractionCube", cubeNum),
                ObjProp(asset, "RootComponent", rootNum),
                BpCreatedComponents(asset, new[] { rootNum, boxNum, mtNum, cubeNum }),
            },
            Extras = MakeActorExtras(label),
        };
        asset.Exports.Add(actor);

        // Root component
        var root = new NormalExport()
        {
            ObjectName = FName.FromString(asset, "Root"),
            ClassIndex = new FPackageIndex(sceneClsImp),
            TemplateIndex = new FPackageIndex(rootImp),
            OuterIndex = new FPackageIndex(actorNum),
            ObjectFlags = EObjectFlags.RF_Transactional | EObjectFlags.RF_DefaultSubObject,
            IsInheritedInstance = true,
            bNotAlwaysLoadedForEditorGame = true,
            SerializationBeforeCreateDependencies = new List<FPackageIndex> {
                new(sceneClsImp), new(rootImp) },
            CreateBeforeCreateDependencies = new List<FPackageIndex> { new(actorNum) },
            Data = new List<PropertyData>
            {
                VecProp(asset, "RelativeLocation", x, y, z),
                RotProp(asset, "RelativeRotation", pitch, yaw, roll),
            },
            Extras = MakeComponentExtras(),
        };
        asset.Exports.Add(root);

        // Child components — byte-layout differs by component.
        // Patterns observed on real Interaction_ParkingSpace_Large_C instances in cells:
        //   Box           : Inherited DefaultSubObject, 1 prop (AttachParent),   extras 4
        //   MTInteractable: SCS 4 props (+UCS/bNet/Creation),                    extras 4
        //   InteractionCube: SCS 4 props,                                        extras 16
        NormalExport MakeInheritedChild(string name, int classImp, int tmplImp)
        {
            EnsureName(asset, name);
            return new NormalExport()
            {
                ObjectName = FName.FromString(asset, name),
                ClassIndex = new FPackageIndex(classImp),
                TemplateIndex = new FPackageIndex(tmplImp),
                OuterIndex = new FPackageIndex(actorNum),
                ObjectFlags = EObjectFlags.RF_Transactional | EObjectFlags.RF_DefaultSubObject,
                IsInheritedInstance = true,
                bNotAlwaysLoadedForEditorGame = true,
                CreateBeforeSerializationDependencies = new List<FPackageIndex> { new(rootNum) },
                SerializationBeforeCreateDependencies = new List<FPackageIndex> {
                    new(classImp), new(tmplImp) },
                CreateBeforeCreateDependencies = new List<FPackageIndex> { new(actorNum) },
                Data = new List<PropertyData> { ObjProp(asset, "AttachParent", rootNum) },
                Extras = MakeComponentExtras(),   // 4-byte zeros
            };
        }

        NormalExport MakeScsChild(string name, int classImp, int tmplImp, bool sixteenByteExtras)
        {
            EnsureName(asset, name);
            return new NormalExport()
            {
                ObjectName = FName.FromString(asset, name),
                ClassIndex = new FPackageIndex(classImp),
                TemplateIndex = new FPackageIndex(tmplImp),
                OuterIndex = new FPackageIndex(actorNum),
                ObjectFlags = EObjectFlags.RF_NoFlags,
                IsInheritedInstance = false,
                bNotAlwaysLoadedForEditorGame = true,
                CreateBeforeSerializationDependencies = new List<FPackageIndex> { new(rootNum) },
                SerializationBeforeCreateDependencies = new List<FPackageIndex> {
                    new(classImp), new(tmplImp) },
                CreateBeforeCreateDependencies = new List<FPackageIndex> { new(actorNum) },
                Data = MakeScsComponentProps(asset, rootNum, isPrimitive: false),
                Extras = sixteenByteExtras ? MakeScsComponentExtras() : MakeComponentExtras(),
            };
        }

        asset.Exports.Add(MakeInheritedChild("Box",            boxClsImp,  boxImp));
        asset.Exports.Add(MakeScsChild      ("MTInteractable", mtClsImp,   mtImp,  sixteenByteExtras: false));
        asset.Exports.Add(MakeScsChild      ("InteractionCube",smcClsImp,  cubeImp, sixteenByteExtras: true));

        // Add to LevelExport actor list
        if (level is LevelExport lvl)
        {
            lvl.Actors.Add(new FPackageIndex(actorNum));
            lvl.CreateBeforeSerializationDependencies.Add(new FPackageIndex(actorNum));
        }
        else
        {
            // RawExport / unknown level type — attempt to add to dependency list
            level.CreateBeforeSerializationDependencies ??= new List<FPackageIndex>();
            level.CreateBeforeSerializationDependencies.Add(new FPackageIndex(actorNum));
        }

        // DependsMap (one empty entry per new export)
        for (int i = 0; i < 5; i++)
            asset.DependsMap?.Add(Array.Empty<int>());
    }

    // ----------------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------------

    // Replace the PersistentLevel LevelExport with a RawExport containing the
    // original bytes, then patch the binary Actors count+list to include new
    // actor indices. Mirrors convert2.py's approach — preserves WP metadata
    // bytes UAssetAPI doesn't fully parse.
    private static void PatchLevelExportAsRaw(UAsset asset, string originalPath, List<int> newActorIndices)
    {
        if (newActorIndices.Count == 0) return;
        int lvlIdx = -1;
        for (int i = 0; i < asset.Exports.Count; i++)
            if (asset.Exports[i] is LevelExport) { lvlIdx = i; break; }
        if (lvlIdx < 0)
        {
            for (int i = 0; i < asset.Exports.Count; i++)
                if (asset.Exports[i].ObjectName.ToString() == "PersistentLevel") { lvlIdx = i; break; }
        }
        if (lvlIdx < 0) { Console.Error.WriteLine("  No PersistentLevel found to patch"); return; }
        var lvl = asset.Exports[lvlIdx];

        // Always go through raw-byte patching: UAssetAPI's LevelExport.Write
        // is incomplete for UE5.5 WP cells (the upstream TODO). Read the
        // current body from disk, patch Actors count+list, replace with a
        // RawExport preserving the original SerialSize + Extras layout.
        // If PersistentLevel is already RawExport (chained patch), read from
        // its in-memory Data rather than disk so the accumulated patches stay.
        byte[] bodyIn;
        if (lvl is RawExport alreadyRaw && alreadyRaw.Data != null && alreadyRaw.Data.Length > 0)
        {
            bodyIn = alreadyRaw.Data;
        }
        else
        {
            string uexpPath = Path.ChangeExtension(originalPath, ".uexp");
            byte[] umapBytes = File.ReadAllBytes(originalPath);
            byte[] uexpBytes = File.Exists(uexpPath) ? File.ReadAllBytes(uexpPath) : Array.Empty<byte>();
            long off = lvl.SerialOffset;
            long sz  = lvl.SerialSize;
            if (sz <= 0) { Console.Error.WriteLine("  SerialSize unknown"); return; }
            bodyIn = new byte[sz];
            if (off >= umapBytes.Length)
                Array.Copy(uexpBytes, off - umapBytes.Length, bodyIn, 0, sz);
            else
                Array.Copy(umapBytes, off, bodyIn, 0, sz);
        }

        // Debug probe: show current count before patching
        int dbgCountPre = -1;
        byte[] markerDbg = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlDbg = IndexOfSeq(bodyIn, markerDbg);
        if (urlDbg > 0)
        {
            for (int pr = urlDbg - 4; pr >= 4; pr -= 4)
            {
                int cc = BitConverter.ToInt32(bodyIn, pr);
                if (cc > 0 && pr + 4 + cc * 4 == urlDbg) { dbgCountPre = cc; break; }
            }
        }
        Console.WriteLine($"  [dbg] PersistentLevel source={(lvl is RawExport ? "RawExport" : "LevelExport")} pre-patch count={dbgCountPre} bodyLen={bodyIn.Length}");

        int expectedCt = (lvl is LevelExport tLvl) ? tLvl.Actors.Count : -1;
        var patched = PatchActorsInBytes(bodyIn, newActorIndices, expectedCt);
        if (patched == null) { Console.Error.WriteLine("  URL marker not found in PersistentLevel body"); return; }

        if (lvl is RawExport raw)
        {
            raw.Data = patched;
            foreach (var n in newActorIndices)
                raw.CreateBeforeSerializationDependencies.Add(new FPackageIndex(n));
            Console.WriteLine($"  Patched PersistentLevel (raw in-place): +{newActorIndices.Count}");
        }
        else
        {
            var newRaw = new RawExport { Data = patched, Asset = asset };
            CopyExportHeader(from: lvl, to: newRaw);
            newRaw.Extras = Array.Empty<byte>();
            foreach (var n in newActorIndices)
                newRaw.CreateBeforeSerializationDependencies.Add(new FPackageIndex(n));
            asset.Exports[lvlIdx] = newRaw;
            Console.WriteLine($"  Patched PersistentLevel (typed -> raw): +{newActorIndices.Count}");
        }
    }

    // Patch Actors count + list in an opaque LevelExport body. Returns new bytes
    // or null if the layout couldn't be located. If expectedCount >= 0, only
    // accept a match whose int32 equals that exact value (avoids false
    // positives from both small actor indices AND large int32s that land
    // earlier in the body by coincidence).
    private static byte[] PatchActorsInBytes(byte[] body, List<int> newActorIndices, int expectedCount = -1)
    {
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(body, marker);
        if (urlOff < 0) return null;
        int countOff = -1;
        int oldCount = 0;
        if (expectedCount >= 0)
        {
            int probe = urlOff - 4 - expectedCount * 4;
            if (probe >= 4 && BitConverter.ToInt32(body, probe) == expectedCount)
            { countOff = probe; oldCount = expectedCount; }
        }
        if (countOff < 0)
        {
            // Fall back to "largest-c" heuristic.
            for (int probe = urlOff - 4; probe >= 4; probe -= 4)
            {
                int c = BitConverter.ToInt32(body, probe);
                if (c > 0 && probe + 4 + c * 4 == urlOff && c > oldCount)
                {
                    countOff = probe;
                    oldCount = c;
                }
            }
        }
        if (countOff < 0) return null;
        int newCount = oldCount + newActorIndices.Count;
        int insertBytes = newActorIndices.Count * 4;
        byte[] patched = new byte[body.Length + insertBytes];
        Array.Copy(body, patched, countOff + 4);
        BitConverter.GetBytes(newCount).CopyTo(patched, countOff);
        Array.Copy(body, countOff + 4, patched, countOff + 4, urlOff - (countOff + 4));
        for (int i = 0; i < newActorIndices.Count; i++)
            BitConverter.GetBytes(newActorIndices[i]).CopyTo(patched, urlOff + i * 4);
        Array.Copy(body, urlOff, patched, urlOff + insertBytes, body.Length - urlOff);
        return patched;
    }

    private static int IndexOfSeq(byte[] haystack, byte[] needle)
    {
        for (int i = 0; i <= haystack.Length - needle.Length; i++)
        {
            bool match = true;
            for (int j = 0; j < needle.Length; j++)
                if (haystack[i + j] != needle[j]) { match = false; break; }
            if (match) return i;
        }
        return -1;
    }

    private static void ConvertTrailingNormalExportsToRaw(UAsset asset, int countJustAdded)
    {
        if (countJustAdded <= 0) return;
        int start = asset.Exports.Count - countJustAdded;
        if (start < 0) return;

        // Normally WriteData() does this; we're pre-serializing, so do it up front.
        asset.ResolveAncestries();

        for (int i = start; i < asset.Exports.Count; i++)
        {
            var exp = asset.Exports[i];
            if (exp is RawExport) continue;

            byte[] bytes;
            using (var ms = new MemoryStream())
            using (var w = new AssetBinaryWriter(ms, asset))
            {
                exp.Write(w);
                w.Flush();
                bytes = ms.ToArray();
            }

            var raw = new RawExport
            {
                Data = bytes,
                Asset = asset,
            };
            // Copy header fields from the original Export (ClassIndex, TemplateIndex, OuterIndex, etc.)
            // Export base has shared properties we need to preserve in the export map.
            CopyExportHeader(from: exp, to: raw);
            asset.Exports[i] = raw;
        }
    }

    private static void CopyExportHeader(Export from, Export to)
    {
        to.ObjectName = from.ObjectName;
        to.ClassIndex = from.ClassIndex;
        to.SuperIndex = from.SuperIndex;
        to.TemplateIndex = from.TemplateIndex;
        to.OuterIndex = from.OuterIndex;
        to.ObjectFlags = from.ObjectFlags;
        to.SerialSize = from.SerialSize;
        to.SerialOffset = from.SerialOffset;
        to.bForcedExport = from.bForcedExport;
        to.bNotForClient = from.bNotForClient;
        to.bNotForServer = from.bNotForServer;
        to.PackageGuid = from.PackageGuid;
        to.PackageFlags = from.PackageFlags;
        to.bNotAlwaysLoadedForEditorGame = from.bNotAlwaysLoadedForEditorGame;
        to.bIsAsset = from.bIsAsset;
        to.GeneratePublicHash = from.GeneratePublicHash;
        to.SerializationBeforeSerializationDependencies = from.SerializationBeforeSerializationDependencies;
        to.CreateBeforeSerializationDependencies = from.CreateBeforeSerializationDependencies;
        to.SerializationBeforeCreateDependencies = from.SerializationBeforeCreateDependencies;
        to.CreateBeforeCreateDependencies = from.CreateBeforeCreateDependencies;
        to.IsInheritedInstance = from.IsInheritedInstance;
        to.Extras = from.Extras;
    }

    private static string DeriveContentRoot(string gameContentCellsDir)
    {
        // .../Content/Maps/Jeju/Jeju_World/_Generated_  ->  .../Content
        var d = new DirectoryInfo(gameContentCellsDir);
        while (d != null && !string.Equals(d.Name, "Content", StringComparison.OrdinalIgnoreCase))
            d = d.Parent;
        return d?.FullName ?? gameContentCellsDir;
    }

    private static string? ResolveBpUasset(string contentRoot, string bpPath)
    {
        // /Game/Objects/ParkingSpace/Interaction_ParkingSpace_Large
        // ->  <contentRoot>/Objects/ParkingSpace/Interaction_ParkingSpace_Large.uasset
        if (!bpPath.StartsWith("/Game/")) return null;
        var rel = bpPath.Substring("/Game/".Length).Replace('/', Path.DirectorySeparatorChar);
        var full = Path.Combine(contentRoot, rel) + ".uasset";
        return File.Exists(full) ? full : null;
    }

    private static ArrayPropertyData BpCreatedComponents(UAsset asset, int[] exportNums)
    {
        EnsureName(asset, "BlueprintCreatedComponents");
        EnsureName(asset, "ObjectProperty");
        var arr = new ArrayPropertyData(FName.FromString(asset, "BlueprintCreatedComponents"))
        {
            ArrayType = FName.FromString(asset, "ObjectProperty"),
            Value = exportNums.Select(n => (PropertyData)new ObjectPropertyData
            {
                Name = FName.FromString(asset, "BlueprintCreatedComponents"),
                Value = new FPackageIndex(n),
            }).ToArray(),
        };
        return arr;
    }

    private static void EnsureName(UAsset asset, string name) => asset.AddNameReference(new FString(name));

    private static void RegisterStubSchema(UAsset asset, string className, string modulePath, string superType, params string[] objectProps)
    {
        if (asset.Mappings == null) return;
        if (asset.Mappings.Schemas == null) return;
        var props = new System.Collections.Concurrent.ConcurrentDictionary<int, UAssetAPI.Unversioned.UsmapProperty>();
        for (ushort i = 0; i < objectProps.Length; i++)
        {
            var pdata = new UAssetAPI.Unversioned.UsmapPropertyData(UAssetAPI.Unversioned.EPropertyType.ObjectProperty);
            props[i] = new UAssetAPI.Unversioned.UsmapProperty(objectProps[i], i, 0, 1, pdata);
        }
        var schema = new UAssetAPI.Unversioned.UsmapSchema(
            className, superType, (ushort)objectProps.Length, props, false, null, fromAsset: true);
        schema.ModulePath = modulePath;
        asset.Mappings.Schemas[className] = schema;
        asset.Mappings.Schemas[modulePath + "." + className] = schema;
    }

    private static int FindOrAddImport(UAsset asset, string objectName, int outerIndex,
                                       string classPackage, string className)
    {
        for (int i = 0; i < asset.Imports.Count; i++)
        {
            var imp = asset.Imports[i];
            if (imp.ObjectName.ToString() == objectName &&
                imp.OuterIndex.Index == outerIndex)
                return -(i + 1);
        }
        EnsureName(asset, objectName);
        EnsureName(asset, classPackage);
        EnsureName(asset, className);
        var newImp = new Import(
            classPackage,
            className,
            new FPackageIndex(outerIndex),
            objectName,
            false, asset);
        asset.Imports.Add(newImp);
        return -asset.Imports.Count;
    }

    private static ObjectPropertyData ObjProp(UAsset asset, string name, int value)
    {
        EnsureName(asset, name);
        return new ObjectPropertyData(FName.FromString(asset, name)) { Value = new FPackageIndex(value) };
    }

    private static StructPropertyData VecProp(UAsset asset, string name, double x, double y, double z)
    {
        EnsureName(asset, name);
        return new StructPropertyData(FName.FromString(asset, name), FName.FromString(asset, "Vector"))
        {
            SerializeNone = true,
            Value = new List<PropertyData> { new VectorPropertyData(FName.FromString(asset, name)) {
                Value = new FVector(x, y, z) } },
        };
    }

    private static StructPropertyData RotProp(UAsset asset, string name, double p, double y, double r)
    {
        EnsureName(asset, name);
        return new StructPropertyData(FName.FromString(asset, name), FName.FromString(asset, "Rotator"))
        {
            SerializeNone = true,
            Value = new List<PropertyData> { new RotatorPropertyData(FName.FromString(asset, name)) {
                Value = new FRotator(p, y, r) } },
        };
    }

    private static byte[] MakeActorExtras(string label)
    {
        var lb = System.Text.Encoding.UTF8.GetBytes(label);
        var withNull = new byte[lb.Length + 1];
        Array.Copy(lb, withNull, lb.Length);
        using var ms = new MemoryStream();
        using var bw = new BinaryWriter(ms);
        bw.Write((uint)1);                  // count
        bw.Write((uint)withNull.Length);    // strlen
        bw.Write(withNull);                 // label
        bw.Write(Guid.NewGuid().ToByteArray()); // GUID 16 bytes
        bw.Write(new byte[16]);             // padding
        return ms.ToArray();
    }

    private static byte[] MakeComponentExtras()
    {
        // Real root-style components (Root/Scene) use 4 zero bytes.
        return new byte[4];
    }

    private static byte[] MakeScsComponentExtras()
    {
        // Real SCS-created components have 16 bytes: 8 zeros, count=1, 4 zeros.
        return new byte[] { 0,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0 };
    }

    // Real SCS components carry these 5 props (order matches what we observed on
    // live exports like InteractionCube / PassengerSpawnBoxComponent).
    private static List<PropertyData> MakeScsComponentProps(UAsset asset, int rootNum, bool isPrimitive)
    {
        EnsureName(asset, "BodyInstance");
        EnsureName(asset, "AttachParent");
        EnsureName(asset, "UCSSerializationIndex");
        EnsureName(asset, "bNetAddressable");
        EnsureName(asset, "CreationMethod");
        EnsureName(asset, "EComponentCreationMethod");

        var list = new List<PropertyData>();
        if (isPrimitive)
        {
            list.Add(new UAssetAPI.PropertyTypes.Structs.StructPropertyData(FName.FromString(asset, "BodyInstance"))
            {
                StructType = FName.FromString(asset, "BodyInstance"),
                Value = new List<PropertyData>(),
            });
        }
        list.Add(ObjProp(asset, "AttachParent", rootNum));
        list.Add(new UAssetAPI.PropertyTypes.Objects.IntPropertyData(FName.FromString(asset, "UCSSerializationIndex")) { Value = 0 });
        list.Add(new UAssetAPI.PropertyTypes.Objects.BoolPropertyData(FName.FromString(asset, "bNetAddressable")) { Value = false });
        // Unversioned schema encodes CreationMethod as ByteProperty. SCS = 1.
        list.Add(new UAssetAPI.PropertyTypes.Objects.BytePropertyData(FName.FromString(asset, "CreationMethod"))
        {
            ByteType = UAssetAPI.PropertyTypes.Objects.BytePropertyType.Byte,
            EnumType = FName.FromString(asset, "EComponentCreationMethod"),
            Value    = 1,
        });
        return list;
    }

    // Find the WP cell whose actor-position bounding box contains (or is nearest to)
    // the target coords. Scans each cell's .uexp for triples of doubles that look
    // like actor world positions, builds a bbox, picks the best cell.
    private static string? FindCellForCoords(string genDir, double tx, double ty)
    {
        const double MAP_MIN = -2_000_000, MAP_MAX = 2_000_000;   // sanity bounds
        const double Z_MIN   = -200_000,   Z_MAX   = 200_000;     // plausible Z
        string? containingBest = null;
        double containingArea = double.MaxValue;
        string? nearestBest = null;
        double nearestDist = double.MaxValue;

        foreach (var path in Directory.EnumerateFiles(genDir, "*.uexp"))
        {
            byte[] data;
            try { data = File.ReadAllBytes(path); } catch { continue; }

            double minX = double.PositiveInfinity, maxX = double.NegativeInfinity;
            double minY = double.PositiveInfinity, maxY = double.NegativeInfinity;
            int count = 0;

            // Step by 4 to catch misaligned positions. Each hit = 3 plausible doubles (x,y,z).
            for (int o = 0; o + 24 <= data.Length; o += 4)
            {
                double dx = BitConverter.ToDouble(data, o);
                double dy = BitConverter.ToDouble(data, o + 8);
                double dz = BitConverter.ToDouble(data, o + 16);
                if (!(dx >= MAP_MIN && dx <= MAP_MAX)) continue;
                if (!(dy >= MAP_MIN && dy <= MAP_MAX)) continue;
                if (!(dz >= Z_MIN   && dz <= Z_MAX  )) continue;
                // Cell grid is ~12800, so large clustering expected
                if (Math.Abs(dx) < 1e-6 && Math.Abs(dy) < 1e-6) continue; // skip origin noise
                if (dx < minX) minX = dx;
                if (dx > maxX) maxX = dx;
                if (dy < minY) minY = dy;
                if (dy > maxY) maxY = dy;
                count++;
            }

            if (count < 3) continue;

            // Cell bounds are ~12800 wide; reject wildly wide bboxes (likely spurious)
            if (maxX - minX > 100_000 || maxY - minY > 100_000) continue;

            string name = Path.GetFileNameWithoutExtension(path);

            // Containing box: pick smallest one that contains target
            if (tx >= minX && tx <= maxX && ty >= minY && ty <= maxY)
            {
                double area = (maxX - minX) * (maxY - minY);
                if (area < containingArea)
                {
                    containingArea = area;
                    containingBest = name;
                    Console.WriteLine($"    [candidate] {name} bbox=[{minX:F0},{minY:F0}..{maxX:F0},{maxY:F0}] area={area:F0} count={count}");
                }
            }

            // Nearest box (fallback): distance from target to box center
            double cx = (minX + maxX) * 0.5, cy = (minY + maxY) * 0.5;
            double d = (cx - tx) * (cx - tx) + (cy - ty) * (cy - ty);
            if (d < nearestDist)
            {
                nearestDist = d;
                nearestBest = name;
                Console.WriteLine($"    [nearest-so-far] {name} center=({cx:F0},{cy:F0}) dist={Math.Sqrt(d):F0} count={count}");
            }
        }

        return containingBest ?? nearestBest;
    }
}
