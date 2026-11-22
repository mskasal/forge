"""{{part}} — {{project}}.

Spec: SPEC.md | Parameters: params.py | Components: ../../components.md

Fast check (no STEP/STL/PNG):  forge run hardware/parts/{{part}}/{{part}}.py --fast --json
Full check (exports + PNG):    forge run hardware/parts/{{part}}/{{part}}.py
Preview upload (no slicing):   forge push {{forge_name}} --preview -m "what changed"
Print-ready upload (sliced):   forge push {{forge_name}} --plate textured -m "what changed"
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from build123d import *  # noqa: F403

from forge.check import check


def _load_params():
    path = Path(__file__).with_name("params.py")
    spec = importlib.util.spec_from_file_location(f"_forge_params_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_params()


def build() -> dict[str, Part]:
    P.validate_params()
    raise SystemExit("Spec is not approved yet: clarify SPEC.md first, then write the model.")


if __name__ == "__main__":
    parts = build()
    check(
        parts,
        name="{{forge_name}}",
        params_file=Path(__file__).with_name("params.py"),
        assumptions=P.ASSUMPTIONS,
    )
