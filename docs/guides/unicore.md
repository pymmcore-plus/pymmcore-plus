# UniMMCore

!!! tip "Experimental"

    This is an experimental feature, and the API may change in future releases.

## A Unified controller of C++ and Pure-Python Devices

The [`UniMMCore`][pymmcore_plus.experimental.unicore.UniMMCore] class is a
subclass of [`CMMCorePlus`][pymmcore_plus.CMMCorePlus] that can control both
"classic" C++ devices (via the CMMCore) as well pure-Python device adapters.
This simplifies the task of controlling new devices using pure-Python code,
without the need to write and compile a C++ device adapter.

## Overview

UniMMCore allows you to seamlessly mix traditional Micro-Manager C++ device
adapters with custom Python device implementations. When you call methods like
`core.setXYPosition()` or `core.snapImage()`, UniMMCore automatically routes the
call to the appropriate device implementation (C++ or Python) based on which
device is currently active.

### Benefits

- **Rapid Development**: Write device adapters entirely in Python, no C++
  compilation required.
- **Integration**: Python devices work alongside the more than 250 existing
  C++ device adapters.
- **Same API**: UniMMCore uses the same `CMMCorePlus` API and may be used as a
  drop-in replacement.
- **Full feature support**: Properties and sequences work with Python devices

## Getting Started

### Basic Usage

To use UniMMCore, replace `CMMCorePlus` with `UniMMCore`:

```python
from pymmcore_plus.experimental.unicore import UniMMCore

# Instead of: core = CMMCorePlus()
core = UniMMCore()

# Load traditional C++ devices defined in a config file (optional)
core.loadSystemConfiguration(...)

# Load Python devices (we'll discuss creating these below)
from my_custom_devices import MyCamera

core.loadPyDevice("MyCamera", MyCamera())
core.initializeDevice("MyCamera")

# Set as the current camera device
core.setCameraDevice("MyCamera")

# Use the same API, UniMMCore routes to Python device automatically
core.setExposure(100)
img = core.snapImage()
```

## Supported Device Types

UniMMCore currently supports the following device types for Python
implementation:

