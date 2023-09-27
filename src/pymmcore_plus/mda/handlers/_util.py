from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import useq


def get_full_sequence_axes(sequence: useq.MDASequence) -> tuple[str, ...]:
    """Get the combined axes from sequence and sub-sequences."""
    # axes main sequence
    main_seq_axes = list(sequence.used_axes)
    if not sequence.stage_positions:
        return tuple(main_seq_axes)
    # axes from sub sequences
    sub_seq_axes: list = []
    for p in sequence.stage_positions:
        if p.sequence is not None:
            sub_seq_axes.extend(
                [ax for ax in p.sequence.used_axes if ax not in main_seq_axes]
            )
    return tuple(main_seq_axes + sub_seq_axes)
