"""Check marker_role reads the OUTLINER LABEL first, asset name second.

    python test_marker_role.py

Twenty-five buses dropped in as plain SM_Veh_Bus_01 named nothing, because a
rename in the outliner never reaches the mesh's asset path. Both conventions
have to work: the label when it names a role, the asset name when it does.
"""
from import_meshes import marker_role

BUS = "/Game/PolygonTown/Meshes/Vehicles/SM_Veh_Bus_01.SM_Veh_Bus_01"
NAMED = "/Game/DC/Actors/BusStops/BusStop_Old_Harbour.BusStop_Old_Harbour"

def main():
    # The label names the role; the mesh is an ordinary bus.
    assert marker_role(BUS, "BusStop_Old_Harbour") == ("busstop", "Old Harbour", None)
    # No label -> an ordinary bus stays ordinary.
    assert marker_role(BUS) is None
    assert marker_role(BUS, "") is None
    # A label that names nothing falls back to the asset name.
    assert marker_role(NAMED, "Bus_42") == ("busstop", "Old Harbour", None)
    assert marker_role(NAMED) == ("busstop", "Old Harbour", None)
    # camelCase still splits, via the label path too.
    assert marker_role(BUS, "BusStop_EarlyBridge") == ("busstop", "Early Bridge", None)
    # Other roles keep working off the label.
    assert marker_role(BUS, "Home_")[0] == "home"
    assert marker_role(BUS, "Work_Dock")[0] == "work"
    print("marker_role: label wins, asset name is the fallback -- OK")

if __name__ == "__main__":
    main()
