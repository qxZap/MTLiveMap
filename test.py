all_el = []

start_x = -329000
delta = -1000

count = 40

el = {
                "path": "/Game/Road/Road_Bare_01.Road_Bare_01",
                "X": -340000.0,
                "Y": 1377000.0,
                "Z": -19169.0,
                "Pitch": 0.0,
                "Roll": 0.0,
                "Yaw": 0.0
            }

for i in range(count):
    new_el = el.copy()
    new_el["X"] = start_x + i * delta
    all_el.append(new_el)

print(all_el)