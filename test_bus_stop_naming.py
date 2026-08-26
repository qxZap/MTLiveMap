"""One check for the BusStop_* mesh naming convention."""
from import_meshes import bus_stop_label as L

# the object name is after the last DOT, not the last slash
assert L("/Game/DC/Meshes/BusStop_My_Cool_Location.BusStop_My_Cool_Location") == "My Cool Location"
assert L("/Game/DC/BusStop_Harbour.BusStop_Harbour") == "Harbour"
# not a station
assert L("/Game/DC/SM_SM_Concrete_Base_XXL1.SM_SM_Concrete_Base_XXL1") is None
assert L("/Game/DC/BusStopSign.BusStopSign") is None      # prefix needs the underscore
assert L("/Game/DC/BusStop_.BusStop_") is None            # nothing left to name it
print("bus stop naming OK")
