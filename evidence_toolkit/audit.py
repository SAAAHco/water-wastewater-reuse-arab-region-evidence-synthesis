"""Automated audits of an evidence table against the source PDFs.

1. Numeric precision: for a random sample of findings whose text contains numbers, is every number present on the
   cited page or the adjacent pages? (Years and the integers 1 to 10 are skipped as too ambiguous.)
2. Place tags: for a random sample of findings tagged with exactly one country, is that country, or a place in it,
   named on the cited or adjacent pages?
3. Coverage proxy: for a random sample of documents, what share of the numbers on each text page appears in at
   least one finding cited to that page or the two following pages?

The audits read the text layer of the PDFs; numbers that only exist inside images are invisible to them.
"""
from __future__ import annotations

import random
import re

from .places import COUNTRY_PATTERNS
from .textutil import normalize, reference_heading_offset

_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")
_YEAR = re.compile(r"(19|20)\d\d")
_PAGE_NUM = re.compile(r"(?<![\w.])(\d{2,}(?:\.\d+)?)(?![\w])")


def _norm_numbers(text: str) -> str:
    t = normalize(text)
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)
    t = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", t)
    t = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", t)
    return t


def numbers_in(text: str) -> set[str]:
    vals = set()
    for m in _NUM.finditer(_norm_numbers(text)):
        v = m.group(1)
        if _YEAR.fullmatch(v) or v in {str(i) for i in range(1, 11)}:
            continue
        vals.add(v)
    return vals


def _present(v: str, text: str) -> bool:
    if v in text:
        return True
    try:
        fv = float(v)
    except ValueError:
        return False
    alts = {f"{fv:g}", f"{fv:.0f}", f"{fv:.1f}", f"{fv:.2f}", f"{fv / 1000:g}", f"{fv * 1000:g}", f"{fv / 1e6:g}",
            f"{fv * 100:g}", f"{fv / 100:g}"}
    return any(re.search(r"(?<![\d.])" + re.escape(a) + r"(?![\d])", text) for a in alts if a)


def _page_text(pages: list[str], page: int, span: int = 1) -> str:
    n = len(pages)
    return "\n".join(pages[p] for p in range(max(0, page - 1 - span), min(n, page + span)))


def _finding_text(f: dict, finding_col: str, quote_col: str) -> str:
    return str(f.get(finding_col) or "") or str(f.get(quote_col) or "")


def _page(f: dict, page_col: str) -> int | None:
    try:
        return int(float(f.get(page_col)))
    except (TypeError, ValueError):
        return None


def numeric_precision(findings: list[dict], corpus: dict[str, list[str]], n: int = 600, seed: int = 1,
                      file_col: str = "Source file", page_col: str = "PDF page", finding_col: str = "Finding (paraphrased)",
                      quote_col: str = "Verbatim anchor quote") -> dict:
    rng = random.Random(seed)
    pool = [f for f in findings if f.get(file_col) in corpus and _page(f, page_col) and numbers_in(_finding_text(f, finding_col, quote_col))]
    sample = rng.sample(pool, min(n, len(pool)))
    rows = []
    for f in sample:
        txt = _norm_numbers(_page_text(corpus[f[file_col]], _page(f, page_col)))
        vals = numbers_in(_finding_text(f, finding_col, quote_col))
        found = [v for v in vals if _present(v, txt)]
        rows.append({"file": f[file_col], "page": _page(f, page_col), "numbers": len(vals), "found": len(found),
                     "missing": sorted(set(vals) - set(found))[:5]})
    checked = len(rows)
    all_found = sum(1 for r in rows if r["found"] == r["numbers"])
    n_total = sum(r["numbers"] for r in rows)
    n_found = sum(r["found"] for r in rows)
    return {"findings_checked": checked, "findings_all_numbers_found": all_found,
            "share_findings_all_found": round(all_found / checked * 100, 1) if checked else None,
            "numbers_checked": n_total, "numbers_found": n_found,
            "share_numbers_found": round(n_found / n_total * 100, 1) if n_total else None,
            "examples_missing": [r for r in rows if r["found"] < r["numbers"]][:15]}