- **[Common Methods](#common-methods)**
- **[CameraDevice](#camera-devices-cameradevice)**
- **[XYStageDevice](#xy-stage-devices-xystagedevice)**
- **[StateDevice](#state-devices-statedevice)**
- **[ShutterDevice](#shutter-devices-shutterdevice)**
- **[SLMDevice](#slm-devices-slmdevice)**
- **[GenericDevice](#generic-devices-genericdevice)**

### Common Methods

All device base classes inherit from
[`Device`][pymmcore_plus.experimental.unicore.Device], and may re-implement any
of the following methods:

```python
from pymmcore_plus.experimental.unicore import Device

class MyDevice(Device):
    def initialize(self) -> None:
        """Initialize the device.
        
        Note: Communication with and initialization of the device should be
        done here, *not* in `__init__`.
        """
    
    def shutdown(self) -> None:
        """Called when device is unloaded."""
    
    def busy(self) -> bool:
        """Return `True` if the device is busy. (Returns False by default)."""

    @classmethod
    def name(cls) -> str:
        """Return the name of the device.
        
        By default, the class name is used.  (This is *not* the same as
        the user-defined label)
        """
    
    def description(self) -> str:
        """Return a description of the device.
        
        By default, the class docstring is used.
        """
```

### Camera Devices (`CameraDevice`)

For image acquisition devices. Implement the following abstract methods:

```python
from pymmcore_plus.experimental.unicore import CameraDevice
import numpy as np

class MyCamera(CameraDevice):
    def get_exposure(self) -> float:
        """Return current exposure time in milliseconds."""
        pass

    def set_exposure(self, exposure: float) -> None:
        """Set exposure time in milliseconds."""
        pass

    def shape(self) -> tuple[int, ...]:
        """Return (height, width, [channels]) of current image."""
        pass

    def dtype(self) -> np.dtype:
        """Return NumPy dtype of camera images."""
        pass

    def start_sequence(self, n: int | None, get_buffer: Callable) -> Iterator[dict]:
        """Start sequence acquisition yielding metadata dicts."""
        pass
```

!!! warning

    `SimpleCameraDevice` is **not** recommended for real hardware cameras: a per-frame `snap()` prevents SDK-level optimizations like ring buffers and DMA transfers. Use `CameraDevice` with `start_sequence()` instead.

For simple or simulated cameras, use `SimpleCameraDevice` instead — it only
requires `sensor_shape()` and `snap()`, and provides automatic software ROI:

```python
from pymmcore_plus.experimental.unicore import SimpleCameraDevice

class MySimpleCamera(SimpleCameraDevice):
    def get_exposure(self) -> float: ...
    def set_exposure(self, exposure: float) -> None: ...

    def sensor_shape(self) -> tuple[int, ...]:
        """Return (height, width) of the full sensor."""
        ...

    def dtype(self) -> np.dtype: ...

    def snap(self, buffer: np.ndarray) -> dict:
        """Fill the full-frame buffer with image data."""
        ...
```

### XY Stage Devices (`XYStageDevice`)

For controlling 2-axis positioning stages:

=== "Position Motors"

    ```python
    from pymmcore_plus.experimental.unicore import XYStageDevice

    class MyStage(XYStageDevice):
        def set_position_um(self, x: float, y: float) -> None:
            """Set stage position in micrometers."""
            pass
        
        def get_position_um(self) -> tuple[float, float]:
            """Get current stage position in micrometers."""
            pass
        
        def set_origin_x(self) -> None:
            """Set current X position as origin."""
            pass
        
        def set_origin_y(self) -> None:
            """Set current Y position as origin."""
            pass
        
        def stop(self) -> None:
            """Stop stage movement."""
            pass
        
        def home(self) -> None:
            """Move stage to home position."""
            pass
    ```

=== "Stepper Motor"

    For stepper motor stages with sequence support, use `XYStepperStageDevice`:

    ```python
    from pymmcore_plus.experimental.unicore import XYStepperStageDevice

    class MyStepperStage(XYStepperStageDevice):
        def get_position_steps(self) -> tuple[int, int]:
            """Get position in motor steps."""
            pass
        
        def set_position_steps(self, x: int, y: int) -> None:
            """Set position in motor steps."""
            pass
        
        def get_step_size_x_um(self) -> float:
            """Get X-axis step size in micrometers."""
            pass
        
        def get_step_size_y_um(self) -> float:
            """Get Y-axis step size in micrometers."""
            pass
        
        # Additional methods for sequence support
        def get_sequence_max_length(self) -> int:
            """Maximum length of position sequences."""
            pass
        
        def send_sequence(self, sequence: tuple[tuple[float, float], ...]) -> None:
            """Load sequence of (x, y) positions."""
            pass
    ```

### State Devices (`StateDevice`)

For devices with discrete states (filter wheels, objective turrets, etc.):

```python
from pymmcore_plus.experimental.unicore import StateDevice

class MyFilterWheel(StateDevice):
    def set_state(self, pos: int) -> None:
        """Set device to specified state/position."""
        pass
    
    def get_state(self) -> int:
        """Get current state/position."""
        pass
```

### Shutter Devices (`ShutterDevice`)

For controlling shutters or any binary open/close devices:

```python
from pymmcore_plus.experimental.unicore import ShutterDevice

class MyShutter(ShutterDevice):
    def get_open(self) -> bool:
        """Return True if shutter is open."""
        pass
    
    def set_open(self, open: bool) -> None:
        """Open (True) or close (False) the shutter."""
        pass
```

### SLM Devices (`SLMDevice`)

For Spatial Light Modulators:

```python
from pymmcore_plus.experimental.unicore import SLMDevice
import numpy as np

class MySLM(SLMDevice):
    def get_width(self) -> int:
        """Return SLM width in pixels."""
        pass
    
    def get_height(self) -> int:
        """Return SLM height in pixels."""
        pass
    
    def get_number_of_components(self) -> int:
        """Return 1 for grayscale, 3 for RGB."""
        pass
    
    def get_bytes_per_pixel(self) -> int:
        """Return bytes per pixel."""
        pass
    
    def set_image(self, pixels: np.ndarray) -> None:
        """Set the image to display."""
        pass
    
    def display_image(self) -> None:
        """Display the currently loaded image."""
        pass
    
    def get_exposure(self) -> float:
        """Get exposure time in milliseconds."""
        pass
    
    def set_exposure(self, exposure_ms: float) -> None:
        """Set exposure time in milliseconds."""
        pass
```

### Generic Devices (`GenericDevice`)

For devices that don't fit other categories but need property control:

```python
from pymmcore_plus.experimental.unicore import GenericDevice

class MyGenericDevice(GenericDevice):
    # Only basic Device methods needed - mainly for property-only devices
    pass
```

## Device Properties

Python devices support the full property system. 

## Defining Device Properties

Properties are defined either on the class using the
[`@pymm_property`][pymmcore_plus.experimental.unicore.pymm_property] decorator,
or dynamically at runtime using
[`Device.register_property`][pymmcore_plus.experimental.unicore.Device.register_property].

These two methods may be freely mixed, and accept largely the same arguments.

=== "`@pymm_property`"

    ```python
    from pymmcore_plus.experimental.unicore import GenericDevice, pymm_property

    class MyDevice(GenericDevice):
        _my_prop = 42
        
        @pymm_property(name="MyProp", default_value=42, limits=(0, 100))
        def my_prop(self) -> int:
            """MyProp property with limits 0-100 and default 42."""
            return self._my_prop

        @my_prop.setter
        def my_prop(self, value: int) -> None:
            self._my_prop = value
    ```

=== "`register_property`"

    In many cases, you may not know ahead of device initialization which
    properties are supported. In this case, you can register properties
    at runtime in `initialize()`:

    ```python
    from pymmcore_plus.experimental.unicore import GenericDevice

    class MyDevice(GenericDevice):
        def initialize(self) -> None:
            cls = type(self)
            self.register_property(
                name="MyProp",
                getter=cls._get_my_prop,
                setter=cls._set_my_prop,
                default_value=42,
                limits=(0, 100),
            )

        def _set_my_prop(self, value: int) -> None:
            ...

        def _get_my_prop(self) -> int:
            ...

    ```

### Properties with Constraints

Properties may have value constraints such as numerical limits or
(categorical) allowed values:

```python
class MyStage(XYStageDevice):
    @pymm_property(limits=(0.0, 100.0))
    def speed(self) -> float:
        """Stage speed (0-100%)."""
        return self._speed
    
    @pymm_property(allowed_values=[1, 2, 4, 8])
    def step_size(self) -> int:
        """Step size multiplier."""
        return self._step_size
```

### Sequenceable Properties

In order to declare a property as "sequenceable" (i.e. supporting hardware-synchronized
parameter changes), you must:

1. Define a `sequence_max_length` of greater than zero.
2. Implement `sequence_loader` and `sequence_starter`, (and optionally `sequence_stopper`)
   methods.

=== "`@pymm_property`"

    ```python
    class MyDevice(GenericDevice):
        @pymm_property(sequence_max_length=100)
        def someprop(self) -> float:
            return self._someprop
        
        @someprop.setter
        def set_someprop(self, value: float) -> None:
            self._someprop = value
        
        @someprop.sequence_loader
        def load_someprop_sequence(self, sequence: list[float]) -> None:
            """Load a sequence of someprop values into hardware."""

        @someprop.sequence_starter  
        def start_someprop_sequence(self) -> None:
            """Tell hardware to start the sequence."""
        
        @someprop.sequence_stopper  # optional
        def stop_someprop_sequence(self) -> None:
            """Tell hardware to stop the sequence."""
    ```

=== "`register_property`"

    ```python
    class MyDevice(GenericDevice):
        def initialize(self) -> None:
            cls = type(self)
            self.register_property(
                name="someprop",
                getter=cls._get_someprop,
                setter=cls._set_someprop,
                sequence_loader=cls.load_someprop_sequence,
                sequence_starter=cls.start_someprop_sequence,
                sequence_stopper=cls.stop_someprop_sequence,
                sequence_max_length=100,
                default_value=10.0,
                limits=(0.1, 10000.0),
            )
        
        def _get_someprop(self) -> float:
            return self._someprop
        
        def _set_someprop(self, value: float) -> None:
            self._someprop = value
        
        def load_someprop_sequence(self, sequence: list[float]) -> None:
            """Load a sequence of someprop values into hardware."""
        
        def start_someprop_sequence(self) -> None:
            """Tell hardware to start the sequence."""
        
        def stop_someprop_sequence(self) -> None:
            """Tell hardware to stop the sequence."""
    ```

### Property Types and Validation

Properties are automatically typed based on their return annotations,
but you can be explicit:

```python
class MyDevice(GenericDevice):
    @pymm_property(property_type=str)
    def serial_number(self) -> str:
        return "12345"
    
    @pymm_property(property_type=int, limits=(1, 1000))
    def gain(self) -> int:
        return self._gain
```

## Device Lifecycle

All Python devices follow this lifecycle:

### 1. Creation and Loading

```python
# Create device instance
device = MyCamera()

# Load into core with a label
core.loadPyDevice("Camera1", device)
```

### 2. Initialization

```python
# Initialize the device (calls device.initialize())
core.initializeDevice("Camera1")
```

Override `initialize()` for device-specific setup:

```python
class MyCamera(CameraDevice):
    def initialize(self) -> None:
        """Called when device is initialized."""
        # Setup hardware connections, configure device, etc.
        self.connect_to_hardware()
        super().initialize()  # Call parent if needed
```

### 3. Usage

Once loaded and initialized, use the device through the standard CMMCore API:

```python
# Set as current device
core.setCameraDevice("Camera1") 

# Use standard API
core.setExposure(50)
image = core.snapImage()
```

### 4. Shutdown

```python
# Shutdown specific device
core.unloadDevice("Camera1")

# Or shutdown all devices  
core.unloadAllDevices()
```

Override `shutdown()` for cleanup:

```python
class MyCamera(CameraDevice):
    def shutdown(self) -> None:
        """Called when device is unloaded."""
        self.disconnect_from_hardware()
        super().shutdown()
```

## Thread Safety

Python devices are automatically made thread-safe using locks. All device
methods are called with the device locked to prevent concurrent access.

If you need manual locking:

```python
device = MyCamera()
core.loadPyDevice("Camera", device)

# Manual locking
with device:
    # Device is locked for this block
    device.some_internal_method()
```

## Events and Metadata

Python devices work seamlessly with the event system:

```python
@core.events.propertyChanged.connect
def on_property_changed(device, prop, value):
    print(f"{device}.{prop} = {value}")

# This will emit the event
core.setProperty("Camera1", "Exposure", 100)
```

Sequence acquisitions include metadata just as C++ camera adapters do

```python
core.startSequenceAcquisition(10)
while core.getRemainingImageCount() > 0:
    img, metadata = core.getLastImageAndMD()
    print(f"Image {metadata['ImageNumber']} timestamp: {metadata['ElapsedTime-ms']}")
```

## Error Handling

Python devices can raise exceptions which are converted to appropriate
Micro-Manager errors:

```python
class MyCamera(CameraDevice):
    def set_exposure(self, exposure: float) -> None:
        if exposure < 0:
            raise ValueError("Exposure must be positive")
        if exposure > 10000:
            raise ValueError("Exposure too long")
        self._exposure = exposure
```

```python
# This will raise a RuntimeError (converted from ValueError)
core.setExposure(-5)
```

## Complete Examples

See the `examples/` directory for complete working examples:

- `examples/unicore_camera.py` - Synthetic camera with temporal patterns
- `examples/unicore_hamamatsu.py` - Real Hamamatsu camera integration
- `examples/unicore.py` - Basic XY stage with properties

These examples demonstrate real-world usage patterns and best practices for
implementing Python device adapters with UniMMCore.
