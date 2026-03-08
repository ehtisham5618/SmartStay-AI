"""Word-aware overlapping chunks for the hotel document corpus."""

from __future__ import annotations

import re
from typing import List


def chunk_text(text: str, chunk_words: int = 180, overlap_words: int = 30) -> List[str]:
    if chunk_words < 20:
        raise ValueError("chunk_words must be at least 20")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("overlap_words must be between 0 and chunk_words")

    words = re.findall(r"\S+", text.strip())
    if not words:
        return []
    step = chunk_words - overlap_words
    return [" ".join(words[start : start + chunk_words]) for start in range(0, len(words), step)]

