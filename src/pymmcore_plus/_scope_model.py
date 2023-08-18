from typing import ClassVar

from pymmcore import CMMCore

from pymmcore_plus import Device


class MicroscopeModel:
    DEVLIST_FILE_NAME: ClassVar[str] = "MMDeviceList.txt"
    PIXEL_SIZE_GROUP: ClassVar[str] = "PixelSizeGroup"

    def __init__(self) -> None:
        self.filename: str = ""
        self._devices: list[Device] = []

    # @staticmethod
    # def generateDeviceListFile(deviceListFileName: str, c: CMMCore) -> bool:
    #     pass

    # --------------------------- High priority ---------------------------

    # --------------------------- Low priority ---------------------------

    def isModified(self) -> bool:
        pass

    def setModified(self, mod: bool) -> None:
        pass

    def loadDeviceDataFromHardware(self, core: CMMCore) -> None:
        for device in self._devices:
            device.loadFromHardware(core)

    def loadStateLabelsFromHardware(self, core: CMMCore) -> None:
        pass

    def loadFocusDirectionsFromHardware(self, core: CMMCore) -> None:
        pass

    def loadAvailableDeviceList(self, core: CMMCore) -> None:
        pass

    def getAvailableDevicesCompact(self) -> List[Device]:
        pass

    def getAvailableHubs(self) -> List[Device]:
        pass

    def getAvailableSerialPorts(self) -> List[Device]:
        pass

    def getBadLibraries(self) -> List[str]:
        pass

    def isPortInUse(self, index: int) -> bool:
        pass

    def isPortInUse(self, device: Device) -> bool:
        pass

    def addSetupProperty(self, deviceName: str, prop: PropertyItem) -> None:
        pass

    def addSetupLabel(self, deviceName: str, lab: Label) -> None:
        pass

    def applySetupLabelsToHardware(self, core: CMMCore) -> None:
        pass

    def applySetupConfigsToHardware(self, core: CMMCore) -> None:
        pass

    def createSetupConfigsFromHardware(self, core: CMMCore) -> None:
        pass

    def updateLabelsInPreset(
        self, deviceName: str, oldLabel: str, newLabel: str
    ) -> None:
        pass

    def createResolutionsFromHardware(self, core: CMMCore) -> None:
        pass

    def applyDelaysToHardware(self, core: CMMCore) -> None:
        pass

    def addConfigGroup(self, name: str) -> bool:
        pass

    def loadFromFile(self, path: str) -> None:
        pass

    def getDeviceDescription(self, library: str, adapter: str) -> str:
        pass

    def saveToFile(self, path: str) -> None:
        pass

    def dumpSetupConf(self) -> None:
        pass

    def dumpDeviceProperties(self, device: str) -> None:
        pass

    def dumpComPortProperties(self, device: str) -> None:
        pass

    def dumpComPortsSetupProps(self) -> None:
        pass

    def reset(self) -> None:
        pass

    def getDevices(self) -> List[Device]:
        pass

    def getPeripheralDevices(self) -> List[Device]:
        pass

    def getChildDevices(self, hub: Device) -> List[Device]:
        pass

    def removePeripherals(self, hubName: str, core: CMMCore) -> None:
        pass

    def removeDevice(self, devName: str) -> None:
        pass

    def addSynchroDevice(self, name: str) -> None:
        pass

    def clearSynchroDevices(self) -> None:
        pass

    def addDevice(self, dev: Device) -> None:
        pass

    def changeDeviceName(self, oldName: str, newName: str) -> None:
        pass

    def getDeviceSetupProperty(self, devName: str, propName: str) -> str:
        pass

    def setDeviceSetupProperty(self, devName: str, propName: str, value: str) -> None:
        pass

    def removeGroup(self, name: str) -> None:
        pass

    def renameGroup(self, grp: ConfigGroup, name: str) -> None:
        pass

    def removeDuplicateComPorts(self) -> None:
        pass

    def removeInvalidConfigurations(self) -> None:
        pass

    def addSelectedPeripherals(self, c: CMMCore, pd: List[Device]) -> None:
        pass

    def loadModel(self, c: CMMCore) -> None:
        pass

    def initializeModel(self, core: CMMCore, amLoading: AtomicBoolean) -> None:
        pass
