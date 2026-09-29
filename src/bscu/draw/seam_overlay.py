"""
Drawing seams and preview state in the viewport (UX-7, UIUX 3.5).

What gets drawn is kept separate from how it is drawn, so the part that
decides *what the user should see* is testable without a GPU, and the draw
handler stays a thin layer over it.

Three rules from the spec shape this:

* The hidden part has its own look. Drawing an occluded seam as if it were in
  front tells the user they can click something they cannot see.
* Hiding a chart is for looking, not for deleting. Nothing here touches the
  mesh or the design region.
* A preview that is not current says so. An out-of-date picture with no label
  is worse than no picture, because it looks like an answer.

Blender is imported inside the functions that need it rather than at the top of
the module. Everything above the draw callback is plain numpy, so the decisions
about what to show can be checked without a viewport.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

MM_PER_METRE = 1000.0

#: The four palettes the spec asks for, as RGBA in 0..1.
PALETTES: Dict[str, Tuple[Tuple[float, float, float, float], ...]] = {
    "safe": ((0.16, 0.70, 0.31, 1.0), (0.16, 0.70, 0.31, 0.28)),
    "stretch": ((0.86, 0.20, 0.20, 1.0), (0.16, 0.42, 0.86, 1.0)),
    "density": ((0.95, 0.70, 0.13, 1.0), (0.55, 0.20, 0.62, 1.0)),
    "height": ((0.10, 0.55, 0.80, 1.0), (0.85, 0.25, 0.45, 1.0)),
}

#: A seam thinner than this in screen pixels is not worth drawing.
MIN_WIDTH_PX = 2.0


@dataclass
class Batch:
    """A run of line segments sharing one colour and width."""

    points: np.ndarray
    colour: Tuple[float, float, float, float]
    width_px: float
    label: str = ""

    def __len__(self) -> int:
        """How many edges this batch holds; a line batch is two points per edge."""
        return int(self.points.shape[0] // 2)


@dataclass
class OverlayState:
    """What the overlay is showing, and how honestly."""

    seam_mm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2, 3)))
    hidden_edges: set = field(default_factory=set)
    """Which seam edges are behind something. The overlay has edges, not the
    vertices they join: hiding is decided upstream, by chart, and what arrives
    here is which edges the user cannot see through."""
    candidate_mm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2, 3)))
    preview_current: bool = True
    preview_label: str = ""
    palette: str = "safe"
    width_px: float = 4.0
    show_hidden: bool = True

    def label_for_preview(self) -> str:
        """The text that goes with the preview, or nothing when it is current."""
        if self.preview_current:
            return ""
        return self.preview_label or "Preview, not up to date"


def seam_points_mm(state: OverlayState) -> np.ndarray:
    """Seam edges as a flat (N, 2, 3) array in millimetres."""
    return np.asarray(state.seam_mm, dtype=np.float64).reshape(-1, 2, 3)


def visible_seams(state: OverlayState) -> np.ndarray:
    """The seam edges that are not behind anything."""
    return seam_points_mm(state)[_shown_mask(state)]


def _shown_mask(state: OverlayState) -> np.ndarray:
    edges = seam_points_mm(state)
    mask = np.ones(len(edges), dtype=bool)
    for index in state.hidden_edges:
        if 0 <= int(index) < len(edges):
            mask[int(index)] = False
    return mask


def hidden_seams(state: OverlayState) -> np.ndarray:
    """The seam edges behind something, drawn in their own fainter look."""
    edges = seam_points_mm(state)
    return edges[~_shown_mask(state)]


def build_batches(state: OverlayState) -> List[Batch]:
    """Everything the overlay would draw, as batches.

    Returned rather than drawn so the decisions can be checked: which edges are
    shown, which colour a palette gives them, and whether the preview is marked
    as not current.
    """
    colours = PALETTES.get(state.palette) or PALETTES["safe"]
    width = max(float(state.width_px), MIN_WIDTH_PX)
    batches: List[Batch] = []

    shown = visible_seams(state)
    if shown.size:
        batches.append(Batch(_flatten(shown), colours[0], width))

    if state.show_hidden:
        hidden = hidden_seams(state)
        if hidden.size:
            batches.append(Batch(_flatten(hidden), colours[1],
                                 max(width - 1.0, 1.0)))

    candidate = np.asarray(state.candidate_mm, dtype=np.float64).reshape(-1, 2, 3)
    if candidate.size:
        batches.append(Batch(_flatten(candidate), colours[0], width + 1.0,
                             state.label_for_preview()))
    return batches


def label_positions(state: OverlayState) -> List[Tuple[str, np.ndarray]]:
    """Where the overlay's text goes, in millimetres."""
    placed = []
    note = state.label_for_preview()
    if note:
        placed.append((note, np.zeros(3, dtype=np.float64)))
    return placed


