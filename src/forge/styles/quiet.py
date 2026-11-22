"""quiet — calm, long-lived objects for the home. See quiet.md."""

from forge.styles import Style

STYLE = Style(
    name="quiet",
    intent="Calm, durable objects: few elements, soft but precise edges, nothing extra.",
    fits=("wall and desk devices", "displays", "chargers", "home electronics", "enclosures"),
    inspired_by=(
        "https://www.vitsoe.com/us/about/good-design",
        "https://en.wikipedia.org/wiki/Dieter_Rams",
    ),
    corner_r=3.0,
    top_edge="fillet",
    top_edge_size=1.0,
    bed_chamfer=0.5,
    wall=2.0,
    floor=1.6,
    grid=5.0,
    grille="slots",
    grille_size=1.6,
    grille_pitch=3.2,
    slot_len=20.0,
    panel_recess=0.0,
    text_font="IBMPlexSans-SemiBold.ttf",
    text_size=8.0,
    text_depth=0.6,
    text_case="lower",
    body_color="PLA Matte Black",
    preview_color="#2b2b2b",
    accent="PLA Matte Red",
)
