import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from evidence_toolkit.endpoint_reader import extract, parse_items, segments
from evidence_toolkit.verify import verify_findings

PAGES = ["Reclaimed water is priced at JOD 0.55 per cubic metre against JOD 1.00 for freshwater in the valley.",
         "The King Talal Dam stores effluent from the As-Samra plant and releases it to the Jordan Valley farms."]
REPLY = json.dumps([
    {"qid": "1", "quote": "Reclaimed water is priced at JOD 0.55 per cubic metre against JOD 1.00 for freshwater", "page": 1, "place": "Jordan", "note": "Price ratio."},
    {"qid": "3", "quote": "The dam stores effluent and releases it to farms every single day of the year", "page": 2, "place": "Jordan", "note": "Invented wording."},
    {"qid": "9", "quote": "unknown question identifier", "page": 1, "place": "", "note": ""},
])


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        assert body["messages"][0]["role"] == "system"
        out = json.dumps({"choices": [{"message": {"role": "assistant", "content": "```json\n" + REPLY + "\n```"}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):  # silence
        pass


class EndpointReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1/chat/completions"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_segments_carry_page_markers_and_respect_the_limit(self):
        segs = segments(PAGES, max_chars=120)
        self.assertEqual(len(segs), 2)
        self.assertTrue(segs[0].startswith("[PAGE 1]"))
        self.assertTrue(segs[1].startswith("[PAGE 2]"))

    def test_parse_items_tolerates_fences_and_drops_incomplete_items(self):
        items = parse_items("```json\n[{\"qid\": \"1\", \"quote\": \"x y z\", \"page\": \"2\"}, {\"qid\": \"\", \"quote\": \"q\"}]\n```")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["page"], 2)

    def test_extract_then_verify_flags_invented_quotes(self):
        questions = [{"id": "1", "question": "Price of reclaimed water?"}, {"id": "3", "question": "Storage of effluent?"}]
        findings = extract({"doc.pdf": PAGES}, questions, url=self.url, model="any-model")
        self.assertEqual(len(findings), 2)  # the item with an unknown question identifier is dropped
        s = verify_findings(findings, {"doc.pdf": PAGES})
        self.assertEqual(s["found"], 1)
        statuses = {f["Question ID(s)"]: f["Verification"] for f in findings}
        self.assertEqual(statuses["1"], "exact-page")
        self.assertEqual(statuses["3"], "not-found")


if __name__ == "__main__":
    unittest.main()
