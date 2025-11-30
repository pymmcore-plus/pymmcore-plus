"""Sample objects that can be rendered by the simulation engine.

All objects are defined in world-space coordinates (typically microns).
The RenderEngine handles transformation to pixel coordinates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TypeAlias

    # A transformation function converts continuous (x, y) to pixel coordinates.
    TransformFn: TypeAlias = Callable[[float, float], tuple[int, int]]

# Bounding box in continuous space: (left, top, right, bottom)
Bounds: TypeAlias = tuple[float, float, float, float]


def rects_intersect(a: Bounds, b: Bounds) -> bool:
    """Check if two rectangles intersect.

    Parameters
    ----------
    a : Bounds
        First rectangle as (left, top, right, bottom).
    b : Bounds
        Second rectangle as (left, top, right, bottom).

    Returns
    -------
    bool
        True if rectangles intersect.
    """
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


class SampleObject(ABC):
    """Base class for drawable sample objects.

    All coordinates are in world-space (typically microns). Objects are rendered
    by calling `draw()` with a transform function that converts world coordinates
    to pixel coordinates.

    Subclasses must implement:
    - `draw()`: Render the object onto a PIL ImageDraw context
    - `get_bounds()`: Return the bounding box in world coordinates
    """

    @abstractmethod
    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        """Draw this object onto the given context.

        Parameters
        ----------
        draw_context : ImageDraw.ImageDraw
            PIL ImageDraw context to draw on.
        transform : TransformFn
            Function to convert (world_x, world_y) to (pixel_x, pixel_y).
        scale : float
            Pixels per world unit (e.g., pixels per micron).
        """

    @abstractmethod
    def get_bounds(self) -> Bounds:
        """Return bounding box in world coordinates.

        Returns
        -------
        Bounds
            Tuple of (left, top, right, bottom) in world units.
        """

    def should_draw(self, fov_rect: Bounds) -> bool:
        """Check if this object intersects the field of view.

        Parameters
        ----------
        fov_rect : Bounds
            Field of view rectangle in world coordinates.

        Returns
        -------
        bool
            True if object should be drawn (intersects FOV).
        """
        return rects_intersect(fov_rect, self.get_bounds())


@dataclass
class Point(SampleObject):
    """A circular point/spot in the sample.

    Parameters
    ----------
    x : float
        X coordinate in world units.
    y : float
        Y coordinate in world units.
    intensity : int
        Brightness value (0-255). Default 255.
    radius : float
        Radius in world units. Default 2.0.
    """

    x: float
    y: float
    intensity: int = 255
    radius: float = 2.0

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        cx, cy = transform(self.x, self.y)
        r = self.radius * scale
        draw_context.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.intensity)

    def get_bounds(self) -> Bounds:
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius,
        )


@dataclass
class Ellipse(SampleObject):
    """An ellipse in the sample.

    Parameters
    ----------
    center : tuple[float, float]
        Center (x, y) in world units.
    rx : float
        X radius in world units.
    ry : float
        Y radius in world units.
    intensity : int
        Brightness value (0-255). Default 255.
    fill : bool
        If True, fill the ellipse. If False, draw outline only. Default False.
    width : int
        Outline width in pixels (only used if fill=False). Default 1.
    """

    center: tuple[float, float]
    rx: float
    ry: float
    intensity: int = 255
    fill: bool = False
    width: int = 1

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        cx, cy = transform(*self.center)
        rx_pix = self.rx * scale
        ry_pix = self.ry * scale
        bbox = [cx - rx_pix, cy - ry_pix, cx + rx_pix, cy + ry_pix]
        if self.fill:
            draw_context.ellipse(bbox, fill=self.intensity)
        else:
            draw_context.ellipse(bbox, outline=self.intensity, width=self.width)

    def get_bounds(self) -> Bounds:
        return (
            self.center[0] - self.rx,
            self.center[1] - self.ry,
            self.center[0] + self.rx,
            self.center[1] + self.ry,
        )


@dataclass
class Rectangle(SampleObject):
    """A rectangle in the sample.

    Parameters
    ----------
    top_left : tuple[float, float]
        Top-left corner (x, y) in world units.
    width : float
        Width in world units.
    height : float
        Height in world units.
    intensity : int
        Brightness value (0-255). Default 255.
    fill : bool
        If True, fill the rectangle. If False, draw outline only. Default False.
    corner_radius : float
        Corner radius for rounded rectangles, in world units. Default 0.
    line_width : int
        Outline width in pixels (only used if fill=False). Default 1.
    """

    top_left: tuple[float, float]
    width: float
    height: float
    intensity: int = 255
    fill: bool = False
    corner_radius: float = 0
    line_width: int = 1

    @property
    def bottom_right(self) -> tuple[float, float]:
        """Bottom-right corner coordinates."""
        return (self.top_left[0] + self.width, self.top_left[1] + self.height)

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        tl = transform(*self.top_left)
        br = transform(*self.bottom_right)
        radius = int(self.corner_radius * scale)
        if self.fill:
            draw_context.rounded_rectangle([tl, br], radius=radius, fill=self.intensity)
        else:
            draw_context.rounded_rectangle(
                [tl, br], radius=radius, outline=self.intensity, width=self.line_width
            )

    def get_bounds(self) -> Bounds:
        return (
            self.top_left[0],
            self.top_left[1],
            self.top_left[0] + self.width,
            self.top_left[1] + self.height,
        )


@dataclass
class Line(SampleObject):
    """A line segment in the sample.

    Parameters
    ----------
    start : tuple[float, float]
        Start point (x, y) in world units.
    end : tuple[float, float]
        End point (x, y) in world units.
    intensity : int
        Brightness value (0-255). Default 255.
    width : int
        Line width in pixels. Default 1.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    intensity: int = 255
    width: int = 1

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        pt1 = transform(*self.start)
        pt2 = transform(*self.end)
        draw_context.line([pt1, pt2], fill=self.intensity, width=self.width)

    def get_bounds(self) -> Bounds:
        x1, y1 = self.start
        x2, y2 = self.end
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


