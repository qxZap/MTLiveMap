import unreal
import json

def export_static_meshes_to_json(output_path):
    actors = unreal.EditorLevelLibrary.get_all_level_actors()

    data = {
        "static_meshes": {
            "container_ship": []
        }
    }

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

            path_name = static_mesh.get_path_name()
            mesh_name = static_mesh.get_name()
            if "."+mesh_name in path_name:
                path_name = path_name.replace("."+mesh_name,'')

            entry = {
                "asset_path": path_name,
                "asset_key": mesh_name,
                "X": location.x,
                "Y": location.y,
                "Z": location.z,
                "Pitch": rotation.pitch,
                "Roll": rotation.roll,
                "Yaw": rotation.yaw
            }

            data["static_meshes"]["container_ship"].append(entry)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)

    unreal.log(f"Exported {len(data['static_meshes']['container_ship'])} meshes.")


export_static_meshes_to_json("D:/MTLiveMap/static_meshes.json")