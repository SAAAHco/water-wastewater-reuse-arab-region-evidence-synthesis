"""Evidence digests: for every question, the verified quotations grouped by document, ready for a reviewer to read.

The digest contains no generated text. It compiles what the documents say, with a citation and page for every
quotation, so that a human writes the answer.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def build_digest(findings: list[dict], questions: list[dict], verified_only: bool = True) -> str:
    by_q: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        if verified_only and not f.get("Quote found in source"):
            continue
        for qid in str(f.get("Question ID(s)", "")).split(","):
            by_q[qid.strip()].append(f)
    lines = ["# Evidence digest", "", "Each entry is a verbatim quotation with its document and page. "
             "Nothing here is generated; the digest is the raw material for a written answer.", ""]
    for q in questions:
        items = by_q.get(q["id"], [])
        lines += [f"## {q['id']} {q['question']}", ""]
        if not items:
            lines += ["No verified evidence was found for this question.", ""]
            continue
        by_doc: dict[str, list[dict]] = defaultdict(list)
        for f in items:
            by_doc[str(f.get("Citation key") or f.get("Source file"))].append(f)
        lines.append(f"{len(items)} quotations from {len(by_doc)} documents.")
        lines.append("")
        for key in sorted(by_doc):
            for f in sorted(by_doc[key], key=lambda r: (int(float(r.get("PDF page") or 0)))):
                note = f" {f['Finding (paraphrased)']}" if f.get("Finding (paraphrased)") else ""
                lines.append(f"- [{key}, p. {f.get('PDF page')}] \"{f.get('Verbatim anchor quote')}\"{note}")
        lines.append("")
    return "\n".join(lines)


def write_digest(findings: list[dict], questions: list[dict], out_dir: str | Path, verified_only: bool = True) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "evidence_digest.md"
    path.write_text(build_digest(findings, questions, verified_only), encoding="utf-8")
    return path
