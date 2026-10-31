"""Local reader: question-driven retrieval of verbatim passages, with page numbers, from the PDF text layer.

No external service is needed. Every page is split into sentences; single sentences and pairs of consecutive
sentences of 8 to 60 words become candidate passages. A BM25 index over all candidates ranks them for each
question, and the best passages of every document that share enough terms with the question are returned as
findings anchored to a verbatim quotation. The reader is deliberately recall-oriented: it returns candidate
evidence for a human to screen, and it never paraphrases.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .places import tag_place
from .textutil import normalize, reference_heading_offset, sentences, tokenize


@dataclass
class Passage:
    file: str
    page: int
    text: str
    tokens: tuple[str, ...]


_CITATION_LIKE = re.compile(
    r"https?://|doi\.org|\bdoi:|\(\d{4}[a-z]?\)\.|\b\d{1,4}\(\d{1,3}\)\s*[,:]?\s*\d+\s*[-–]\s*\d+|\b\d{1,4}:\s*\d+\s*[-–]\s*\d+"
    r"|\b\d{4};\s*\d+:|\bpp?\.\s*\d+")


def reference_cutoff(pages: list[str]) -> tuple[int, int]:
    """(page index, character offset) where the reference list begins, searched in the second half of the document."""
    start = len(pages) // 2
    for i in range(start, len(pages)):
        off = reference_heading_offset(pages[i])
        if off is not None:
            return i, off
    return len(pages), 0


def build_passages(corpus: dict[str, list[str]], min_words: int = 8, max_words: int = 60) -> list[Passage]:
    passages: list[Passage] = []
    seen: set[tuple[str, str]] = set()
    for file, pages in corpus.items():
        cut_page, cut_offset = reference_cutoff(pages)
        for page_no, raw in enumerate(pages, start=1):
            if page_no - 1 > cut_page:
                break
            if page_no - 1 == cut_page:
                raw = raw[:cut_offset]
            sents = [s for s in sentences(normalize(raw)) if not _CITATION_LIKE.search(s)]
            candidates = []
            for i, s in enumerate(sents):
                candidates.append(s)
                if i + 1 < len(sents):
                    candidates.append(s + " " + sents[i + 1])
            for text in candidates:
                words = text.split()
                if len(words) > max_words:
                    words = words[:max_words]
                    text = " ".join(words)
                if len(words) < min_words:
                    continue
                key = (file, text)
                if key in seen:
                    continue
                seen.add(key)
                toks = tuple(tokenize(text))
                if toks:
                    passages.append(Passage(file, page_no, text, toks))
    return passages


class BM25Index:
    """Okapi BM25 over passages with an inverted index; terms in more than ``max_df_ratio`` of passages get no weight."""

    def __init__(self, passages: list[Passage], k1: float = 1.5, b: float = 0.75, max_df_ratio: float = 0.5):
        self.passages = passages
        self.k1, self.b = k1, b
        n = max(len(passages), 1)
        self.avgdl = sum(len(p.tokens) for p in passages) / n
        self.postings: dict[str, dict[int, int]] = defaultdict(dict)
        for pid, p in enumerate(passages):
            post = self.postings
            for t in p.tokens:
                d = post[t]
                d[pid] = d.get(pid, 0) + 1
        self.idf: dict[str, float] = {}
        for t, post in self.postings.items():
            df = len(post)
            self.idf[t] = 0.0 if df / n > max_df_ratio else math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query_tokens: list[str]) -> tuple[dict[int, float], dict[int, set[str]]]:
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, set[str]] = defaultdict(set)
        k1, b, avgdl = self.k1, self.b, self.avgdl
        for t in set(query_tokens):
            post = self.postings.get(t)
            if not post:
                continue
            idf = self.idf.get(t, 0.0)
            for pid, tf in post.items():
                matched[pid].add(t)
                if idf > 0:
                    dl = len(self.passages[pid].tokens)
                    scores[pid] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
        return scores, matched


def load_citation_map(path: str | Path | None) -> dict[str, str]:
    """CSV with two columns, file name and citation key (header optional)."""
    if not path:
        return {}
    import csv

    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip() and row[0].strip().lower() not in ("file", "source file", "filename"):
                out[row[0].strip()] = row[1].strip()
    return out


def extract(corpus: dict[str, list[str]], questions: list[dict], top_k_per_doc: int = 3, min_terms: int = 2,
            rel_threshold: float = 0.5, max_per_question: int = 500, min_words: int = 8, max_words: int = 60,
            citation_map: dict[str, str] | None = None, progress=None) -> list[dict]:
    """Findings for every question: the best-matching passages of each document, anchored to verbatim quotations.

    A passage qualifies for a question when it contains at least ``min_terms`` distinct terms of the question (or all
    of them for shorter questions) and scores at least ``rel_threshold`` times the best score for that question
    across the corpus. At most ``top_k_per_doc`` passages per document and ``max_per_question`` per question are kept.
    Passages matched by several questions are merged into one finding listing all their question identifiers.
    """
    citation_map = citation_map or {}
    passages = build_passages(corpus, min_words, max_words)
    if progress:
        progress(f"{len(passages):,} candidate passages from {len(corpus)} documents")
    index = BM25Index(passages)
    merged: dict[tuple[str, int, str], dict] = {}
    for i, q in enumerate(questions, start=1):
        q_tokens = tokenize(q["question"])
        need = min(min_terms, len(set(q_tokens)))
        scores, matched = index.search(q_tokens)
        if not scores:
            continue
        best = max(scores.values())
        per_doc: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for pid, sc in scores.items():
            if len(matched[pid]) >= need and sc >= rel_threshold * best:
                per_doc[passages[pid].file].append((sc, pid))
        rows = []
        for file, lst in per_doc.items():
            lst.sort(reverse=True)
            kept: list[tuple[float, int]] = []
            for sc, pid in lst:
                text = passages[pid].text
                if any(text in passages[k].text or passages[k].text in text for _, k in kept):
                    continue  # a sentence and the pair that contains it: keep the better-scoring one only
                kept.append((sc, pid))
                if len(kept) >= top_k_per_doc:
                    break
            rows.extend(kept)
        rows.sort(reverse=True)
        for sc, pid in rows[:max_per_question]:
            p = passages[pid]
            key = (p.file, p.page, p.text)
            if key in merged:
                merged[key]["Question ID(s)"] += ", " + q["id"]
                merged[key]["Matched terms"] = "; ".join(sorted(set(merged[key]["Matched terms"].split("; ")) | matched[pid]))
                merged[key]["Relevance score"] = max(merged[key]["Relevance score"], round(sc, 3))
                continue
            merged[key] = {
                "Question ID(s)": q["id"],
                "Citation key": citation_map.get(p.file, Path(p.file).stem),
                "Source file": p.file,
                "PDF page": p.page,
                "Place": tag_place(p.text, corpus[p.file][p.page - 1]),
                "Finding (paraphrased)": "",
                "Verbatim anchor quote": p.text,
                "Matched terms": "; ".join(sorted(matched[pid])),
                "Relevance score": round(sc, 3),
            }
        if progress and (i % 10 == 0 or i == len(questions)):
            progress(f"question {i}/{len(questions)}: {len(rows[:max_per_question])} findings")
    findings = list(merged.values())
    findings.sort(key=lambda r: (r["Source file"], r["PDF page"], -r["Relevance score"]))
    return findings
