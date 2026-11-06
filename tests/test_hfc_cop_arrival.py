"""ETIT FIBRA HFC: delay between outage start and COP arrival (admin only)."""
import io
import unittest
from datetime import datetime
from unittest.mock import Mock

import pandas as pd

from tests.isolated_database import isolate_sqlite_database
from src.config.seed import seed_foundation
from src.features.ingestion.residential_indicators import parse_residential_indicators
from src.infrastructure.repositories import SegmentRepository, IndicatorRepository
from src.application.dashboard_service import DashboardService
from src.application.access_service import AccessService
from src.infrastructure.repositories import UserRepository


class HFCCopArrivalTest(unittest.TestCase):
    @staticmethod
    def xlsx(rows):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name="Analitico", index=False)
        return buf.getvalue()

    @staticmethod
    def base():
        return {
            "INDICADOR_NOME_ICG": "ETIT FIBRA HFC",
            "IN_REGIONAL": "Leste",
            "IN_GRUPO": "RIO E ES",
            "INDICADOR": 1,
            "VOLUME": 1,
            "ANOMES": 202611,
            "DT_INICIO": "2026-11-03 01:25:00",
            "LOGIN_PRIMEIRO_ACIONAMENTO_FO": "F104752",
            "ID_MOSTRA": "INM001",
            "DT_INICIO_SISTEMA": "2026-11-02 23:25:00",
            "DT_INICIO_CHEGOU_COP_FO": "2026-11-03 01:25:00",
        }

    def test_consolidated_and_per_group_use_arrival_clock_and_all_leste_events(self):
        rows = []
        def add(**changes):
            item = self.base()
            item.update(changes)
            rows.append(item)
        add(ID_MOSTRA="INM001", IN_GRUPO="RIO E ES",
            DT_INICIO_SISTEMA="2026-11-02 21:00:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-02 22:00:00")
        add(ID_MOSTRA="INM002", IN_GRUPO="RIO E ES",
            LOGIN_PRIMEIRO_ACIONAMENTO_FO="EXTERNO",
            DT_INICIO_SISTEMA="2026-11-02 23:00:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-03 01:00:00")
        add(ID_MOSTRA="INM003", IN_GRUPO="NORTE",
            LOGIN_PRIMEIRO_ACIONAMENTO_FO="EXTERNO",
            DT_INICIO_SISTEMA="2026-11-03 00:00:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-03 04:00:00")
        # Must not multiply repeated outage IDs or include arrivals outside shift.
        add(ID_MOSTRA="INM002", IN_GRUPO="RIO E ES",
            LOGIN_PRIMEIRO_ACIONAMENTO_FO="EXTERNO",
            DT_INICIO_SISTEMA="2026-11-02 23:00:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-03 01:00:00")
        add(ID_MOSTRA="INM004", IN_GRUPO="NORTE",
            DT_INICIO_SISTEMA="2026-11-02 22:00:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-03 06:00:00")
        # A valid arrival but invalid start must be counted as excluded, not zero delay.
        add(ID_MOSTRA="INM005", IN_GRUPO="RIO E ES",
            DT_INICIO_SISTEMA="2026-11-03 23:30:00",
            DT_INICIO_CHEGOU_COP_FO="2026-11-03 23:00:00")
        # Ignore ETIT GPON and regions outside Leste.
        add(ID_MOSTRA="INM006", INDICADOR_NOME_ICG="ETIT GPON")
        add(ID_MOSTRA="INM007", IN_REGIONAL="São Paulo")

        batches = parse_residential_indicators(self.xlsx(rows), {"F104752"})
        batch = next(b for b in batches if b.indicator_key == "res_etit_fibra_hfc")
        operational = [b for b in batch.breakdowns if b["scope"] == "operational"]
        overall = next(b for b in operational if b["dimension"] == "cop_arrival_overall")
        self.assertEqual(4, overall["volume"])
        self.assertEqual(3, overall["successes"])
        self.assertEqual(1, overall["losses"])
        self.assertEqual(3, overall["tma_count"])
        self.assertEqual(7 * 3600, overall["tma_seconds_sum"])

        groups = {
            b["dimension_value"]: b for b in operational
            if b["dimension"] == "cop_arrival_group"
        }
        self.assertEqual({"RIO E ES", "NORTE"}, set(groups))
        self.assertEqual(3, groups["RIO E ES"]["volume"])
        self.assertEqual(2, groups["RIO E ES"]["tma_count"])
        self.assertEqual(3 * 3600, groups["RIO E ES"]["tma_seconds_sum"])
        self.assertEqual(4 * 3600, groups["NORTE"]["tma_seconds_sum"])

    def test_excel_serials_midnight_and_exact_clock_boundaries(self):
        from src.features.ingestion.hfc_cop_arrival import parse_source_datetime, in_night_arrival
        self.assertEqual(
            datetime(2026, 11, 3, 1, 25),
            parse_source_datetime("2026-11-03 01:25:00"),
        )
        ts = pd.Timestamp("2026-11-03 01:25:00")
        serial = (ts.to_pydatetime() - datetime(1899, 12, 30)).total_seconds() / 86400
        parsed = parse_source_datetime(str(serial))
        self.assertLess(abs((parsed - ts.to_pydatetime()).total_seconds()), 0.01)
        self.assertIsNone(parse_source_datetime("2026-11-03"))
        midnight_serial = (
            datetime(2026, 11, 3) - datetime(1899, 12, 30)
        ).days
        self.assertEqual(
            datetime(2026, 11, 3), parse_source_datetime(midnight_serial)
        )
        self.assertTrue(in_night_arrival(datetime(2026, 11, 2, 22, 0)))
        self.assertTrue(in_night_arrival(datetime(2026, 11, 3, 5, 59, 59)))
        self.assertFalse(in_night_arrival(datetime(2026, 11, 3, 6, 0)))
        self.assertFalse(in_night_arrival(datetime(2026, 11, 2, 21, 59)))

    def test_group_display_uses_weighted_overall_and_flags_invalid_cases(self):
        from src.ui.admin.indicators.etit_residential import (
            build_cop_arrival_lag_table,
        )

        data = pd.DataFrame([
            {
                "group_name": "RIO E ES", "arrivals": 4,
                "valid_pairs": 3, "excluded": 1,
                "delay_seconds": 6 * 3600,
            },
            {
                "group_name": "NORTE", "arrivals": 1,
                "valid_pairs": 1, "excluded": 0,
                "delay_seconds": 4 * 3600,
            },
        ])
        summary, table = build_cop_arrival_lag_table(data)
        self.assertEqual(5, summary["arrivals"])
        self.assertEqual(4, summary["valid_pairs"])
        self.assertEqual(1, summary["excluded"])
        self.assertEqual(2.5 * 3600, summary["mean_seconds"])
        self.assertEqual("NORTE", table.iloc[0]["Grupo"])
        self.assertEqual("4h00min", table.iloc[0]["Tempo médio"])
        self.assertEqual("2h00min", table.iloc[1]["Tempo médio"])
        self.assertEqual(60.0, table.iloc[1]["Participação do tempo (%)"])
        # Groups with no arrivals must be visible, not given a false 0-minute lag.
        nordeste = table[table["Grupo"] == "NORDESTE"].iloc[0]
        self.assertEqual(0, nordeste["Outages válidos"])
        self.assertEqual("—", nordeste["Tempo médio"])
        self.assertEqual(
            "—", build_cop_arrival_lag_table(
                pd.DataFrame([{
                    "group_name": "RIO E ES", "arrivals": 1,
                    "valid_pairs": 0, "excluded": 1, "delay_seconds": 0,
                }])
            )[1].iloc[0]["Tempo médio"],
        )

    def test_same_outage_with_conflicting_timestamps_is_not_double_counted(self):
        first = self.base()
        second = self.base()
        second["DT_INICIO_SISTEMA"] = "2026-11-03 00:25:00"
        batch = next(
            b for b in parse_residential_indicators(
                self.xlsx([first, second]), {"F104752"}
            ) if b.indicator_key == "res_etit_fibra_hfc"
        )
        operational = [
            b for b in batch.breakdowns
            if b["dimension"] == "cop_arrival_overall"
        ]
        self.assertEqual(1, len(operational))
        self.assertEqual(1, operational[0]["volume"])
        self.assertEqual(0, operational[0]["tma_count"])
        self.assertEqual(1, operational[0]["losses"])

    def test_admin_query_isolated_from_team_kpi_and_requires_admin(self):
        from src.application.upload_service import UploadProcessingService

        isolate_sqlite_database(self)
        seed_foundation()
        users = UserRepository()
        admin = AccessService(users).context(users.get_by_login("ADMIN").id)
        res = SegmentRepository().get_by_slug("residencial")
        item = self.base()
        item["LOGIN_PRIMEIRO_ACIONAMENTO_FO"] = "F104752"
        ext = self.base()
        ext.update({
            "ID_MOSTRA": "INM002", "IN_GRUPO": "NORTE",
            "LOGIN_PRIMEIRO_ACIONAMENTO_FO": "EXTERNO",
            "DT_INICIO_SISTEMA": "2026-11-03 00:25:00",
            "DT_INICIO_CHEGOU_COP_FO": "2026-11-03 01:25:00",
        })
        payload = self.xlsx([item, ext])
        for _ in range(2):
            UploadProcessingService().process_global_source(
                admin, "residential_indicators", "hfc.xlsx", payload
            )
            repo = IndicatorRepository()
            report = repo.hfc_cop_arrival_by_group(res.id, "2026-11")
            self.assertEqual(2, sum(int(x["arrivals"]) for x in report))
            self.assertEqual(2, sum(int(x["valid_pairs"]) for x in report))
            self.assertEqual(3 * 3600, sum(x["delay_seconds"] for x in report))
            self.assertEqual({"RIO E ES", "NORTE"}, {x["group_name"] for x in report})
            self.assertEqual([], repo.hfc_cop_arrival_by_group(res.id, "2026-10"))
        service = DashboardService()
        self.assertEqual(2, len(service.hfc_cop_arrival_by_group(admin, res.id, "2026-11")))
        with self.assertRaises(PermissionError):
            service.hfc_cop_arrival_by_group(Mock(is_admin=False), res.id, "2026-11")
