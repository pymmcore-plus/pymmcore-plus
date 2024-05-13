from pymmcore_plus import CMMCorePlus

core = CMMCorePlus()
core.loadSystemConfiguration()
core.loadDevice("Camer2", "DemoCamera", "DCam")
core.loadDevice("MC", "Utilities", "Multi Camera")
core.initializeDevice("MC")
core.initializeDevice("Camer2")
core.setProperty("Camer2", "BitDepth", "16")
core.setProperty("MC", "Physical Camera 1", "Camera")
core.setProperty("MC", "Physical Camera 2", "Camer2")
core.setCameraDevice("MC")
core.snapImage()