@dataclass
class Polygon(SampleObject):
    """A polygon in the sample.

    Parameters
    ----------
    vertices : Sequence[tuple[float, float]]
        List of (x, y) vertices in world units.
    intensity : int
        Brightness value (0-255). Default 255.
    fill : bool
        If True, fill the polygon. Default False.
    width : int
        Outline width in pixels (only used if fill=False). Default 1.
    """

    vertices: Sequence[tuple[float, float]]
    intensity: int = 255
    fill: bool = False
    width: int = 1

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        transformed = [transform(x, y) for x, y in self.vertices]
        if self.fill:
            draw_context.polygon(transformed, fill=self.intensity)
        elif self.width == 1:
            draw_context.polygon(transformed, outline=self.intensity)
        else:
            # ImageDraw.polygon doesn't support width, use lines instead
            draw_context.line(
                [*transformed, transformed[0]], fill=self.intensity, width=self.width
            )

    def get_bounds(self) -> Bounds:
        xs = [x for x, _ in self.vertices]
        ys = [y for _, y in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class RegularPolygon(SampleObject):
    """A regular polygon inscribed in a circle.

    Parameters
    ----------
    center : tuple[float, float]
        Center (x, y) in world units.
    radius : float
        Radius of bounding circle in world units.
    n_sides : int
        Number of sides.
    rotation : float
        Rotation angle in degrees. Default 0.
    intensity : int
        Brightness value (0-255). Default 255.
    fill : bool
        If True, fill the polygon. Default False.
    width : int
        Outline width in pixels (only used if fill=False). Default 1.
    """

    center: tuple[float, float]
    radius: float
    n_sides: int
    rotation: float = 0
    intensity: int = 255
    fill: bool = False
    width: int = 1
    _vertices: list[tuple[float, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Compute vertices."""
        import math

        cx, cy = self.center
        angle_offset = math.radians(self.rotation)
        self._vertices = []
        for i in range(self.n_sides):
            angle = 2 * math.pi * i / self.n_sides + angle_offset
            x = cx + self.radius * math.cos(angle)
            y = cy + self.radius * math.sin(angle)
            self._vertices.append((x, y))

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        transformed = [transform(x, y) for x, y in self._vertices]
        if self.fill:
            draw_context.polygon(transformed, fill=self.intensity)
        elif self.width == 1:
            draw_context.polygon(transformed, outline=self.intensity)
        else:
            draw_context.line(
                [*transformed, transformed[0]], fill=self.intensity, width=self.width
            )

    def get_bounds(self) -> Bounds:
        return (
            self.center[0] - self.radius,
            self.center[1] - self.radius,
            self.center[0] + self.radius,
            self.center[1] + self.radius,
        )


@dataclass
class Arc(SampleObject):
    """An arc (partial ellipse outline) in the sample.

    Parameters
    ----------
    center : tuple[float, float]
        Center (x, y) in world units.
    rx : float
        X radius in world units.
    ry : float
        Y radius in world units.
    start_angle : float
        Start angle in degrees.
    end_angle : float
        End angle in degrees.
    intensity : int
        Brightness value (0-255). Default 255.
    width : int
        Arc width in pixels. Default 1.
    """

    center: tuple[float, float]
    rx: float
    ry: float
    start_angle: float
    end_angle: float
    intensity: int = 255
    width: int = 1

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        cx, cy = transform(*self.center)
        rx_pix = self.rx * scale
        ry_pix = self.ry * scale
        bbox = [cx - rx_pix, cy - ry_pix, cx + rx_pix, cy + ry_pix]
        draw_context.arc(
            bbox,
            start=self.start_angle,
            end=self.end_angle,
            fill=self.intensity,
            width=self.width,
        )

    def get_bounds(self) -> Bounds:
        return (
            self.center[0] - self.rx,
            self.center[1] - self.ry,
            self.center[0] + self.rx,
            self.center[1] + self.ry,
        )


@dataclass
class Bitmap(SampleObject):
    """A bitmap image placed in the sample.

    The bitmap is placed at a fixed position and scale in world coordinates.
    Each pixel of the bitmap corresponds to one world unit.

    Parameters
    ----------
    top_left : tuple[float, float]
        Top-left corner (x, y) in world units.
    data : np.ndarray | Image.Image | str
        Image data as numpy array, PIL Image, or path to image file.
    scale : float
        World units per bitmap pixel. Default 1.0 (1 pixel = 1 world unit).
    """

    top_left: tuple[float, float]
    data: np.ndarray | Image.Image | str
    bitmap_scale: float = 1.0
    _image: Image.Image = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Convert input to PIL Image."""
        if isinstance(self.data, np.ndarray):
            self._image = Image.fromarray(self.data)
        elif isinstance(self.data, str):
            self._image = Image.open(self.data)
        elif isinstance(self.data, Image.Image):
            self._image = self.data
        else:
            raise TypeError(
                f"Invalid bitmap type: {type(self.data)}. "
                "Expected np.ndarray, PIL.Image.Image, or str path."
            )
        # Convert to grayscale if needed
        if self._image.mode != "L":
            self._image = self._image.convert("L")

    def draw(
        self,
        draw_context: ImageDraw.ImageDraw,
        transform: TransformFn,
        scale: float,
    ) -> None:
        tl = transform(*self.top_left)
        # Scale the bitmap to match world-to-pixel scale
        new_width = int(self._image.width * self.bitmap_scale * scale)
        new_height = int(self._image.height * self.bitmap_scale * scale)
        if new_width > 0 and new_height > 0:
            new_size = (new_width, new_height)
            scaled = self._image.resize(new_size, Image.Resampling.NEAREST)
            # Get the underlying image from the draw context
            base_image: Image.Image = draw_context._image  # noqa: SLF001
            base_image.paste(scaled, tl)

    def get_bounds(self) -> Bounds:
        width = self._image.width * self.bitmap_scale
        height = self._image.height * self.bitmap_scale
        return (
            self.top_left[0],
            self.top_left[1],
            self.top_left[0] + width,
            self.top_left[1] + height,
        )
