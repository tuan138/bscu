"""
Turning canvas geometry into drawable batches (UX-9a, UIUX 1.1).

The canvas, the seam overlay and the relief preview all draw through this, which
is the point: three features that grew their own drawing code would disagree
about line width and units within a week.

Everything is in millimetres, because that is the space the user draws in and
the space a cutter reads. The conversion to the scene's metres happens once, in
:func:`bscu.draw.canvas_2d.to_scene`, at the last moment before the GPU.
"""

from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np

from bscu.core.geom2d import Arc, Line

#: How finely an arc is sampled. Chosen so a quarter circle of a 100 mm part
#: comes out smooth without pushing thousands of points at the GPU.
ARC_STEPS = 32

COLOUR = (0.9, 0.9, 0.9, 1.0)
WIDTH_PX = 2.0

#: A line thinner than this in screen pixels is not worth drawing. It lives here
#: rather than in the overlay because the rule belongs to a drawn line, not to
#: any one feature's use of it.
MIN_WIDTH_PX = 2.0


@dataclass
class Batch:
    """A run of points to draw, all of it in one call.

    The one batch type in the product. The seam overlay and the canvas both
    produce these, so there is a single answer to how thick a line is and what
    a hidden thing looks like.
    """

    points: np.ndarray
    colour: Tuple[float, float, float, float] = COLOUR
    width_px: float = WIDTH_PX
    label: str = ""

    def __len__(self) -> int:
        """How many edges this batch holds; a line batch is two points per edge."""
        return int(np.asarray(self.points).shape[0] // 2)


@dataclass
class CanvasBatch(Batch):
    """A batch that came from canvas geometry.

    Straight runs and sampled curves cannot share one draw call - a curve whose
    points are re-read as edges gains a phantom corner at every point - so the
    kind is carried on the batch rather than assumed by the caller.
    """

    sampled: bool = False

    def extend(self, more) -> "CanvasBatch":
        """Append more points, keeping the run a single draw call."""
        addition = np.asarray(more, dtype=np.float64).reshape(-1, 2)
        if addition.shape[0] < 2:
            return self
        self.points = np.vstack([self.points, addition])
        return self

    def is_empty(self) -> bool:
        return self.points.shape[0] < 2


def from_shapes(shapes: Sequence, colour=COLOUR, width_px: float = WIDTH_PX
                ) -> CanvasBatch:
    """Turn a list of canvas geometry into one drawable run.

    Arcs are sampled and straight runs are not, and the batch says which it
    holds, so a caller can put the two in separate batches rather than risk a
    sampled curve being drawn as if every point were a corner.
    """
    batch = CanvasBatch(np.zeros((0, 2), dtype=np.float64), colour, width_px)
    for shape in shapes:
        run = _points_of(shape)
        if run is None or len(run) < 2:
            continue
        if batch.is_empty():
            # Keyword, not positional: the base class puts label before this.
            batch = CanvasBatch(run, colour, width_px, sampled=_is_curve(shape))
        elif _is_curve(shape) == batch.sampled:
            batch.points = np.vstack([batch.points, run])
        else:
            break
    return batch


def batches_for(shape_groups: Sequence, colour=COLOUR, width_px: float = WIDTH_PX
                ) -> List[CanvasBatch]:
    """One batch per group, so groups with different kinds stay apart."""
    return [from_shapes(group, colour, width_px) for group in shape_groups]


def _points_of(shape) -> np.ndarray:
    if isinstance(shape, Line):
        span = shape.length
        if span <= 0.0:
            return None
        return np.asarray([shape.start, shape.end], dtype=np.float64)
    if isinstance(shape, Arc):
        if shape.radius <= 0.0:
            return None
        return np.asarray(shape.sample(ARC_STEPS), dtype=np.float64)
    points = getattr(shape, "points", None)
    if points is None:
        return None
    data = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    return data if len(data) >= 2 else None


def _is_curve(shape) -> bool:
    return isinstance(shape, Arc)


__all__ = ("ARC_STEPS", "COLOUR", "WIDTH_PX", "CanvasBatch", "batches_for",
           "from_shapes")
