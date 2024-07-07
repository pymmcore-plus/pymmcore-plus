# Metadata Schema

This page defines the schema for the metadata `dicts` emitted during the
course of an [Multi-dimensional Acquisition](./guides/mda_engine.md) (MDA).

These are not classes (and should not be imported outside of a
[`typing.TYPE_CHECKING`][] clause), but rather are [`typing.TypedDict`][]
definitions that outline the structure of objects that are passed to the
[`sequenceStarted`][pymmcore_plus.mda.events.PMDASignaler.sequenceStarted] and
[`frameReady`][pymmcore_plus.mda.events.PMDASignaler.frameReady] callbacks in an
MDA.  One use case for these definitions is to provide type hints for the
arguments to these callbacks, which is both handy for looking up the structure
of the metadata and for static type checking.

![metadata hints](./images/meta_hints.png)

## Primary Metadata Types

:::pymmcore_plus.metadata.SummaryMetaV1
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.FrameMetaV1
    options:
        heading_level: 3
        members: []

------------

## Supporting Types

:::pymmcore_plus.metadata.DeviceInfo
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.SystemInfo
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.ImageInfo
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.ConfigGroup
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.ConfigPreset
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.PixelSizeConfigPreset
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.PropertyInfo
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.PropertyValue
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.Position
    options:
        heading_level: 3
        members: []

:::pymmcore_plus.metadata.StagePosition
    options:
        heading_level: 3
        members: []

------------

## Functions

In most cases, the metadata dicts described above will be received as an
argument to either the
[`sequenceStarted`][pymmcore_plus.mda.events.PMDASignaler.sequenceStarted] or
[`frameReady`][pymmcore_plus.mda.events.PMDASignaler.frameReady] callbacks in an
MDA. However, they can also be generated with the following functions.

:::pymmcore_plus.metadata.summary_metadata
    options:
        show_source: true
        heading_level: 3

:::pymmcore_plus.metadata.frame_metadata
    options:
        show_source: true
        heading_level: 3