def country_tags(findings: list[dict], corpus: dict[str, list[str]], n: int = 600, seed: int = 2,
                 file_col: str = "Source file", page_col: str = "PDF page", place_col: str = "Place",
                 patterns: dict[str, str] | None = None) -> dict:
    pats = {k: re.compile(v, re.I) for k, v in (patterns or COUNTRY_PATTERNS).items()}
    rng = random.Random(seed)

    def one_country(place: str):
        hits = [c for c, p in pats.items() if p.search(place)]
        return hits[0] if len(hits) == 1 else None

    pool = [f for f in findings if f.get(file_col) in corpus and _page(f, page_col) and one_country(str(f.get(place_col) or ""))]
    sample = rng.sample(pool, min(n, len(pool)))
    ok, missing = 0, []
    for f in sample:
        c = one_country(str(f.get(place_col)))
        txt = _page_text(corpus[f[file_col]], _page(f, page_col))
        if pats[c].search(txt):
            ok += 1
        else:
            missing.append({"file": f[file_col], "page": _page(f, page_col), "place": str(f.get(place_col))[:60]})
    checked = len(sample)
    return {"findings_checked": checked, "country_found_on_page": ok,
            "share": round(ok / checked * 100, 1) if checked else None, "examples_missing": missing[:15]}


def coverage_proxy(findings: list[dict], corpus: dict[str, list[str]], n_docs: int = 20, seed: int = 3,
                   file_col: str = "Source file", page_col: str = "PDF page", finding_col: str = "Finding (paraphrased)",
                   quote_col: str = "Verbatim anchor quote", min_chars: int = 300) -> dict:
    rng = random.Random(seed)
    docs = sorted({f.get(file_col) for f in findings if f.get(file_col) in corpus})
    sample = rng.sample(docs, min(n_docs, len(docs)))
    per_doc = []
    for file in sample:
        pages = corpus[file]
        mine = [f for f in findings if f.get(file_col) == file and _page(f, page_col)]
        total = caught = checked = 0
        for p in range(len(pages)):
            txt = pages[p]
            if reference_heading_offset(txt) is not None or len(txt) < min_chars:
                continue
            on_page = set()
            for m in _PAGE_NUM.finditer(_norm_numbers(txt)):
                v = m.group(1)
                if _YEAR.fullmatch(v) or len(v) > 7:
                    continue
                on_page.add(v)
            if not on_page:
                continue
            checked += 1
            in_findings = set()
            for f in mine:
                if p + 1 <= _page(f, page_col) <= p + 3:
                    in_findings |= numbers_in(_finding_text(f, finding_col, quote_col))
            total += len(on_page)
            caught += sum(1 for v in on_page if v in in_findings)
        per_doc.append({"document": file, "pages": len(pages), "pages_checked": checked, "numbers_on_pages": total,
                        "captured": caught, "share": round(caught / total * 100, 1) if total else None,
                        "findings": len(mine)})
    shares = sorted(d["share"] for d in per_doc if d["share"] is not None)
    median = (shares[len(shares) // 2] if len(shares) % 2 else (shares[len(shares) // 2 - 1] + shares[len(shares) // 2]) / 2) if shares else None
    median = round(median, 1) if median is not None else None
    return {"documents": len(per_doc), "median_share": median, "min": min(shares) if shares else None,
            "max": max(shares) if shares else None, "per_document": per_doc}


def run_all(findings: list[dict], corpus: dict[str, list[str]], n: int = 600, n_docs: int = 20, seed: int = 1, **cols) -> dict:
    return {"numeric_precision": numeric_precision(findings, corpus, n, seed, **{k: v for k, v in cols.items() if k in ("file_col", "page_col", "finding_col", "quote_col")}),
            "country_tags": country_tags(findings, corpus, n, seed + 1, **{k: v for k, v in cols.items() if k in ("file_col", "page_col", "place_col")}),
            "coverage_proxy": coverage_proxy(findings, corpus, n_docs, seed + 2, **{k: v for k, v in cols.items() if k in ("file_col", "page_col", "finding_col", "quote_col")})}


def summary_markdown(results: dict) -> str:
    npv, ct, cov = results["numeric_precision"], results["country_tags"], results["coverage_proxy"]
    lines = ["# Audit summary", "",
             f"- Numeric precision: {npv['findings_all_numbers_found']} of {npv['findings_checked']} sampled findings "
             f"({npv['share_findings_all_found']}%) had every number on the cited or adjacent pages; "
             f"{npv['numbers_found']} of {npv['numbers_checked']} numbers ({npv['share_numbers_found']}%) were found.",
             f"- Place tags: {ct['country_found_on_page']} of {ct['findings_checked']} sampled findings ({ct['share']}%) "
             f"name the tagged country, or a place in it, on the cited or adjacent pages.",
             f"- Coverage proxy: median {cov['median_share']}% of the numeric statements on the text pages of "
             f"{cov['documents']} sampled documents appear in a finding (range {cov['min']} to {cov['max']}%).", ""]
    return "\n".join(lines)
