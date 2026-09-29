"""Integration test for the four seam tools (UX-6, UIUX 3.7).

Runs inside a real Blender, because the whole point of this milestone is that
the tools produce a chain Blender can actually mark as a seam - and a chain
built from a triangulation's invented diagonals looks perfect in numpy and
cannot be applied at all.

The cases here are the ones the spec names: a grid, a mesh with an open border,
and a seam with a legitimate loose end. None of them may be reported as an
error, and the mesh topology must not move while a seam is being chosen.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from bscu.bridge import seam_bridge  # noqa: E402
from bscu.core.seam_tools import selection_boundary  # noqa: E402
from bscu.core.uv_validate import validate_chart  # noqa: E402


def fresh_grid(subdivisions: int = 4):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdivisions,
                                    y_subdivisions=subdivisions)
    return bpy.context.active_object


def topology_signature(obj) -> tuple:
    return (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons))


class TestSeamChain(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_grid()
        self.name = self.obj.name
        # Push after the object exists, so undo stops at the seam rather than
        # unwinding the object's creation as well.
        bpy.ops.ed.undo_push()

    def tearDown(self):
        seam_bridge.clear_stage(self.name)
        if self.name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[self.name], do_unlink=True)

    def test_a_staged_chain_changes_nothing_until_it_is_confirmed(self):
        seam_bridge.propose_chain(self.obj, 0, 24)

        self.assertTrue(seam_bridge.staged(self.obj)["edges"])
        self.assertEqual(sum(1 for e in self.obj.data.edges if e.use_seam), 0)

    def test_confirming_marks_exactly_the_previewed_edges(self):
        """The chain the user previewed is the chain that lands."""
        seam_bridge.propose_chain(self.obj, 0, 24)
        previewed = seam_bridge.staged(self.obj)["edges"]

        seam_bridge.confirm(self.obj)

        marked = {tuple(sorted(e.vertices)) for e in self.obj.data.edges if e.use_seam}
        self.assertEqual(marked, set(previewed))

    def test_the_chain_uses_edges_the_mesh_really_has(self):
        """A quad mesh's triangulation invents diagonals; a seam cannot use them."""
        seam_bridge.propose_chain(self.obj, 0, 24)
        available = set(seam_bridge.mesh_edge_pairs(self.obj.data))

        for edge in seam_bridge.staged(self.obj)["edges"]:
            self.assertIn(tuple(edge), available)

    def test_the_mesh_topology_does_not_move_while_a_seam_is_chosen(self):
        before = topology_signature(self.obj)
        seam_bridge.propose_chain(self.obj, 0, 24)
        seam_bridge.confirm(self.obj)

        self.assertEqual(topology_signature(self.obj), before)

    def test_undo_takes_the_seam_back_with_it(self):
        name = self.name
        seam_bridge.propose_chain(self.obj, 0, 24)
        seam_bridge.confirm(self.obj)
        self.assertTrue(any(e.use_seam for e in self.obj.data.edges))

        bpy.ops.ed.undo()

        # Undo rebuilds the data, so the old handle is dead by design.
        survivor = bpy.data.objects[name]
        self.assertFalse(any(e.use_seam for e in survivor.data.edges))

    def test_cancelling_leaves_the_mesh_exactly_as_it_was(self):
        seam_bridge.propose_chain(self.obj, 0, 24)
        seam_bridge.clear_stage(self.obj.name)

        self.assertEqual(seam_bridge.staged(self.obj)["edges"], [])
        self.assertEqual(sum(1 for e in self.obj.data.edges if e.use_seam), 0)


class TestSeamSelectionBorder(unittest.TestCase):
    def setUp(self):
        self.obj = fresh_grid()

    def tearDown(self):
        bpy.data.objects.remove(self.obj, do_unlink=True)

    def test_the_border_of_a_picked_region_is_offered_and_applies(self):
        faces = seam_bridge.mesh_faces(self.obj.data)
        polygons = self.obj.data.polygons
        chosen = [index < 2 for index in range(len(polygons))]
        expanded = seam_bridge.polygon_selection_to_triangles(self.obj.data, chosen)
        self.assertEqual(len(expanded), len(faces))
        self.assertTrue(selection_boundary(faces, expanded))

        seam_bridge.propose_selection_border(self.obj, chosen)

        self.assertTrue(seam_bridge.staged(self.obj)["edges"])


class TestValidatorOnRealMeshes(unittest.TestCase):
    """The validator has to stay quiet on meshes that are merely awkward."""

    def setUp(self):
        self.obj = fresh_grid()
        self.obj.data.uv_layers.new(name="BSCU_UV_Active")

    def tearDown(self):
        bpy.data.objects.remove(self.obj, do_unlink=True)

    def _layout(self):
        layer = self.obj.data.uv_layers["BSCU_UV_Active"]
        points = [[0.0, 0.0] for _ in self.obj.data.vertices]
        for loop in self.obj.data.loops:
            points[loop.vertex_index] = list(layer.data[loop.index].uv)
        return np.asarray(points, dtype=np.float64)

    def test_a_flat_grid_lands_with_no_errors(self):
        faces = seam_bridge.mesh_faces(self.obj.data)
        islands = np.zeros(len(faces), dtype=np.int64)

        report = validate_chart(faces, self._layout(), islands)

        self.assertEqual(report.errors, [], [f.message for f in report.errors])

    def test_a_loose_seam_end_is_not_an_error_on_a_real_mesh(self):
        faces = seam_bridge.mesh_faces(self.obj.data)
        islands = np.zeros(len(faces), dtype=np.int64)
        loose = [(0, 1), (1, 6)]

        report = validate_chart(faces, self._layout(), islands, seam_edges=loose)

        self.assertEqual(report.errors, [], [f.message for f in report.errors])
        self.assertIn("LOOSE_SEAM_END", {f.code for f in report.findings})


if __name__ == "__main__":
    unittest.main()
