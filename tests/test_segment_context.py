import unittest

from src.application.segment_context import switch_segment_state


class SegmentContextTest(unittest.TestCase):
    def test_segment_switch_clears_segment_scoped_state(self):
        state = {
            "active_segment_id": 1,
            "segment_data:frame": "old",
            "segment_filter:period": "2026-09",
            "global_theme": "light",
        }
        switch_segment_state(state, 2)
        self.assertEqual(2, state["active_segment_id"])
        self.assertNotIn("segment_data:frame", state)
        self.assertNotIn("segment_filter:period", state)
        self.assertEqual("light", state["global_theme"])


if __name__ == "__main__":
    unittest.main()
