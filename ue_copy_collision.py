r"""
Copy collision between two mesh sets. Run in the Motor Town editor console:

    exec(open(r'D:\MTLiveMap\ue_copy_collision.py').read())

The winter trees in DC/Meshes/Nature are duplicates of the green ones in
DC/Meshes/NatureGreen with a different leaf material, but their collision
drifted, so vehicles behave differently against a winter tree than a green
one. This copies the collision geometry from the green (reference) set onto
the winter one, mesh by mesh, matching on name.

Copies BodySetup.AggGeom wholesale — spheres, boxes, capsules, convex
hulls, the lot — plus CollisionTraceFlag. Both are reflected UPROPERTYs, so
this is the same edit you'd make by hand in the Static Mesh editor, not a
back door.

Only meshes present in BOTH folders are touched. Anything with no
counterpart is reported and skipped.

DRY_RUN is True by default: it prints the before/after collision counts and
changes nothing. Read the report, then set DRY_RUN = False and re-run.

Afterwards: re-cook, then build.bat. Collision ships with the MESH, so the
pipeline picks it up with no config change.
"""
import unreal

# Reference set — collision is copied FROM here.
SRC_FOLDER = "/Game/DC/Meshes/NatureGreen"
# Target set — collision is copied TO here.
DST_FOLDER = "/Game/DC/Meshes/Nature"

# Only touch meshes whose name contains one of these (case-insensitive).
# Empty tuple = every mesh that exists in both folders.
NAME_INCLUDES = ()

DRY_RUN = False

# ---------------------------------------------------------------------------


def _counts(sub, mesh):
    try:
        return sub.get_simple_collision_count(mesh), sub.get_convex_collision_count(mesh)
    except Exception:
        return -1, -1


def _matches(name):
    if not NAME_INCLUDES:
        return True
    low = name.lower()
    return any(s.lower() in low for s in NAME_INCLUDES)


def copy_collision():
    eal = unreal.EditorAssetLibrary
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

    src_assets = eal.list_assets(SRC_FOLDER, recursive=False)
    by_name = {}
    for a in src_assets:
        short = a.split("/")[-1].split(".")[0]
        by_name[short] = a

    unreal.log("=" * 72)
    unreal.log("Copy collision  {}  ->  {}".format(SRC_FOLDER, DST_FOLDER))
    unreal.log("{:<44s} {:>10s}  {:>10s}".format("mesh", "green", "winter"))

    done = skipped = 0
    for short in sorted(by_name):
        if not _matches(short):
            continue
        dst_path = "{}/{}.{}".format(DST_FOLDER, short, short)
        if not eal.does_asset_exist(dst_path):
            unreal.log("  {:<42s} {:>10s}  {:>10s}  no counterpart".format(short, "-", "-"))
            skipped += 1
            continue

        src = eal.load_asset(by_name[short])
        dst = eal.load_asset(dst_path)
        if not src or not dst:
            unreal.log_warning("  {}: load failed".format(short))
            skipped += 1
            continue

        s_simple, s_convex = _counts(sub, src)
        d_simple, d_convex = _counts(sub, dst)
        same = (s_simple, s_convex) == (d_simple, d_convex)
        unreal.log("  {:<42s} {:>4}s/{:<4}c  {:>4}s/{:<4}c  {}".format(
            short, s_simple, s_convex, d_simple, d_convex,
            "already matches" if same else "WILL COPY"))
        if same or DRY_RUN:
            continue

        try:
            s_body = src.get_editor_property("body_setup")
            d_body = dst.get_editor_property("body_setup")
            if not s_body or not d_body:
                unreal.log_warning("  {}: missing BodySetup".format(short))
                skipped += 1
                continue
            # AggGeom is a USTRUCT — assigning copies it by value, so the two
            # meshes do NOT end up sharing collision data.
            d_body.set_editor_property("agg_geom", s_body.get_editor_property("agg_geom"))
            try:
                d_body.set_editor_property(
                    "collision_trace_flag",
                    s_body.get_editor_property("collision_trace_flag"))
            except Exception:
                pass
            dst.mark_package_dirty()
            eal.save_asset(dst_path)
            done += 1
        except Exception as e:
            unreal.log_error("  {}: FAILED {}".format(short, e))
            skipped += 1

    unreal.log("-" * 72)
    if DRY_RUN:
        unreal.log("  DRY_RUN — nothing changed. Set DRY_RUN = False and re-run to apply.")
    else:
        unreal.log("  copied collision onto {} mesh(es), {} skipped. Now RE-COOK, then build.bat."
                   .format(done, skipped))
    unreal.log("=" * 72)
    return done


copy_collision()
