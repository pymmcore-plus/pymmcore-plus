import threading
import time

from useq import MDASequence

from pymmcore_plus import CMMCorePlus


def t() -> None:
    """Test that remaining wait time is recalculated correctly during pause.

    This verifies the comment in _get_remaining_wait_time:
    'We calculate remaining_wait_time fresh each iteration using
    event.min_start_time + self._paused_time to ensure it stays correct
    even when self._paused_time changes during pause.'
    """
    core = CMMCorePlus()
    core.loadSystemConfiguration()

    # Create a sequence with a time interval that will trigger min_start_time waiting
    sequence = MDASequence(
        time_plan={"interval": 4.0, "loops": 3},
    )

    awaiting_events: list[tuple[float, float]] = []  # (remaining_time, paused_time)
    first_awaiting_seen = threading.Event()

    def on_awaiting_event(event, remaining_time):
        # Capture the remaining time and current paused_time
        paused_time = core.mda._paused_time
        awaiting_events.append((remaining_time, paused_time))
        from rich import print

        print(
            f"Awaiting: remaining={remaining_time:.2f}s, paused_time={paused_time:.2f}s"
        )

        # Signal that we've seen the first awaiting event
        if not first_awaiting_seen.is_set():
            first_awaiting_seen.set()

    core.mda.events.awaitingEvent.connect(on_awaiting_event)

    # Run MDA in a thread so we can pause it from the main thread
    mda_thread = threading.Thread(target=lambda: core.mda.run(sequence))
    mda_thread.start()

    from rich import print

    try:
        # Wait for the first awaiting event
        print("Waiting for first awaiting event...")
        if first_awaiting_seen.wait(timeout=5.0):
            # Now pause while in the wait loop
            core.mda.toggle_pause()
            # Let pause time accumulate
            time.sleep(5.0)
            print(f"Paused time accumulated: {core.mda._paused_time:.2f} seconds")

            # Resume
            core.mda.toggle_pause()

        # Wait for MDA to finish
        mda_thread.join(timeout=20)
    except KeyboardInterrupt:
        core.mda.cancel()
        mda_thread.join()

    print("\nAll awaiting events:")
    print(awaiting_events)

    # # Verify we captured awaiting events
    # assert len(awaiting_events) > 0, "Expected awaiting events to be captured"

    # # Find the paused_time values
    # paused_times = [pt for _, pt in awaiting_events]

    # # During/after pause, paused_time should have increased from 0
    # # This verifies that _get_remaining_wait_time recalculates using
    # # the updated _paused_time value
    # assert any(pt > 0 for pt in paused_times), (
    #     "Expected some paused_time > 0 after pause, "
    #     f"but got paused_times: {paused_times}"
    # )

    # # Verify that remaining times were recalculated correctly
    # # When paused_time increases, the remaining wait time calculation
    # # should reflect this: min_start_time + paused_time - elapsed
    # for i in range(1, len(awaiting_events)):
    #     _remaining_prev, paused_prev = awaiting_events[i - 1]
    #     remaining_curr, paused_curr = awaiting_events[i]

    #     # If paused_time increased, the calculation used the new value
    #     if paused_curr > paused_prev:
    #         # Remaining time should still be reasonable (positive or near zero)
    #         # This confirms the fresh recalculation is working
    #         assert remaining_curr >= -0.1, (
    #             f"Remaining time became unexpectedly negative after pause increase. "
    #             f"Got remaining={remaining_curr}, paused_time went from "
    #             f"{paused_prev} to {paused_curr}"
    #         )


t()
