from pymmcore_plus import DeviceType


class MyCam:
    device_name: str = "MyCam"  # optional... will default to class name
    device_type: DeviceType = DeviceType.Camera
    device_description: str = "Demo camera"

    def __init__(self) -> None:
        # don't communicate with hardware here
        ...

    def initialize(self) -> None:
        # communicate with hardware here
        # - establishes the connection with the hardware
        # - makes device ready to accept commands
        # - once called, repeated calls should have no effect
        pass

    def shutdown(self) -> None:
        # communicate and cleanup with hardware here
        # - should reverse the effects of initialize
        # - once called, repeated calls should have no effect
        # - after called, device should never attempt to communicate with
        #   the hardware, except after Initialize() is called again
        # - Calling Shutdown() without a previous Initialize() should have no effect.
        pass

    def __del__(self) -> None:
        # don't communicate with hardware here
        pass
