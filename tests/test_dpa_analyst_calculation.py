import os
import tempfile
import unittest
from pathlib import Path


class DpaAnalystCalculationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")

        from src.infrastructure import database

        database.DATABASE_URL = ""
        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])

        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation

        initialize_database()
        seed_foundation()

    def tearDown(self):
        self.tmp.cleanup()

    def test_personal_dpa_is_weighted_by_journey_and_team_is_mean_of_analysts(self):
        from src.infrastructure.database import transaction
        from src.infrastructure.repositories import (
            IndicatorRepository,
            SegmentRepository,
            UserRepository,
        )

        users = UserRepository()
        segment = SegmentRepository().get_by_slug("residencial")
        alan = users.get_by_login("N4014011")
        cristiane = users.get_by_login("N5972428")

        with transaction() as conn:
            definition = conn.execute(
                """
                SELECT id
                FROM indicator_definitions
                WHERE segment_id=? AND indicator_key='dpa_official'
                """,
                (segment.id,),
            ).fetchone()
            definition_id = int(definition["id"])

            rows = [
                # Alan: (80*100 + 100*300) / 400 = 95.0
                (alan.id, "2026-09-28", 80.0, 100),
                (alan.id, "2026-09-29", 100.0, 300),
                # Cristiane: 80.0 no mês, com jornada muito maior.
                (cristiane.id, "2026-09-29", 80.0, 1000),
            ]
            for user_id, period, value, volume in rows:
                conn.execute(
                    """
                    INSERT INTO indicator_results(
                        segment_id, user_id, indicator_definition_id,
                        period, data_month, value, volume
                    ) VALUES (?, ?, ?, ?, '2026-09', ?, ?)
                    """,
                    (
                        segment.id,
                        user_id,
                        definition_id,
                        period,
                        value,
                        volume,
                    ),
                )

        payload = IndicatorRepository().dashboard_payload(segment.id, alan.id)

        personal = next(
            row
            for row in payload["summary"]
            if row["indicator_key"] == "dpa_official"
            and row["period"] == "2026-09"
        )
        team = next(
            row
            for row in payload["team_averages"]
            if row["indicator_key"] == "dpa_official"
            and row["period"] == "2026-09"
        )
        day = next(
            row
            for row in payload["team_daily"]
            if row["indicator_key"] == "dpa_official"
            and row["period"] == "2026-09-29"
        )

        self.assertEqual(95.0, float(personal["value"]))
        # Média da equipe = média dos DPAs mensais dos analistas:
        # (95.0 + 80.0) / 2 = 87.5.
        self.assertEqual(87.5, float(team["team_avg"]))
        # Média diária em 29/09 = (100.0 + 80.0) / 2 = 90.0.
        self.assertEqual(90.0, float(day["team_avg"]))


    def test_productivity_team_reference_is_mean_of_analyst_monthly_averages(self):
        from src.infrastructure.database import transaction
        from src.infrastructure.repositories import (
            IndicatorRepository,
            SegmentRepository,
            UserRepository,
        )

        users = UserRepository()
        segment = SegmentRepository().get_by_slug("empresarial")
        sandro = users.get_by_login("N5737414")
        fernanda = users.get_by_login("F201714")

        with transaction() as conn:
            definition = conn.execute(
                """
                SELECT id
                FROM indicator_definitions
                WHERE segment_id=? AND indicator_key='productivity_avg_daily'
                """,
                (segment.id,),
            ).fetchone()
            definition_id = int(definition["id"])

            rows = [
                # Sandro: média mensal = (60 + 80) / 2 = 70.
                (sandro.id, "2026-09-28", 60.0),
                (sandro.id, "2026-09-29", 80.0),
                # Fernanda: média mensal = 100.
                (fernanda.id, "2026-09-29", 100.0),
            ]
            for user_id, period, value in rows:
                conn.execute(
                    """
                    INSERT INTO indicator_results(
                        segment_id, user_id, indicator_definition_id,
                        period, data_month, value, volume
                    ) VALUES (?, ?, ?, ?, '2026-09', ?, 1)
                    """,
                    (
                        segment.id,
                        user_id,
                        definition_id,
                        period,
                        value,
                    ),
                )

        payload = IndicatorRepository().dashboard_payload(segment.id, sandro.id)

        personal = next(
            row
            for row in payload["summary"]
            if row["indicator_key"] == "productivity_avg_daily"
            and row["period"] == "2026-09"
        )
        team = next(
            row
            for row in payload["team_averages"]
            if row["indicator_key"] == "productivity_avg_daily"
            and row["period"] == "2026-09"
        )

        self.assertEqual(70.0, float(personal["value"]))
        # Referência do setor = média das médias individuais:
        # (70 + 100) / 2 = 85.
        self.assertEqual(85.0, float(team["team_avg"]))


if __name__ == "__main__":
    unittest.main()
