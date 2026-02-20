"""Demonstrate the MDA runner's consumer-based dispatch system.

This example shows how to use FrameConsumer, ConsumerSpec, and RunPolicy to
register per-consumer worker threads with bounded queues, backpressure policies,
and critical/non-critical error semantics.

Run with: uv run python examples/consumer_dispatch.py
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from useq import MDAEvent, MDASequence

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import (
    BackpressurePolicy,
    ConsumerReport,
    ConsumerSpec,
    CriticalErrorPolicy,
    FrameConsumer,
    NonCriticalErrorPolicy,
    RunPolicy,
    RunReport,
    RunStatus,
)

if TYPE_CHECKING:
    import numpy as np

# ─── Define some example consumers ─────────────────────────────────

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


class TiffWriter(FrameConsumer):
    """Simulates a critical file-writer consumer."""

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        print(f"{CYAN}[TiffWriter]{RESET}  setup() — got {len(meta)} metadata keys")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        time.sleep(0.01)  # simulate I/O
        print(
            f"{CYAN}[TiffWriter]{RESET}  frame {event.index} "
            f"shape={img.shape} "
            f"runner_t={meta.get('runner_time_ms', 0):.0f}ms"
        )

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        print(f"{CYAN}[TiffWriter]{RESET}  finish() — status={status.value}")


class LiveDisplay(FrameConsumer):
    """Simulates a non-critical display consumer (e.g. napari)."""

    def __init__(self) -> None:
        self._count = 0

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        self._count = 0
        print(f"{GREEN}[Display]   {RESET}  setup()")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        time.sleep(0.05)  # simulate slow rendering
        self._count += 1
        print(
            f"{GREEN}[Display]   {RESET}  "
            f"rendered frame {self._count} — event {event.index}"
        )

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        print(
            f"{GREEN}[Display]   {RESET}  finish() — "
            f"rendered {self._count} frames total, status={status.value}"
        )


class MetricsLogger(FrameConsumer):
    """A non-critical consumer that logs frame timing."""

    def __init__(self) -> None:
        self._t0 = 0.0

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        self._t0 = time.perf_counter()
        print(f"{YELLOW}[Metrics]   {RESET}  setup()")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        elapsed = (time.perf_counter() - self._t0) * 1000
        print(
            f"{YELLOW}[Metrics]   {RESET}  "
            f"event {event.index} delivered at {elapsed:.0f}ms"
        )

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        total = (time.perf_counter() - self._t0) * 1000
        print(f"{YELLOW}[Metrics]   {RESET}  finish() — total {total:.0f}ms")


class FlakyAnalyzer(FrameConsumer):
    """A non-critical consumer that errors on every 3rd frame."""

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        self._count = 0
        print(f"{RED}[Flaky]     {RESET}  setup()")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self._count += 1
        if self._count % 3 == 0:
            raise RuntimeError(f"analysis failed on frame {self._count}!")
        print(f"{RED}[Flaky]     {RESET}  analyzed frame {self._count}")

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        print(f"{RED}[Flaky]     {RESET}  finish()")


# ─── Helper to print the RunReport ──────────────────────────────────


def print_report(report: RunReport) -> None:
    elapsed = report.finished_at - report.started_at
    print(f"\n{'=' * 60}")
    print(f"  Run Report: {report.status.value} in {elapsed:.2f}s")
    print(f"{'=' * 60}")
    for cr in report.consumer_reports:
        _print_consumer_report(cr)
    print()


def _print_consumer_report(cr: ConsumerReport) -> None:
    print(
        f"  {cr.name:20s}  submitted={cr.submitted}  processed={cr.processed}", end=""
    )
    if cr.dropped:
        print(f"  {RED}dropped={cr.dropped}{RESET}", end="")
    if cr.errors:
        print(f"  {RED}errors={len(cr.errors)}{RESET}", end="")
    print()


# ─── Define the sequence ──────────────────────────────────────────

sequence = MDASequence(
    channels=["DAPI", "FITC"],
    time_plan={"interval": 0.5, "loops": 3},
    axis_order="tc",
)

# ─── Configure core ────────────────────────────────────────────────

mmc = CMMCorePlus.instance()
mmc.loadSystemConfiguration()


# ─── Example 1: Multiple consumers with different criticality ──────


def example_basic() -> None:
    """Run with a critical writer, a non-critical display, and metrics."""
    print(f"\n{'─' * 60}")
    print("  Example 1: Basic multi-consumer dispatch")
    print(f"{'─' * 60}\n")

    consumers = [
        ConsumerSpec("tiff-writer", TiffWriter(), critical=True),
        ConsumerSpec("display", LiveDisplay(), critical=False),
        ConsumerSpec("metrics", MetricsLogger(), critical=False),
    ]

    report = mmc.mda.run(sequence, consumers=consumers)
    print_report(report)


# ─── Example 2: Non-critical error handling (DISCONNECT policy) ────


def example_disconnect_on_error() -> None:
    """A flaky consumer gets disconnected after its first error."""
    print(f"\n{'─' * 60}")
    print("  Example 2: Non-critical error → DISCONNECT")
    print(f"{'─' * 60}\n")

    consumers = [
        ConsumerSpec("tiff-writer", TiffWriter(), critical=True),
        ConsumerSpec("flaky", FlakyAnalyzer(), critical=False),
    ]

    policy = RunPolicy(
        noncritical_error=NonCriticalErrorPolicy.DISCONNECT,
    )

    report = mmc.mda.run(sequence, consumers=consumers, policy=policy)
    print_report(report)


# ─── Example 3: Backpressure with DROP_NEWEST ──────────────────────


def example_backpressure() -> None:
    """A slow display with a tiny queue drops frames it can't keep up with."""
    print(f"\n{'─' * 60}")
    print("  Example 3: Backpressure with DROP_NEWEST (queue=2)")
    print(f"{'─' * 60}\n")

    # A very slow display that can't keep up at all
    class VerySlowDisplay(FrameConsumer):
        def __init__(self) -> None:
            self._count = 0

        def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
            self._count = 0
            print(f"{GREEN}[SlowDisp]  {RESET}  setup()")

        def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
            time.sleep(0.15)  # very slow — will miss frames
            self._count += 1
            print(
                f"{GREEN}[SlowDisp]  {RESET}  "
                f"rendered frame {self._count} — event {event.index}"
            )

        def finish(self, sequence: MDASequence, status: RunStatus) -> None:
            print(
                f"{GREEN}[SlowDisp]  {RESET}  finish() — "
                f"rendered {self._count} frames, status={status.value}"
            )

    # Use a fast sequence so frames arrive faster than the display can render.
    fast_sequence = MDASequence(
        channels=["DAPI", "FITC"],
        time_plan={"interval": 0.0, "loops": 5},
        axis_order="tc",
    )

    consumers = [
        ConsumerSpec("tiff-writer", TiffWriter(), critical=True),
        ConsumerSpec("slow-display", VerySlowDisplay(), critical=False),
    ]

    policy = RunPolicy(
        backpressure=BackpressurePolicy.DROP_NEWEST,
        observer_queue=2,  # tiny queue for the non-critical display
        critical_queue=256,  # writer gets a big queue
    )

    report = mmc.mda.run(fast_sequence, consumers=consumers, policy=policy)
    print_report(report)


