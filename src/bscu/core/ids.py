"""
Design ID allocation (UX-2, UIUX K2).

Pure Python, no bpy. IDs are 64-bit, strictly increasing and never reused.

The counter is monotonic by construction: restoring an older value is a no-op,
never a step backwards. Undo restores the stored counter inside the datablock,
and taking that at face value would reissue IDs that the UV map and the height
field still reference.
"""

# Largest value the 64-bit signed space can hand out.
INT64_MAX = (1 << 63) - 1


class IdAllocator:
    """Monotonic, non-reusing ID source for one stored design."""

    def __init__(self, high_water: int = 0) -> None:
        self._high_water = 0
        self._issued: set = set()
        self.restore_high_water(high_water)

    @property
    def high_water(self) -> int:
        """Largest ID issued or reserved so far."""
        return self._high_water

    @property
    def issued(self) -> frozenset:
        """Every ID ever handed out or reserved, for collision auditing."""
        return frozenset(self._issued)

    def next_id(self) -> int:
        """Hand out the next unused ID."""
        if self._high_water >= INT64_MAX:
            raise OverflowError("design ID space exhausted")
        self._high_water += 1
        self._issued.add(self._high_water)
        return self._high_water

    def reserve(self, design_id: int) -> None:
        """Record an ID that came from elsewhere, such as a loaded file."""
        if design_id > self._high_water:
            self._high_water = design_id
        self._issued.add(design_id)

    def restore_high_water(self, value: int) -> None:
        """Adopt a stored counter, never below what was already issued.

        Called from the Undo/Redo/load handlers: a lower value from the restored
        datablock is deliberately ignored so no ID is ever handed out twice.
        """
        self._high_water = max(self._high_water, max(int(value), 0))
