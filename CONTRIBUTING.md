# Contributing to Forge

Thank you for contributing to Forge!

## Development Setup

```bash
./install.sh
.venv/bin/pytest tests/
.venv/bin/pytest hub/tests/
```

## Architecture Boundaries

- **`src/forge/`** (workstation): Build123d CAD toolkit, validation, slicers, styles, components, CLI.
- **`hub/`** (always-on server): Lightweight FastAPI + web preview + printer registry. **`hub/` must never import `forge`, `build123d`, `OCCT`, or `scipy`** so Raspberry Pi / Docker deployments stay under ~40 MB RAM.
- **Printer safety is non-negotiable:** any printer backend must enforce a strict command allowlist (status + explicitly approved print jobs only) and validate target printer model/nozzle/temperature bounds before dispatching.

## Contributor License Agreement (CLA)

Forge is licensed under **GNU AGPL-3.0**. To keep the option of offering commercial/hosted services or distributing the Apple TV client via the Apple App Store in the future, by submitting a pull request to this repository you agree that:

1. Your contribution is your original work and you have the legal right to submit it.
2. You license your contribution under **AGPL-3.0**, and you additionally grant the project maintainer (Mustafa Samed Kasal) a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, modify, redistribute, and relicense your contribution under alternative open-source or commercial licenses.

## Ownership of Generated Parts

CAD scripts, `params.py`, `SPEC.md`, and exported STEP/STL/3MF/GLB/USDZ files that **you** create using Forge belong 100% to you and are not derivative works of Forge.
