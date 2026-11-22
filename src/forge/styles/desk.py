"""desk — friendly desk gadgets: warm white block, ribbed ends, one orange control. See desk.md."""

from forge.styles import Style

STYLE = Style(
    name="desk",
    intent="Friendly desk gadgets: a warm white block on its own base, ribbed ends, one orange control.",
    fits=("desk devices", "clocks and status displays", "speakers", "chargers and docks"),
    inspired_by=(
        "https://www.ulanzi.com/products/tc002-pixbar-smart-pixel-clock-ii",
        "https://en.wikipedia.org/wiki/Dieter_Rams",
        "https://teenage.engineering/products/ep-133",
    ),
    corner_r=1.6,
    top_edge="fillet",
    top_edge_size=0.8,
    bed_chamfer=0.4,
    wall=2.0,
    floor=1.6,
    grid=5.0,
    grille="holes",
    grille_size=1.6,
    grille_pitch=3.2,
    slot_len=0.0,
    panel_recess=0.0,
    text_font="IBMPlexSans-SemiBold.ttf",
    text_size=0.0,
    text_depth=0.0,
    text_case="as-is",
    body_color="PLA Matte Ivory White",
    preview_color="#ece9e2",
    accent="PLA Matte Mandarin Orange",
    rib_width=0.8,
    rib_pitch=2.0,
    rib_depth=0.6,
    grille_depth=0.8,
)
