"""
The 2D canvas drawn in the 3D viewport (UX-9a, UIUX 1.1).

One canvas, shared by everything: the seam tool, the Caro preview and the
relief drawing all put their geometry here rather than each opening its own
view. The spec is explicit that the product is one surface, and a second
overlay would be a second set of rules about line width, visibility and units.

It is drawn on the stock's top face in the top orthographic view, in
millimetres. The unit is the part that would be hardest to notice going wrong:
a canvas in metres looks identical on screen and cuts a part a thousand times
too small, so the conversion lives in one function and is checked by tests.

Hiding a stroke is for looking past it, never for deleting it. The stroke stays
in the design and comes back when it is shown again.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from bscu.draw.batches import COLOUR, WIDTH_PX, CanvasBatch, from_shapes

MM_PER_METRE = 1000.0

#: The one view the canvas is drawn in, per the spec.
CANVAS_VIEW = "ORTHO"


def canvas_plane(z_mm: float = 0.0) -> np.ndarray:
    """The canvas plane in canvas millimetres: the stock's top face."""
    return np.asarray([0.0, 0.0, float(z_mm)], dtype=np.float64)


def to_scene(point_mm) -> np.ndarray:
    """Canvas millimetres into the scene's metres, for the GPU.

    The last conversion before anything is drawn. Everything above this line is
    in millimetres, which is what the user measures and the cutter reads.
    """
    return np.asarray(point_mm, dtype=np.float64).ravel() / MM_PER_METRE


def scene_to_canvas(point) -> np.ndarray:
    """Scene metres back into canvas millimetres."""
    return np.asarray(point, dtype=np.float64).ravel() * MM_PER_METRE


@dataclass
class Canvas:
    """Every stroke on the canvas, in millimetres, by name."""

    strokes: Dict[str, list] = field(default_factory=dict)
    hidden: set = field(default_factory=set)
    z_mm: float = 0.0
    colour: Tuple[float, float, float, float] = COLOUR
    width_px: float = WIDTH_PX

    def add_stroke(self, name: str, shapes: Sequence = ()) -> "Canvas":
        """Add or replace a stroke. Re-adding is how a re-solve lands."""
        self.strokes[name] = list(shapes)
        self.hidden.discard(name)
        return self

    def remove_stroke(self, name: str) -> bool:
        """Take a stroke off the canvas entirely, as one undo step."""
        if name not in self.strokes:
            return False
        del self.strokes[name]
        self.hidden.discard(name)
        return True

    def hide(self, name: str) -> bool:
        """Stop drawing a stroke without removing it from the design."""
        if name not in self.strokes:
            return False
        self.hidden.add(name)
        return True

    def show(self, name: str) -> bool:
        if name not in self.strokes:
            return False
        self.hidden.discard(name)
        return True

    def show_all(self) -> None:
        self.hidden.clear()

    def has_content(self) -> bool:
        return any(len(shapes) for shapes in self.strokes.values())

    def visible(self) -> List[Tuple[str, list]]:
        return [(name, shapes) for name, shapes in self.strokes.items()
                if name not in self.hidden and shapes]

    def to_batches(self) -> List[CanvasBatch]:
        """One batch per visible stroke, so hiding one hides only that one."""
        return [from_shapes(shapes, self.colour, self.width_px)
                for _name, shapes in self.visible()]

    def to_points(self) -> np.ndarray:
        """Every visible point in one array, for bounds and for picking."""
        runs = [batch.points for batch in self.to_batches()]
        if not runs:
            return np.zeros((0, 2), dtype=np.float64)
        return np.vstack(runs)

    def bounds(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """The canvas extent in millimetres, or None when there is nothing on it."""
        points = self.to_points()
        if not points.size:
            return None
        return points.min(axis=0), points.max(axis=0)

    def save_state(self) -> dict:
        """A plain copy, for a panel that wants to restore what it changed."""
        return {
            "strokes": {name: list(shapes) for name, shapes in self.strokes.items()},
            "hidden": set(self.hidden),
            "z_mm": self.z_mm,
        }

    def restore_state(self, saved: dict) -> None:
        self.strokes = {name: list(shapes)
                        for name, shapes in saved.get("strokes", {}).items()}
        self.hidden = set(saved.get("hidden", set()))
        self.z_mm = saved.get("z_mm", self.z_mm)


__all__ = ("CANVAS_VIEW", "Canvas", "canvas_plane", "scene_to_canvas", "to_scene")
