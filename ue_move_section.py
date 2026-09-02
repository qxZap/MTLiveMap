"""
ue_move_section.py -- copy (or move) a whole section of the scene elsewhere.

    Run inside Unreal. Set TARGET_CENTER, run once to READ the plan, then set
    DRY_RUN = False and run again. MODE picks copy (default) or move.

WHY THIS IS NOT AN IMPORT
    The old harbour is already in the level. It sits at (90100, 11880) in
    OLD-scene coordinates, which is well east of the island -- the current
    ground runs X -1,295,566 .. -62,544 -- so it exports, ships, and lands in
    the game out in the void. Nothing has to be read back out of the 2.96 GB
    static_meshes.json: the actors exist, they are simply in the wrong place.

WHAT IT SELECTS
    Every StaticMeshActor whose location is within RADIUS of SOURCE_CENTER in
    XY. Radius rather than a name filter because a section is a PLACE, not an
    asset set -- the harbour is ships, drydock gates, quay slabs, fencing and
    cones, and no name pattern covers that without also catching every other
    cone on the island.

    Measured contents of the harbour at a few radii:
        15,000    5 meshes   the vessels alone
        25,000   99 meshes   vessels + drydock + quay + fencing   <- default
        35,000  173 meshes   the above, plus more of the old bridge
        60,000  227 meshes   drifts into the old bridge proper

DRY RUN FIRST
    Moving actors edits the level. DRY_RUN prints exactly what would move and
    changes nothing, so the radius can be tuned against a real list instead of
    against a guess. Nothing is saved either way -- save the level yourself if
    the result is right, which also means Ctrl+Z still undoes it.
"""
import math

import unreal

# The stranded harbour, in the coordinates it actually sits at today.
SOURCE_CENTER = (90100.0, 11880.0)
RADIUS = 25000.0

# Where it should end up: (X, Y, Z) in the same editor space you read off the
# transform panel.
#
# Z = None KEEPS THE CURRENT HEIGHT, and for the harbour that is what you
# want. Sea level here is -145 and the container ship sits at -385, so the
# section is already floating correctly -- it is only X and Y that are in
# old-scene space. Moving it to another stretch of coast means the same sea,
# so the height does not change.
#
# Do not anchor the move on the cluster's MEAN Z either: the quay pillars
# reach down to -25,100 while the decks sit near zero, so the mean sits far
# below anything you can see and matching it to a coastal Z would lift the
# whole harbour into the air.
# READ THIS BEFORE SETTING A TARGET.
#
# The harbour is NOT stranded. SM_BridgeStart sits at (117,927, 1,184), right
# beside it, and the bridge runs 12.78 km west from there to the island: 38
# bridge pieces lie within 300 m of the harbour centre. The harbour is the
# bridge's eastern TERMINUS, and the 1.66 km of open water between it and the
# nearest terrain (a CliffDirtA at -72,582, -23,530) is the point of the
# bridge, not a mistake.
#
# So moving the harbour DISCONNECTS it unless the bridge moves too -- and the
# bridge is 12.78 km of 257 pieces that reach the island at the far end, so it
# cannot follow.
#
# Targets if you want it closer anyway, measured from the selection's bbox
# centre (96,746, 35) with its own 145 m half-width accounted for:
#     200 m of clear water ->  (-45,056, -6,929)
#     400 m of clear water ->  (-25,247, -4,173)
# Either leaves the bridge ending in mid-air where the harbour used to be.
TARGET_CENTER = None

# "copy" leaves the original where it is and puts a duplicate at the target.
# "move" relocates the originals.
#
# Copy is the default: the stranded section is the only surviving record of
# how that harbour was laid out, and it costs nothing to leave it sitting out
# in the void as a reference. Move it only once you are happy with the copy.
MODE = "copy"

DRY_RUN = True


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


def selected():
    """(actor, location) for everything inside the radius, nearest first."""
    cx, cy = SOURCE_CENTER
    out = []
    for a in all_actors():
        if not isinstance(a, unreal.StaticMeshActor):
            continue
        loc = a.get_actor_location()
        d = math.hypot(loc.x - cx, loc.y - cy)
        if d <= RADIUS:
            out.append((d, a, loc))
    out.sort(key=lambda t: t[0])
    return out


