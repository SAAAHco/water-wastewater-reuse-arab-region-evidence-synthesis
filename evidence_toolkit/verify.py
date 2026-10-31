"""Locate every anchor quotation in its source document.

Order of checks for one quotation: exact match on the cited page; exact match on the adjacent pages; exact match
anywhere in the document (which also catches quotations that run across a page break); and finally a fuzzy match,
accepted when at least ``fuzzy_threshold`` of the quotation's four-word sequences occur in the document. A quotation
that fails every check is reported as not found and should be treated as unverified evidence.
"""
from __future__ import annotations

from .textutil import _WORD, fold, shingles


class DocumentIndex:
    """Folded page texts of one document, with the document's word shingles built on first use."""

    def __init__(self, pages: list[str]):
        self.pages = [fold(p) for p in pages]
        self.full = " ".join(self.pages)
        self._shingles: set | None = None

    @property
    def doc_shingles(self) -> set:
        if self._shingles is None:
            self._shingles = shingles(self.full)
        return self._shingles

    def page_of(self, folded_quote: str) -> int | None:
        for i, p in enumerate(self.pages, start=1):
            if folded_quote in p:
                return i
        return None

    def locate(self, quote: str, page_hint: int | None = None, window: int = 2, fuzzy_threshold: float = 0.6) -> dict:
        q = fold(quote)
        n = len(self.pages)
        if not q:
            return {"status": "empty", "page": None, "share": 0.0}
        if page_hint and 1 <= page_hint <= n and q in self.pages[page_hint - 1]:
            return {"status": "exact-page", "page": page_hint, "share": 1.0}
        if page_hint and 1 <= page_hint <= n:
            for d in range(1, window + 1):
                for p in (page_hint - d, page_hint + d):
                    if 1 <= p <= n and q in self.pages[p - 1]:
                        return {"status": "exact-adjacent", "page": p, "share": 1.0}
        if q in self.full:
            return {"status": "exact-document", "page": self.page_of(q), "share": 1.0}
        qs = shingles(q)
        if qs:
            share = len(qs & self.doc_shingles) / len(qs)
        else:  # fewer than four words: compare the words themselves
            words = set(_WORD.findall(q))
            share = len([w for w in words if w in self.full]) / max(len(words), 1)
        if share >= fuzzy_threshold:
            return {"status": "fuzzy", "page": None, "share": round(share, 3)}
        return {"status": "not-found", "page": None, "share": round(share, 3)}


def verify_findings(findings: list[dict], corpus: dict[str, list[str]], file_col: str = "Source file",
                    page_col: str = "PDF page", quote_col: str = "Verbatim anchor quote", window: int = 2,
                    fuzzy_threshold: float = 0.6, progress=None) -> dict:
    """Add verification columns to every finding in place and return summary counts."""
    indexes: dict[str, DocumentIndex] = {}
    counts: dict[str, int] = {}
    missing_files: set[str] = set()
    for i, f in enumerate(findings, start=1):
        file = str(f.get(file_col, "")).strip()
        pages = corpus.get(file)
        if pages is None:
            missing_files.add(file)
            f["Verification"] = "file-not-in-corpus"
            f["Quote found in source"] = False
            f["Located page"] = None
            f["Shingle share"] = None
            counts["file-not-in-corpus"] = counts.get("file-not-in-corpus", 0) + 1
            continue
        if file not in indexes:
            indexes[file] = DocumentIndex(pages)
        try:
            hint = int(float(f.get(page_col) or 0))
        except (TypeError, ValueError):
            hint = None
        res = indexes[file].locate(str(f.get(quote_col, "")), hint, window, fuzzy_threshold)
        f["Verification"] = res["status"]
        f["Quote found in source"] = res["status"] in ("exact-page", "exact-adjacent", "exact-document", "fuzzy")
        f["Located page"] = res["page"]
        f["Shingle share"] = res["share"]
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if progress and (i % 2000 == 0 or i == len(findings)):
            progress(f"verified {i:,}/{len(findings):,}")
    total = len(findings)
    found = sum(1 for f in findings if f.get("Quote found in source"))
    return {"findings": total, "found": found, "share_found": round(found / total * 100, 2) if total else None,
            "by_status": counts, "files_not_in_corpus": sorted(missing_files)}