def _flatten(edges: np.ndarray) -> np.ndarray:
    """A run of segments as the (2N, 3) point list a batch needs."""
    return np.asarray(edges, dtype=np.float64).reshape(-1, 3)


#: The state the handler draws. Set by the panel, read by the draw call.
_state = OverlayState()

#: Attached draw handlers, so install and shutdown are symmetrical.
_HANDLERS: List[object] = []


def state() -> OverlayState:
    """The overlay's current state, for whatever wants to change it."""
    return _state


def set_state(new: OverlayState) -> None:
    """Replace the state and ask for a redraw, which is the whole update path."""
    global _state
    _state = new
    redraw()


def _draw() -> None:
    """Blender's draw callback: turn the batches into pixels."""
    import bpy

    region = bpy.context.region
    if region is None or _state.width_px <= 0.0:
        return
    batches = build_batches(_state)
    if not batches:
        return

    import gpu
    from gpu_extras.batch import batch_for_shader

    shader = _shader()
    if shader is None:
        return
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(1.0)
    with gpu.matrix.push_pop():
        for group in batches:
            gpu.shader.uniform_float("colour", group.colour)
            gpu.shader.uniform_float("width", max(group.width_px, 1.0))
            handle = batch_for_shader(shader, "LINES",
                                      {"pos": _to_clip(group.points)})
            handle.draw(shader)
    gpu.state.blend_set("NONE")


def _shader():
    """The flat-colour line shader, built once and kept."""
    global _shader_handle
    if _shader_handle is not None:
        return _shader_handle
    try:
        import gpu
    except ImportError:
        return None
    _shader_handle = gpu.shader.from_builtin("UNIFORM_COLOR")
    del gpu
    return _shader_handle


_shader_handle = None


def _to_clip(points_mm: np.ndarray) -> np.ndarray:
    """Millimetres to the clip space the GPU wants.

    The view matrix turns millimetres into the region; the projection is left to
    the shader's own uniform, so only the transform is applied here.
    """
    import bpy

    data = np.asarray(points_mm, dtype=np.float64).reshape(-1, 3) / MM_PER_METRE
    view = np.asarray(bpy.context.region.data.view_matrix.inverted(), dtype=np.float64)
    homogeneous = np.column_stack([data, np.ones(len(data))])
    camera = homogeneous @ view.T
    return np.ascontiguousarray(camera[:, :3].astype(np.float32))


def install() -> bool:
    """Attach the draw handler to every 3D view, once.

    Returns whether it was attached. Importing the module outside a viewport -
    a headless run, a test - is not an error; there is simply nothing to draw on.
    """
    import bpy

    for handler in list(_HANDLERS):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW", "POST_VIEW")
        except (ValueError, ReferenceError):
            continue
    _HANDLERS.clear()
    if bpy.app.background:
        return False
    _HANDLERS.append(_draw)
    bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW")
    return True


def redraw() -> None:
    """Ask every 3D view to paint again."""
    try:
        import bpy
    except ImportError:
        return
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                region.tag_redraw()


def shutdown() -> None:
    """Remove the draw handler, and say so if it had already gone."""
    import bpy

    for handler in list(_HANDLERS):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handler, "WINDOW", "POST_VIEW")
        except (ValueError, ReferenceError):
            continue
    _HANDLERS.clear()


__all__ = ("Batch", "MIN_WIDTH_PX", "OverlayState", "PALETTES",
           "build_batches", "hidden_seams", "install", "label_positions",
           "redraw", "seam_points_mm", "set_state", "shutdown", "state",
           "visible_seams")
