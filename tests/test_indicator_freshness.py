import os
import tempfile
import unittest
from pathlib import Path


class IndicatorFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")

        from src.infrastructure import database

        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database, transaction
        from src.config.seed import seed_foundation

        initialize_database()
        seed_foundation()

        with transaction() as conn:
            segment_id = conn.execute(
                "SELECT id FROM segments WHERE slug='preventiva'"
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO indicator_definitions(segment_id, indicator_key, name, target_value) "
                "VALUES (?, 'chat_10m', 'Chat 10 min', 75)",
                (segment_id,),
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_upload_updates_data_coverage_per_indicator(self):
        from src.application.access_service import AccessService
        from src.application.indicator_freshness_service import IndicatorFreshnessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        admin = users.get_by_login("ADMIN")
        segment = SegmentRepository().get_by_slug("preventiva")
        ctx = AccessService(users).context(admin.id)
        service = IndicatorFreshnessService()

        first_upload = service.start_upload(ctx, segment.id, "chat_toa", "chat-setembro.xlsx")
        service.record_indicator_data_through(
            ctx,
            segment.id,
            "chat_10m",
            "28/09/2026",
            "chat_toa",
            first_upload,
        )

        rows = service.freshness(ctx, segment.id)
        self.assertEqual("2026-09-28", rows[0]["data_through"])
        self.assertEqual("chat_toa", rows[0]["source_key"])
        self.assertEqual("chat-setembro.xlsx", rows[0]["filename"])

        second_upload = service.start_upload(ctx, segment.id, "chat_toa", "chat-atualizado.xlsx")
        service.record_indicator_data_through(
            ctx,
            segment.id,
            "chat_10m",
            "29/09/2026",
            "chat_toa",
            second_upload,
        )

        rows = service.freshness(ctx, segment.id)
        self.assertEqual("2026-09-29", rows[0]["data_through"])
        self.assertEqual("chat-atualizado.xlsx", rows[0]["filename"])

    def test_analyst_can_read_but_cannot_write_freshness(self):
        from src.application.access_service import AccessService
        from src.application.indicator_freshness_service import IndicatorFreshnessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        users = UserRepository()
        daniel = users.get_by_login("N5604148")
        segment = SegmentRepository().get_by_slug("preventiva")
        ctx = AccessService(users).context(daniel.id)
        service = IndicatorFreshnessService()

        self.assertEqual(1, len(service.freshness(ctx, segment.id)))
        with self.assertRaises(PermissionError):
            service.record_indicator_data_through(
                ctx, segment.id, "chat_10m", "29/09/2026", "chat_toa"
            )


if __name__ == "__main__":
    unittest.main()
