# Evidence toolkit

Question-driven evidence extraction, quotation verification and audits for literature reviews, in plain Python.

The toolkit implements the workflow used in the review *Water and wastewater reuse in the Arab region: An evidence synthesis along the reuse chain* (WIREs Water): every document in a library is read against a fixed set of review questions, every finding is anchored to a verbatim quotation with its page number, every quotation is located in the source PDF before it counts as evidence, and the resulting evidence table is audited against the PDFs. The review itself was run on the Revio platform (https://revio.tools). This repository lets anyone reproduce the verification and audit steps on the review's findings database, and run the same question-driven workflow on their own PDFs, without any commercial service.

## What it does

| Command | What happens |
|---|---|
| `read` | Reads the text layer of every PDF in a folder, page by page, and reports pages without text (scanned pages that need OCR). |
| `extract` | Reads every document against every question and writes an evidence table. Each finding has the question identifiers, citation key, source file, PDF page, a place tag, a verbatim anchor quotation and a verification result. |
| `verify` | Locates every anchor quotation of an existing evidence table in its PDF and flags the ones it cannot find. |
| `audit` | Samples the evidence table and checks numeric precision, place tags and coverage against the PDFs. |
| `digest` | Compiles the verified quotations per question, grouped by document, into a Markdown file for a reviewer to read. |

Two readers are available for `extract`:

* **Local reader (default).** Needs nothing but the PDFs. Every page is split into sentences; sentences and pairs of consecutive sentences of 8 to 60 words become candidate passages; a BM25 index ranks them for each question; and the best passages of each document that share enough terms with the question are returned as findings. It never paraphrases and never invents text, because every finding is a passage copied from the page. It is recall-oriented: it proposes candidate evidence for a human to screen.
* **Endpoint reader (optional).** Sends each document, in segments with `[PAGE n]` markers, with the question list to any chat-completion endpoint you run or subscribe to, and expects a JSON array of findings back. Whatever the model returns is then located in the PDF by `verify`; quotations that are not in the source are flagged, not trusted.

## Installation

```bash
pip install -e .
```

Requirements: Python 3.10 or later, `pymupdf`, `pandas`, `openpyxl`. Add `python-docx` if you want to read questions from a Word file.

## Quick start

```bash
# 1. Check that the PDFs have a text layer
evidence-toolkit read --pdfs ./pdfs --cache ./cache

# 2. Extract findings for every question (local reader)
evidence-toolkit extract --pdfs ./pdfs --questions examples/questions_example.csv --out ./output --cache ./cache

# 3. Verify an existing evidence table (for example the findings database of the review, Data S1)
evidence-toolkit verify --pdfs ./pdfs --evidence Data_S1.xlsx --out ./verified --cache ./cache

# 4. Audit an evidence table against the PDFs
evidence-toolkit audit --pdfs ./pdfs --evidence Data_S1.xlsx --out ./audit --cache ./cache --sample 600 --documents 20

# 5. Compile the verified quotations per question
evidence-toolkit digest --evidence ./output/Evidence_matrix.xlsx --questions examples/questions_example.csv --out ./output
```

`python -m evidence_toolkit ...` works the same way without installation.

## Inputs

* **PDFs**: a folder of PDF files. Files are identified by their file name, which is also the default citation key; pass `--citation-map keys.csv` (two columns: file name, citation key) to use your own keys.
* **Questions**: a CSV with columns `id` and `question`, or a Word file whose numbered paragraphs (`1.1 Text`) are the questions. See `examples/questions_example.csv`.
* **Evidence table** (for `verify`, `audit`, `digest`): Excel or CSV with at least the columns `Source file`, `PDF page` and `Verbatim anchor quote`; `Question ID(s)`, `Citation key`, `Place` and `Finding (paraphrased)` are used when present. Common alternative column names (`file`, `page`, `quote`, `country`) are recognized.

## Outputs of `extract`

`Evidence_matrix.xlsx` (sheets `Evidence` and `Questions`) and `Evidence_matrix.csv` with one row per finding:

| Column | Content |
|---|---|
| Question ID(s) | identifiers of the questions the passage answers, comma separated |
| Citation key | from the citation map, or the file name |
| Source file, PDF page | where the quotation is |
| Place | countries named in the passage; else regions; else countries named on the page; else `Unspecified` |
| Finding (paraphrased) | empty for the local reader (it does not paraphrase); the model's note for the endpoint reader |
| Verbatim anchor quote | the passage, copied from the page |
| Quote found in source, Verification, Located page, Shingle share | result of the verification step |
| Matched terms, Relevance score | local reader only: the question terms found in the passage and its BM25 score |

`coverage.csv` lists, for every question, the documents and findings that address it. `flagged_quotes.csv` lists the findings whose quotation could not be located. `verification_summary.json` gives the counts by verification status.

## How verification works

For each quotation, after unifying quotation marks, dashes, soft hyphens, line-end hyphenation and spacing on both sides:

1. exact match on the cited page;
2. exact match on the pages within `--window` of it (default 2);
3. exact match anywhere in the document, which also catches quotations that run across a page break;
4. fuzzy match: the quotation is accepted when at least `--fuzzy` (default 0.6) of its four-word sequences occur in the document.

A quotation that fails all four checks is reported as `not-found` and `Quote found in source` is `False`.

## How the audits work

* **Numeric precision.** From the findings whose text contains numbers (years and the integers 1 to 10 excluded), `--sample` findings are drawn at random (`--seed`); every number is searched on the cited page and the adjacent pages, allowing for thousand separators, rounding to 0, 1 or 2 decimals and scaling by 100, 1,000 or a million. The result is the share of findings with every number present and the share of numbers found.
* **Place tags.** From the findings whose place tag names exactly one country of the gazetteer in `evidence_toolkit/places.py`, `--sample` findings are drawn and the country, or a city or site in it, is searched on the cited and adjacent pages.
* **Coverage proxy.** `--documents` documents are drawn; on every page with at least 300 characters that is not a reference list, every number of two or more digits is collected, and the share of those numbers that appear in a finding cited to that page or the two following pages is computed. The median across documents is reported with the range.

The audits read the text layer of the PDFs, so numbers that exist only inside images are invisible to them. They test precision and a proxy for recall; they do not replace a human re-extraction.

## Reproducing the checks reported in the review

With the review's findings database (Data S1 of the Supporting Information) saved as `Data_S1.xlsx` and the 221 included PDFs in a folder, the two commands below reproduce the verification and the three audits reported in Section 2 of the paper. The database uses the column names the toolkit expects (`Source file`, `PDF page`, `Verbatim anchor quote`, `Finding (paraphrased)`, `Place`, `Question ID(s)`), so no mapping is needed.

```bash
evidence-toolkit verify --pdfs ./pdfs --evidence Data_S1.xlsx --out ./verified --cache ./cache
evidence-toolkit audit  --pdfs ./pdfs --evidence Data_S1.xlsx --out ./audit --cache ./cache --sample 600 --documents 20 --seed 1
```

`verified/flagged_quotes.csv` lists every anchor the toolkit could not locate, and `audit/audit_summary.md` gives the three audit results. Random samples depend on `--seed`, so the shares will differ slightly from the published ones for other seeds.

## Using the endpoint reader

Set three environment variables (or pass `--url`, `--model`, `--key`):

```bash
export EVIDENCE_LLM_URL=http://localhost:11434/v1/chat/completions   # your own server or a hosted service
export EVIDENCE_LLM_MODEL=the-model-name
export EVIDENCE_LLM_KEY=optional-bearer-token
evidence-toolkit extract --pdfs ./pdfs --questions questions.csv --out ./output --reader endpoint --segment-chars 60000
```

The request body follows the common `{"model": ..., "messages": [...]}` convention and the reply is read from `choices[0].message.content`, so local servers and most hosted services work without changes. The instruction sent with each segment is in `evidence_toolkit/endpoint_reader.py`; it asks for verbatim quotations of 8 to 60 words with the page number and forbids paraphrase. Every returned quotation is verified against the PDF.

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests cover normalization, sentence splitting, the local reader, the four verification checks, the three audits and the endpoint reader (against a small local HTTP server started by the test).

## Citation

If you use this toolkit, cite the review it accompanies and this repository: Ashkanani, M. (2026). *Evidence toolkit* (Version 0.1.0) [Computer software]. https://github.com/SAAAHco/water-wastewater-reuse-arab-region-evidence-synthesis

## License

MIT. See `LICENSE`.
