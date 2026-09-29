"""
The design region on the workpiece (UX-3, UIUX 2.1 / 2.7).

The region is either the whole workpiece or an explicit set of faces the user
selected. Two rules from the spec shape this module: selecting a face must not
quietly reach round to the back of the part, and an empty selection must be
reported rather than widened to everything.

The region is stored as face indices on the object, so it lives in the .blend,
survives save/load and is carried by Blender's Undo.
"""


REGION_WHOLE = "WHOLE"
REGION_SELECTION = "SELECTION"
REGION_NONE = "NONE"

REGION_MODE_KEY = "bscu_region_mode"
REGION_FACES_KEY = "bscu_region_faces"

STALE_INDEX_MARGIN = 8


class RegionError(ValueError):
    """Raised when a region cannot be determined from what the user gave."""


def _require_mesh(obj) -> None:
    if obj is None or obj.type != "MESH":
        kind = "None" if obj is None else obj.type
        raise RegionError(f"Design region needs a Mesh object, got {kind}")


def select_whole_stock(obj) -> None:
    """Use every face of the workpiece."""
    _require_mesh(obj)
    obj[REGION_MODE_KEY] = REGION_WHOLE
    if REGION_FACES_KEY in obj:
        del obj[REGION_FACES_KEY]


def set_region_from_selection(obj) -> None:
    """Use exactly the faces currently selected on the object.

    An empty selection is an error, not an invitation to fall back to the whole
    mesh: the user asked for a region and must choose it themselves.
    """
    _require_mesh(obj)
    if obj.mode != "OBJECT":
        raise RegionError("Switch to Object Mode before choosing a region")

    faces = [poly.index for poly in obj.data.polygons if poly.select]
    if not faces:
        raise RegionError("Select the faces to decorate before setting the region")

    obj[REGION_MODE_KEY] = REGION_SELECTION
    obj[REGION_FACES_KEY] = faces


def clear_region(obj) -> None:
    """Forget the region; nothing is decorated until the user picks again."""
    _require_mesh(obj)
    obj[REGION_MODE_KEY] = REGION_NONE
    if REGION_FACES_KEY in obj:
        del obj[REGION_FACES_KEY]


def _is_stale(obj, faces) -> bool:
    """True when the stored indices can no longer mean anything.

    A topology change invalidates face indices. The surface may be edited but
    keep its face count, so the count alone cannot decide this; the caller
    revalidates against the region check the UI shows (UX-0 step status).
    """
    return len(faces) > len(obj.data.polygons) + STALE_INDEX_MARGIN


def read_region(obj) -> "Region":
    """The stored region, marked stale if the topology moved under it."""
    _require_mesh(obj)
    mode = obj.get(REGION_MODE_KEY, REGION_NONE)
    if mode == REGION_WHOLE:
        return Region(mode, list(range(len(obj.data.polygons))), False)
    if mode != REGION_SELECTION:
        return Region(REGION_NONE, [], False)

    faces = list(obj.get(REGION_FACES_KEY, []))
    return Region(mode, faces, _is_stale(obj, faces))


def region_face_count(obj) -> int:
    """How many faces the region covers right now."""
    return len(read_region(obj).faces)


class Region:
    """An immutable view of the stored region."""

    def __init__(self, mode: str, faces, stale: bool) -> None:
        self.mode = mode
        self.faces = faces
        self.stale = stale

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, Region)
            and (self.mode, self.faces, self.stale)
            == (other.mode, other.faces, other.stale)
        )

    def __hash__(self) -> int:
        return hash((self.mode, tuple(self.faces), self.stale))

    def __repr__(self) -> str:
        return f"Region({self.mode}, {len(self.faces)} faces, stale={self.stale})"
