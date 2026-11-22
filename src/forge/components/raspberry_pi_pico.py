"""Raspberry Pi Pico / Pico W board mechanical dimensions (official datasheet)."""

from build123d import Align, Box, Part

from forge.dim import Dim

_DS = "datasheet: https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf"

NAME = "Raspberry Pi Pico / Pico W"
PCB_L = Dim(51.0, _DS)
PCB_W = Dim(21.0, _DS)
PCB_T = Dim(1.0, _DS)
HOLE_D = Dim(2.1, _DS)
HOLE_DX = Dim(11.4, _DS)
HOLE_DY = Dim(47.0, _DS)
USB_OVERHANG = Dim(1.3, _DS)


def body() -> Part:
    """Simplified PCB envelope on Z=0, centred in XY."""
    return Box(PCB_L, PCB_W, PCB_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
