"""Deterministic local providers. Replace at these boundaries for a hosted model."""

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

DIMENSIONS = 128
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "how", "i", "in", "is", "it", "of", "on", "or", "the", "to",
    "was", "were", "what", "when", "where", "which", "who", "with",
}


def terms(text: str) -> set[str]:
    return {word for word in re.findall(r"\w+", text.lower()) if len(word) > 2 and word not in STOPWORDS}


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


class AnswerProvider(Protocol):
    def answer(self, question: str, evidence: list[dict]) -> tuple[str, list[dict]]: ...


class HashEmbedding:
    """Signed feature hashing: repeatable, free, and intentionally less semantic than a model."""

    dimensions = DIMENSIONS

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        counts = Counter(terms(text))
        for word, count in counts.items():
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += (1 if digest[4] % 2 else -1) * (1 + math.log(count))
        length = math.sqrt(sum(value * value for value in vector))
        return [value / length for value in vector] if length else vector


@dataclass
class ExtractiveAnswer:
    min_overlap: float = 0.55

    def answer(self, question: str, evidence: list[dict]) -> tuple[str, list[dict]]:
        query = terms(question)
        if not query:
            return "I can't answer from the available sources.", []
        candidates = []
        for item in evidence:
            # A sentence is the smallest unit we can quote and verify.
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", item["content"]):
                sentence = sentence.strip().lstrip("-• ")
                overlap = len(query & terms(sentence)) / len(query)
                if len(query & terms(sentence)) >= min(2, len(query)) and overlap >= self.min_overlap:
                    candidates.append((overlap, item["similarity"], sentence, item))
        if not candidates:
            return "I can't answer from the available sources.", []
        _, _, sentence, item = max(candidates, key=lambda row: (row[0], row[1]))
        citation = {"document_id": item["document_id"], "title": item["title"], "section": item["section"], "quote": sentence}
        return sentence, [citation]


# Adapters live behind these protocols. A hosted implementation can be wired here
# without changing ingestion, retrieval, permissions or the HTTP contract.
embedding_provider: EmbeddingProvider = HashEmbedding()
answer_provider: AnswerProvider = ExtractiveAnswer()


def sections_from_text(text: str, suffix: str) -> list[tuple[str, str]]:
    """Keep headings as citation anchors; split long bodies at paragraph boundaries."""
    if suffix == ".pdf":
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return [section for i, paragraph in enumerate(paragraphs, 1) for section in split_section(f"Paragraph {i}", paragraph)]

    sections: list[tuple[str, str]] = []
    heading = "Introduction"
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if body:
                sections.extend(split_section(heading, "\n".join(body)))
            heading = line.lstrip("# ").strip() or "Untitled"
            body = []
        else:
            body.append(line)
    if body:
        sections.extend(split_section(heading, "\n".join(body)))
    return sections


def split_section(heading: str, body: str, max_chars: int = 900) -> list[tuple[str, str]]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in (paragraph[i:i + max_chars] for i in range(0, len(paragraph), max_chars)):
            if current and len(current) + len(piece) + 2 > max_chars:
                chunks.append(current)
                current = ""
            current = f"{current}\n\n{piece}".strip()
    if current:
        chunks.append(current)
    return [(heading if len(chunks) == 1 else f"{heading} · {i}", chunk) for i, chunk in enumerate(chunks, 1)]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
