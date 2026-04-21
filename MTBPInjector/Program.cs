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
                "clone-actor"  => CloneActor(args.Skip(1).ToArray()),
                "clone-cross-cell" => CloneCrossCell(args.Skip(1).ToArray()),
                "inspect-cell" => InspectCell(args.Skip(1).ToArray()),
                "inspect-export" => InspectExport(args.Skip(1).ToArray()),
                "inspect-imports" => InspectImports(args.Skip(1).ToArray()),
                "inspect-by-class" => InspectByClass(args.Skip(1).ToArray()),
                "find-cell-wp" => FindCellWP(args.Skip(1).ToArray()),
                "dump-level-extras" => DumpLevelExtras(args.Skip(1).ToArray()),
                "dump-streaming-grids" => DumpStreamingGridsCmd(args.Skip(1).ToArray()),
                "decode-layer-keys" => DecodeLayerKeys(args.Skip(1).ToArray()),
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
                    for (int i = 0; i < Math.Min(ap.Value.Length, 3); i++)
                    {
                        Console.WriteLine($"{indent}  [{i}]:");
                        DumpField(ap.Value[i], indent + "    ", maxDepth - 1);
                    }
                    if (ap.Value.Length > 3) Console.WriteLine($"{indent}  ... {ap.Value.Length - 3} more");
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
    private static int FindCellWP(string[] args)
    {
        var f = ParseFlags(args);
        var asset = new UAsset(f["main"], EngineVer, LoadMappings(f["mappings"]));
        double tx = double.Parse(f["x"], System.Globalization.CultureInfo.InvariantCulture);
        double ty = double.Parse(f["y"], System.Globalization.CultureInfo.InvariantCulture);

        var results = new List<(int idx, string name, FVector pos, double extent, string grid, int level, string cellOwner)>();
        for (int i = 0; i < asset.Exports.Count; i++)
        {
            var e = asset.Exports[i];
            if (e is NormalExport ne)
            {
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
        }
        Console.WriteLine($"Total cell-data exports: {results.Count}");

        // Find cells whose bbox contains target (2D, XY)
        var containing = results.Where(r =>
            tx >= r.pos.X - r.extent && tx <= r.pos.X + r.extent &&
            ty >= r.pos.Y - r.extent && ty <= r.pos.Y + r.extent).ToList();
        Console.WriteLine($"Cells containing ({tx}, {ty}): {containing.Count}");
        foreach (var c in containing.OrderBy(c => c.level))
            Console.WriteLine($"  #{c.idx} {c.name} grid={c.grid} L{c.level} pos=({c.pos.X},{c.pos.Y}) ext={c.extent} owner={c.cellOwner}");

        // Also print cells whose center is closest (nearest fallback)
        var nearest = results.OrderBy(r => Math.Pow(r.pos.X - tx, 2) + Math.Pow(r.pos.Y - ty, 2)).Take(5).ToList();
        Console.WriteLine("\nNearest 5 cells by center distance:");
        foreach (var c in nearest)
            Console.WriteLine($"  #{c.idx} pos=({c.pos.X},{c.pos.Y}) ext={c.extent} L{c.level} grid={c.grid} name={c.name}");
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

        // Register in dst PersistentLevel's Actors (via raw-bytes patch preserving unparsed WP data)
        PatchLevelExportAsRaw(dst, dstCellPath, new List<int> { newActorNum });

        Console.WriteLine($"Writing {dstOutPath}");
        dst.Write(dstOutPath);
        Console.WriteLine($"Cloned actor #{newActorNum}, {srcChildren.Count} children at #{newActorNum + 1}..{newActorNum + srcChildren.Count}");
        return 0;
    }

    private static int InspectExport(string[] args)
    {
        var f = ParseFlags(args);
        var mappings = LoadMappings(f["mappings"]);
        var asset = new UAsset(f["cell"], EngineVer, mappings);
        var filter = f.TryGetValue("name", out var fn) ? fn : null;
        int limit = f.TryGetValue("limit", out var ls) ? int.Parse(ls) : 3;
        int idxFilter = f.TryGetValue("index", out var idxs) ? int.Parse(idxs) : -1;
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
                foreach (var p in ne.Data)
                {
                    string valStr = p switch
                    {
                        UAssetAPI.PropertyTypes.Structs.VectorPropertyData vp => $" = ({vp.Value.X},{vp.Value.Y},{vp.Value.Z})",
                        UAssetAPI.PropertyTypes.Structs.RotatorPropertyData rp => $" = (P{rp.Value.Pitch},Y{rp.Value.Yaw},R{rp.Value.Roll})",
                        UAssetAPI.PropertyTypes.Objects.ObjectPropertyData op => $" -> {op.Value?.Index}",
                        UAssetAPI.PropertyTypes.Structs.StructPropertyData sp => DumpStruct(sp),
                        UAssetAPI.PropertyTypes.Objects.FloatPropertyData fp => $" = {fp.Value}",
                        UAssetAPI.PropertyTypes.Objects.IntPropertyData ip => $" = {ip.Value}",
                        UAssetAPI.PropertyTypes.Objects.NamePropertyData np => $" = \"{np.Value}\"",
                        UAssetAPI.PropertyTypes.Objects.ArrayPropertyData ap => $" [Array {ap.ArrayType} count={ap.Value?.Length ?? 0}]",
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
                Console.WriteLine($"  last 5 actors: {string.Join(",", lvl.Actors.Skip(Math.Max(0, lvl.Actors.Count-5)).Select(a => a.Index))}");
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

        // Fast path: if typed LevelExport, just mutate the Actors list.
        // UAssetAPI's LevelExport.Write preserves unparsed trailing bytes via Extras.
        if (lvl is LevelExport typedLvl)
        {
            foreach (var n in newActorIndices)
            {
                typedLvl.Actors.Add(new FPackageIndex(n));
                typedLvl.CreateBeforeSerializationDependencies.Add(new FPackageIndex(n));
            }
            Console.WriteLine($"  Patched PersistentLevel (typed): +{newActorIndices.Count} actor(s), now {typedLvl.Actors.Count}");
            return;
        }

        // RawExport path: patch bytes directly.
        if (lvl is RawExport prev && prev.Data != null && prev.Data.Length > 0)
        {
            var patchedInPlace = PatchActorsInBytes(prev.Data, newActorIndices);
            if (patchedInPlace != null)
            {
                prev.Data = patchedInPlace;
                Console.WriteLine($"  Patched PersistentLevel (in-memory RawExport): +{newActorIndices.Count} actor(s)");
                return;
            }
        }

        // Read original body bytes from source .umap/.uexp combined stream.
        // SerialOffset is absolute in the combined file (.umap header + .uexp data).
        string uexpPath = Path.ChangeExtension(originalPath, ".uexp");
        byte[] umapBytes = File.ReadAllBytes(originalPath);
        byte[] uexpBytes = File.Exists(uexpPath) ? File.ReadAllBytes(uexpPath) : Array.Empty<byte>();
        // Combined length = umapBytes.Length + uexpBytes.Length (but there may be a split marker; simpler: read each half).
        long serialOffset = lvl.SerialOffset;
        long serialSize = lvl.SerialSize;
        if (serialSize <= 0) { Console.Error.WriteLine("  SerialSize unknown"); return; }

        byte[] body;
        if (serialOffset >= umapBytes.Length)
        {
            long uexpStart = serialOffset - umapBytes.Length;
            body = new byte[serialSize];
            Array.Copy(uexpBytes, uexpStart, body, 0, serialSize);
        }
        else
        {
            body = new byte[serialSize];
            Array.Copy(umapBytes, serialOffset, body, 0, serialSize);
        }

        // Locate URL marker (7 + "unreal\0" = int32(7) + "unreal\0")
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(body, marker);
        if (urlOff < 0) { Console.Error.WriteLine("  URL marker not found in LevelExport body"); return; }

        // Find count position: scan backward from urlOff, look for int32 C where urlOff == probe + 4 + C*4
        int countOff = -1;
        int oldCount = 0;
        for (int probe = urlOff - 4; probe >= 4; probe -= 4)
        {
            int c = BitConverter.ToInt32(body, probe);
            if (c > 0 && probe + 4 + c * 4 == urlOff)
            {
                countOff = probe;
                oldCount = c;
                break;
            }
        }
        if (countOff < 0) { Console.Error.WriteLine("  Actor count not located"); return; }

        int newCount = oldCount + newActorIndices.Count;
        int insertBytes = newActorIndices.Count * 4;
        byte[] patched = new byte[body.Length + insertBytes];
        // Copy up to and including countOff..+4 (the count field)
        Array.Copy(body, patched, countOff + 4);
        // Write new count in place
        BitConverter.GetBytes(newCount).CopyTo(patched, countOff);
        // Copy existing actor list
        Array.Copy(body, countOff + 4, patched, countOff + 4, urlOff - (countOff + 4));
        // Append new actor indices
        for (int i = 0; i < newActorIndices.Count; i++)
            BitConverter.GetBytes(newActorIndices[i]).CopyTo(patched, urlOff + i * 4);
        // Copy remainder (URL onwards)
        Array.Copy(body, urlOff, patched, urlOff + insertBytes, body.Length - urlOff);

        // Replace LevelExport with RawExport preserving all header fields.
        var raw = new RawExport { Data = patched, Asset = asset };
        CopyExportHeader(from: lvl, to: raw);
        raw.Extras = Array.Empty<byte>(); // body now contains everything incl. extras
        asset.Exports[lvlIdx] = raw;

        Console.WriteLine($"  Patched PersistentLevel: actor count {oldCount} -> {newCount} (as RawExport)");
    }

    // Patch Actors count + list in an opaque LevelExport body. Returns new bytes
    // or null if the layout couldn't be located.
    private static byte[] PatchActorsInBytes(byte[] body, List<int> newActorIndices)
    {
        byte[] marker = new byte[] { 7, 0, 0, 0, (byte)'u', (byte)'n', (byte)'r', (byte)'e', (byte)'a', (byte)'l', 0 };
        int urlOff = IndexOfSeq(body, marker);
        if (urlOff < 0) return null;
        int countOff = -1;
        int oldCount = 0;
        for (int probe = urlOff - 4; probe >= 4; probe -= 4)
        {
            int c = BitConverter.ToInt32(body, probe);
            if (c > 0 && probe + 4 + c * 4 == urlOff) { countOff = probe; oldCount = c; break; }
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
