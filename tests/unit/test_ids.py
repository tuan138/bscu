"""Unit tests for the design ID allocator (UX-2, UIUX K2).

K2 is explicit: IDs are 64-bit, increase with the design and are never reused.
Undo restores the stored counter, so the allocator must be able to refuse to go
backwards: the UV map and the height field keep referencing IDs long after the
shape that created them is gone.
"""

import unittest

from bscu.core.ids import INT64_MAX, IdAllocator


class TestIdAllocator(unittest.TestCase):
    def test_first_id_is_one(self):
        self.assertEqual(IdAllocator().next_id(), 1)

    def test_ids_increase_by_one(self):
        allocator = IdAllocator()
        self.assertEqual([allocator.next_id() for _ in range(4)], [1, 2, 3, 4])

    def test_undo_restoring_an_older_counter_never_reuses_ids(self):
        allocator = IdAllocator()
        first = allocator.next_id()
        second = allocator.next_id()
        allocator.restore_high_water(first)
        self.assertGreater(allocator.next_id(), second)

    def test_restoring_a_lower_counter_is_a_no_op(self):
        allocator = IdAllocator()
        for _ in range(3):
            allocator.next_id()
        allocator.restore_high_water(1)
        self.assertEqual(allocator.next_id(), 4)

    def test_restoring_a_higher_counter_resumes_from_there(self):
        allocator = IdAllocator()
        allocator.next_id()
        allocator.restore_high_water(10)
        self.assertEqual(allocator.next_id(), 11)

    def test_reserve_moves_the_counter_past_the_reserved_id(self):
        allocator = IdAllocator()
        allocator.next_id()
        allocator.reserve(50)
        self.assertEqual(allocator.next_id(), 51)

    def test_issued_set_keeps_every_id_ever_used(self):
        allocator = IdAllocator()
        allocator.next_id()
        allocator.reserve(50)
        self.assertEqual(allocator.issued, frozenset({1, 50}))

    def test_high_water_is_the_largest_id_issued(self):
        allocator = IdAllocator()
        allocator.reserve(7)
        allocator.next_id()
        self.assertEqual(allocator.high_water, 8)

    def test_exhausting_the_id_space_raises_instead_of_wrapping(self):
        allocator = IdAllocator()
        allocator.next_id()
        allocator.reserve(INT64_MAX)
        with self.assertRaises(OverflowError):
            allocator.next_id()
        self.assertEqual(allocator.high_water, INT64_MAX)

    def test_two_allocators_are_independent(self):
        """Isolation is the caller's job: one allocator per stored design."""
        first = IdAllocator()
        second = IdAllocator()
        first.next_id()
        self.assertEqual(second.next_id(), 1)


if __name__ == "__main__":
    unittest.main()
