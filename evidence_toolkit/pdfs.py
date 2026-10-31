"""Read the text layer of PDF files page by page, with an optional JSON cache."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pymupdf

EXTENSIONS = (".pdf",)


def read_pdf(path: str | Path) -> list[str]:
    """Text of every page of one PDF, in reading order of the text layer."""
    with pymupdf.open(str(path)) as doc:
        return [page.get_text() for page in doc]


def _fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


def load_corpus(pdf_dir: str | Path, cache_dir: str | Path | None = None, progress=None) -> dict[str, list[str]]:
    """Return ``{file name: [page texts]}`` for every PDF in ``pdf_dir``.

    When ``cache_dir`` is given, each document's pages are stored as JSON and reused while the file's size and
    modification time are unchanged.
    """
    pdf_dir = Path(pdf_dir)
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
    corpus: dict[str, list[str]] = {}
    files = sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() in EXTENSIONS)
    for i, path in enumerate(files, start=1):
        fp = _fingerprint(path)
        cpath = cache / (hashlib.md5(path.name.encode("utf-8")).hexdigest() + ".json") if cache else None
        if cpath and cpath.exists():
            try:
                data = json.loads(cpath.read_text(encoding="utf-8"))
                if data.get("fingerprint") == fp:
                    corpus[path.name] = data["pages"]
                    continue
            except (OSError, ValueError):
                pass
        try:
            pages = read_pdf(path)
        except Exception as ex:  # noqa: BLE001 - a broken file must not stop the run
            if progress:
                progress(f"cannot read {path.name}: {ex}")
            continue
        corpus[path.name] = pages
        if cpath:
            cpath.write_text(json.dumps({"fingerprint": fp, "pages": pages}), encoding="utf-8")
        if progress and (i % 20 == 0 or i == len(files)):
            progress(f"read {i}/{len(files)} files")
    return corpus


def scanned_pages(pages: list[str], min_chars: int = 40) -> list[int]:
    """Page numbers (1-based) whose text layer is empty or nearly empty, which usually means a scanned page."""
    return [i + 1 for i, text in enumerate(pages) if len(text.strip()) < min_chars]


def corpus_summary(corpus: dict[str, list[str]]) -> dict:
    n_pages = sum(len(p) for p in corpus.values())
    scanned = {f: scanned_pages(p) for f, p in corpus.items()}
    scanned = {f: s for f, s in scanned.items() if s}
    return {"documents": len(corpus), "pages": n_pages, "documents_with_scanned_pages": len(scanned), "scanned_pages": scanned}


def pages_env(env_var: str = "EVIDENCE_PDF_DIR") -> str | None:
    return os.environ.get(env_var)
