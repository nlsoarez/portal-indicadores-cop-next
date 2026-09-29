import io
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class SourceIngestionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")
        from src.infrastructure import database

        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation

        initialize_database()
        seed_foundation()

        from src.application.access_service import AccessService
        from src.infrastructure.repositories import SegmentRepository, UserRepository

        self.users = UserRepository()
        self.segment = SegmentRepository().get_by_slug("preventiva")
        admin = self.users.get_by_login("ADMIN")
        self.ctx = AccessService(self.users).context(admin.id)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _xlsx(df: pd.DataFrame, sheet: str, startrow: int = 0) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet, index=False, startrow=startrow)
        return buffer.getvalue()

    def test_chat_upload_filters_scope_and_persists_daily_result_and_freshness(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository

        df = pd.DataFrame(
            {
                "FECHAMENTO_COPREDE_LOGIN_ANALISTA": [
                    "N5604148", "N5604148", "N5941223", "OUTSIDE", "N0158974"
                ],
                "ABERTURA_ANOMES": [202609, 202609, 202609, 202609, 202608],
                "FECHAMENTO_FILA": ["RJO RES", "RJO RES", "RJO RES", "RJO RES", "RJO RES"],
                "INDICADOR_TMA_DENTRO": [1, 0, 1, 1, 1],
                "CHAT_INICIO": [
                    "2026-09-28 22:10:00",
                    "2026-09-28 22:20:00",
                    "2026-09-28 23:10:00",
                    "2026-09-28 23:20:00",
                    "2026-08-31 23:00:00",
                ],
            }
        )
        result = UploadProcessingService().process(
            self.ctx,
            self.segment.id,
            "chat_toa",
            "chat.xlsx",
            self._xlsx(df, "Analítico CHAT TOA", startrow=3),
        )
        self.assertEqual("2026-09-28", result.data_through)
        self.assertEqual(2, result.analyst_count)
        self.assertEqual(3, result.total_volume)

        daniel = self.users.get_by_login("N5604148")
        rows = IndicatorRepository().results_for_user(self.segment.id, daniel.id)
        chat = [row for row in rows if row["indicator_key"] == "chat_10m"]
        self.assertEqual(1, len(chat))
        self.assertEqual(50.0, chat[0]["value"])
        self.assertEqual(2, chat[0]["volume"])

        freshness = IndicatorRepository().freshness(self.segment.id)
        chat_fresh = next(row for row in freshness if row["indicator_key"] == "chat_10m")
        self.assertEqual("2026-09-28", chat_fresh["data_through"])
        self.assertEqual("chat.xlsx", chat_fresh["filename"])

        summary = IndicatorRepository().monthly_summary_for_user(self.segment.id, daniel.id)
        chat_summary = next(row for row in summary if row["indicator_key"] == "chat_10m")
        self.assertEqual(50.0, chat_summary["value"])
        self.assertEqual(2, chat_summary["volume"])

        team = IndicatorRepository().team_monthly_summary(self.segment.id)
        team_chat = next(row for row in team if row["indicator_key"] == "chat_10m")
        self.assertEqual(66.7, team_chat["team_avg"])
        self.assertEqual(3, team_chat["team_volume"])
        self.assertEqual(1.5, team_chat["avg_volume_per_analyst"])

    def test_validation_upload_uses_latest_month_leste_and_membership(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository

        df = pd.DataFrame(
            {
                "INDICADOR_NOME": [
                    "TEMPO DE VALIDAÇÃO DO FORMULÁRIO",
                    "TEMPO DE VALIDAÇÃO DO FORMULÁRIO",
                    "TEMPO DE VALIDAÇÃO DO FORMULÁRIO",
                    "TEMPO DE VALIDAÇÃO DO FORMULÁRIO",
                    "TAREFAS CANCELADAS",
                ],
                "LOGIN": ["N5577565", "N5577565", "N0158974", "N5941223", "N5604148"],
                "INDICADOR": [1, 1, 0, 1, 1],
                "ANOMES": [202609, 202609, 202609, 202608, 202609],
                "IN_REGIONAL": ["Leste", "Leste", "Leste", "Leste", "Leste"],
                "DATA": ["2026-09-27", "2026-09-29", "2026-09-29", "2026-08-30", "2026-09-29"],
            }
        )
        result = UploadProcessingService().process(
            self.ctx,
            self.segment.id,
            "toa_validation",
            "validacao.xlsx",
            self._xlsx(df, "TOA"),
        )
        self.assertEqual("2026-09-29", result.data_through)
        self.assertEqual(2, result.analyst_count)
        self.assertEqual(3, result.total_volume)

        carlos = self.users.get_by_login("N0158974")
        rows = IndicatorRepository().results_for_user(self.segment.id, carlos.id)
        validation = [row for row in rows if row["indicator_key"] == "validacao_20m"]
        self.assertEqual(1, len(validation))
        self.assertEqual(0.0, validation[0]["value"])

    def test_reupload_same_month_replaces_old_days_instead_of_duplicating(self):
        from src.application.upload_service import UploadProcessingService
        from src.infrastructure.repositories import IndicatorRepository

        service = UploadProcessingService()
        first = pd.DataFrame(
            {
                "FECHAMENTO_COPREDE_LOGIN_ANALISTA": ["N5604148", "N5604148"],
                "ABERTURA_ANOMES": [202609, 202609],
                "FECHAMENTO_FILA": ["RJO RES", "RJO RES"],
                "INDICADOR_TMA_DENTRO": [1, 0],
                "CHAT_INICIO": ["2026-09-27 22:00:00", "2026-09-28 22:00:00"],
            }
        )
        service.process(
            self.ctx, self.segment.id, "chat_toa", "chat-1.xlsx",
            self._xlsx(first, "Analítico CHAT TOA", startrow=3),
        )

        second = pd.DataFrame(
            {
                "FECHAMENTO_COPREDE_LOGIN_ANALISTA": ["N5604148"],
                "ABERTURA_ANOMES": [202609],
                "FECHAMENTO_FILA": ["RJO RES"],
                "INDICADOR_TMA_DENTRO": [1],
                "CHAT_INICIO": ["2026-09-29 22:00:00"],
            }
        )
        service.process(
            self.ctx, self.segment.id, "chat_toa", "chat-2.xlsx",
            self._xlsx(second, "Analítico CHAT TOA", startrow=3),
        )

        daniel = self.users.get_by_login("N5604148")
        rows = IndicatorRepository().results_for_user(self.segment.id, daniel.id)
        chat = [row for row in rows if row["indicator_key"] == "chat_10m"]
        self.assertEqual(1, len(chat))
        self.assertEqual("2026-09-29", chat[0]["period"])
        self.assertEqual(100.0, chat[0]["value"])
        self.assertEqual(1, chat[0]["volume"])


if __name__ == "__main__":
    unittest.main()
