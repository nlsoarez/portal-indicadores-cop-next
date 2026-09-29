import unittest


class UploadSourceCatalogTest(unittest.TestCase):
    def test_exact_seven_official_sources_all_integrated(self):
        from src.features.ingestion.source_catalog import UPLOAD_SOURCES
        self.assertEqual(
            ("residential_indicators","enterprise_indicators","dpa","productivity","closing_toa_sir","chat_toa","toa_indicators"),
            tuple(source.key for source in UPLOAD_SOURCES),
        )
        self.assertEqual(7,len(UPLOAD_SOURCES))
        self.assertTrue(all(source.implemented for source in UPLOAD_SOURCES))


if __name__ == "__main__": unittest.main()
