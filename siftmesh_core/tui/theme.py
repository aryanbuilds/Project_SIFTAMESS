"""SIFTMesh cockpit themes (Epic O redesign).

Two custom Textual themes registered by the app; the built-in command palette (ctrl+p → "Change
theme") switches between these and Textual's stock themes. The CSS + the content-markup color tokens
(`$primary`, `$accent`, `$success`, …) resolve against whichever theme is active, so the whole
cockpit re-colors with one switch. Forensic palette: cyan=active, amber=focus/files,
green=confirmed, amber-orange=retry/gate, red=rejected, violet=human-review, teal=vitals.
"""

from __future__ import annotations

from textual.theme import Theme

SIFTMESH_DARK = Theme(
    name="siftmesh-dark",
    primary="#56b6c2",  # cyan — active / dispatched / primary borders
    secondary="#c678dd",  # violet — human-review / side accents
    accent="#e5c07b",  # amber — current stage / files / nav
    success="#98c379",  # green — confirmed / accepted
    warning="#d19a66",  # amber-orange — retry / blocked gate
    error="#e06c75",  # red — rejected / error
    foreground="#abb2bf",
    background="#1b1f24",
    surface="#22272e",
    panel="#2c313a",
    boost="#0c3b3b",  # deep teal — the vitals bar
    dark=True,
    variables={
        "footer-key-foreground": "#56b6c2",
        "block-cursor-text-style": "none",
    },
)

SIFTMESH_LIGHT = Theme(
    name="siftmesh-light",
    primary="#0184bc",
    secondary="#a626a4",
    accent="#b06a00",
    success="#50a14f",
    warning="#986801",
    error="#e45649",
    foreground="#383a42",
    background="#fafafa",
    surface="#f0f0f1",
    panel="#e6e6e7",
    boost="#cfeaea",
    dark=False,
    variables={"footer-key-foreground": "#0184bc"},
)

SIFTMESH_THEMES = (SIFTMESH_DARK, SIFTMESH_LIGHT)
DEFAULT_THEME = SIFTMESH_DARK.name
