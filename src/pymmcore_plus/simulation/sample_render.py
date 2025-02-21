from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PIL import Image, ImageDraw
import numpy as np

if TYPE_CHECKING:
    from typing import TypeAlias

    from pymmcore_plus.metadata.schema import ImageInfo, SummaryMetaV1

    # A transformation function converts continuous (x, y) to pixel coordinates.
    TransformFn: TypeAlias = Callable[[float, float], tuple[int, int]]
    Bounds: TypeAlias = tuple[float, float, float, float]


# Base class for sample objects.
class SampleObject:
    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        """Draw object on `draw_context` using continuous -> pixelcoordinates tform."""
        raise NotImplementedError()

    def get_bounds(self) -> Bounds:
        """Return bounding box in continuous space as (left, top, right, bottom)."""
        raise NotImplementedError()


def rects_intersect(a: Bounds, b: Bounds) -> bool:
    """Check if rectangle a and b intersect.

    Each rectangle is (left, top, right, bottom) in continuous space.
    """
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


# Example geometric primitives.
class Point(SampleObject):
    def __init__(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int] = (255, 0, 0),
        radius: float = 2.0,
    ) -> None:
        self.x = x
        self.y = y
        self.color = color
        self.radius = radius

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        cx, cy = transform(self.x, self.y)
        r = self.radius
        draw_context.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.color)

    def get_bounds(self) -> Bounds:
        return (
            self.x - self.radius,
            self.y - self.radius,
            self.x + self.radius,
            self.y + self.radius,
        )


class Ellipse(SampleObject):
    def __init__(
        self,
        center: tuple[float, float],
        rx: float,
        ry: float,
        color: tuple[int, int, int] = (0, 255, 0),
    ) -> None:
        self.center = center
        self.rx = rx
        self.ry = ry
        self.color = color

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        cx, cy = transform(*self.center)
        # Compute scale: number of pixels per micron.
        # Since our transform rounds to int, we subtract just the x-coordinate.
        unit_edge, _ = transform(1, 0)
        unit_origin, _ = transform(0, 0)
        scale = abs(unit_edge - unit_origin)  # pixels per micron
        rx_pix = self.rx * scale
        ry_pix = self.ry * scale
        draw_context.ellipse(
            [cx - rx_pix, cy - ry_pix, cx + rx_pix, cy + ry_pix],
            outline=self.color,
            width=2,
        )

    def get_bounds(self) -> Bounds:
        return (
            self.center[0] - self.rx,
            self.center[1] - self.ry,
            self.center[0] + self.rx,
            self.center[1] + self.ry,
        )


class Rectangle(SampleObject):
    def __init__(
        self,
        top_left: tuple[float, float],
        width: float,
        height: float,
        color: tuple[int, int, int] = (0, 0, 255),
        radius: float = 0,
    ) -> None:
        self.top_left = top_left
        self.width = width
        self.height = height
        self.color = color
        self.radius = radius

    @property
    def bot_right(self) -> tuple[float, float]:
        return (self.top_left[0] + self.width, self.top_left[1] + self.height)

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        tl = transform(*self.top_left)
        br = transform(*self.bot_right)
        draw_context.rounded_rectangle(
            [tl, br], radius=self.radius, outline=self.color, width=2
        )

    def get_bounds(self) -> Bounds:
        return (
            self.top_left[0],
            self.top_left[1],
            self.top_left[0] + self.width,
            self.top_left[1] + self.height,
        )


class Line(SampleObject):
    def __init__(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        color: tuple[int, int, int] = (0, 0, 0),
        width: int = 1,
    ) -> None:
        self.start = start
        self.end = end
        self.color = color
        self.width = width

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        pt1 = transform(*self.start)
        pt2 = transform(*self.end)
        draw_context.line([pt1, pt2], fill=self.color, width=self.width)

    def get_bounds(self) -> Bounds:
        x1, y1 = self.start
        x2, y2 = self.end
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        return (left, top, right, bottom)


class Polygon(SampleObject):
    def __init__(
        self,
        vertices: list[tuple[float, float]],
        outline: tuple[int, int, int] = (0, 0, 0),
        fill: tuple[int, int, int] | None = None,
        width: int = 1,
    ) -> None:
        self.vertices = vertices
        self.outline = outline
        self.fill = fill
        self.width = width

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        # Transform all vertices from continuous to pixel coordinates.
        transformed = [transform(x, y) for x, y in self.vertices]
        # If a fill color is provided, fill the polygon first.
        if self.fill is not None:
            draw_context.polygon(transformed, fill=self.fill)
        # Draw the outline.
        # Note: ImageDraw.polygon does not support a width parameter.
        # For width > 1, we draw the outline using line() to connect the vertices.
        if self.width == 1:
            draw_context.polygon(transformed, outline=self.outline)
        else:
            draw_context.line(
                transformed + [transformed[0]], fill=self.outline, width=self.width
            )

    def get_bounds(self) -> Bounds:
        xs = [x for x, _ in self.vertices]
        ys = [y for _, y in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))


