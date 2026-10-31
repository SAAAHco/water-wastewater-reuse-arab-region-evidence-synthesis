"""Command-line interface.

    evidence-toolkit read    --pdfs DIR [--cache DIR]
    evidence-toolkit extract --pdfs DIR --questions FILE --out DIR [--reader local|endpoint] [options]
    evidence-toolkit verify  --pdfs DIR --evidence FILE --out DIR [--limit N]
    evidence-toolkit audit   --pdfs DIR --evidence FILE --out DIR [--sample N] [--documents N]
    evidence-toolkit digest  --evidence FILE --questions FILE --out DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audit as audit_mod
from . import digest as digest_mod
from . import endpoint_reader, local_reader
from .matrix import read_evidence, write_coverage, write_evidence, write_flagged, write_json
from .pdfs import corpus_summary, load_corpus
from .questions import load_questions
from .verify import verify_findings


def log(msg: str) -> None:
    print(msg, flush=True)


def _corpus(args):
    corpus = load_corpus(args.pdfs, args.cache, progress=log)
    s = corpus_summary(corpus)
    log(f"{s['documents']} documents, {s['pages']:,} pages; {s['documents_with_scanned_pages']} documents with pages that have no text layer")
    return corpus


def cmd_read(args):
    corpus = _corpus(args)
    s = corpus_summary(corpus)
    if s["scanned_pages"]:
        log("pages without a text layer (consider OCR): " + json.dumps(s["scanned_pages"]))


def cmd_extract(args):
    corpus = _corpus(args)
    questions = load_questions(args.questions)
    log(f"{len(questions)} questions")
    cmap = local_reader.load_citation_map(args.citation_map)
    if args.reader == "endpoint":
        findings = endpoint_reader.extract(corpus, questions, url=args.url, model=args.model, key=args.key,
                                           max_chars=args.segment_chars, citation_map=cmap, progress=log)
    else:
        findings = local_reader.extract(corpus, questions, top_k_per_doc=args.top_k, min_terms=args.min_terms,
                                        rel_threshold=args.threshold, max_per_question=args.max_per_question,
                                        min_words=args.min_words, max_words=args.max_words, citation_map=cmap, progress=log)
    summary = verify_findings(findings, corpus, window=args.window, fuzzy_threshold=args.fuzzy, progress=log)
    out = Path(args.out)
    path = write_evidence(findings, out, questions)
    write_coverage(findings, questions, out)
    write_flagged(findings, out)
    write_json(summary, out / "verification_summary.json")
    log(f"{len(findings):,} findings written to {path}; anchors located: {summary['found']:,} ({summary['share_found']}%)")


def cmd_verify(args):
    corpus = _corpus(args)
    findings = read_evidence(args.evidence, limit=args.limit)
    log(f"{len(findings):,} findings read from {args.evidence}")
    summary = verify_findings(findings, corpus, window=args.window, fuzzy_threshold=args.fuzzy, progress=log)
    out = Path(args.out)
    write_evidence(findings, out, name="verified_evidence.xlsx")
    write_flagged(findings, out)
    write_json(summary, out / "verification_summary.json")
    log(json.dumps({k: v for k, v in summary.items() if k != "files_not_in_corpus"}, indent=1))
    if summary["files_not_in_corpus"]:
        log(f"{len(summary['files_not_in_corpus'])} source files were not found in the PDF folder")


def cmd_audit(args):
    corpus = _corpus(args)
    findings = read_evidence(args.evidence, limit=args.limit)
    log(f"{len(findings):,} findings read from {args.evidence}")
    results = audit_mod.run_all(findings, corpus, n=args.sample, n_docs=args.documents, seed=args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(results, out / "audit_results.json")
    (out / "audit_summary.md").write_text(audit_mod.summary_markdown(results), encoding="utf-8")
    log(audit_mod.summary_markdown(results))


def cmd_digest(args):
    findings = read_evidence(args.evidence)
    questions = load_questions(args.questions)
    path = digest_mod.write_digest(findings, questions, args.out, verified_only=not args.include_unverified)
    log(f"digest written to {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="evidence-toolkit", description="Question-driven evidence extraction, quotation verification and audits for literature reviews.")
    sub = p.add_subparsers(dest="command", required=True)

    def pdf_args(sp):
        sp.add_argument("--pdfs", required=True, help="folder with the PDF documents")
        sp.add_argument("--cache", default=None, help="folder for the page-text cache (optional, speeds up reruns)")

    sp = sub.add_parser("read", help="read the PDFs and report pages without a text layer")
    pdf_args(sp)
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("extract", help="extract findings for every question, anchored to verbatim quotations")
    pdf_args(sp)
    sp.add_argument("--questions", required=True, help="CSV (id, question) or .docx with numbered questions")
    sp.add_argument("--out", required=True)
    sp.add_argument("--reader", choices=["local", "endpoint"], default="local")
    sp.add_argument("--citation-map", default=None, help="CSV mapping file name to citation key")
    sp.add_argument("--top-k", type=int, default=3, help="passages kept per document and question (local reader)")
    sp.add_argument("--min-terms", type=int, default=2, help="question terms a passage must contain (local reader)")
    sp.add_argument("--threshold", type=float, default=0.5, help="minimum score relative to the best passage (local reader)")
    sp.add_argument("--max-per-question", type=int, default=500)
    sp.add_argument("--min-words", type=int, default=8)
    sp.add_argument("--max-words", type=int, default=60)
    sp.add_argument("--url", default=None, help="chat-completion URL (endpoint reader; or EVIDENCE_LLM_URL)")
    sp.add_argument("--model", default=None, help="model name (endpoint reader; or EVIDENCE_LLM_MODEL)")
    sp.add_argument("--key", default=None, help="bearer token (endpoint reader; or EVIDENCE_LLM_KEY)")
    sp.add_argument("--segment-chars", type=int, default=60_000)
    sp.add_argument("--window", type=int, default=2, help="adjacent pages searched when locating a quotation")
    sp.add_argument("--fuzzy", type=float, default=0.6, help="share of four-word sequences required for a fuzzy match")
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("verify", help="locate every anchor quotation of an evidence table in its PDF")
    pdf_args(sp)
    sp.add_argument("--evidence", required=True, help="Excel or CSV evidence table")
    sp.add_argument("--out", required=True)
    sp.add_argument("--limit", type=int, default=None, help="verify only the first N rows")
    sp.add_argument("--window", type=int, default=2)
    sp.add_argument("--fuzzy", type=float, default=0.6)
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("audit", help="numeric precision, place-tag and coverage audits of an evidence table")
    pdf_args(sp)
    sp.add_argument("--evidence", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--limit", type=int, default=None)
    sp.add_argument("--sample", type=int, default=600, help="findings sampled for the precision and place audits")
    sp.add_argument("--documents", type=int, default=20, help="documents sampled for the coverage proxy")
    sp.add_argument("--seed", type=int, default=1)
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("digest", help="write the verified quotations per question as a Markdown digest")
    sp.add_argument("--evidence", required=True)
    sp.add_argument("--questions", required=True)
    sp.add_argument("--out", required=True)
    sp.add_argument("--include-unverified", action="store_true")
    sp.set_defaults(func=cmd_digest)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
