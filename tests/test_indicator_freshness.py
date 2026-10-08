import os
import tempfile
import unittest
from pathlib import Path


from tests.isolated_database import isolate_sqlite_database

class IndicatorFreshnessTest(unittest.TestCase):
    def setUp(self):
        isolate_sqlite_database(self)
        from src.config.seed import seed_foundation
        seed_foundation()


    def test_each_upload_updates_data_coverage_per_indicator(self):
        from src.application.access_service import AccessService
        from src.application.indicator_freshness_service import IndicatorFreshnessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users=UserRepository(); segment=SegmentRepository().get_by_slug("preventiva")
        ctx=AccessService(users).context(users.get_by_login("ADMIN").id); service=IndicatorFreshnessService()
        first=service.start_upload(ctx,segment.id,"chat_toa","chat-setembro.xlsx")
        service.record_indicator_data_through(ctx,segment.id,"chat_10m","28/09/2026","chat_toa",first)
        row=next(r for r in service.freshness(ctx,segment.id) if r["indicator_key"]=="chat_10m")
        self.assertEqual("2026-09-28",row["data_through"]); self.assertEqual("chat-setembro.xlsx",row["filename"])
        second=service.start_upload(ctx,segment.id,"chat_toa","chat-atualizado.xlsx")
        service.record_indicator_data_through(ctx,segment.id,"chat_10m","29/09/2026","chat_toa",second)
        row=next(r for r in service.freshness(ctx,segment.id) if r["indicator_key"]=="chat_10m")
        self.assertEqual("2026-09-29",row["data_through"]); self.assertEqual("chat-atualizado.xlsx",row["filename"])

    def test_analyst_can_read_but_cannot_write_freshness(self):
        from src.application.access_service import AccessService
        from src.application.indicator_freshness_service import IndicatorFreshnessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository
        users=UserRepository(); segment=SegmentRepository().get_by_slug("preventiva")
        ctx=AccessService(users).context(users.get_by_login("N5604148").id); service=IndicatorFreshnessService()
        self.assertEqual(6,len(service.freshness(ctx,segment.id)))
        with self.assertRaises(PermissionError):
            service.record_indicator_data_through(ctx,segment.id,"chat_10m","29/09/2026","chat_toa")


if __name__ == "__main__":
    unittest.main()
