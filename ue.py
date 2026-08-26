"""
UE-side static-mesh + foliage exporter. Run from inside the Motor Town
editor's Python console — it walks every level actor and writes the export
the rest of the pipeline consumes.

Output is written as JSONL SHARDS into a directory (static_meshes_parts/),
NOT one giant static_meshes.json. A full Jeju export is ~6M entries / ~2.7 GB;
emitting it as a single JSON document made the downstream `json.load` blow up
with MemoryError. Streaming into capped shard files keeps both the editor's
memory (entries are flushed as we go) and every downstream stage bounded.

The output directory is derived from MTMI_REPO_ROOT, which build.bat exports
before kicking off the editor task. If you run this from the editor's Python
console manually, set MTMI_REPO_ROOT in your shell before launching the
editor, OR edit the FALLBACK_OUTPUT_DIR constant below and re-save.

Failures here halt the export with a clear message instead of silently
writing nowhere — fixing a misconfigured path is much faster than
debugging an empty pipeline downstream.
"""
import os
import sys
import glob
import json
import unreal


# Entries per shard file (kept in sync with mesh_shards.SHARD_SIZE). ~200k
# flat entries is ~90 MB of JSONL.
SHARD_SIZE = 200_000


class _ShardWriter:
    """Inlined streaming JSONL shard writer (ue.py can't import repo modules
    reliably inside the editor runtime). Format matches mesh_shards.py:
    <dir>/<prefix>_00000.jsonl, one json object per line."""

    def __init__(self, out_dir, prefix="sm", shard_size=SHARD_SIZE):
        self.dir = out_dir
        self.prefix = prefix
        self.shard_size = shard_size
        self.count = 0
        self._idx = 0
        self._f = None
        self._n = 0
        os.makedirs(out_dir, exist_ok=True)
        for p in glob.glob(os.path.join(out_dir, f"{prefix}_*.jsonl")):
            try:
                os.remove(p)
            except OSError:
                pass

    def _roll(self):
        if self._f is not None:
            self._f.close()
        path = os.path.join(self.dir, f"{self.prefix}_{self._idx:05d}.jsonl")
        self._f = open(path, "w", encoding="utf-8")
        self._idx += 1
        self._n = 0

    def write(self, entry):
        if self._f is None or self._n >= self.shard_size:
            self._roll()
        self._f.write(json.dumps(entry))
        self._f.write("\n")
        self._n += 1
        self.count += 1

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None


def _resolve_output_dir():
    repo_root = os.environ.get("MTMI_REPO_ROOT", "").strip().strip('"')
    if repo_root:
        repo_dir = repo_root
    else:
        # Fallback: hardcoded development path. Editor users without env
        # vars set should change this once and forget about it.
        FALLBACK_OUTPUT_DIR = "D:/MTLiveMap"
        repo_dir = FALLBACK_OUTPUT_DIR
        unreal.log_warning(
            f"MTMI_REPO_ROOT not set — falling back to '{repo_dir}'. "
            "Set the env var or edit ue.py FALLBACK_OUTPUT_DIR for your machine."
        )
    if not os.path.isdir(repo_dir):
        unreal.log_error(
            f"\n[ue.py] Output directory does not exist: '{repo_dir}'\n"
            f"  Either create it manually, set the env var MTMI_REPO_ROOT to\n"
            f"  the absolute path of your MTMapInjector repo checkout, or edit\n"
            f"  the FALLBACK_OUTPUT_DIR constant at the top of ue.py.\n"
            f"  The exporter cannot write the static-mesh shards without a target."
        )
        sys.exit(1)
    return os.path.join(repo_dir, "static_meshes_parts")


OUTPUT_DIR = _resolve_output_dir()


