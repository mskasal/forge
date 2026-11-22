"""plain — objects that disappear into daily life. See plain.md."""

from forge.styles import Style

STYLE = Style(
    name="plain",
    intent="Super-normal everyday objects: soft volumes, no text, no decoration.",
    fits=("organisers", "holders", "boxes", "kitchen and bathroom things", "objects without electronics"),
    inspired_by=(
        "https://en.wikipedia.org/wiki/Naoto_Fukasawa",
        "https://en.wikipedia.org/wiki/Muji",
    ),
    corner_r=8.0,
    top_edge="fillet",
    top_edge_size=1.6,
    bed_chamfer=0.5,
    wall=2.4,
    floor=2.0,
    grid=10.0,
    grille="holes",
    grille_size=1.6,
    grille_pitch=4.0,
    slot_len=0.0,
    panel_recess=0.0,
    text_font="IBMPlexSans-SemiBold.ttf",
    text_size=0.0,
    text_depth=0.0,
    text_case="as-is",
    body_color="PLA Matte Black",
    preview_color="#2b2b2b",
)
