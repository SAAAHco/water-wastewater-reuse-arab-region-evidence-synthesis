"""Text normalization, tokenization, sentence splitting and word shingles.

Everything that compares a quotation with a document goes through ``normalize`` so that curly quotation marks,
dashes, soft hyphens, line-end hyphenation and runs of white space do not break a match.
"""
from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    """a about above across after again against all also among an and any are around as at be been being below
    between both but by can could did do does down during each few for from further had has have having he her here
    hers him his how i if in into is it its itself just may me might more most must my no nor not now of off on once
    only or other our ours out over own per same shall she should so some such than that the their theirs them then
    there these they this those through to too under until up upon us very via was we were what when where whether
    which while who whom whose why will with within without would you your yours""".split()
)

_REPLACEMENTS = {
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "­": "", "ﬁ": "fi", "ﬂ": "fl",
}
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_SPACES = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def normalize(text: str | None) -> str:
    """Unify quotation marks, dashes and spacing; join words hyphenated at a line break."""
    text = unicodedata.normalize("NFKC", text or "")
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    return _SPACES.sub(" ", text).strip()


def fold(text: str | None) -> str:
    """Normalized, lower-case text for matching."""
    return normalize(text).lower()


def stem(token: str) -> str:
    """Light suffix stripping so that plural and inflected forms match (reuses, reused, reusing -> reus)."""
    if any(ch.isdigit() for ch in token) or len(token) < 4:
        return token
    if token.endswith("ies") and len(token) >= 5:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) >= 6:
        return token[:-3]
    if token.endswith("ed") and len(token) >= 5:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str | None, stopwords: frozenset = STOPWORDS) -> list[str]:
    """Lower-case, lightly stemmed word and number tokens without stop words or single characters."""
    return [stem(t) for t in _TOKEN.findall((text or "").lower()) if len(t) > 1 and t not in stopwords]


_WORD = re.compile(r"[a-z0-9]+(?:[.,'][a-z0-9]+)*")


def sentences(text: str) -> list[str]:
    """Split normalized text into sentences at a full stop, exclamation or question mark followed by a capital."""
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def word_count(text: str) -> int:
    return len(text.split())


REFERENCE_HEADINGS = frozenset({"references", "reference list", "bibliography", "literature cited", "works cited", "references cited"})
_LEADING_NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[ivx]+[.)])\s+", re.I)


def reference_heading_offset(text: str, max_len: int = 40) -> int | None:
    """Character offset of a line that is only a reference-list heading (``References``, ``7. Bibliography``), else None."""
    pos = 0
    for line in (text or "").splitlines(keepends=True):
        stripped = line.strip()
        if 0 < len(stripped) <= max_len:
            core = _LEADING_NUMBER.sub("", stripped).strip().rstrip(".:").lower()
            if core in REFERENCE_HEADINGS:
                return pos
        pos += len(line)
    return None


def shingles(text: str, n: int = 4) -> set[tuple[str, ...]]:
    """Set of ``n``-word sequences of the folded text, punctuation ignored."""
    words = _WORD.findall(fold(text))
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}
