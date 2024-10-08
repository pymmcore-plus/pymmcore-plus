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


def position_sizes(seq: useq.MDASequence) -> list[dict[str, int]]:
    """Return a list of size dicts for each position in the sequence.

    There will be one dict for each position in the sequence. Each dict will contain
    `{dim: size}` pairs for each dimension in the sequence. Dimensions with no size
    will be omitted, though singletons will be included.
    """
    main_sizes = dict(seq.sizes)
    main_sizes.pop("p", None)  # remove position

    if not seq.stage_positions:
        # this is a simple MDASequence
        return [{k: v for k, v in main_sizes.items() if v}]

    sizes = []
    for p in seq.stage_positions:
        if p.sequence is not None:
            psizes = {k: v or main_sizes.get(k, 0) for k, v in p.sequence.sizes.items()}
        else:
            psizes = main_sizes.copy()
        sizes.append({k: v for k, v in psizes.items() if v and k != "p"})
    return sizes
