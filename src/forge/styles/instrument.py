"""instrument — compact handheld tools that look like lab instruments. See instrument.md."""

from forge.styles import Style

STYLE = Style(
    name="instrument",
    intent="Compact, honest little instruments: flat slabs, tight grid, everything labelled.",
    fits=("handheld tools", "controllers", "gadgets with buttons and ports", "desk instruments"),
    inspired_by=(
        "https://teenage.engineering/products/ep-133",
        "https://teenage.engineering/products/ob-4",
    ),
    corner_r=0.8,
    top_edge="chamfer",
    top_edge_size=0.4,
    bed_chamfer=0.4,
    wall=2.0,
    floor=1.6,
    grid=2.5,
    grille="holes",
    grille_size=2.0,
    grille_pitch=3.5,
    slot_len=0.0,
    panel_recess=0.6,
    text_font="IBMPlexMono-SemiBold.ttf",
    text_size=8.0,
    text_depth=0.6,
    text_case="upper",
    body_color="PLA Matte Black",
    preview_color="#2b2b2b",
    accent="PLA Matte Red",
)