# ─── Example 4: Critical error → CANCEL ───────────────────────────


class FailingWriter(FrameConsumer):
    """A critical consumer that fails on the 2nd frame."""

    def setup(self, sequence: MDASequence, meta: dict[str, Any]) -> None:
        self._count = 0
        print(f"{RED}[FailWriter]{RESET}  setup()")

    def frame(self, img: np.ndarray, event: MDAEvent, meta: dict[str, Any]) -> None:
        self._count += 1
        if self._count == 2:
            raise OSError("disk full!")
        print(f"{RED}[FailWriter]{RESET}  wrote frame {self._count}")

    def finish(self, sequence: MDASequence, status: RunStatus) -> None:
        print(f"{RED}[FailWriter]{RESET}  finish() — status={status.value}")


def example_critical_cancel() -> None:
    """A critical consumer error cancels the entire acquisition."""
    print(f"\n{'─' * 60}")
    print("  Example 4: Critical error → CANCEL acquisition")
    print(f"{'─' * 60}\n")

    consumers = [
        ConsumerSpec("fail-writer", FailingWriter(), critical=True),
        ConsumerSpec("display", LiveDisplay(), critical=False),
    ]

    policy = RunPolicy(
        critical_error=CriticalErrorPolicy.CANCEL,
    )

    report = mmc.mda.run(sequence, consumers=consumers, policy=policy)
    print_report(report)


# ─── Run all examples ─────────────────────────────────────────────

if __name__ == "__main__":
    example_basic()
    example_disconnect_on_error()
    example_backpressure()
    example_critical_cancel()
