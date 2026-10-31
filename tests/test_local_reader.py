import unittest

from evidence_toolkit.local_reader import build_passages, extract
from evidence_toolkit.verify import verify_findings

CORPUS = {
    "jordan.pdf": [
        "Jordan reuses around 90 percent of its treated wastewater in agriculture. Reclaimed water is priced at JOD 0.55 per cubic metre against JOD 1.00 for freshwater, which keeps farmers interested.",
        "The King Talal Dam stores effluent from the As-Samra plant and releases it to the Jordan Valley. Soil salinity in the irrigated fields is monitored every season by the ministry.",
    ],
    "soil.pdf": [
        "After three decades of irrigation with secondary effluent, soil organic matter rose by 90 percent and phosphorus by 472 percent at the Tunisian site. Electrical conductivity rose by 72 percent relative to the control.",
        "7. References\nSmith J (2001) Irrigation. Journal of Things 1:1-2.",
    ],
}
QUESTIONS = [
    {"id": "1", "question": "What price do farmers pay for reclaimed water compared with freshwater?"},
    {"id": "2", "question": "How does long-term irrigation with treated wastewater change soil salinity and organic matter?"},
    {"id": "3", "question": "Which dams store treated effluent and release it to irrigated areas?"},
]


class LocalReaderTests(unittest.TestCase):
    def test_passages_are_verbatim_and_sized(self):
        passages = build_passages(CORPUS, min_words=8, max_words=60)
        self.assertTrue(passages)
        for p in passages:
            self.assertTrue(8 <= len(p.text.split()) <= 60)
            self.assertIn(p.text.split()[0], CORPUS[p.file][p.page - 1].replace("\n", " "))

    def test_extract_finds_the_right_document_and_page(self):
        findings = extract(CORPUS, QUESTIONS, top_k_per_doc=2, min_terms=2, rel_threshold=0.5)
        by_q = {}
        for f in findings:
            for qid in f["Question ID(s)"].split(", "):
                by_q.setdefault(qid, []).append(f)
        self.assertTrue(any(f["Source file"] == "jordan.pdf" and f["PDF page"] == 1 for f in by_q["1"]))
        self.assertTrue(any(f["Source file"] == "soil.pdf" and f["PDF page"] == 1 for f in by_q["2"]))
        self.assertTrue(any(f["Source file"] == "jordan.pdf" and f["PDF page"] == 2 for f in by_q["3"]))
        self.assertTrue(any("Jordan" in f["Place"] for f in by_q["1"]))

    def test_extracted_quotes_verify_exactly(self):
        findings = extract(CORPUS, QUESTIONS)
        s = verify_findings(findings, CORPUS)
        self.assertEqual(s["found"], s["findings"])
        self.assertTrue(all(f["Verification"] == "exact-page" for f in findings))

    def test_reference_lists_and_citations_are_skipped(self):
        passages = build_passages(CORPUS)
        self.assertFalse(any("Journal of Things" in p.text for p in passages))

    def test_overlapping_passages_are_not_both_kept(self):
        findings = extract(CORPUS, QUESTIONS, top_k_per_doc=5)
        texts = [f["Verbatim anchor quote"] for f in findings if f["Source file"] == "jordan.pdf" and "1" in f["Question ID(s)"].split(", ")]
        for a in texts:
            for b in texts:
                self.assertTrue(a == b or (a not in b and b not in a))


if __name__ == "__main__":
    unittest.main()
