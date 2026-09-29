import unittest


class UploadSourceCatalogTest(unittest.TestCase):
    def test_exact_seven_official_sources(self):
        from src.features.ingestion.source_catalog import UPLOAD_SOURCES

        self.assertEqual(
            (
                "residential_indicators",
                "enterprise_indicators",
                "dpa",
                "productivity",
                "closing_toa_sir",
                "chat_toa",
                "toa_indicators",
            ),
            tuple(source.key for source in UPLOAD_SOURCES),
        )
        self.assertEqual(7, len(UPLOAD_SOURCES))

    def test_only_currently_integrated_sources_have_adapters(self):
        from src.features.ingestion.source_catalog import UPLOAD_SOURCE_BY_KEY

        self.assertTrue(UPLOAD_SOURCE_BY_KEY["chat_toa"].implemented)
        self.assertTrue(UPLOAD_SOURCE_BY_KEY["toa_indicators"].implemented)
        self.assertFalse(UPLOAD_SOURCE_BY_KEY["productivity"].implemented)
        self.assertFalse(UPLOAD_SOURCE_BY_KEY["dpa"].implemented)


if __name__ == "__main__":
    unittest.main()
