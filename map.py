"""
map.py — top-down PNG of your level, run from inside the Motor Town editor.

    exec(open(r"D:\\MTLiveMap\\map.py").read())

That is the whole thing. No plugin, no external tool, nothing to install: it
uses an orthographic SceneCapture2D and a render target, both of which the
editor already has, driven through the Python console you already have open.

Deliberately SEPARATE from ue.py. That one exports the scene and takes minutes
on a full foliage pass; this one takes seconds and you will want to re-run it
far more often, after moving a road or adding a town. Bundling them meant
paying for the export every time you wanted a picture.

Writes two files next to the mesh shards:

    map.png          the image
    map_bounds.json  the world rectangle it covers, and the uu-per-pixel scale

The second one is what makes it a map rather than a picture. Without it no
coordinate can be placed on the image, so markers, an in-game map replacement
and anything else built on top would all be guesswork.

    px = (X - min_x) / uu_per_px
    py = (Y - min_y) / uu_per_px

The capture is oriented so screen-right is world +X and screen-down is world
+Y, so there is no axis to flip.

Knobs, edited right here — this file is meant to be read and changed:
"""
import json
import os
import sys

import unreal


# Resolution. MATCH_GAME_SCALE derives it so ONE captured pixel equals one
# pixel of the game's own world map, which is the minimum that keeps the island
# as sharp as the map it is composited into.
#
# MTMI_MAP_SCALE in .env multiplies that. 2 gives four times the pixels, so
# detail survives being scaled down again during compositing -- a 14 km frame
# at scale 1 is 3008 px, at scale 2 it is 6016. Nothing downstream is fixed to
# a size: cutout takes the image as it comes, and expand works from
# map_bounds.json, so raising it costs only capture time and memory.
#
# Set MATCH_GAME_SCALE = False to use SIZE verbatim instead -- for a standalone
# picture rather than one destined for the game's map.
MATCH_GAME_SCALE = True
UU_PER_MAP_PIXEL = 537.109375
SIZE = 4096          # used when MATCH_GAME_SCALE is False.
                     # Raise for a standalone image you want to zoom into:
                     # 8192 is four times the pixels, 12288 is nine. Cost is a
                     # bigger render target (12288^2 RGBA8 is ~600 MB of VRAM)
                     # and a PNG in the hundreds of MB. Keep 4096 for anything
                     # destined for the in-game map, which IS 4096.
PADDING = 0.12       # margin around the content, as a fraction of the span.
                     # Framing measures actor ORIGINS, and a large mesh whose
                     # pivot is inside the frame still extends outside it -- so
                     # the picture came out clipped at 2%. Widening the frame
                     # fixes that without touching the render setup, which is
                     # where every black-image regression came from.
ONLY_Z_ABOVE = None  # ignore actors below this Z when framing. None = all of them.
                     # Use it when one buried or far-flung prop zooms everything out.
CAMERA_CLEARANCE = 50000.0   # uu above the tallest actor. 500 m clears terrain
                             # and towers while staying UNDER the cloud layer.
# Chroma key. Measured against a real render: NOTHING in a top-down tone-mapped
# capture comes near pure green -- green never even dominates a pixel, and the
# greenest thing in the whole island is (142,194,121), a dull sage. So an unlit
# pure-green water material keys out perfectly and cannot eat terrain.
#
# It has to be UNLIT. A lit surface reflects the sky and smears across dozens of
# shades -- the water in the last capture ran from (0,39,74) to (0,49,87), which
# is why keying it failed. Unlit renders one exact value.
CHROMA = "00FF00"

# Actors kept OUT of the capture entirely, matched as a substring of the actor's
# name or label. This is the simpler answer to "how do I key the sea": do not
# render it. A hidden mesh leaves background behind it, and the background is
# already keyed automatically from the image corners -- so no material has to be
# authored, made Unlit, or colour-matched at all.
#
# Authoring a flat unlit material still works and is the better route if you
# want the water VISIBLE in the picture but keyable. This is for when you just
# want it gone.
CHROMA_RGB = (1.0, 0.0, 1.0) # What the water is painted for the capture, and
                             # then keyed on exactly. Magenta rather than the
                             # green first suggested for one reason: the island
                             # carries ~248k foliage actors, and a green key has
                             # to be told apart from every leaf in the picture.
                             # Nothing here is magenta. Set to None to skip.
