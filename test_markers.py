"""Checks for the editor marker convention: prefixes, and Zones/<Key>/ folders."""
from import_meshes import marker_role as R, bus_stop_label as L, zone_folder as Z

def p(n): return f"/Game/DC/Meshes/{n}.{n}"           # shard-shaped asset path
def z(folder, n): return f"/Game/DC/Zones/{folder}/{n}.{n}"

# --- prefix form -----------------------------------------------------------
# the object name is after the last DOT, not the last slash
assert R(p("BusStop_Old_Harbour"))  == ("busstop", "Old Harbour", None)
assert R(p("Home_Fisher_Row"))      == ("home",    "Fisher Row",  None)
assert R(p("Work_Sawmill"))         == ("work",    "Sawmill",     None)
assert R(p("Zone_Arini_01"))        == ("zone",    "Arini", 1)
assert R(p("Zone_North_Bay_03"))    == ("zone",    "North Bay", 3)

# --- folder form: the folder under Zones/ IS the key -----------------------
assert Z(z("Arini", "Border_01")) == "Arini"
assert Z(p("Home_Fisher_Row")) is None
assert R(z("Arini", "Border_01"))  == ("zone", "Arini", 1)
assert R(z("Arini", "Border_12"))  == ("zone", "Arini", 12)
assert R(z("North_Bay", "Border_2")) == ("zone", "North Bay", 2)
# other markers keep their own role; the folder only says which zone
assert R(z("Arini", "Home_Fisher_Row")) == ("home", "Fisher Row", None)
assert R(z("Arini", "BusStop_Pier"))    == ("busstop", "Pier", None)

# a Border_ outside a zone folder names nothing, so it cannot silently
# invent a zone from whatever folder it happens to sit in
assert R(p("Border_01")) is None

# --- ordinary meshes are left alone ---------------------------------------
assert R(p("SM_SM_Concrete_Base_XXL1")) is None
assert R(p("BusStopSign")) is None          # the prefix needs its underscore
# A bare Home_/Work_ is valid: the label is only read for stops and zones.
assert R(p("Home_")) == ("home", "Home", None)
assert R(p("Work_")) == ("work", "Work", None)
# but a bus stop still needs a name, since it displays one
assert R(p("BusStop_")) is None

assert L(p("BusStop_Old_Harbour")) == "Old Harbour"
assert L(p("Home_Fisher_Row")) is None
print("marker naming OK")
