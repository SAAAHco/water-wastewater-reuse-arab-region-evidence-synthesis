"""Load the review questions that drive the extraction.

Accepted inputs:
* a CSV file with an ``id`` column and a ``question`` column (other columns are kept as metadata);
* a Word file (.docx) in which every numbered paragraph (``1.1 Text``, ``2.3.4 Text``) is one question.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)[.):]?\s+(.+?)\s*$")


def load_questions(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _from_csv(path)
    if path.suffix.lower() == ".docx":
        return _from_docx(path)
    raise ValueError("questions must be a .csv file (columns id, question) or a .docx file with numbered paragraphs")


def _from_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    cols = {c.lower().strip(): c for c in rows[0].keys()}
    id_col = cols.get("id") or cols.get("qid") or cols.get("question id") or list(rows[0].keys())[0]
    q_col = cols.get("question") or cols.get("text") or list(rows[0].keys())[1]
    out = []
    for r in rows:
        q = (r.get(q_col) or "").strip()
        if not q:
            continue
        meta = {k: v for k, v in r.items() if k not in (id_col, q_col)}
        out.append({"id": (r.get(id_col) or "").strip(), "question": q, **meta})
    return out


def _from_docx(path: Path) -> list[dict]:
    try:
        import docx  # python-docx, optional
    except ImportError as ex:  # pragma: no cover
        raise ImportError("reading questions from .docx needs the python-docx package: pip install python-docx") from ex
    out = []
    for p in docx.Document(str(path)).paragraphs:
        m = _NUMBERED.match(p.text)
        if m:
            out.append({"id": m.group(1), "question": m.group(2)})
    return out


def write_questions_csv(questions: list[dict], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "question"])
        for q in questions:
            w.writerow([q["id"], q["question"]])
