"""Checks for the editor marker naming convention."""
from import_meshes import marker_role as R, bus_stop_label as L

def p(n): return f"/Game/DC/Meshes/{n}.{n}"           # shard-shaped asset path

# the object name is after the last DOT, not the last slash
assert R(p("BusStop_Old_Harbour"))  == ("busstop", "Old Harbour", None)
assert R(p("Home_Fisher_Row"))      == ("home",    "Fisher Row",  None)
assert R(p("Work_Sawmill"))         == ("work",    "Sawmill",     None)

# a zone corner carries its winding order, and the number is not part of the key
assert R(p("Zone_Arini_01"))        == ("zone",    "Arini", 1)
assert R(p("Zone_Arini_12"))        == ("zone",    "Arini", 12)
assert R(p("Zone_North_Bay_03"))    == ("zone",    "North Bay", 3)
# no trailing number is still a corner, just unordered
assert R(p("Zone_Arini"))           == ("zone",    "Arini", None)

# ordinary meshes are left alone
assert R(p("SM_SM_Concrete_Base_XXL1")) is None
assert R(p("BusStopSign")) is None          # the prefix needs its underscore
assert R(p("Home_")) is None                # nothing left to name it

# bus_stop_label still answers only for stops
assert L(p("BusStop_Old_Harbour")) == "Old Harbour"
assert L(p("Home_Fisher_Row")) is None
print("marker naming OK")
