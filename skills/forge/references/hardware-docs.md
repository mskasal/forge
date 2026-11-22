# Project Hardware Documentation & Shared Component Library

## Per-project `hardware/` layout

```text
<project>/hardware/
├── HARDWARE.md              # project card: purpose, parts table, design language, constraints
├── components.md            # BOM: make/model, links, sourced dimensions
└── parts/<part>/
    ├── SPEC.md              # behavior, layout, assembly, acceptance criteria, print history
    ├── params.py            # ONLY dimensions, clearances, assumptions, validate_params()
    └── <part>.py            # ONLY Build123d geometry importing params.py + forge.* helpers
```

## Rules
1. **Read first:** search for `hardware/HARDWARE.md` from git root before asking questions. Never re-ask sourced facts.
2. **Missing docs:** offer `forge init --part <name>` (for a tiny one-off like a single hook, ask whether to skip docs).
3. **No duplicated numbers:** keep real-object measurements in `components.md` (or `forge.components`) and `params.py` with source comments. Do not copy dimensions into `SPEC.md` prose.
4. **No versioned copy-paste files:** never create `part_v5.py`, `part_v6.py`, `part_v7.py` side by side. Git and Forge Hub already version every revision.
5. **Status lifecycle:** `draft → approved → designed → printed vN → verified`. No geometry code while `draft`. Record every real print result in `SPEC.md`.
6. **Shared library (`forge.components`):** reusable measured or datasheet-verified components live under `src/forge/components/<slug>.py` using `forge.dim.Dim(value, "measured YYYY-MM-DD" | "datasheet: <url>")`. Run `forge components` to list and validate.