def _mesh_collision(static_mesh, mesh_name):
    """What the MESH itself says about collision.

    Read from BodySetup.DefaultInstance -- the collision preset you set in
    the Static Mesh editor -- NOT from counting AggGeom primitives. A mesh
    set to NoCollision can still carry a leftover primitive, and counting
    shapes called it solid: that is why the corn and wheat you cooked as
    no-collision still blocked the vehicle.

    Returns (profile, prims):
      profile None  -> mesh says nothing useful, fall back to the prim count
      profile str   -> honour it verbatim
    """
    out_profile, prims = None, -1
    try:
        body_setup = static_mesh.get_editor_property("body_setup")
        if not body_setup:
            return None, 0
        agg = body_setup.get_editor_property("agg_geom")
        prims = 0
        for field in ("convex_elems", "box_elems", "sphere_elems", "sphyl_elems"):
            try:
                prims += len(agg.get_editor_property(field))
            except Exception:
                pass
        inst = body_setup.get_editor_property("default_instance")
        enabled = str(inst.get_editor_property("collision_enabled"))
        profile = str(inst.get_editor_property("collision_profile_name"))
        # "NoCollision" / "QueryOnly" etc. come back as enum reprs; the mesh
        # having collision switched off beats any leftover geometry.
        if "NoCollision" in enabled or "NONE" in enabled.upper():
            out_profile = "NoCollision"
        elif profile and profile not in ("None", "Default", "Custom"):
            out_profile = profile
        elif prims == 0:
            out_profile = "NoCollision"
        else:
            out_profile = "BlockAll"
        unreal.log(f"  {mesh_name}: mesh collision enabled={enabled} "
                   f"profile={profile} prims={prims} -> {out_profile}")
    except Exception as e:
        unreal.log_warning(f"  {mesh_name}: cannot read mesh collision ({e})")
    return out_profile, prims


def _read_comp_settings(comp, static_mesh, mesh_name):
    """Settings the pipeline must reproduce on the cells it builds.

    Our cells are clones of a VANILLA foliage template, so anything not
    explicitly carried over silently takes that template's value instead of
    yours. Missing properties come back as None and the pipeline leaves them
    alone.

    Collision comes from the MESH (see _mesh_collision); cull
    distances come from the component, which is where they actually live.
    """
    out = {}
    profile, prims = _mesh_collision(static_mesh, mesh_name)
    out["mesh_collision_prims"] = prims
    out["collision_profile_name"] = profile
    try:
        body = comp.get_editor_property("body_instance")
        out["component_collision_profile"] = str(
            body.get_editor_property("collision_profile_name"))  # recorded, not used
    except Exception:
        out["component_collision_profile"] = None
    for prop in ("instance_start_cull_distance", "instance_end_cull_distance"):
        try:
            out[prop] = int(comp.get_editor_property(prop))
        except Exception:
            out[prop] = None
    try:
        out["cast_shadow"] = bool(comp.get_editor_property("cast_shadow"))
    except Exception:
        out["cast_shadow"] = None
    # Material overrides live on the COMPONENT, not the mesh. The season look
    # (winter leaves) is applied this way, so without carrying it the game
    # renders the mesh's own material and you get summer trees in a winter map.
    # None entries are kept: they mean "use the mesh's material" for that slot
    # and dropping them would shift every later slot.
    mats = []
    try:
        for m in (comp.get_editor_property("override_materials") or []):
            if m is None:
                mats.append({"path": None, "class": None})
            else:
                mats.append({"path": m.get_path_name(),
                             "class": m.get_class().get_name()})
    except Exception as e:
        unreal.log_warning(f"  {mesh_name}: cannot read override_materials ({e})")
    out["override_materials"] = mats
    return out


