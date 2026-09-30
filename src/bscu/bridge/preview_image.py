"""
The relief preview image (UX-10, UIUX 5.4 and D10).

The spec's D10 sets out the two tiers, and this is the part that makes the
cheap one honest. A preview is a *coarse sampling* of the height field, and
its resolution is a sampling artefact that must never be mistaken for a
statement about the surface. So every image says what it was sampled at, and
the numbers derived from it carry the same caveat.

Two rules do most of the work here:

* **The preview comes from the height field, not from the mesh.** Re-reading
  the evaluated mesh would make a coarse preview look like a fine one, and the
  whole point of the cheap tier is that it is cheap.
* **A preview that did not finish is labelled.** Drawing the previous picture
  as though it were the new one is the failure D10 exists to prevent.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ..core.height_field import HeightField

MM_PER_METRE = 1000.0

#: The coarse sampling the cheap tier is allowed to use, in millimetres.
COARSE_STEP_MM = 0.25

#: The fine sampling, for a picture the user is about to cut from.
FINE_STEP_MM = 0.05

#: Millimetres the height is quantised to, per the spec.
HEIGHT_QUANTUM_MM = 0.001


@dataclass
class PreviewImage:
    """A sampled height field, with the sampling it was made at."""

    heights_mm: np.ndarray
    origin_mm: np.ndarray
    step_mm: float
    current: bool = True
    label: str = ""
    issues: List[str] = field(default_factory=list)

    @property
    def shape(self) -> Tuple[int, int]:
        return tuple(self.heights_mm.shape)

    @property
    def max_mm(self) -> float:
        return float(self.heights_mm.max()) if self.heights_mm.size else 0.0

    def sample_at(self, point_mm) -> float:
        """The height at a canvas point, by nearest sample.

        Nearest, not interpolated: a preview is a picture of a field, and
        inventing a smooth value between samples would claim a precision the
        picture does not have.
        """
        offset = (np.asarray(point_mm, dtype=np.float64).ravel()[:2]
                  - self.origin_mm) / max(self.step_mm, 1e-9)
        column = int(round(float(offset[0])))
        row = int(round(float(offset[1])))
        if not (0 <= row < self.heights_mm.shape[0]
                and 0 <= column < self.heights_mm.shape[1]):
            return 0.0
        return float(self.heights_mm[row, column])

    def label_text(self) -> str:
        """What goes under the picture, so its provenance is never a secret.

        The "not up to date" marker is always kept even when a message is
        supplied with it: a message about what is still running is a reason to
        add a warning, not a reason to drop the warning.
        """
        if not self.current:
            message = self.label or "Preview"
            return f"{message} - not up to date"
        if self.step_mm >= COARSE_STEP_MM:
            return f"Sampled every {self.step_mm:g} mm"
        return ""


def sample(field: HeightField, low_mm, high_mm,
           step_mm: float = COARSE_STEP_MM) -> PreviewImage:
    """Sample the field over a rectangle, in millimetres.

    The rectangle is the decorated region, not the whole stock: sampling empty
    stock wastes most of the image and shows the user a large flat nothing.
    """
    low = np.asarray(low_mm, dtype=np.float64).ravel()[:2]
    high = np.asarray(high_mm, dtype=np.float64).ravel()[:2]
    if step_mm <= 0.0:
        raise ValueError(f"a sampling step has to be positive, got {step_mm}")
    if np.any(high < low):
        raise ValueError(f"the region runs backwards: {low} to {high}")

    columns = max(2, int((high[0] - low[0]) / step_mm) + 1)
    rows = max(2, int((high[1] - low[1]) / step_mm) + 1)
    xs = low[0] + np.arange(columns) * step_mm
    ys = low[1] + np.arange(rows) * step_mm
    grid = np.stack(np.meshgrid(xs, ys, indexing="xy"), axis=-1).reshape(-1, 2)
    heights = field.evaluate(grid).reshape(rows, columns)
    return PreviewImage(np.round(heights / HEIGHT_QUANTUM_MM) * HEIGHT_QUANTUM_MM,
                        low, step_mm, True, "")


def preview_of(field: HeightField, low_mm, high_mm,
               fine: bool = False) -> PreviewImage:
    """The two tiers: a coarse one while dragging, a fine one when finished."""
    return sample(field, low_mm, high_mm,
                  FINE_STEP_MM if fine else COARSE_STEP_MM)


def carried_forward(previous: Optional[PreviewImage], label: str) -> PreviewImage:
    """The previous picture, relabelled as not current.

    D10's rule: if the pass has not finished, the old picture stays on screen
    with a label. It is never reissued as though it were the new result.
    """
    if previous is None:
        raise ValueError("there is no earlier picture to carry forward")
    carried = PreviewImage(previous.heights_mm.copy(), previous.origin_mm.copy(),
                           previous.step_mm, False, label, list(previous.issues))
    return carried


def to_image_buffer(preview: PreviewImage):
    """The sampled field as a Blender image, for the material to read.

    A single-channel float image in the field's own units: millimetres. The
    material divides by 1000 on the way in, and the conversion lives there
    rather than being baked in twice.
    """
    import bpy

    height, width = preview.heights_mm.shape
    image = bpy.data.images.new("BSCU_Relief_Preview", width=width, height=height,
                                alpha=False, float_buffer=True)
    pixels = np.empty((height, width, 4), dtype=np.float32)
    pixels[:, :, 0] = preview.heights_mm
    pixels[:, :, 1] = preview.heights_mm
    pixels[:, :, 2] = preview.heights_mm
    pixels[:, :, 3] = 1.0
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    return image


def forget_images() -> None:
    """Drop the preview images BSCU made, on shutdown."""
    import bpy

    for image in list(bpy.data.images):
        if image.name.startswith("BSCU_Relief_Preview"):
            bpy.data.images.remove(image)


__all__ = ("COARSE_STEP_MM", "FINE_STEP_MM", "HEIGHT_QUANTUM_MM", "PreviewImage",
           "carried_forward", "forget_images", "preview_of", "sample",
           "to_image_buffer")
