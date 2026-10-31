"""Optional reader that lets you plug in any text-generation model you run or subscribe to.

The reader sends each document, in segments with ``[PAGE n]`` markers, together with the full question list, to a
chat-completion endpoint and expects a JSON array of findings back. Nothing returned is trusted as such: every
quotation is afterwards located in the PDF by ``verify.py``, and quotations that cannot be found are flagged.

Configuration (environment variables or command-line options):
* ``EVIDENCE_LLM_URL``   full URL of the chat-completion route of your server, e.g. ``http://localhost:11434/v1/chat/completions``
* ``EVIDENCE_LLM_MODEL`` model name as your server expects it
* ``EVIDENCE_LLM_KEY``   bearer token if your server needs one (optional)

The request body follows the widely used ``{"model": ..., "messages": [{"role": ..., "content": ...}]}`` convention
and the reply is read from ``choices[0].message.content``. Local servers and most hosted services accept this form.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .places import tag_place

INSTRUCTION = (
    "You are helping a literature review. You receive one document with [PAGE n] markers and a numbered list of "
    "questions. For each question that the document answers, return one object per distinct piece of evidence with "
    "these fields: \"qid\" (the question identifier), \"quote\" (8 to 60 consecutive words copied exactly from the "
    "document; do not paraphrase, shorten with ellipses or correct anything), \"page\" (the number in the nearest "
    "[PAGE n] marker before the quote), \"place\" (the country, site or region the evidence refers to, or an empty "
    "string), and \"note\" (one sentence saying what the quote shows for the question). Most questions will have no "
    "evidence in a given document; return only evidence that answers a question. If the document answers nothing, "
    "return []. Output only a JSON array, without code fences or commentary."
)


def segments(pages: list[str], max_chars: int = 60_000) -> list[str]:
    """The document as text blocks with ``[PAGE n]`` markers, split at page boundaries into pieces of at most ``max_chars``."""
    blocks = [f"[PAGE {i}]\n{text.strip()}\n" for i, text in enumerate(pages, start=1)]
    out, current = [], ""
    for block in blocks:
        if len(block) > max_chars:
            block = block[:max_chars]
        if current and len(current) + len(block) > max_chars:
            out.append(current)
            current = ""
        current += block
    if current:
        out.append(current)
    return out


def question_block(questions: list[dict]) -> str:
    return "\n".join(f"{q['id']}: {q['question']}" for q in questions)


def parse_items(text: str) -> list[dict]:
    """The JSON array in a model reply, tolerant of code fences and surrounding prose."""
    if not text:
        return []
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.M)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return []
    items = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict):
            continue
        quote = str(it.get("quote", "")).strip()
        qid = str(it.get("qid", "")).strip()
        if not quote or not qid:
            continue
        try:
            page = int(it.get("page", 0))
        except (TypeError, ValueError):
            page = 0
        items.append({"qid": qid, "quote": quote, "page": page, "place": str(it.get("place", "")).strip(),
                      "note": str(it.get("note", "")).strip()})
    return items


def call_endpoint(url: str, model: str, system: str, user: str, key: str | None = None, timeout: int = 300,
                  retries: int = 3) -> str:
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                reply = json.loads(resp.read().decode("utf-8"))
            return reply["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as ex:
            last_error = ex
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"endpoint call failed after {retries} attempts: {last_error}")


def extract(corpus: dict[str, list[str]], questions: list[dict], url: str | None = None, model: str | None = None,
            key: str | None = None, max_chars: int = 60_000, citation_map: dict[str, str] | None = None,
            progress=None) -> list[dict]:
    url = url or os.environ.get("EVIDENCE_LLM_URL")
    model = model or os.environ.get("EVIDENCE_LLM_MODEL")
    key = key or os.environ.get("EVIDENCE_LLM_KEY")
    if not url or not model:
        raise ValueError("the endpoint reader needs EVIDENCE_LLM_URL and EVIDENCE_LLM_MODEL (or --url and --model)")
    citation_map = citation_map or {}
    qblock = question_block(questions)
    known = {q["id"] for q in questions}
    findings = []
    for i, (file, pages) in enumerate(corpus.items(), start=1):
        for seg in segments(pages, max_chars):
            user = f"QUESTIONS\n{qblock}\n\nDOCUMENT: {file}\n{seg}"
            try:
                reply = call_endpoint(url, model, INSTRUCTION, user, key)
            except RuntimeError as ex:
                if progress:
                    progress(f"{file}: {ex}")
                continue
            for it in parse_items(reply):
                if it["qid"] not in known:
                    continue
                page = it["page"] if 1 <= it["page"] <= len(pages) else 0
                findings.append({
                    "Question ID(s)": it["qid"],
                    "Citation key": citation_map.get(file, Path(file).stem),
                    "Source file": file,
                    "PDF page": page,
                    "Place": it["place"] or tag_place(it["quote"], pages[page - 1] if page else ""),
                    "Finding (paraphrased)": it["note"],
                    "Verbatim anchor quote": it["quote"],
                })
        if progress:
            progress(f"document {i}/{len(corpus)}: {file}")
    return findings
