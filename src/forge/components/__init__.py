"""Shared real-component dimensional library.

Each component is a module under `forge.components.<slug>` containing source-tracked
`Dim` constants and an optional `body() -> Part` envelope resting on Z=0, centred in XY.
Run `forge components` to list and validate all modules.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from forge.dim import Dim


def all_components() -> dict[str, ModuleType]:
    mods: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        mods[info.name] = importlib.import_module(f"{__name__}.{info.name}")
    return mods


def dims(module: ModuleType) -> dict[str, Dim]:
    return {k: v for k, v in vars(module).items() if k.isupper() and isinstance(v, Dim)}


def validate(module: ModuleType) -> list[str]:
    name = module.__name__.rsplit(".", 1)[-1]
    problems: list[str] = []
    if not isinstance(getattr(module, "NAME", None), str):
        problems.append(f"{name}: NAME is missing")
    for k, v in vars(module).items():
        if k.isupper() and isinstance(v, (int, float)) and not isinstance(v, (bool, Dim)):
            problems.append(f"{name}.{k} = {v}: unsourced number (use Dim)")
    if not dims(module):
        problems.append(f"{name}: no Dim measurements defined")
    body = getattr(module, "body", None)
    if body is not None:
        try:
            shape = body()
            if not shape.is_valid or len(shape.solids()) != 1:
                problems.append(f"{name}.body(): must return one valid solid")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{name}.body() raised: {e}")
    return problems


def print_catalog() -> int:
    mods = all_components()
    if not mods:
        print("Component library is empty.")
        return 0
    problems: list[str] = []
    for name, mod in sorted(mods.items()):
        print(f"{name}: {getattr(mod, 'NAME', '?')}")
        for k, d in dims(mod).items():
            print(f"    {k} = {float(d)} mm  ({d.source})")
        problems += validate(mod)
    for p in problems:
        print(f"PROBLEM: {p}")
    return 1 if problems else 0
