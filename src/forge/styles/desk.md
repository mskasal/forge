# desk

Friendly desk gadgets: a warm white block that sits on its own base, ribbed ends, one orange
control. Calm like `quiet`, a bit more playful like `instrument`.
Inspired by the Ulanzi TC002 Pixbar Pixel Clock II (in-house Ulanzi design; no named designer
found), which itself sits in the Braun / Teenage Engineering lineage.

**Use for:** devices that live on a desk — clocks, status displays, small speakers, docks.
**Not for:** handheld tools (→ `instrument`), wall devices that should disappear (→ `quiet`),
holders and boxes (→ `plain`).

## Principles

1. Two parts: a simple **body** and a separate **base** it sits on. The base reads as a
   plinth; feet, cable exit and connector live there, not on the body.
2. Texture comes from geometry: ribbed end faces and one long dot pattern. No decoration
   beyond these two.
3. The pattern is bigger than the need: a dot row runs the full length of a face, but only
   the few holes that do a job (speaker, mic, air) go through.
4. One control is the hero: a single orange knob or button, larger than you'd expect.
5. No text on visible faces.

## Form

- Rectangular block, soft vertical corners (R1.6), small top fillet (0.8), bed chamfer 0.4.
- Flush faces on a 5 mm grid.
- **Ribs** on both short end faces: vertical grooves 0.8 wide, 2.0 pitch, 0.6 deep
  (`ribs()`), with a plain margin around them. Grooves run along Z when printed.
- **Base:** separate part, slightly smaller than the body footprint so it reads as a shadow
  line; pockets for bought rubber feet (measure the feet first).

## Interface

- **Dot pattern:** round holes Ø1.6 on a 3.2 mm grid, one or two rows along the full length
  of the back or top. Blind (0.8 deep) by default; through-holes only where needed, in a
  small cluster (e.g. 2×3 for a speaker) inside the pattern.
- The hero control sits on the top face near one end; everything else is secondary
  (dark, flush or recessed).

## Graphics

- None on visible faces. Regulatory or model text, if ever needed, goes on the base underside.

## Colour, material, finish

- Body: PLA Matte Ivory White (or any matte neutral). Accent: PLA Matte Mandarin Orange (separate part, hero control only).
- Base material decided per project: Matte Black, translucent PETG (frosted, not clear) or a
  bought laser-cut acrylic plate. Clear PLA does not print clear.

## Do / don't

- Do: ribbed ends, one long dot row, one orange control, a separate base.
- Don't: text on the body, more than one accent, ribs on every face, holes that only look
  functional by being through (keep decorative dots blind).
- Tripod insert (1/4") and magnetic connector: part of the look, but **untested** — wait for
  a heat-set insert test print.

## References

- https://www.ulanzi.com/products/tc002-pixbar-smart-pixel-clock-ii
- https://en.wikipedia.org/wiki/Dieter_Rams
- https://teenage.engineering/products/ep-133
