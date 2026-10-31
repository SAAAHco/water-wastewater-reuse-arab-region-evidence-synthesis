import unittest

from evidence_toolkit.textutil import normalize, reference_heading_offset, sentences, shingles, stem, tokenize
from evidence_toolkit.verify import DocumentIndex, verify_findings

PAGES = [
    "Wastewater reuse in the region remains limited. About 10.5% of the municipal waste-\nwater generated was directly reused in 2020, mostly for fodder irrigation.",
    "The share of effluent that is discharged to the sea is large. Treatment capacity has grown faster than conveyance to farms, so plants stand idle.",
    "Farmers in the valley accept treated water when the price is low. Trust in the authorities to ensure quality was reported by 21.9% of respondents.",
]


class TextUtilTests(unittest.TestCase):
    def test_normalize_joins_hyphenation_and_unifies_quotes(self):
        self.assertEqual(normalize("waste-\nwater “reuse” – 2020"), 'wastewater "reuse" - 2020')

    def test_sentences(self):
        self.assertEqual(len(sentences("One sentence here. Another one? Yes! (Third.)")), 4)

    def test_tokenize_drops_stopwords(self):
        self.assertEqual(tokenize("The reuse of water in the region"), ["reuse", "water", "region"])

    def test_shingles(self):
        self.assertEqual(len(shingles("a b c d e")), 2)
        self.assertEqual(shingles("plants stand idle."), shingles("plants stand idle"))

    def test_stem(self):
        self.assertEqual([stem(w) for w in ("reuses", "reused", "reusing", "cities", "glass", "2020")],
                         ["reuse", "reus", "reus", "city", "glass", "2020"])

    def test_reference_heading_offset(self):
        self.assertEqual(reference_heading_offset("Some text.\n7. References\nDoe J (2019)"), 11)
        self.assertIsNone(reference_heading_offset("References to earlier work are given in the text of this long sentence."))


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.idx = DocumentIndex(PAGES)

    def test_exact_on_cited_page(self):
        r = self.idx.locate("about 10.5% of the municipal wastewater generated was directly reused in 2020", page_hint=1)
        self.assertEqual(r["status"], "exact-page")

    def test_exact_on_adjacent_page(self):
        r = self.idx.locate("Treatment capacity has grown faster than conveyance to farms", page_hint=1)
        self.assertEqual((r["status"], r["page"]), ("exact-adjacent", 2))

    def test_exact_elsewhere_in_document(self):
        r = self.idx.locate("Trust in the authorities to ensure quality was reported by 21.9% of respondents", page_hint=1, window=1)
        self.assertEqual((r["status"], r["page"]), ("exact-document", 3))

    def test_fuzzy_match(self):
        r = self.idx.locate("Treatment capacity has grown far faster than conveyance to farms, so plants stand idle", page_hint=2)
        self.assertEqual(r["status"], "fuzzy")
        self.assertGreaterEqual(r["share"], 0.6)

    def test_not_found(self):
        r = self.idx.locate("This sentence was invented and appears nowhere in the document at all", page_hint=2)
        self.assertEqual(r["status"], "not-found")

    def test_verify_findings_summary(self):
        corpus = {"doc.pdf": PAGES}
        findings = [
            {"Source file": "doc.pdf", "PDF page": 3, "Verbatim anchor quote": "Farmers in the valley accept treated water when the price is low."},
            {"Source file": "doc.pdf", "PDF page": 1, "Verbatim anchor quote": "An invented quotation that is not in the text layer of any page here."},
            {"Source file": "missing.pdf", "PDF page": 1, "Verbatim anchor quote": "Anything"},
        ]
        s = verify_findings(findings, corpus)
        self.assertEqual((s["findings"], s["found"]), (3, 1))
        self.assertTrue(findings[0]["Quote found in source"])
        self.assertFalse(findings[1]["Quote found in source"])
        self.assertEqual(findings[2]["Verification"], "file-not-in-corpus")


if __name__ == "__main__":
    unittest.main()