def export_static_meshes_to_shards(out_dir):
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    # Two shard sets so a build can drop foliage: placed StaticMeshActors go
    # to sm_*.jsonl, HISM foliage instances to fol_*.jsonl. import_meshes can
    # skip the fol_* set (MTMI_SKIP_FOLIAGE=1 / --skip-foliage).
    writer = _ShardWriter(out_dir, prefix="sm")
    foliage_writer = _ShardWriter(out_dir, prefix="fol")

    actor_count = 0
    foliage_count = 0
    # Per-mesh component settings, read off the LIVE components. The pipeline
    # builds its cells from a vanilla template cell, so without this every
    # generated component silently inherits that template's collision profile
    # and cull distances and whatever you set on your FoliageType never
    # reaches the game. Exporting them makes the editor the source of truth.
    fol_settings = {}
    fog_volumes = []

    try:
        # --- Static Mesh Actors ---
        for actor in actors:
            if isinstance(actor, unreal.StaticMeshActor):
                sm_component = actor.get_editor_property("static_mesh_component")
                if not sm_component:
                    continue
                static_mesh = sm_component.get_editor_property("static_mesh")
                if not static_mesh:
                    continue

                transform = actor.get_actor_transform()
                location = transform.translation
                rotation = transform.rotation.rotator()
                scale = transform.scale3d

                writer.write({
                    "asset_path": static_mesh.get_path_name(),
                    "asset_key": static_mesh.get_name(),
                    "X": location.x,
                    "Y": location.y,
                    "Z": location.z,
                    "Pitch": rotation.pitch,
                    "Roll": rotation.roll,
                    "Yaw": rotation.yaw,
                    "ScaleX": scale.x,
                    "ScaleY": scale.y,
                    "ScaleZ": scale.z,
                })
                actor_count += 1

        # --- Local Fog Volumes ---
        # UE 5.5 ships ALocalFogVolume and MT's build has the class (it is in
        # the .usmap), but the game itself places none. Authoring them here
        # and rebuilding them at inject time means the editor stays the
        # source of truth: place as many as you like, each with its own
        # density, and the radius comes from the actor's scale.
        for actor in actors:
            if actor.get_class().get_name() != "LocalFogVolume":
                continue
            comp = None
            try:
                comps = actor.get_components_by_class(unreal.LocalFogVolumeComponent)
                comp = comps[0] if comps else None
            except Exception as e:
                unreal.log_warning(f"Skip fog {actor.get_name()}: {e}")
            if not comp:
                continue
            t = actor.get_actor_transform()
            loc, rot, scl = t.translation, t.rotation.rotator(), t.scale3d

            def _f(prop, default):
                try:
                    return float(comp.get_editor_property(prop))
                except Exception:
                    return default

            def _col(prop):
                try:
                    c = comp.get_editor_property(prop)
                    return [float(c.r), float(c.g), float(c.b), float(c.a)]
                except Exception:
                    return None

            fog_volumes.append({
                "name": actor.get_actor_label(),
                "X": loc.x, "Y": loc.y, "Z": loc.z,
                "Pitch": rot.pitch, "Roll": rot.roll, "Yaw": rot.yaw,
                "ScaleX": scl.x, "ScaleY": scl.y, "ScaleZ": scl.z,
                "RadialFogExtinction": _f("radial_fog_extinction", 1.0),
                "HeightFogExtinction": _f("height_fog_extinction", 1.0),
                "HeightFogFalloff":    _f("height_fog_falloff", 1.0),
                "HeightFogOffset":     _f("height_fog_offset", 0.0),
                "FogPhaseG":           _f("fog_phase_g", 0.0),
                "FogSortPriority":     int(_f("fog_sort_priority", 0)),
                "FogAlbedo":           _col("fog_albedo"),
                "FogEmissive":         _col("fog_emissive"),
            })

        # --- Foliage Instances (from InstancedFoliageActor + HISM components) ---
        for actor in actors:
            actor_class = actor.get_class().get_name()

            # Check all actors for HISM components (foliage, PCG, etc.)
            try:
                components = actor.get_components_by_class(
                    unreal.HierarchicalInstancedStaticMeshComponent
                )
            except Exception as e:
                unreal.log_warning(f"Skip {actor.get_name()}: {e}")
                continue

            if not components:
                continue

            unreal.log(f"Found {len(components)} HISM in {actor.get_name()} ({actor_class})")

            for comp in components:
                try:
                    static_mesh = comp.get_editor_property("static_mesh")
                except Exception:
                    static_mesh = None
                if not static_mesh:
                    continue

                path_name = static_mesh.get_path_name()
                mesh_name = static_mesh.get_name()
                # Key by PATH, not short name: DC/Meshes/Nature and
                # DC/Meshes/NatureGreen hold identically-named meshes, and
                # keying by name collapses the winter set onto the green one.
                if path_name not in fol_settings:
                    fol_settings[path_name] = _read_comp_settings(comp, static_mesh, mesh_name)
                instance_count = comp.get_instance_count()
                unreal.log(f"  {mesh_name}: {instance_count} instances")

                for idx in range(instance_count):
                    try:
                        transform = comp.get_instance_transform(idx, True)
                    except TypeError:
                        # Some UE versions return (bool, transform), others just transform
                        try:
                            success, transform = comp.get_instance_transform(idx, True)
                            if not success:
                                continue
                        except Exception:
                            continue
                    except Exception:
                        continue

                    location = transform.translation
                    rotation = transform.rotation.rotator()
                    scale = transform.scale3d

                    foliage_writer.write({
                        "asset_path": path_name,
                        "asset_key": mesh_name,
                        "X": location.x,
                        "Y": location.y,
                        "Z": location.z,
                        "Pitch": rotation.pitch,
                        "Roll": rotation.roll,
                        "Yaw": rotation.yaw,
                        "ScaleX": scale.x,
                        "ScaleY": scale.y,
                        "ScaleZ": scale.z,
                    })
                    foliage_count += 1
    finally:
        writer.close()
        foliage_writer.close()
        settings_path = os.path.join(out_dir, "foliage_settings.json")
        try:
            with open(settings_path, "w", encoding="utf-8") as fh:
                json.dump(fol_settings, fh, indent=2, sort_keys=True)
            unreal.log(f"Wrote component settings for {len(fol_settings)} mesh(es) "
                       f"-> {settings_path}")
        except Exception as e:
            unreal.log_warning(f"Could not write {settings_path}: {e}")
        # Fog volumes are their own sidecar rather than a shard: there are a
        # handful of them, each with its own settings, and the injector wants
        # them as one list.
        fog_path = os.path.join(out_dir, "fog_volumes.json")
        try:
            with open(fog_path, "w", encoding="utf-8") as fh:
                json.dump(fog_volumes, fh, indent=2)
            unreal.log(f"Wrote {len(fog_volumes)} local fog volume(s) -> {fog_path}")
        except Exception as e:
            unreal.log_warning(f"Could not write {fog_path}: {e}")

    unreal.log(
        f"Exported {actor_count} static mesh actors (sm_*) + {foliage_count} foliage "
        f"instances (fol_*) -> {writer.count + foliage_writer.count} entries in {out_dir}"
    )