CHROMA_MATCHING = ["SM_Env_Unreal_Water", "M_Water", "MI_Water",
                   "Mat_PolygonCity_Water"]
                             # Actors repainted with CHROMA_RGB for the capture
                             # and restored afterwards. MATERIAL names are in
                             # here as well as mesh names on purpose: which
                             # asset a water plane is built from varies, but it
                             # is always drawn with a water material, so this
                             # keeps matching when the mesh name does not.
HIDE_MATCHING = ["SM_SkySphere"]
# Editor MARKERS, hidden for the shot and restored afterwards: a cone marking a
# zone corner is a survey stake, not scenery, and Border_* never ships at all.
#
# These match on PREFIX, against the actor's label and object name ONLY -- not
# substring, and not against material names. HIDE_MATCHING is substring-and-
# materials because a water plane has to be caught however it is built, and
# that same looseness is wrong here: "Work_" as a substring is one unlucky
# material name away from hiding the sea, and a hidden sea is a grey frame
# instead of a magenta one.
HIDE_PREFIXES = ["BusStop_", "Home_", "Work_", "Border_", "Spawn_"]
                             # The sky dome, and NOT the water. Hiding the sea
                             # works -- 36% of the frame came back as clean
                             # background -- but it throws away the one thing
                             # worth knowing: with the sea merely absent, a gap
                             # in the terrain and the sea itself are both
                             # "background" and indistinguishable. Painted
                             # instead, the sea is magenta and a gap is still
                             # background, so the two separate by colour and
                             # neither needs a threshold or a flood fill.
                             # An actor in both lists would be hidden before
                             # its paint could draw, so they must stay disjoint.
                             # The sea plane. It was "SM_Env_Unreal_Water_DC"
                             # and matched NOTHING -- the _DC copy is something
                             # the pipeline makes downstream, while the editor
                             # scene this captures holds the plain name. Kept
                             # narrow on purpose: a bare "Water" would also take
                             # out SM_Water_Tower_01, SM_Bld_WaterTank_01 and
                             # the SM_Env_WaterEdge shoreline pieces, which
                             # belong in the picture.
HIDE = ["Cloud", "Atmosphere", "Fog", "LightShafts"]
                             # Show flags switched off for the capture. Clouds
                             # and atmosphere sit between an overhead camera and
                             # the ground; fog washes out the far edges of a
                             # 14 km frame. Everything else renders normally.


def _names_of(a):
    """Every name an actor answers to: label, object name, its meshes, and the
    materials those meshes draw with."""
    out = []
    for get in (a.get_actor_label, a.get_name):
        try:
            out.append(get())
        except Exception:
            pass
    try:
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            m = c.static_mesh
            if m:
                out.append(m.get_name())
            for mat in c.get_editor_property("override_materials") or []:
                if mat:
                    out.append(mat.get_name())
            try:
                for i in range(c.get_num_materials()):
                    mi = c.get_material(i)
                    if mi:
                        out.append(mi.get_name())
            except Exception:
                pass
    except Exception:
        pass
    return out


