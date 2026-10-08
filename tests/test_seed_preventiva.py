import os
import tempfile
import unittest
from pathlib import Path


from tests.isolated_database import isolate_sqlite_database

class PreventivaSeedTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        from src.config.seed import seed_foundation
        seed_foundation()


    def test_preventiva_has_four_analysts_with_short_names(self):
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        segment = SegmentRepository().get_by_slug("preventiva")
        users = UserRepository().list_for_segment(segment.id)
        people = {u.login: u.display_name for u in users}
        self.assertEqual(
            {
                "N5604148": "Daniel",
                "N5941223": "Rosana",
                "N0158974": "Carlos",
                "N5577565": "Maristella",
            },
            people,
        )


if __name__ == "__main__":
    unittest.main()
