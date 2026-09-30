import unittest

from src.integrations.m365_etit import (
    EtitPilotSource,
    M365TokenProvider,
    PILOT_SOURCES,
    graph_share_id,
    remote_changed,
    resolve_folder_by_owner_path,
    select_latest_file,
)


class M365EtitPilotTest(unittest.TestCase):

    def test_token_provider_rejects_example_placeholders(self):
        provider = M365TokenProvider(
            tenant_id="SEU_TENANT_ID",
            client_id="SEU_CLIENT_ID",
            cache_key="invalid-but-present",
        )
        self.assertFalse(provider.configured)

    def test_token_provider_accepts_real_ids(self):
        provider = M365TokenProvider(
            tenant_id="55247d4b-b435-47a5-881b-ca7627434e79",
            client_id="5c36fcc6-8e44-481a-b822-b56a22ccc767",
            cache_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        )
        self.assertTrue(provider.configured)

    def test_token_provider_requires_cache_encryption_key(self):
        provider = M365TokenProvider(
            tenant_id="55247d4b-b435-47a5-881b-ca7627434e79",
            client_id="5c36fcc6-8e44-481a-b822-b56a22ccc767",
            cache_key="",
        )
        self.assertFalse(provider.configured)

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

    def test_source_accepts_owner_and_folder_path_configuration(self):
        source = EtitPilotSource(
            source_key="x",
            label="X",
            env_prefix="TEST_M365",
            filename_regex=r".*",
        )
        import os
        previous_owner = os.environ.get("TEST_M365_OWNER_UPN")
        previous_path = os.environ.get("TEST_M365_FOLDER_PATH")
        try:
            os.environ["TEST_M365_OWNER_UPN"] = "user@example.com"
            os.environ["TEST_M365_FOLDER_PATH"] = "Indicadores/Novo BI"
            self.assertTrue(source.configured)
            self.assertEqual("user@example.com", source.owner_upn)
            self.assertEqual("Indicadores/Novo BI", source.folder_path)
        finally:
            if previous_owner is None:
                os.environ.pop("TEST_M365_OWNER_UPN", None)
            else:
                os.environ["TEST_M365_OWNER_UPN"] = previous_owner
            if previous_path is None:
                os.environ.pop("TEST_M365_FOLDER_PATH", None)
            else:
                os.environ["TEST_M365_FOLDER_PATH"] = previous_path

    def test_owner_path_resolver_uses_user_drive_path(self):
        class FakeClient:
            def __init__(self):
                self.path = None

            def get_json(self, path):
                self.path = path
                return {
                    "id": "folder-id",
                    "name": "Novo BI",
                    "parentReference": {"driveId": "drive-id"},
                    "folder": {},
                }

        client = FakeClient()
        drive_id, folder_id = resolve_folder_by_owner_path(
            client,
            "fernando@example.com",
            "Indicadores COP/Analítico Residencial/Novo BI",
        )

        self.assertEqual("drive-id", drive_id)
        self.assertEqual("folder-id", folder_id)
        self.assertIn("/users/fernando%40example.com/drive/root:/", client.path)
        self.assertIn("Anal%C3%ADtico%20Residencial", client.path)

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
