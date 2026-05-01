"""
UE-side static-mesh + foliage exporter. Run from inside the Motor Town
editor's Python console — it walks every level actor and writes a JSON
the rest of the pipeline consumes.

The output path is read from the environment variable MTMI_REPO_ROOT,
which fulltest.bat exports before kicking off the editor task. If you
run this from the editor's Python console manually, set MTMI_REPO_ROOT
in your shell before launching the editor, OR edit the FALLBACK_OUTPUT
constant below and re-save.

Failures here halt the export with a clear message instead of silently
writing nowhere — fixing a misconfigured path is much faster than
debugging an empty pipeline downstream.
"""
import os
import sys
import unreal
import json


def _resolve_output_path():
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
            f"  The exporter cannot write static_meshes.json without a target."
        )
        sys.exit(1)
    return os.path.join(repo_dir, "static_meshes.json")


OUTPUT_PATH = _resolve_output_path()


def export_static_meshes_to_json(output_path):
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    data = {
        "static_meshes": {
            "actors": [],
            "foliage": []
        }
    }

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

            path_name = static_mesh.get_path_name()
            mesh_name = static_mesh.get_name()

            entry = {
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
                "ScaleZ": scale.z
            }
            data["static_meshes"]["actors"].append(entry)

    # --- Foliage Instances (from InstancedFoliageActor + HISM components) ---
    foliage_count = 0
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

                entry = {
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
                    "ScaleZ": scale.z
                }
                data["static_meshes"]["foliage"].append(entry)
                foliage_count += 1

    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)

    actor_count = len(data["static_meshes"]["actors"])
    foliage_count = len(data["static_meshes"]["foliage"])
    unreal.log(f"Exported {actor_count} static mesh actors + {foliage_count} foliage instances.")


export_static_meshes_to_json(OUTPUT_PATH)
