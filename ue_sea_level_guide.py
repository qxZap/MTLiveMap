r"""
Sea-level guide plane. Run from the Motor Town editor's Python console:

    exec(open(r'D:\MTLiveMap\ue_sea_level_guide.py').read())

Spawns a big translucent plane at Z = SEA_LEVEL so you can SEE the
waterline while erasing foliage by hand with the Foliage tool. Run it
again to move/resize it; run it with REMOVE = True to delete it.

It is only a visual reference: no collision (so the foliage brush traces
straight through it to the terrain instead of painting on the plane), and
hidden in game. Delete it before shipping anyway — it's an actor in your
level, and ue.py would otherwise export it as a static mesh.

Why a guide instead of a script that deletes: there is NO scriptable
foliage deletion in UE 5.5. FoliageEdit (the editor module) exposes zero
UFUNCTIONs, and the two runtime calls that do exist
(AddInstances/RemoveAllInstances) destroy World Partition foliage — see
AGENTS.md. Erasing by hand with the Foliage tool is the only safe way, so
this makes that fast rather than replacing it.

Suggested workflow:
  1. Run this.
  2. Foliage mode (Shift+4), tick ONLY the tree types in the palette.
  3. Put the camera just under the plane looking along it — everything
     poking below is what you want gone.
  4. Shift+paint (erase) along the underside.
  5. Run with REMOVE = True, then save.
"""
import unreal

# Waterline. Instances below this are the ones you're erasing.
SEA_LEVEL = -145.0

# Centre + size, defaulted to the foliage bounds measured from your export
# (editor space): X -1,285,922..-75,072  Y -776,378..628,581.
CENTER_X = -680497.0
CENTER_Y = -73899.0
SCALE = 15500.0          # Plane mesh is 100uu, so this is ~1.55M uu across

ACTOR_LABEL = "SEA_LEVEL_GUIDE"

# True = delete the guide and spawn nothing.
REMOVE = True

# ---------------------------------------------------------------------------

PLANE_MESH = "/Engine/BasicShapes/Plane.Plane"
# Translucent — the material UE uses for editor brush volumes, so you can
# see through it to the terrain below.
GUIDE_MATERIAL = "/Engine/EngineMaterials/EditorBrushMaterial.EditorBrushMaterial"


def _existing():
    out = []
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        try:
            if a.get_actor_label() == ACTOR_LABEL:
                out.append(a)
        except Exception:
            pass
    return out


def sea_level_guide():
    old = _existing()
    for a in old:
        unreal.EditorLevelLibrary.destroy_actor(a)
    if old:
        unreal.log("Removed {} existing guide(s)".format(len(old)))
    if REMOVE:
        unreal.log("REMOVE=True — guide deleted, nothing spawned.")
        return None

    mesh = unreal.EditorAssetLibrary.load_asset(PLANE_MESH)
    if not mesh:
        unreal.log_error("Could not load {}".format(PLANE_MESH))
        return None

    loc = unreal.Vector(CENTER_X, CENTER_Y, SEA_LEVEL)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.StaticMeshActor, loc, unreal.Rotator(0, 0, 0))
    actor.set_actor_label(ACTOR_LABEL)
    actor.set_actor_scale3d(unreal.Vector(SCALE, SCALE, 1.0))

    smc = actor.static_mesh_component
    smc.set_static_mesh(mesh)

    mat = unreal.EditorAssetLibrary.load_asset(GUIDE_MATERIAL)
    if mat:
        smc.set_material(0, mat)
    else:
        unreal.log_warning("No translucent material; the plane will be opaque. "
                           "Press H to toggle it while working.")

    # No collision, or the foliage brush would trace against this plane
    # instead of the ground and paint/erase on it.
    smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    smc.set_editor_property("cast_shadow", False)
    actor.set_actor_hidden_in_game(True)

    unreal.log("=" * 60)
    unreal.log("{} spawned at Z = {}".format(ACTOR_LABEL, SEA_LEVEL))
    unreal.log("  centre ({:,.0f}, {:,.0f})  scale {:,.0f} (~{:,.0f} uu across)".format(
        CENTER_X, CENTER_Y, SCALE, SCALE * 100))
    unreal.log("  no collision, no shadow, hidden in game")
    unreal.log("  Foliage mode (Shift+4) -> tick tree types -> Shift+paint below it")
    unreal.log("  Delete it when done: set REMOVE = True and re-run, then save")
    unreal.log("=" * 60)
    return actor


sea_level_guide()
