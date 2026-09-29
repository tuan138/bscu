"""
Bridge from Blender scene state to the pure StepFacts snapshot (UX-0).

Reads only. Nothing here mutates the mesh, the seam set or the UV map, so
drawing a panel can never change the document (UIUX mục 2.2).
"""

import bpy

from ..core.workflow import StepFacts

# UV map the pipeline owns; a user-authored map never counts as accepted.
BSCU_UV_ACTIVE = "BSCU_UV_Active"


def active_stock(context) -> bpy.types.Object | None:
    """Return the object currently acting as the workpiece, if any."""
    return context.active_object


def has_bscu_uv(obj) -> bool:
    """True when the object carries the pipeline's own approved UV map."""
    if obj is None or obj.type != "MESH":
        return False
    return obj.data.uv_layers.get(BSCU_UV_ACTIVE) is not None


def collect_step_facts(context=None) -> StepFacts:
    """Snapshot what is observable in the scene right now.

    Only the stock selection and the presence of the approved UV map are judged
    at UX-0. Seam, layout and pattern gates stay false until the modules that
    produce them (UX-4, UX-8, UX-10) exist, so the step bar never claims work
    that has not happened.
    """
    if context is None:
        context = bpy.context

    obj = active_stock(context)
    has_selection = obj is not None
    is_mesh = has_selection and obj.type == "MESH"

    return StepFacts(
        has_stock=has_selection,
        stock_is_mesh=is_mesh,
        has_uv_active=has_bscu_uv(obj),
        has_approved_layout=False,
        has_pattern=False,
    )
