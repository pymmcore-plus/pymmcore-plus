REGISTRY_DEVICES = {} # global dictionary containing the class instances of the python devices


def device_registry(name, *args, **kwargs):
    """
    Decorator to register a python device in a UniMMCore instance
    """
    def decorator(func):
        device_instance = func(*args, **kwargs)
        REGISTRY_DEVICES[name] = device_instance
        return func
    return decorator

"""
This decorator is used to register a python device implemented for UniMMCore instance. In this way, we can
simulate the use of loadSystemConfiguration file using python devices.

Example:
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
<script.py>
core = UniMMCore() # core instance
microscope_sim = MicroscopeSim() # an example of a simulation ro reproduce using python devices
# Here you need to register the devices that you will use
@device_registry("Camera", core, microscope_sim)
def make_camera(my_core, my_sim):
    return SimCameraDevice(my_core, my_sim)


@device_registry("Shutter")
def make_shutter():
    return SimShutterDevice()


@device_registry("LED", "led", {0:"UV", 1:"BLUE", 2:"CYAN", 3:"GREEN", 4:"YELLOW", 5:"ORANGE", 6:"RED"}, microscope_sim)
def make_led(my_label, state_label, my_sim):
    return SimStateDevice(my_label, state_label, my_sim)

@device_registry("Filter Wheel", "Filter Wheel", {0:"Electra1(402/454)", 1:"SCFP2(434/474)", 2:"TagGFP2(483/506)", 3:"obeYFP(514/528)", 5:"mRFP1-Q667(549/570)", 6:"mScarlet3(569/582)", 7:"miRFP670(642/670)"}, microscope_sim)
def make_filter_wheel(my_label, state_label, my_sim):
    return SimStateDevice(my_label, state_label, my_sim)


@device_registry("XYStage", microscope_sim)
def make_xy_stage(my_sim):
    return SimStageDevice(my_sim)
+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++    
<local_python_config.cfg> -> To simulate the .cfg file that you would use on a real microscope
# Unload all devices
Property,Core,Initialize,0
# Load devices
Device,Camera,py,CameraDevice
Device,XYStage,py,XYStageDevice
Device,LED,py,StateDevice
Device,Filter Wheel,py,StateDevice
Device,Shutter,py,ShutterDevice
# Pre-initialization properties
# Hub references
Property,Core,Initialize,1
# Delays
# Stage focus directions
# Labels
Label,LED,0,UV
Label,LED,1,BLUE
Label,LED,2,CYAN
Label,LED,3,GREEN
Label,LED,4,YELLOW
Label,LED,5,ORANGE
Label,LED,6,RED
Label,Filter Wheel,0,Electra1(402/454)
Label,Filter Wheel,1,SCFP2(434/474)
Label,Filter Wheel,2,TagGFP2(483/506)
Label,Filter Wheel,3,obeYFP(514/528)
Label,Filter Wheel,4,mRFP1-Q667(549/570)
Label,Filter Wheel,5,mScarlet3(569/582)
Label,Filter Wheel,6,miRFP670(642/670)
# Group configurations
ConfigGroup,test,nucleus-channel,LED,Label,ORANGE
ConfigGroup,test,nucleus-channel,Filter Wheel,Label,mScarlet3(569/582)
ConfigGroup,test,membrane-channel,LED,Label,RED
ConfigGroup,test,membrane-channel,Filter Wheel,Label,miRFP670(642/670)
ConfigGroup,test,cell-channel,LED,Label,BLUE
ConfigGroup,test,cell-channel,Filter Wheel,Label,mScarlet3(569/582)
# Pixel Size configurations

# Roles
"""