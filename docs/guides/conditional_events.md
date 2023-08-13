# Conditional Event Sequences

!!! warning "Important"

    This page assumes you have a basic understanding of how the default MDA
    acquisition engine works to execute a sequence of `useq.MDAEvent` objects.
    If you haven't already done so, please read the [Acquisition
    Engine](./mda_engine.md) guide first.

Sometimes, you may not know the exact sequence of events you want to execute
ahead of time. For example, you may want to start acquiring images at a certain
frequency, but then take a burst of images at a faster frame rate or in a
specific region of interest when a specific (possibly rare) event occurs.
This is sometimes referred to as "event-driven" microscopy, or "smart-microscopy".

!!! info "In publications"

    For two compelling examples of this type of event-driven microscopy, see:

    1. Mahecic D, Stepp WL, Zhang C, Griffié J, Weigert M, Manley S.
    *Event-driven acquisition for content-enriched microscopy.*
    Nat Methods 19, 1262–1267 (2022).
    [https://doi.org/10.1038/s41592-022-01589-x](https://doi.org/10.1038/s41592-022-01589-x)

    2. Shi Y, Tabet JS, Milkie DE, Daugird TA, Yang CQ, Giovannucci A, Legant WR.
    *Smart Lattice Light Sheet Microscopy for imaging rare and complex cellular events.*
    bioRxiv. 2023 Mar 9
    [https://doi.org/10.1101/2023.03.07.531517.](https://doi.org/10.1101/2023.03.07.531517)

Obviously, in this case, you can't just create a list of `useq.MDAEvent` objects
and pass them to the acquisition engine, since that list needs to change based
on the results of previous events.