def export_height_fog(out_dir):
    """Copy the ExponentialHeightFog you tuned in the viewport out to
    height_fog.json, so the build can write the same numbers onto Jeju's fog.

    This is how fog reaches the game. It is NOT placed as an actor: a scene has
    exactly one height fog, the renderer only ever reads ExponentialFogs[0],
    and Jeju already ships one. So injecting a second would be ignored at best.
    Instead the build treats your fog actor as a set of VALUES and stamps them
    onto the game's own fog, which is the only fog here known to render --
    three separate mesh-based approaches were invisible in game (see
    fog_placements.json).

    Consequence worth knowing: that fog is global, so what you set here is
    Jeju's weather too, not just the island's.
    """
    fogs = [a for a in unreal.EditorLevelLibrary.get_all_level_actors()
            if isinstance(a, unreal.ExponentialHeightFog)]
    if not fogs:
        unreal.log("No ExponentialHeightFog in the level — height_fog.json not written, "
                   "the build keeps whatever MTMI_FOG_PROPS says")
        return
    if len(fogs) > 1:
        unreal.log_warning(f"{len(fogs)} ExponentialHeightFogs in the level; only the "
                           f"first ('{fogs[0].get_name()}') is exported, because the "
                           f"renderer only reads one")
    comp = fogs[0].get_editor_property("component")
    # Floats only. The build's setter is typed, and these are the knobs that
    # decide whether fog is visible at the island's altitude at all --
    # fog_height_falloff above all, since vanilla's 0.75 keeps fog in the
    # valleys and the island sits ~200 m up.
    names = [
        "fog_density", "fog_height_falloff", "fog_max_opacity", "start_distance",
        "fog_cutoff_distance", "volumetric_fog_scattering_distribution",
        "volumetric_fog_extinction_scale", "volumetric_fog_distance",
        "volumetric_fog_static_lighting_scattering_intensity",
    ]
    out = {}
    for n in names:
        try:
            v = comp.get_editor_property(n)
        except Exception:
            continue                      # property absent on this engine version
        if isinstance(v, (int, float)):
            # UE python uses snake_case; the asset stores PascalCase.
            out["".join(p.title() for p in n.split("_"))] = float(v)
    try:
        out["bEnableVolumetricFog"] = bool(comp.get_editor_property("volumetric_fog"))
    except Exception:
        pass
    path = os.path.join(out_dir, "height_fog.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, sort_keys=True)
    unreal.log(f"Exported height fog ({len(out)} values) -> {path}")


export_static_meshes_to_shards(OUTPUT_DIR)
export_height_fog(OUTPUT_DIR)
