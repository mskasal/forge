# Design Languages (`forge.styles`)

Every project uses **one** design language (`forge styles` lists and validates them). Never mix two languages in one project.

| Language | Use for | Look |
| --- | --- | --- |
| `instrument` | handheld tools, controllers, gadgets with buttons/ports | flat slabs, near-sharp edges, 2.5 mm grid, hole grilles, inset panels, UPPERCASE mono labels |
| `quiet` | home devices: wall/desk displays, chargers, enclosures | soft precise edges (R3), flush faces, slot grilles, few lowercase labels |
| `plain` | holders, organisers, boxes, everyday utility items | soft volumes (R8), no text, no decoration |
| `desk` | desk devices: clocks, status displays, speakers, docks | warm white block on separate base, ribbed ends, full-length blind dot row, one orange control, no text |

## Rules
- **Choosing:** if `hardware/HARDWARE.md` has no language set, propose the best match with one reason, wait for confirmation, then write it to `HARDWARE.md` (`forge init --style <name>`).
- **Applying:** import tokens and helpers instead of inventing numbers:
  `from forge.styles import load, shell, grille, label, panel, ribs`.
  Any deviation from the language requires a reason in `SPEC.md`.
- **Priority:** safety > FDM rules (`forge.fdm`) > design language.
- **Text:** engraved in the language's font; never smaller than `text_size` (stroke ≥ 1 mm).
