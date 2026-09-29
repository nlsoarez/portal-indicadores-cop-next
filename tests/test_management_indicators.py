import io
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class ManagementIndicatorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["COP_PORTAL_DB"] = str(Path(self.tmp.name) / "portal.db")
        from src.infrastructure import database
        database.DB_PATH = Path(os.environ["COP_PORTAL_DB"])
        from src.infrastructure.database import initialize_database
        from src.config.seed import seed_foundation
        initialize_database()
        seed_foundation()

    def tearDown(self):
        self.tmp.cleanup()

    def test_shared_indicator_returns_all_segments_and_all_analysts(self):
        from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository

        indicators = IndicatorRepository()
        segments = SegmentRepository()
        users = UserRepository()
        fixtures = [
            ("residencial", "F104752", 90.0, 100),
            ("empresarial", "N0189105", 80.0, 200),
            ("preventiva", "N5604148", 70.0, 300),
        ]
        segment_ids = []
        for slug, login, value, volume in fixtures:
            segment = segments.get_by_slug(slug)
            user = users.get_by_login(login)
            definition = indicators.get_definition(segment.id, "dpa_official")
            segment_ids.append(segment.id)
            indicators.replace_results_for_months(
                segment_id=segment.id,
                indicator_definition_id=int(definition["id"]),
                login_to_user_id={login: user.id},
                rows=({
                    "login": login,
                    "period": "2026-09-29",
                    "data_month": "2026-09",
                    "value": value,
                    "volume": volume,
                },),
                months=("2026-09",),
            )

        payload = indicators.management_payload(segment_ids, include_external=True)
        dpa_segments = [r for r in payload["segment_summary"] if r["indicator_key"] == "dpa_official"]
        dpa_people = [r for r in payload["analyst_summary"] if r["indicator_key"] == "dpa_official"]
        self.assertEqual({"Residencial", "Empresarial", "Preventiva"}, {r["segment_name"] for r in dpa_segments})
        self.assertEqual({"F104752", "N0189105", "N5604148"}, {r["login"] for r in dpa_people})

    def test_breakdowns_and_external_rows_are_available_to_management(self):
        from src.infrastructure.repositories import IndicatorRepository, SegmentRepository, UserRepository

        indicators = IndicatorRepository()
        segment = SegmentRepository().get_by_slug("preventiva")
        user = UserRepository().get_by_login("N5604148")
        definition = indicators.get_definition(segment.id, "chat_10m")
        indicators.replace_results_for_months(
            segment_id=segment.id,
            indicator_definition_id=int(definition["id"]),
            login_to_user_id={"N5604148": user.id},
            rows=({
                "login": "N5604148", "period": "2026-09-29", "data_month": "2026-09",
                "value": 50.0, "volume": 2,
            },),
            months=("2026-09",),
        )
        indicators.replace_breakdowns_for_months(
            segment_id=segment.id,
            indicator_definition_id=int(definition["id"]),
            months=("2026-09",),
            rows=(
                {
                    "scope": "team", "login": "N5604148", "period": "2026-09-29",
                    "data_month": "2026-09", "dimension": "hour", "dimension_value": "22",
                    "value": 50.0, "volume": 2, "successes": 1, "losses": 1,
                },
                {
                    "scope": "external", "login": "OUTSIDE", "period": "2026-09-29",
                    "data_month": "2026-09", "dimension": "external_hour", "dimension_value": "23",
                    "value": 0.0, "volume": 1, "successes": 0, "losses": 1,
                },
            ),
        )
        payload = indicators.management_payload([segment.id], include_external=True)
        self.assertEqual("22", payload["breakdowns"][0]["dimension_value"])
        self.assertEqual("OUTSIDE", payload["external"][0]["login"])
        self.assertEqual("23", payload["external"][0]["hour"])

    def test_toa_indicators_are_shared_across_all_segments(self):
        from src.features.ingestion.source_catalog import UPLOAD_SOURCE_BY_KEY
        from src.infrastructure.repositories import IndicatorRepository, SegmentRepository

        source = UPLOAD_SOURCE_BY_KEY["toa_indicators"]
        self.assertEqual(
            ("residencial", "empresarial", "preventiva"),
            source.target_segment_slugs,
        )

        indicators = IndicatorRepository()
        segments = SegmentRepository()
        for slug in source.target_segment_slugs:
            segment = segments.get_by_slug(slug)
            self.assertIsNotNone(indicators.get_definition(segment.id, "validacao_20m"))
            self.assertIsNotNone(indicators.get_definition(segment.id, "toa_cancellation_rate"))

    def test_residential_parser_persists_service_scoped_cluster_and_city(self):
        from src.features.ingestion.residential_indicators import parse_residential_indicators

        df = pd.DataFrame({
            "INDICADOR_NOME_ICG": ["ETIT GPON", "ETIT GPON"],
            "VOLUME": [1, 1],
            "INDICADOR": [1, 0],
            "IN_REGIONAL": ["Leste", "Leste"],
            "DT_INICIO": ["2026-09-29 22:10:00", "2026-09-29 23:10:00"],
            "ANOMES": [202609, 202609],
            "LOGIN_PRIMEIRO_ACIONAMENTO_GPON": ["N5772086", "N5772086"],
            "IN_GRUPO": ["Rio e ES", "Rio e ES"],
            "IN_CIDADE_UF": ["RIO DE JANEIRO/RJ", "RIO DE JANEIRO/RJ"],
            "IN_UF": ["RJ", "RJ"],
            "SERVICO": ["BROWNFIELD", "GREENFIELD"],
            "NATUREZA": ["EMERGENCIAL", "EMERGENCIAL"],
            "SOLUCAO": ["SOLUCAO A", "SOLUCAO B"],
            "IMPACTO": ["NAO MASSIVO", "MASSIVO"],
        })
        raw = io.BytesIO()
        with pd.ExcelWriter(raw, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Analitico", index=False)

        batches = parse_residential_indicators(raw.getvalue(), {"N5772086"})
        gpon = next(batch for batch in batches if batch.indicator_key == "res_etit_gpon")
        dimensions = {(row["dimension"], row["dimension_value"]) for row in gpon.breakdowns}

        self.assertIn(("service", "BROWNFIELD"), dimensions)
        self.assertIn(("service", "GREENFIELD"), dimensions)
        self.assertIn(("group", "Rio e ES"), dimensions)
        self.assertIn(("city", "RIO DE JANEIRO/RJ"), dimensions)
        self.assertIn(("service__group", "BROWNFIELD|||Rio e ES"), dimensions)
        self.assertIn(("service__city", "GREENFIELD|||RIO DE JANEIRO/RJ"), dimensions)

    def test_scope_frame_handles_legacy_empty_breakdown(self):
        from src.ui.shared.management_indicators import _scope_frame

        self.assertTrue(_scope_frame(pd.DataFrame(), "Residencial").empty)
        self.assertTrue(_scope_frame(pd.DataFrame({"period": ["2026-09-29"]}), "Residencial").empty)

        frame = pd.DataFrame({
            "segment_name": ["Residencial", "Empresarial"],
            "value": [90.0, 80.0],
        })
        scoped = _scope_frame(frame, "Residencial")
        self.assertEqual(1, len(scoped))
        self.assertEqual("Residencial", scoped.iloc[0]["segment_name"])

    def test_empty_payload_frames_keep_expected_columns(self):
        from src.ui.shared.management_indicators import FRAME_SCHEMAS, _payload_frame

        for key, expected in FRAME_SCHEMAS.items():
            frame = _payload_frame({}, key)
            self.assertTrue(frame.empty)
            self.assertTrue(set(expected).issubset(set(frame.columns)))

    def test_empty_breakdown_helpers_are_safe(self):
        from src.ui.shared.management_indicators import (
            _dimension_rows,
            _dimensions_rows,
            _scope_frame,
            _weighted_value,
        )

        frame = pd.DataFrame()
        self.assertTrue(_scope_frame(frame, "Residencial").empty)
        self.assertTrue(_dimension_rows(frame, "turn").empty)
        self.assertTrue(_dimensions_rows(frame, ("turn", "hour")).empty)
        self.assertIsNone(_weighted_value(frame))

    def test_chat_parser_keeps_hour_zero_and_external_night_record(self):
        from src.features.ingestion.chat_toa import parse_chat_toa

        df = pd.DataFrame({
            "FECHAMENTO_COPREDE_LOGIN_ANALISTA": ["N5604148", "OUTSIDE"],
            "ABERTURA_ANOMES": [202609, 202609],
            "INDICADOR_TMA_DENTRO": [1, 0],
            "CHAT_INICIO": ["2026-09-29 00:10:00", "2026-09-29 23:10:00"],
        })
        raw = io.BytesIO()
        with pd.ExcelWriter(raw, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Analítico CHAT TOA", index=False, startrow=3)
        batch = parse_chat_toa(raw.getvalue(), {"N5604148"})
        team_hours = [r for r in batch.breakdowns if r["scope"] == "team" and r["dimension"] == "hour"]
        external = [r for r in batch.breakdowns if r["scope"] == "external"]
        self.assertEqual("0", team_hours[0]["dimension_value"])
        self.assertEqual("23", external[0]["dimension_value"])


if __name__ == "__main__":
    unittest.main()