def main():
    picked = selected()
    if not picked:
        unreal.log_error(
            f"[move] nothing within {RADIUS:,.0f} uu of {SOURCE_CENTER}. "
            f"Check the centre against the transform panel -- this is in "
            f"EDITOR coordinates, not world.")
        return

    zs = [loc.z for _d, _a, loc in picked]
    xs = [loc.x for _d, _a, loc in picked]
    ys = [loc.y for _d, _a, loc in picked]
    unreal.log(f"[move] {len(picked)} actor(s) within {RADIUS:,.0f} uu")
    unreal.log(f"[move]   X {min(xs):,.0f} .. {max(xs):,.0f}")
    unreal.log(f"[move]   Y {min(ys):,.0f} .. {max(ys):,.0f}")
    unreal.log(f"[move]   Z {min(zs):,.0f} .. {max(zs):,.0f}")

    counts = {}
    for _d, a, _loc in picked:
        comp = a.static_mesh_component
        mesh = comp.static_mesh if comp else None
        n = mesh.get_name() if mesh else "(no mesh)"
        counts[n] = counts.get(n, 0) + 1
    for n, c in sorted(counts.items(), key=lambda kv: -kv[1])[:15]:
        unreal.log(f"[move]     x{c:<3} {n}")

    if TARGET_CENTER is None:
        unreal.log_warning(
            "[move] TARGET_CENTER is not set, so there is nowhere to move to. "
            "Set it to (X, Y, Z) and run again. The list above is what will "
            "move.")
        return

    # The section keeps its own shape: every actor shifts by the SAME delta,
    # measured from the source centre. Anchoring on the centre rather than on
    # one landmark actor means the result does not depend on which mesh
    # happens to be first in the level.
    sx, sy = SOURCE_CENTER
    tx, ty = TARGET_CENTER[0], TARGET_CENTER[1]
    tz = TARGET_CENTER[2] if len(TARGET_CENTER) > 2 else None
    dx, dy = tx - sx, ty - sy
    # Z anchors on the MEDIAN, not the mean: the pillars running down to
    # -25,100 drag a mean far below the decks, and every actor would rise by
    # the difference.
    dz = 0.0 if tz is None else tz - sorted(zs)[len(zs) // 2]
    unreal.log(f"[move] delta ({dx:+,.0f}, {dy:+,.0f}, {dz:+,.0f})"
               + ("  (height held)" if tz is None else ""))

    if DRY_RUN:
        unreal.log_warning(
            f"[move] DRY_RUN is on -- nothing {'copied' if MODE == 'copy' else 'moved'}. "
            f"Set DRY_RUN = False and run again.")
        return

    if MODE not in ("copy", "move"):
        unreal.log_error(f"[move] MODE must be 'copy' or 'move', not {MODE!r}")
        return

    sub = actor_subsystem()
    delta = unreal.Vector(dx, dy, dz)
    done, failed = 0, 0
    for _d, a, loc in picked:
        target = unreal.Vector(loc.x + dx, loc.y + dy, loc.z + dz)
        if MODE == "move":
            a.set_actor_location(target, sweep=False, teleport=True)
            done += 1
            continue
        # Duplicate carries material overrides, mobility and collision with
        # it. Re-spawning a bare StaticMeshActor and assigning the mesh would
        # silently drop any per-instance override the section relies on.
        dup = None
        try:
            dup = sub.duplicate_actor(a, None, delta) if sub else None
        except Exception as e:
            unreal.log_warning(f"[move] duplicate_actor failed ({e}); spawning instead")
        if dup is None:
            try:
                dup = sub.spawn_actor_from_class(
                    unreal.StaticMeshActor, target, a.get_actor_rotation())
                comp = a.static_mesh_component
                if dup and comp and comp.static_mesh:
                    dup.static_mesh_component.set_static_mesh(comp.static_mesh)
                    dup.set_actor_scale3d(a.get_actor_scale3d())
            except Exception as e:
                unreal.log_warning(f"[move] could not copy {a.get_actor_label()}: {e}")
                dup = None
        if dup is None:
            failed += 1
            continue
        # duplicate_actor's offset is applied for us; a spawned fallback is
        # already at the target. Setting it again is harmless and keeps the
        # two paths landing in the same place.
        dup.set_actor_location(target, sweep=False, teleport=True)
        done += 1

    verb = "copied" if MODE == "copy" else "moved"
    unreal.log(f"[move] {verb} {done} actor(s)"
               + (f", {failed} failed" if failed else ""))
    unreal.log("[move] SAVE THE LEVEL to keep this, then re-run ue.py so the "
               "build sees it.")


main()
