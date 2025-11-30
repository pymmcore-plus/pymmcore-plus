#!/usr/bin/env python
"""Benchmark script for the simulate module.

Run with:
    uv run scripts/simulate_benchmark.py              # PIL only
    uv run --with opencv-python scripts/simulate_benchmark.py  # with OpenCV

Expected results (512x512, 630 objects):
    Without opencv-python: ~18ms
    With opencv-python:    ~14ms (25% faster)

The benchmark tests:
    - Object count scaling (100-2000 objects)
    - Image size scaling (256-2048 pixels)
    - Noise impact (none, gaussian, shot, both)
    - Blur impact (0-5 radius)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from pymmcore_plus.experimental import simulate as sim

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    name: str
    n_objects: int
    n_iterations: int
    total_time: float
    mean_time: float
    std_time: float
    min_time: float
    max_time: float

    def __str__(self) -> str:
        """String representation of the benchmark result."""
        return (
            f"{self.name}: {self.mean_time * 1000:.2f}ms ± {self.std_time * 1000:.2f}ms"
            f" (min={self.min_time * 1000:.2f}ms, max={self.max_time * 1000:.2f}ms, "
            f"n={self.n_iterations}, objects={self.n_objects})"
        )


def create_mock_state(
    width: int = 512, height: int = 512, pixel_size: float = 1.0
) -> dict:
    """Create a mock microscope state."""
    return {
        "format": "summary-dict",
        "version": "1.0",
        "image_infos": [
            {
                "camera_label": "Camera",
                "width": width,
                "height": height,
                "pixel_size_um": pixel_size,
                "plane_shape": (height, width),
                "dtype": "uint8",
                "pixel_format": "Mono8",
                "pixel_size_config_name": "Res10x",
            }
        ],
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "devices": [
            {
                "label": "Camera",
                "type": "Camera",
                "library": "DemoCamera",
                "name": "DCam",
                "description": "Demo camera",
                "properties": [
                    {
                        "name": "Exposure",
                        "value": "100.0",
                        "data_type": "float",
                        "is_read_only": False,
                    }
                ],
            }
        ],
        "system_info": {},
        "config_groups": (),
        "pixel_size_configs": (),
    }


def create_sample_objects(
    n_points: int = 200,
    n_lines: int = 400,
    n_rectangles: int = 30,
    extent: int = 1000,
    seed: int = 42,
) -> list:
    """Create sample objects matching the example."""
    rng = np.random.default_rng(seed)
    objects: list = []

    # Random lines
    objects.extend(
        sim.Line(
            start=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            end=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            intensity=int(rng.integers(20, 50)),
        )
        for _ in range(n_lines)
    )

    # Random points
    objects.extend(
        sim.Point(
            x=int(rng.integers(-extent, extent)),
            y=int(rng.integers(-extent, extent)),
            intensity=int(rng.integers(30, 150)),
            radius=float(rng.uniform(2, 12)),
        )
        for _ in range(n_points)
    )

    # Random rectangles
    objects.extend(
        sim.Rectangle(
            top_left=(
                int(rng.integers(-extent, extent)),
                int(rng.integers(-extent, extent)),
            ),
            width=float(rng.uniform(20, 60)),
            height=float(rng.uniform(20, 60)),
            intensity=int(rng.integers(40, 100)),
            fill=True,
        )
        for _ in range(n_rectangles)
    )

    return objects


def benchmark(
    func: Callable[[], None],
    n_iterations: int = 20,
    warmup: int = 3,
    name: str = "benchmark",
    n_objects: int = 0,
) -> BenchmarkResult:
    """Run a benchmark with warmup."""
    # Warmup
    for _ in range(warmup):
        func()

    # Benchmark
    times = []
    for _ in range(n_iterations):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)

    times_arr = np.array(times)
    return BenchmarkResult(
        name=name,
        n_objects=n_objects,
        n_iterations=n_iterations,
        total_time=times_arr.sum(),
        mean_time=times_arr.mean(),
        std_time=times_arr.std(),
        min_time=times_arr.min(),
        max_time=times_arr.max(),
    )


def run_benchmarks() -> list[BenchmarkResult]:
    """Run all benchmarks."""
    results = []

    # Test different object counts
    for n_objects in [100, 500, 1000, 2000]:
        n_points = n_objects // 3
        n_lines = n_objects // 3
        n_rects = n_objects // 3

        objects = create_sample_objects(
            n_points=n_points, n_lines=n_lines, n_rectangles=n_rects
        )
        config = sim.RenderConfig(
            noise_std=3.0, shot_noise=True, defocus_scale=0.12, base_blur=1.5
        )
        engine = sim.RenderEngine(objects, config)
        state = create_mock_state()

        result = benchmark(
            lambda e=engine, s=state: e.render(s),  # type: ignore[arg-type]
            name=f"render_{n_objects}_objects",
            n_objects=len(objects),
            n_iterations=10,
        )
        results.append(result)
        print(result)

    # Test different image sizes
    objects = create_sample_objects(n_points=200, n_lines=400, n_rectangles=30)
    config = sim.RenderConfig(noise_std=3.0, shot_noise=True)

    for size in [256, 512, 1024, 2048]:
        engine = sim.RenderEngine(objects, config)
        state = create_mock_state(width=size, height=size)

        result = benchmark(
            lambda e=engine, s=state: e.render(s),  # type: ignore[arg-type]
            name=f"render_{size}x{size}",
            n_objects=len(objects),
            n_iterations=10,
        )
        results.append(result)
        print(result)

    # Test with/without noise
    objects = create_sample_objects()
    state = create_mock_state()

    for noise_std, shot_noise, name in [
        (0, False, "no_noise"),
        (3.0, False, "gaussian_only"),
        (0, True, "shot_only"),
        (3.0, True, "both_noise"),
    ]:
        config = sim.RenderConfig(noise_std=noise_std, shot_noise=shot_noise)
        engine = sim.RenderEngine(objects, config)

        result = benchmark(
            lambda e=engine, s=state: e.render(s),  # type: ignore[arg-type]
            name=f"render_{name}",
            n_objects=len(objects),
            n_iterations=10,
        )
        results.append(result)
        print(result)

    # Test with/without blur
    for blur in [0, 1.0, 2.0, 5.0]:
        config = sim.RenderConfig(noise_std=0, shot_noise=False, base_blur=blur)
        engine = sim.RenderEngine(objects, config)

        result = benchmark(
            lambda e=engine, s=state: e.render(s),  # type: ignore[arg-type]
            name=f"render_blur_{blur}",
            n_objects=len(objects),
            n_iterations=10,
        )
        results.append(result)
        print(result)

    return results


if __name__ == "__main__":
    print("=" * 70)
    print("SIMULATE MODULE BENCHMARKS")
    print("=" * 70)
    print()
    run_benchmarks()
