import unittest

from evidence_toolkit.audit import coverage_proxy, country_tags, numbers_in, numeric_precision

PAGES = ["In 2020 about 21.5 billion m3 were generated and 2,275 million m3 reused, which is 10.5% of the total, in Jordan and Egypt.",
         "Only 41 of 104 plants were operational in Lebanon; 35 had been built but did not operate.",
         "References\nDoe J (2019) Something. Journal 12:34-56."]
CORPUS = {"doc.pdf": PAGES}
FINDINGS = [
    {"Source file": "doc.pdf", "PDF page": 1, "Place": "Jordan", "Finding (paraphrased)": "About 21.5 billion m3 generated; 2,275 million m3 reused (10.5%).", "Verbatim anchor quote": "x"},
    {"Source file": "doc.pdf", "PDF page": 2, "Place": "Lebanon", "Finding (paraphrased)": "41 of 104 plants operational; 35 built but idle.", "Verbatim anchor quote": "x"},
    {"Source file": "doc.pdf", "PDF page": 2, "Place": "Morocco", "Finding (paraphrased)": "Capacity of 999 plants reported.", "Verbatim anchor quote": "x"},
]


class AuditTests(unittest.TestCase):
    def test_numbers_in_skips_years_and_small_integers(self):
        self.assertEqual(numbers_in("In 2020, 3 plants treated 21.5 million m3 and 1,411 units"), {"21.5", "1411"})

    def test_numeric_precision(self):
        r = numeric_precision(FINDINGS, CORPUS, n=10)
        self.assertEqual(r["findings_checked"], 3)
        self.assertEqual(r["findings_all_numbers_found"], 2)

    def test_country_tags(self):
        r = country_tags(FINDINGS, CORPUS, n=10)
        self.assertEqual((r["findings_checked"], r["country_found_on_page"]), (3, 2))

    def test_coverage_proxy_ignores_reference_pages(self):
        r = coverage_proxy(FINDINGS, CORPUS, n_docs=5, min_chars=20)
        self.assertEqual(r["documents"], 1)
        self.assertEqual(r["per_document"][0]["pages_checked"], 2)
        self.assertGreater(r["median_share"], 50)


if __name__ == "__main__":
    unittest.main()