class RegularPolygon(Polygon):
    def __init__(
        self,
        bounding_circle: tuple[float, float, float],
        n_sides: int,
        rotation: float = 0,
        fill: tuple[int, int, int] | None = None,
        outline: tuple[int, int, int] = (0, 0, 0),
        width: int = 1,
    ) -> None:
        try:
            from PIL.ImageDraw import _compute_regular_polygon_vertices
        except ImportError:
            raise ImportError("RegularPolygon not available in this version of Pillow.")
        vertices = _compute_regular_polygon_vertices(bounding_circle, n_sides, rotation)
        super().__init__(vertices, outline, fill, width)


class Arc(SampleObject):
    def __init__(
        self,
        bbox: Bounds,
        start: float,
        end: float,
        color: tuple[int, int, int] = (0, 0, 0),
        width: int = 1,
    ) -> None:
        self.bbox = bbox
        self.start = start
        self.end = end
        self.color = color
        self.width = width

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        # Transform the bounding box corners.
        top_left = transform(self.bbox[0], self.bbox[1])
        bottom_right = transform(self.bbox[2], self.bbox[3])
        # Draw the arc using the transformed bounding box.
        draw_context.arc(
            [top_left, bottom_right],
            start=self.start,
            end=self.end,
            fill=self.color,
            width=self.width,
        )

    def get_bounds(self) -> Bounds:
        return self.bbox


class Bitmap(SampleObject):
    def __init__(
        self,
        top_left: tuple[float, float],
        bitmap: Image.Image | np.ndarray,
        fill: tuple[int, int, int] | None = None,
    ) -> None:
        self.top_left = top_left
        if isinstance(bitmap, np.ndarray):
            bitmap = Image.fromarray(bitmap)
        # Convert to 1-bit if no fill is provided.
        # if fill is None and bitmap.mode != "1":
            # bitmap = bitmap.convert("1")
        self.bitmap = bitmap
        self.fill = fill

    def draw(self, draw_context: ImageDraw.ImageDraw, transform: TransformFn) -> None:
        tl = transform(*self.top_left)
        draw_context.bitmap(tl, self.bitmap, fill=self.fill)

    def get_bounds(self) -> Bounds:
        width, height = self.bitmap.size
        return (
            self.top_left[0],
            self.top_left[1],
            self.top_left[0] + width,
            self.top_left[1] + height,
        )


# The render engine computes the continuous bounds and generates a discrete image.
class RenderEngine:
    def __init__(self, sample_objects: list[SampleObject]) -> None:
        self.sample_objects = sample_objects

    def render(self, state: SummaryMetaV1) -> Image.Image:
        """Render the sample objects in the context of the provided state."""
        img_width, img_height = _img_width_height(state)

        # Compute the field of view (FOV) in continuous space.
        # Assuming stage_xy is the center, determine the bounds.
        pixel_size = _pixel_size(state)
        fov_width = img_width * pixel_size
        fov_height = img_height * pixel_size
        stage_x, stage_y, _ = _xy_position(state)
        left = stage_x - fov_width / 2
        top = stage_y - fov_height / 2
        fov_rect = (left, top, left + fov_width, top + fov_height)

        # Define transformation from continuous (microns) to pixel coordinates.
        def transform(x: float, y: float) -> tuple[int, int]:
            pixel_x = (x - left) / pixel_size
            pixel_y = (y - top) / pixel_size
            return int(pixel_x), int(pixel_y)

        # Create a blank image (white background)
        image = Image.new("RGB", (img_width, img_height), "white")
        draw = ImageDraw.Draw(image)

        # Iterate over sample objects and perform frustum culling.
        print("---------")
        for obj in self.sample_objects:
            obj_bounds = obj.get_bounds()
            if rects_intersect(fov_rect, obj_bounds):
                print("drawing", obj)
                obj.draw(draw, transform)

        return image


# ----------------------


def _img_info(state: SummaryMetaV1) -> ImageInfo:
    if not (img_infos := state["image_infos"]):
        raise ValueError("No image info available.")
    return img_infos[0]


def _img_width_height(state: SummaryMetaV1) -> tuple[int, int]:
    img_info = _img_info(state)
    return img_info["width"], img_info["height"]


def _pixel_size(state: SummaryMetaV1) -> float:
    return _img_info(state)["pixel_size_um"]


def _xy_position(state: SummaryMetaV1) -> tuple[float, float, float]:
    pos = state["position"]
    return (pos.get("x", 0), pos.get("y", 0), pos.get("z", 0))
