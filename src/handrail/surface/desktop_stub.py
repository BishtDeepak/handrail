"""Placeholder for a Windows UI Automation surface (designed, not built).

The artifact needs no change for desktop: ``Target.frame`` becomes a window/pane path, roles map
from UIA control types (Button, Edit, DataItem), and names come from the UIA Name property.
"""

from __future__ import annotations


class DesktopSurface:
    def __init__(self, *_: object, **__: object) -> None:
        raise NotImplementedError(
            "Desktop surface is designed but not implemented; see REPORT.md section 4."
        )
