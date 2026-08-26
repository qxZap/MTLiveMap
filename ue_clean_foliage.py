r"""
UE-side foliage REPORT. Run from the Motor Town editor's Python console:

    exec(open(r'D:\MTLiveMap\ue_clean_foliage.py').read())

Counts the foliage instances that a given mesh filter + Z range would
remove, per mesh. It DELETES NOTHING, on purpose.

WHY THIS DOES NOT DELETE
------------------------
Two approaches were tried and both are unsafe:

1. comp.remove_instance() does not stick. A foliage component is only a
   render proxy; AInstancedFoliageActor keeps the real list in its private
   FoliageInfos map and rebuilds the component from it on reload. Deleted
   foliage reappears after undo or a restart.

2. The only scriptable foliage edits in UE 5.5 are AddInstances and
   RemoveAllInstances, with no remove-by-index. Reading the engine source:

     RemoveAllInstances -> for (TActorIterator<AInstancedFoliageActor> It(World))
                             IFA->RemoveFoliageType(...)
     AddInstances       -> AInstancedFoliageActor::Get(World, true,
                             World->PersistentLevel, Location)

   RemoveAllInstances strips the type from EVERY IFA in the world, and
   AddInstances puts survivors into the PERSISTENT level's IFA. On a World
   Partition map, where foliage lives in a per-cell IFA, that is data loss.
   It wiped the level once. Do not reintroduce it.

So: no scripted subset-delete of WP foliage exists in 5.5. Use either

  * the build-time cull (non-destructive, ships without them):
        .env MTMI_FOLIAGE_CULL_MESHES / _ZMAX / _FEATHER, then build.bat
  * or the Foliage editor's Select tool by hand, which goes through
    FFoliageInfo and therefore persists correctly.

This script exists to tell you how many instances are involved before you
choose.
"""
import random

import unreal

# --- what to delete --------------------------------------------------------

# Only meshes under this package folder are considered.
PATH_PREFIX = "/Game/DC/Meshes/NatureGreen"

# Case-insensitive substrings of the MESH name; a mesh matches if it contains
# any. Empty tuple = every mesh under PATH_PREFIX. Grass lives in the same
# folder, so a path-only rule would take the grass too.
NAME_INCLUDES = ("tree",)

# Sea level here is about -145. Instances at or below Z_MAX go.
Z_MAX = -145.0
Z_MIN = None          # or a float to stop deleting below a depth

# Fades the cut out over this many units ABOVE Z_MAX, so the treeline isn't
# a dead-straight line at the waterline. 0.0 = hard cut.
FEATHER = 150.0

SEED = 1337           # fixed, so a re-run doesn't eat more trees

# How many FoliageType_InstancedStaticMesh_<n> names to probe per IFA.
MAX_TYPE_PROBE = 256

# ---------------------------------------------------------------------------


def _matches(mesh_name):
    if not NAME_INCLUDES:
        return True
    low = mesh_name.lower()
    return any(s.lower() in low for s in NAME_INCLUDES)


def _doomed(z, rng):
    if Z_MIN is not None and z < Z_MIN:
        return False
    if z <= Z_MAX:
        return True
    if FEATHER <= 0.0:
        return False
    over = z - Z_MAX
    return over < FEATHER and rng.random() < (1.0 - over / FEATHER)


def _find_foliage_types(ifa):
    """UFoliageType subobjects of one IFA, found by probing auto-names."""
    found = []
    for i in range(MAX_TYPE_PROBE):
        name = "FoliageType_InstancedStaticMesh_{}".format(i)
        try:
            obj = unreal.find_object(ifa, name)
        except Exception:
            obj = None
        if obj:
            found.append(obj)
    return found


def clean_foliage():
    rng = random.Random(SEED)
    world = unreal.EditorLevelLibrary.get_editor_world()
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    ifas = [a for a in actors if isinstance(a, unreal.InstancedFoliageActor)]
    unreal.log("=" * 64)
    unreal.log("Foliage clean — {} InstancedFoliageActor(s) in loaded cells".format(len(ifas)))
    if not ifas:
        unreal.log("  none loaded. Load the region in the World Partition window first.")
        unreal.log("=" * 64)
        return 0

    jobs = []      # (foliage_type, mesh_name, keep[], kill_count)
    for ifa in ifas:
        for ft in _find_foliage_types(ifa):
            try:
                mesh = ft.get_editor_property("mesh")
            except Exception:
                mesh = None
            if not mesh:
                continue
            path_name = mesh.get_path_name()
            mesh_name = mesh.get_name()
            if not path_name.startswith(PATH_PREFIX) or not _matches(mesh_name):
                continue

            # Read the authoritative instance list for this type. The
            # component's copy can be stale; FFoliageInfo is the truth, and
            # this is the only reader script can reach.
            keep, kill = [], 0
            for comp in ifa.get_components_by_class(
                    unreal.HierarchicalInstancedStaticMeshComponent):
                try:
                    if comp.get_editor_property("static_mesh") != mesh:
                        continue
                except Exception:
                    continue
                for idx in range(comp.get_instance_count()):
                    try:
                        xf = comp.get_instance_transform(idx, True)
                    except TypeError:
                        try:
                            ok, xf = comp.get_instance_transform(idx, True)
                            if not ok:
                                continue
                        except Exception:
                            continue
                    except Exception:
                        continue
                    if _doomed(xf.translation.z, rng):
                        kill += 1
                    else:
                        keep.append(xf)
            if kill:
                jobs.append((ft, mesh_name, keep, kill))

    total_kill = sum(j[3] for j in jobs)
    total_keep = sum(len(j[2]) for j in jobs)
    unreal.log("  Z <= {}{}   feather {}   seed {}".format(
        Z_MAX, "" if Z_MIN is None else "  and Z >= {}".format(Z_MIN), FEATHER, SEED))
    for _ft, mesh_name, keep, kill in sorted(jobs, key=lambda j: j[1]):
        unreal.log("    {:<40s} remove {:>7}   keep {:>7}".format(mesh_name, kill, len(keep)))
    unreal.log("  TOTAL remove {}   keep {}".format(total_kill, total_keep))

    if not jobs:
        unreal.log("  nothing matched")
        unreal.log("=" * 64)
        return 0

    # DELIBERATELY NO DELETE PATH. See the header: the only scriptable
    # removal in UE 5.5 destroys foliage across the whole world and re-adds
    # into the persistent level. On a World Partition map that is data loss,
    # which is exactly what happened the one time this script tried it.
    unreal.log("")
    unreal.log("  REPORT ONLY — this script does not delete.")
    unreal.log("  To actually remove these, use the build-time cull, which is")
    unreal.log("  non-destructive and drops them from the shipped pak:")
    unreal.log("      .env  MTMI_FOLIAGE_CULL_MESHES=tree")
    unreal.log("            MTMI_FOLIAGE_CULL_ZMAX=-145")
    unreal.log("            MTMI_FOLIAGE_CULL_FEATHER=150")
    unreal.log("  Then run build.bat. Your level keeps the instances.")
    unreal.log("  To remove them from the LEVEL, use the Foliage editor's")
    unreal.log("  Select tool by hand -- that goes through FFoliageInfo safely.")
    unreal.log("=" * 64)
    return total_kill


clean_foliage()
