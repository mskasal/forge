"""Source-tracked measurement float.

    PCB_L = Dim(51.0, "datasheet: https://... p.6")
    USB_H = Dim(3.2, "measured 2026-11-03")

`Dim` subclasses `float` so it passes directly into Build123d calls while refusing
unsourced dimensions.
"""

from __future__ import annotations

import re

_SOURCE_RE = re.compile(r"^(measured \d{4}-\d{2}-\d{2}|datasheet: \S+)")


class Dim(float):
    source: str

    def __new__(cls, value: float, source: str) -> Dim:
        if not isinstance(source, str) or not _SOURCE_RE.match(source):
            raise ValueError(
                f"Invalid dimension source: {source!r}. "
                "Must start with 'measured YYYY-MM-DD' or 'datasheet: <url>'."
            )
        obj = super().__new__(cls, value)
        obj.source = source
        return obj

    def __getnewargs__(self) -> tuple[float, str]:
        return (float(self), self.source)

    def __repr__(self) -> str:
        return f"Dim({float(self)!r}, {self.source!r})"
