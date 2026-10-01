"""
Splitting resume text into passages worth embedding.

Why chunk at all: a whole resume squeezed into one 384-dimension vector is an
*average* of everything in it. A single mention of Kubernetes in a five-page CV
is drowned out by four pages about something else, so the document vector can
answer "is this person roughly a fit" but not "has this person done X".

Embedding each line separately keeps that localised signal, and it gives the
recruiter a specific sentence to look at rather than a number with no
explanation.
"""

import re

# Lines shorter than this carry no usable meaning -- section headings like
# "SKILLS", a bare job title, a date range. Embedding them adds noise and
# costs time.
MIN_CHUNK_WORDS = 4

# Split a long paragraph at sentence boundaries. PDF extraction often returns
# whole paragraphs on one line, and a paragraph averaged into one vector has
# the same dilution problem as a whole document.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")

# Bullet glyphs and list markers left behind by PDF and DOCX extraction.
_LEADING_BULLET = re.compile(r"^[\s•‣▪●·*\-–—+>]+")

_WHITESPACE = re.compile(r"\s+")


def _normalise(text):
    """Strip bullet glyphs and collapse runs of whitespace."""
    text = _LEADING_BULLET.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def split_into_chunks(text, min_words=MIN_CHUNK_WORDS):
    """
    Break resume text into a list of short, meaningful passages.

    Splits on line breaks first, because resumes are mostly bullet points, then
    on sentence boundaries to catch extracted paragraphs. Passages under
    `min_words` are dropped, and repeats are removed -- a duplicated line
    cannot change a maximum similarity, so embedding it twice is wasted work.
    """
    if not text:
        return []

    chunks = []
    seen = set()

    for line in text.splitlines():
        for piece in _SENTENCE_BOUNDARY.split(line):
            piece = _normalise(piece)
            if len(piece.split()) < min_words:
                continue

            key = piece.casefold()
            if key in seen:
                continue

            seen.add(key)
            chunks.append(piece)

    return chunks