def _chroma_material(rgb):
    """A flat unlit material in CHROMA_RGB, created once and reused.

    Unlit is the whole point: a lit material takes its colour from the sky and
    lands on a different value in shadow than in sun, which is precisely the
    problem being solved. An unlit emissive constant renders the same value
    everywhere, so keying it is exact rather than a threshold.
    """
    path, name = "/Game/MTMapAddon_Capture", "M_MapChroma"
    full = f"{path}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(full):
        return unreal.EditorAssetLibrary.load_asset(full)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, path, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    # Opaque, stated rather than assumed. The plane must still HIDE what is
    # under it: the point is to change the sea's colour, not to remove the sea.
    # A stock water material is translucent, so this occludes the seabed harder
    # than what it replaces -- nothing below the waterline can appear that was
    # not already appearing.
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    node = unreal.MaterialEditingLibrary.create_material_expression(
        mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
    node.set_editor_property("constant",
                             unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    unreal.MaterialEditingLibrary.connect_material_property(
        node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    unreal.MaterialEditingLibrary.recompile_material(mat)
    unreal.EditorAssetLibrary.save_asset(full)
    unreal.log(f"[map] created {full}")
    return mat


def _cfg(name, default=""):
    """Read a setting, process env first, then the repo's .env.

    map.py runs inside the editor's Python, which does not inherit whatever
    shell the build scripts use, so .env is invisible to os.environ here. The
    rest of the pipeline reads it through mt_paths; importing that from the
    editor drags in the whole path-resolution stack for one string, so this
    parses the handful of lines it needs.
    """
    v = os.environ.get(name, "").strip().strip('"').strip("'")
    if v:
        return v
    root = os.environ.get("MTMI_REPO_ROOT", "").strip().strip('"') or "D:/MTLiveMap"
    try:
        with open(os.path.join(root, ".env"), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, val = line.partition("=")
                if k.strip() == name:
                    return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def _resolve_output_dir():
    """Same rule ue.py uses, so both write to the same place."""
    repo_root = os.environ.get("MTMI_REPO_ROOT", "").strip().strip('"')
    repo_dir = repo_root or "D:/MTLiveMap"
    if not repo_root:
        unreal.log_warning(
            f"[map] MTMI_REPO_ROOT not set — falling back to '{repo_dir}'. "
            "Set the env var or edit this line for your machine.")
    if not os.path.isdir(repo_dir):
        unreal.log_error(f"[map] output directory does not exist: {repo_dir}")
        return None
    out = os.path.join(repo_dir, "static_meshes_parts")
    os.makedirs(out, exist_ok=True)
    return out


def export_map_png(out_dir, size=SIZE, only_z_above=ONLY_Z_ABOVE):
    """Render the level from directly above; write map.png + map_bounds.json."""
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    xs, ys, zs = [], [], []
    for a in actors:
        try:
            if not isinstance(a, unreal.StaticMeshActor):
                continue
            loc = a.get_actor_location()
        except Exception:
            continue
        if only_z_above is not None and loc.z < only_z_above:
            continue
        xs.append(loc.x); ys.append(loc.y); zs.append(loc.z)
    if not xs:
        unreal.log_error("[map] no StaticMeshActors to frame — nothing to capture")
        return None

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    # Square the framing BEFORE capturing. A non-square world rectangle
    # stretched into a square image makes every coordinate derived from it
    # wrong, and wrong in a way that looks fine until you place a marker.
    span = max(max_x - min_x, max_y - min_y) * (1.0 + PADDING)
    cx, cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    min_x, max_x = cx - span / 2.0, cx + span / 2.0
    min_y, max_y = cy - span / 2.0, cy + span / 2.0
    # Camera height. This used to be max(zs) + span, which for a 14.7 km map
    # put the camera 14.7 km up -- above the volumetric cloud layer, so the
    # capture was a photograph of clouds. Orthographic projection does not care
    # how high the camera is (ortho_width sets the framing, not distance), so
    # it only has to clear the tallest thing in the level.
    top = max(zs) + CAMERA_CLEARANCE

    if MATCH_GAME_SCALE:
        # MTMI_MAP_SCALE multiplies the capture resolution. 1 gives one
        # captured pixel per game-map pixel, which is the minimum that keeps
        # the island as sharp as the map it is pasted into; 2 gives four times
        # the pixels, so detail survives being scaled down again during
        # compositing. Nothing downstream is hardcoded to a size -- cutout
        # reads whatever it is given, and expand scales from map_bounds.json --
        # so this is safe to raise, at the cost of capture time and memory.
        try:
            scale = float(_cfg("MTMI_MAP_SCALE", "1") or 1)
        except ValueError:
            scale = 1.0
        if scale <= 0:
            scale = 1.0
        size = max(256, int(round(span / UU_PER_MAP_PIXEL * scale)))
        if scale != 1.0:
            unreal.log(f"[map] MTMI_MAP_SCALE={scale:g} -> {size} px "
                       f"({span / size:.1f} uu per captured pixel)")
        unreal.log(f"[map] matching the game map scale: {span/100000:.1f} km / "
                   f"{UU_PER_MAP_PIXEL:g} uu-per-px = {size} px")

    unreal.log(f"[map] {len(xs)} actors, framing {span/100.0:.0f} m across, "
               f"centre ({cx:.0f}, {cy:.0f})")

    # Resolve the hide list. Done AFTER framing on purpose: hiding the water
    # should not change where the camera points or how wide it looks, only what
    # is drawn. Framing off a different actor set is what caused an earlier
    # black image.
    hidden, census, marked = [], [], []
    if HIDE_MATCHING or HIDE_PREFIXES:
        for a in actors:
            names = []
            for get in (a.get_actor_label, a.get_name):
                try:
                    names.append(get())
                except Exception:
                    pass
            # The mesh asset too, not just the label. Water that stayed in the
            # capture is what forced the cutout to guess the sea by colour, and
            # a shadowed slope takes its light from the same blue sky the sea
            # does -- the two come out the SAME RGB, so no threshold can ever
            # split them. Not drawing the water removes the guess entirely.
            try:
                for c in a.get_components_by_class(unreal.StaticMeshComponent):
                    m = c.static_mesh
                    if m:
                        names.append(m.get_name())
            except Exception:
                pass
            # Markers first, on the actor's own names only. Anything caught
            # here is ours and can never be the sea.
            own = [x for x in names[:2]]
            if any(x.startswith(pfx) for x in own for pfx in HIDE_PREFIXES):
                hidden.append(a)
                marked.append(own[0] if own else "?")
            elif any(m.lower() in n.lower() for n in names for m in HIDE_MATCHING):
                if CHROMA_RGB and any(m.lower() in n.lower()
                                      for n in names for m in CHROMA_MATCHING):
                    unreal.log_warning(
                        f"[map] {names[0]} matches BOTH lists - painting it, "
                        f"not hiding it; a hidden actor never draws its paint")
                else:
                    hidden.append(a)
            # Footprint, so the census below can be sorted by it. The sea is
            # the widest thing in any island scene by a long way, so the top of
            # that list identifies it whatever it happens to be called.
            try:
                _o, e = a.get_actor_bounds(only_colliding_components=False)
                census.append((4.0 * e.x * e.y / 1e10, _names_of(a)))
            except Exception:
                pass
        unreal.log(f"[map] hiding {len(hidden)} actor(s): "
                   f"{len(marked)} marker(s) + {len(hidden) - len(marked)} matched "
                   f"{HIDE_MATCHING}")
        if marked:
            unreal.log(f"[map] markers hidden: {', '.join(sorted(marked)[:12])}"
                       + (" ..." if len(marked) > 12 else ""))
        if not hidden:
            unreal.log_warning(
                "[map] HIDE_MATCHING matched NOTHING. The sea will be rendered, "
                "and `worldmap.py cutout --water` then has to guess it by "
                "colour -- which also eats shadowed slopes, because they are "
                "literally the same RGB. See map_actors.json for what IS here.")

    # Paint the water instead of hiding it. Hiding is one list the capture may
    # or may not consult; a material swap changes what the mesh IS, so it holds
    # however the mesh reaches the frame. The water also stays in the picture,
    # which matters -- the sea is 48% of the frame, and a hole there is a hole
    # in the island's coastline too.
    painted = []          # (component, index, original material) to put back
    if CHROMA_RGB and CHROMA_MATCHING:
        try:
            chroma = _chroma_material(CHROMA_RGB)
            for a in actors:
                names = _names_of(a)
                if not any(m.lower() in n.lower()
                           for n in names for m in CHROMA_MATCHING):
                    continue
                for c in a.get_components_by_class(unreal.StaticMeshComponent):
                    for i in range(c.get_num_materials()):
                        painted.append((c, i, c.get_material(i)))
                        c.set_material(i, chroma)
            unreal.log(f"[map] painted {len(painted)} material slot(s) "
                       f"{tuple(int(v*255) for v in CHROMA_RGB)} for the capture")
            if not painted:
                unreal.log_warning(
                    "[map] CHROMA_MATCHING matched nothing - see "
                    "map_actors.json for the widest actors in the scene and "
                    "add whatever the sea is called to the list")
        except Exception as _e:
            unreal.log_warning(f"[map] could not paint the water ({_e})")

    # A census of the widest actors, written every run. Guessing the sea's name
    # from the asset browser has now failed twice -- once on a suffix the
    # editor scene never had, once on a name that simply is not the one in use
    # -- and each guess costs a capture to disprove. The scene can just say.
    try:
        census.sort(key=lambda t: -t[0])
        seen, rows = set(), []
        for km2, names in census:
            k = names[-1] if names else "?"
            if k in seen:
                continue
            seen.add(k)
            rows.append({"names": names, "footprint_km2": round(km2, 2),
                         "hidden": any(m.lower() in n.lower()
                                       for n in names for m in HIDE_MATCHING),
                         "painted": any(m.lower() in n.lower()
                                        for n in names for m in CHROMA_MATCHING)})
            if len(rows) >= 30:
                break
        import json as _json
        cp = os.path.join(_resolve_output_dir(), "map_actors.json")
        with open(cp, "w", encoding="utf-8") as fh:
            _json.dump({"hide_matching": HIDE_MATCHING,
                        "hidden_count": len(hidden),
                        "widest_actors": rows}, fh, indent=2)
        unreal.log(f"[map] wrote {cp} - the widest actors in the scene, so the "
                   f"sea can be named instead of guessed")
    except Exception as _e:
        unreal.log_warning(f"[map] could not write the actor census ({_e})")

    world = unreal.EditorLevelLibrary.get_editor_world()
    # RGBA8, NOT the RTF_RGBA16f default. ExportRenderTarget picks its file
    # format from the render target, not from the filename you hand it: a float
    # target writes OpenEXR and cheerfully calls it map.png. An 8-bit target is
    # what makes it an actual PNG, and paired with SCS_FINAL_COLOR_LDR below
    # there is no HDR range to lose anyway.
    rt = unreal.RenderingLibrary.create_render_target2d(
        world, size, size, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    # Set the rotator FIELD BY FIELD. Python's unreal.Rotator constructor takes
    # (roll, pitch, yaw) -- NOT (pitch, yaw, roll) like C++'s FRotator. Passing
    # (-90, 0, 0) therefore sets ROLL, and the camera looks at the horizon lying
    # on its side instead of straight down. Naming each field cannot be got
    # wrong by anyone reading or editing this later.
    #
    # pitch -90 aims it at the ground. yaw -90 orients the frame so screen-right
    # is world +X and screen-down is world +Y, which is what the bounds maths
    # below assumes. A downward camera cannot have BOTH +X right and +Y up --
    # that basis is left-handed, i.e. a mirror image -- so one axis has to run
    # the other way, and +Y down is the convention images already use.
    rot = unreal.Rotator()
    rot.roll = 0.0
    rot.pitch = -90.0
    rot.yaw = -90.0
    cap = unreal.EditorLevelLibrary.spawn_actor_from_class(
        unreal.SceneCapture2D, unreal.Vector(cx, cy, top), rot)
    try:
        c = cap.capture_component2d
        c.set_editor_property("projection_type",
                              unreal.CameraProjectionMode.ORTHOGRAPHIC)
        c.set_editor_property("ortho_width", span)
        c.set_editor_property("texture_target", rt)
        # Final tone-mapped colour: what the viewport shows, ready to look at.
        c.set_editor_property("capture_source",
                              unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
        c.set_editor_property("capture_every_frame", False)
        c.set_editor_property("capture_on_movement", False)
        if hidden:
            try:
                c.set_editor_property("hidden_actors", hidden)
            except Exception as _e:
                unreal.log_warning(f"[map] could not hide actors ({_e}) - the "
                                   f"water will still be in the picture")
            # Belt and braces. HiddenActors is a list the capture consults for
            # primitives it owns the drawing of, and it silently does nothing
            # for anything reaching the frame by another route -- an HLOD proxy
            # or a Level Instance draws the mesh without the actor in that list
            # ever being asked. Hiding the actor outright is a different code
            # path and catches those. Restored in the finally below, so the
            # level is exactly as it was whether or not the capture succeeds.
            for a in hidden:
                try:
                    a.set_is_temporarily_hidden_in_editor(True)
                except Exception:
                    pass
        try:
            c.set_editor_property("auto_calculate_ortho_planes", True)
        except Exception:
            pass                      # not present on every engine build
        # Turn off what sits between the camera and the ground.
        try:
            c.set_editor_property("show_flag_settings", [
                unreal.EngineShowFlagsSetting(show_flag_name=n, enabled=False)
                for n in HIDE])
        except Exception as _e:
            unreal.log_warning(f"[map] could not set show flags ({_e}) - "
                               f"expect clouds or haze in the image")
        c.capture_scene()
        unreal.RenderingLibrary.export_render_target(world, rt, out_dir, "map.png")
        # Verify it really is a PNG. Silently getting an EXR under a .png
        # name is the kind of thing nobody notices until it will not open.
        PNG_MAGIC = bytes([137, 80, 78, 71, 13, 10, 26, 10])
        try:
            with open(os.path.join(out_dir, 'map.png'), 'rb') as _fh:
                if _fh.read(8) != PNG_MAGIC:
                    unreal.log_warning(
                        '[map] map.png is not PNG data - the render target '
                        'format did not take. Check RTF_RGBA8 above.')
        except Exception:
            pass
    finally:
        for c, i, mat in painted:
            try:
                c.set_material(i, mat)
            except Exception:
                pass
        for a in hidden:
            try:
                a.set_is_temporarily_hidden_in_editor(False)
            except Exception:
                pass
        # Always clean up, even if the capture threw: a stray SceneCapture2D
        # left in the level would be exported as scene content next run.
        unreal.EditorLevelLibrary.destroy_actor(cap)

    uu_per_px = span / float(size)
    bounds = {
        "image": "map.png",
        "size_px": size,
        "min_x": min_x, "max_x": max_x,
        "min_y": min_y, "max_y": max_y,
        "uu_per_px": uu_per_px,
        "meters_across": span / 100.0,
        "actors_framed": len(xs),
        # cutout reads this and keys it exactly, so the two stay in step
        # without the colour being typed in twice.
        "chroma_rgb": ([int(round(v * 255)) for v in CHROMA_RGB]
                       if CHROMA_RGB and painted else None),
        "_note": [
            "EDITOR coordinates, before the pipeline's import offset.",
            "world_to_pixel:  px = (X - min_x) / uu_per_px",
            "                 py = (Y - min_y) / uu_per_px",
            "pixel_to_world:  X = min_x + px * uu_per_px",
            "                 Y = min_y + py * uu_per_px",
            "No axis flip: the capture is oriented (yaw -90) so screen-right is",
            "world +X and screen-down is world +Y, matching image convention.",
        ],
    }
    path = os.path.join(out_dir, "map_bounds.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bounds, fh, indent=2)
    unreal.log(f"[map] wrote map.png ({size}x{size}, {uu_per_px:.1f} uu/px) "
               f"and map_bounds.json in {out_dir}")
    return bounds


_out = _resolve_output_dir()
if _out:
    export_map_png(_out)
