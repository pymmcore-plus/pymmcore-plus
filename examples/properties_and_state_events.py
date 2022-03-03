from pymmcore_plus import CMMCorePlus

core = CMMCorePlus.instance()
core.loadSystemConfiguration()


# Note that when state devices change either the state or the label
# TWO propertyChanged events will be emitted, one for prop 'State'
# and one for prop 'Label'.
# Probably, best to check the property name and only respond to one of them
@core.events.propertyChanged.connect
def _on_prop_changed(dev, prop, value):
    if dev == "Objective" and prop == "Label":
        print("new objective is", value)


core.setState("Objective", 3)
