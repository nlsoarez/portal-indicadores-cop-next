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

    def test_every_source_has_filename_contract(self):
        from src.features.ingestion.source_catalog import UPLOAD_SOURCES

        for source in UPLOAD_SOURCES:
            self.assertTrue(source.label)
            self.assertTrue(source.filename_hint)
            self.assertTrue(source.target_segment_slugs)


if __name__ == "__main__":
    unittest.main()
