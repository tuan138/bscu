"""
Per-stock design storage (UX-2, UIUX K2).

The design lives in the stock object's own datablock so Undo, Redo and saving
are Blender's problem, not ours. Only durable state is stored: the ID counter
and the named design elements. Everything derivable (cache, preview, computed
regions) stays in RAM by design.

The ID counter is a per-object allocator that lives as long as the session, not
per store instance. A fresh :class:`DesignStore` over the same stock reuses that
allocator, which is what makes the non-reuse rule hold across Undo: Undo may
rewind the number stored in the datablock, but the live allocator refuses to go
below anything it has already issued.
"""

from typing import Dict

from ..core.ids import IdAllocator

DESIGN_PROPERTY = "bscu_design"
NEXT_ID_KEY = "bscu_next_id"

# Keyed by the stock's datablock name so the mapping survives Undo, which swaps
# Python object wrappers but keeps names, and dies with a file load that renames.
_ALLOCATORS: Dict[str, IdAllocator] = {}


def _initialise(obj) -> None:
    """Give a stock its design slot the first time it is used."""
    if NEXT_ID_KEY not in obj:
        obj[NEXT_ID_KEY] = 0
        obj[DESIGN_PROPERTY] = {}


def ensure_design(obj) -> None:
    """Create the design slot if missing; safe to call on any Mesh."""
    if obj is None or obj.type != "MESH":
        return
    _initialise(obj)


def allocator_for(obj) -> IdAllocator:
    """The session-lifetime ID allocator belonging to this stock."""
    _initialise(obj)
    key = obj.name
    allocator = _ALLOCATORS.get(key)
    if allocator is None:
        allocator = IdAllocator(int(obj.get(NEXT_ID_KEY, 0)))
        _ALLOCATORS[key] = allocator
    return allocator


def forget(obj) -> None:
    """Drop a stock's allocator; the next access re-seeds from the datablock."""
    _ALLOCATORS.pop(obj.name, None)


def forget_all() -> None:
    """Drop every allocator, used when the file is replaced or the add-on unloads."""
    _ALLOCATORS.clear()


class DesignStore:
    """Durable design state for one stock object."""

    def __init__(self, obj) -> None:
        if obj is None or obj.type != "MESH":
            kind = "None" if obj is None else obj.type
            raise ValueError(f"Design store needs a Mesh object, got {kind}")
        self._obj = obj
        self._allocator = allocator_for(obj)

    @property
    def object(self):
        return self._obj

    @property
    def high_water(self) -> int:
        return self._allocator.high_water

    @property
    def issued(self) -> frozenset:
        return self._allocator.issued

    def next_id(self) -> int:
        """Allocate and persist the next design ID."""
        design_id = self._allocator.next_id()
        self._obj[NEXT_ID_KEY] = design_id
        return design_id

    def refresh(self) -> None:
        """Re-read the stored counter after Undo, Redo or a file load.

        A rewound counter is adopted only if it is higher, which is exactly the
        non-reuse rule: the allocator refuses to go backwards.
        """
        self._allocator.restore_high_water(int(self._obj.get(NEXT_ID_KEY, 0)))
