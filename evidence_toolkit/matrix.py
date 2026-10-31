"""Read and write evidence tables (Excel or CSV)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

COLUMNS = ["Question ID(s)", "Citation key", "Source file", "PDF page", "Place", "Finding (paraphrased)",
           "Verbatim anchor quote", "Quote found in source"]
ALIASES = {
    "Question ID(s)": ("question id(s)", "question ids", "question id", "qid", "qids", "questions"),
    "Citation key": ("citation key", "citation", "key", "reference"),
    "Source file": ("source file", "file", "document", "doc", "pdf"),
    "PDF page": ("pdf page", "page", "page number"),
    "Place": ("place", "country", "location", "geography"),
    "Finding (paraphrased)": ("finding (paraphrased)", "finding", "paraphrase", "summary", "note"),
    "Verbatim anchor quote": ("verbatim anchor quote", "quote", "anchor quote", "anchor", "quotation"),
    "Quote found in source": ("quote found in source", "verified", "found"),
}


def _rename(df: pd.DataFrame) -> pd.DataFrame:
    lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for std, names in ALIASES.items():
        if std in df.columns:
            continue
        for n in names:
            if n in lower:
                mapping[lower[n]] = std
                break
    return df.rename(columns=mapping)


def read_evidence(path: str | Path, sheet: str | int | None = None, limit: int | None = None) -> list[dict]:
    """Rows of an evidence table as dicts with the standard column names where they can be recognized."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        xl = pd.ExcelFile(path)
        name = sheet if sheet is not None else ("Evidence" if "Evidence" in xl.sheet_names else xl.sheet_names[0])
        df = xl.parse(name)
    else:
        df = pd.read_csv(path, encoding="utf-8-sig")
    df = _rename(df)
    if limit:
        df = df.head(limit)
    rows = df.to_dict(orient="records")
    for r in rows:
        for k, v in list(r.items()):
            if isinstance(v, float) and v != v:  # NaN
                r[k] = None
    return rows


def write_evidence(findings: list[dict], out_dir: str | Path, questions: list[dict] | None = None,
                   name: str = "Evidence_matrix.xlsx") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(findings)
    ordered = [c for c in COLUMNS if c in df.columns] + [c for c in df.columns if c not in COLUMNS]
    df = df[ordered] if len(df) else df
    path = out_dir / name
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Evidence", index=False)
        if questions:
            pd.DataFrame([{"Question ID": q["id"], "Question": q["question"]} for q in questions]).to_excel(
                xw, sheet_name="Questions", index=False)
    df.to_csv(out_dir / (Path(name).stem + ".csv"), index=False, encoding="utf-8-sig")
    return path


def write_coverage(findings: list[dict], questions: list[dict], out_dir: str | Path) -> Path:
    """Per question: documents and findings addressing it, and how many anchors were located."""
    out_dir = Path(out_dir)
    per: dict[str, dict] = {q["id"]: {"documents": set(), "findings": 0, "verified": 0} for q in questions}
    for f in findings:
        for qid in str(f.get("Question ID(s)", "")).split(","):
            qid = qid.strip()
            if qid in per:
                per[qid]["documents"].add(f.get("Source file"))
                per[qid]["findings"] += 1
                per[qid]["verified"] += 1 if f.get("Quote found in source") else 0
    path = out_dir / "coverage.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "question", "documents", "findings", "anchors located", "status"])
        for q in questions:
            p = per[q["id"]]
            status = "none" if p["findings"] == 0 else ("thin" if len(p["documents"]) < 3 else "covered")
            w.writerow([q["id"], q["question"], len(p["documents"]), p["findings"], p["verified"], status])
    return path


def write_flagged(findings: list[dict], out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    flagged = [f for f in findings if not f.get("Quote found in source")]
    path = out_dir / "flagged_quotes.csv"
    pd.DataFrame(flagged).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_json(data, path: str | Path) -> None:
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
