"""Functions defined in this module are called by MkDocs at various points
during the build process.

See: https://www.mkdocs.org/dev-guide/plugins/#events
for the various events that can be hooked into.

For example, we use the `on_pre_build` event to generate the markdown table for the
CMMCorePlus API page.

"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.pages import Page

HAS_RUN = False  # sentinel to prevent loop on mkdocs serve
CORE_API_TABLE = "{{ CMMCorePlus_API_Table }}"
PLUS_MEMBERS = "{{ CMMCorePlus_Members }}"
CORE_MEMBERS = "{{ CMMCore_Members }}"
CLI_LOGS = "{{ CLI_Logs }}"

PLUS_SVG = (
    '<span class="twemoji">'
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path d="M20 14h-6v6h-4v-6H4v-4h6V4h4v6h6v4Z"></path></svg>'
    "</span>"
)


def on_page_content(html: str, page: "Page", config: "MkDocsConfig", files) -> str:
    """Called after the Markdown text is rendered to HTML.

    (but before being passed to a template) and can be used to alter the HTML body
    of the page."""
    # add a plus icons everywhere the bolded text "Override" appears
    # doing this here keeps the source-code docs more readable
    override = "<strong>Why Override?</strong>"
    return html.replace(override, PLUS_SVG + override + "<br/>")


def on_page_markdown(md: str, page: "Page", config: "MkDocsConfig", files) -> str:
    """Called after the page's markdown is loaded from file.

    can be used to alter the Markdown source text.
    """
    if CLI_LOGS in md:
        md = md.replace(CLI_LOGS, _cli_logs_help())
    if CORE_API_TABLE in md:
        md = md.replace(CORE_API_TABLE, _build_table())
    if PLUS_MEMBERS in md or CORE_MEMBERS in md:
        base_members, plus_members = _get_core_and_plus_members()
        bl = ",".join(sorted(base_members))
        base_lines = f"::: pymmcore.CMMCore\n\toptions:\n\t\tmembers: [{bl}]"
        pl = ",".join(sorted(plus_members))
        plus_lines = f"::: pymmcore_plus.CMMCorePlus\n\toptions:\n\t\tmembers: [{pl}]"
        md = md.replace(CORE_MEMBERS, base_lines)
        md = md.replace(PLUS_MEMBERS, plus_lines)

    return md


def _get_core_and_plus_members() -> tuple[set, set]:
    """Return member names found only in CMMCore and those in CMMCorePlus."""
    from pymmcore import CMMCore
    from pymmcore_plus import CMMCorePlus

    base_names = {x for x in CMMCore.__dict__ if not x.startswith("_")}
    plus_names = {x for x in CMMCorePlus.__dict__ if not x.startswith("_")}
    plus_only_names = plus_names - base_names
    base_only_names = base_names - plus_names
    overridden_names = base_names & plus_names

    return base_only_names, plus_only_names | overridden_names


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


def _cli_logs_help() -> str:
    import os
    import subprocess

    env = os.environ.copy()
    env["COLUMNS"] = "76"
    out = subprocess.check_output(["mmcore", "logs", "--help"], env=env)
    return f"```bash\n$ mmcore logs --help\n{out.decode()}\n```"
