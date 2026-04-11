import json

data = {}

with open('map_work_changes.json', 'r') as f:
    data = json.load(f)

data["static_meshes"]["imported"] = []

with open('map_work_changes.json', 'w') as f:
    json.dump(data, f, indent=4)