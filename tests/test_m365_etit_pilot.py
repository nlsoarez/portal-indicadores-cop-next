import unittest

from src.integrations.m365_etit import (
    PILOT_SOURCES,
    graph_share_id,
    remote_changed,
    select_latest_file,
)


class M365EtitPilotTest(unittest.TestCase):
    def test_share_id_uses_graph_u_prefix(self):
        value = graph_share_id("https://example.sharepoint.com/shared?id=abc")
        self.assertTrue(value.startswith("u!"))
        self.assertNotIn("=", value)

    def test_residential_selects_latest_competence(self):
        source = next(
            item for item in PILOT_SOURCES
            if item.source_key == "residential_indicators"
        )
        rows = [
            {
                "id": "old",
                "name": "Analítico Indicadores Residencial - 202608.xlsx",
                "file": {"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                "eTag": "etag-old",
                "lastModifiedDateTime": "2026-09-17T12:00:00Z",
                "size": 100,
                "parentReference": {"driveId": "drive"},
            },
            {
                "id": "new",
                "name": "Analítico Indicadores Residencial - 202609.xlsx",
                "file": {"mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                "eTag": "etag-new",
                "lastModifiedDateTime": "2026-09-29T20:00:00Z",
                "size": 200,
                "parentReference": {"driveId": "drive"},
            },
        ]

        latest = select_latest_file(source, rows)

        self.assertEqual("202609", latest.competence)
        self.assertEqual("new", latest.item_id)
        self.assertEqual(200, latest.size)

    def test_enterprise_ignores_unrelated_workbooks(self):
        source = next(
            item for item in PILOT_SOURCES
            if item.source_key == "enterprise_indicators"
        )
        rows = [
            {
                "id": "dashboard",
                "name": "Produtividade COP Rede 2026 - Dashboard.xlsx",
                "file": {},
                "eTag": "x",
                "lastModifiedDateTime": "2026-09-30T00:00:00Z",
                "size": 100,
                "parentReference": {"driveId": "drive"},
            },
            {
                "id": "emp",
                "name": "Analítico Empresarial - 202609.xlsx",
                "file": {},
                "eTag": "y",
                "lastModifiedDateTime": "2026-09-30T00:00:00Z",
                "size": 120,
                "parentReference": {"driveId": "drive"},
            },
        ]

        latest = select_latest_file(source, rows)

        self.assertEqual("emp", latest.item_id)
        self.assertEqual("202609", latest.competence)

    def test_remote_changed_uses_etag_and_metadata(self):
        source = next(
            item for item in PILOT_SOURCES
            if item.source_key == "enterprise_indicators"
        )
        current = select_latest_file(
            source,
            [
                {
                    "id": "emp",
                    "name": "Analítico Empresarial - 202609.xlsx",
                    "file": {},
                    "eTag": "etag-2",
                    "lastModifiedDateTime": "2026-09-30T10:00:00Z",
                    "size": 120,
                    "parentReference": {"driveId": "drive"},
                }
            ],
        )

        self.assertFalse(remote_changed(current.fingerprint(), current))
        previous = current.fingerprint()
        previous["etag"] = "etag-1"
        self.assertTrue(remote_changed(previous, current))


if __name__ == "__main__":
    unittest.main()
