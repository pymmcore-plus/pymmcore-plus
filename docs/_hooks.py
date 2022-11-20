"""Custom plugin to generate the API reference table for the CMMCorePlus."""
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

HAS_RUN = False  # sentinel to prevent loop on mkdocs serve
CORE_TABLE = "_cmmcore_table.md"
PLUS_MEMBERS = "_cmmcoreplus_members.md"
CORE_MEMBERS = "_cmmcore_members.md"


def on_pre_build(config: "MkDocsConfig") -> None:
    import pymmcore
    import pymmcore_plus

    global HAS_RUN
    if HAS_RUN:
        return

    base_names = set(pymmcore.CMMCore.__dict__)
    plus_names = set(pymmcore_plus.CMMCorePlus.__dict__)
    plus_only_names = plus_names - base_names
    base_only_names = base_names - plus_names
    overridden_names = base_names & plus_names

    base_list = ",".join(sorted([x for x in base_only_names if not x.startswith("_")]))
    lines = [
        "::: pymmcore.CMMCore",
        "    options:",
        f"        members: [{base_list}]",
    ]
    dest = Path(config.docs_dir) / "_includes" / CORE_MEMBERS
    dest.write_text("\n".join(lines))

    plus_list = ",".join(
        sorted([x for x in plus_only_names | overridden_names if not x.startswith("_")])
    )
    lines = [
        "::: pymmcore_plus.CMMCorePlus",
        "    options:",
        f"        members: [{plus_list}]",
    ]
    dest = Path(config.docs_dir) / "_includes" / PLUS_MEMBERS
    dest.write_text("\n".join(lines))

    (Path(config.docs_dir) / "_includes" / CORE_TABLE).write_text(_build_table())
    HAS_RUN = True


def _build_table() -> str:
    """This function builds the markdown table for the CMMCorePlus API page."""
    import griffe
    import pymmcore
    import pymmcore_plus

    core = griffe.load("pymmcore.CMMCore")
    plus = griffe.load("pymmcore_plus.CMMCorePlus")

    base_names = set(pymmcore.CMMCore.__dict__)
    plus_names = set(pymmcore_plus.CMMCorePlus.__dict__)
    all_names = base_names | plus_names
    plus_only_names = plus_names - base_names
    base_only_names = base_names - plus_names
    overridden_names = base_names & plus_names

    header = ["Method", "", "Description"]

    out = "|" + "|".join(header) + "|\n"
    out += "| :-- | :--: | :-- |\n"
    for name in sorted(all_names):
        if name.startswith("_"):
            continue
        icon = ""
        if name in base_only_names:
            icon = ""
        elif name in plus_only_names:
            icon = ":sparkles:"
        elif name in overridden_names:
            icon = ":material-plus-thick:"

        doc = ""
        if name in plus.members:
            if docstring := plus.members[name].docstring:
                doc = docstring.value.splitlines()[0]
        if not doc and name in core.members:
            if docstring := core.members[name].docstring:
                doc = docstring.value.splitlines()[0]

        if name in plus_names:
            link = f"[`{name}`][pymmcore_plus.CMMCorePlus.{name}]"
        elif name in core.members:
            link = f"[`{name}`][pymmcore.CMMCore.{name}]"
        else:
            link = f"`{name}`"

        out += f"| {link} | {icon} | {doc} |\n"
    return out
