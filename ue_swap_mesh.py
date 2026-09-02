"""
ue_swap_mesh.py -- bulk-swap the mesh on every actor under a content folder.

    Run inside Unreal. Edit the two paths below, then run.

        FROM_FOLDER = "/Game/DC/Actors/BusStops"
        TO_MESH     = "/Game/PolygonTown/Meshes/Vehicles/SM_Veh_Bus_01"

WHAT IT MATCHES
    Actors in the level whose MESH ASSET lives under FROM_FOLDER -- not actors
    whose own name or outliner folder is there. That is the useful reading: the
    markers are placed all over the island and what they have in common is the
    asset they point at.

NAMES ARE NOT TOUCHED
    A marker's NAME is its meaning -- BusStop_Old_Harbour is what makes it a
    stop and what the station is called. Swapping the mesh changes what you
    LOOK at and nothing else, so the build still produces the same stops in the
    same places with the same names.

STATIC vs SKELETAL
    A StaticMeshActor can only hold a StaticMesh. SK_ assets are usually
    skeletal, and this reports that clearly rather than failing per-actor: if
    the target will not load as a StaticMesh, nothing is changed and the log
    says what to use instead.
"""
import unreal

FROM_FOLDER = "/Game/Models/PolygonStreetRacer/Meshes/Props"
# ONE of these two. TO_FOLDER re-points each actor at the SAME-NAMED asset in
# another folder, which is what you want after copying meshes somewhere to give
# them a different material: the copies exist, carry the new material, and
# nothing references them until this runs.
TO_FOLDER = "/Game/DC/Meshes/Numbers"
TO_MESH = ""


def actor_subsystem():
    # EditorLevelLibrary is deprecated in this build; the subsystem is the
    # supported route and the old one only warns.
    try:
        return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    except Exception:
        return None


def all_actors():
    sub = actor_subsystem()
    if sub:
        return sub.get_all_level_actors()
    return unreal.EditorLevelLibrary.get_all_level_actors()


def resolve(name):
    """The replacement asset for a mesh called `name`, or None."""
    path = f"{TO_FOLDER.rstrip('/')}/{name}" if TO_FOLDER else TO_MESH
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        return None, f"no asset at {path}"
    if not isinstance(asset, unreal.StaticMesh):
        return None, f"{path} is a {type(asset).__name__}, not a StaticMesh"
    return asset, None


def main():
    if not TO_FOLDER and not TO_MESH:
        unreal.log_error("[swap] set TO_FOLDER or TO_MESH")
        return

    folder = FROM_FOLDER.rstrip("/") + "/"
    swapped, seen = 0, 0
    for a in all_actors():
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        comp = a.static_mesh_component
        if comp is None:
            continue
        mesh = comp.static_mesh
        if mesh is None:
            continue
        path = mesh.get_path_name()
        if not path.startswith(folder):
            continue
        seen += 1
        target, why = resolve(mesh.get_name())
        if target is None:
            unreal.log_warning(f"[swap] {mesh.get_name()}: {why}")
            continue
        if mesh == target:
            continue
        comp.set_static_mesh(target)
        swapped += 1

    unreal.log(f"[swap] {seen} actor(s) using meshes under {FROM_FOLDER}")
    unreal.log(f"[swap] {swapped} swapped to {TO_FOLDER or TO_MESH}")
    if seen == 0:
        unreal.log_warning(
            f"[swap] nothing matched. The filter is on the MESH's path, not the "
            f"actor's outliner folder -- check where the mesh asset lives.")
    else:
        unreal.log("[swap] names untouched, so the build still makes the same "
                   "stops in the same places. Save the level to keep this.")


main()
