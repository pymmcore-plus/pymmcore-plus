"""Simulated microscope sample for testing and development.

This module provides tools for creating virtual microscope samples that
integrate with CMMCorePlus. When a sample is installed on a core, image
acquisition returns rendered images based on the sample objects and
current microscope state (stage position, exposure, pixel size, etc.).

Examples
--------
Create a sample with some objects and use it with a core:

>>> from pymmcore_plus import CMMCorePlus
>>> from pymmcore_plus.experimental.simulate import (
...     Sample,
...     Point,
...     Line,
...     Rectangle,
...     RenderConfig,
... )
>>>
>>> # Create core and load config
>>> core = CMMCorePlus.instance()
>>> core.loadSystemConfiguration()
>>>
>>> # Define sample objects (coordinates in microns)
>>> sample = Sample(
...     [
...         Point(0, 0, intensity=200, radius=5),
...         Point(50, 50, intensity=150, radius=3),
...         Line((0, 0), (100, 100), intensity=100),
...         Rectangle((20, 20), width=30, height=20, intensity=180, fill=True),
...     ]
... )
>>>
>>> # Use as context manager
>>> with sample.patch(core):
...     core.snapImage()
...     img = core.getImage()  # Returns rendered simulation
...     print(img.shape, img.dtype)

Custom render configuration:

>>> config = RenderConfig(
...     noise_std=5.0,  # More noise
...     defocus_scale=0.2,  # More blur with Z
...     shot_noise=False,  # Disable shot noise
...     bit_depth=16,  # 16-bit output
... )
>>> sample = Sample([Point(0, 0)], config=config)

Manual install/uninstall:

>>> sample.install(core)
>>> # ... do stuff ...
>>> sample.uninstall()
"""

from ._objects import (
    Arc,
    Bitmap,
    Bounds,
    Ellipse,
    Line,
    Point,
    Polygon,
    Rectangle,
    RegularPolygon,
    SampleObject,
    rects_intersect,
)
from ._render import RenderConfig, RenderEngine
from ._sample import Sample

__all__ = [
    "Arc",
    "Bitmap",
    # Utilities
    "Bounds",
    "Ellipse",
    "Line",
    "Point",
    "Polygon",
    "Rectangle",
    "RegularPolygon",
    # Configuration
    "RenderConfig",
    "RenderEngine",
    # Main entry point
    "Sample",
    # Sample objects
    "SampleObject",
    "rects_intersect",
]
