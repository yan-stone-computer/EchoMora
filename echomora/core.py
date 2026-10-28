from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def now_ts() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


_CJK_BLOCK = re.compile(r"[\u3400-\u9fff]+")
_ASCII_WORD = re.compile(r"[a-z0-9_]{2,}")


def tokenize(text: str) -> list[str]:
    """Language-light features for a no-dependency, offline demo.

    Production should replace this with a multilingual embedding model. The hashed
    character features deliberately optimize for transparent local testing.
    """
    lowered = normalize_text(text)
    tokens = _ASCII_WORD.findall(lowered)
    for block in _CJK_BLOCK.findall(lowered):
        tokens.extend(block)
        tokens.extend(block[i : i + 2] for i in range(max(0, len(block) - 1)))
    return tokens or [lowered]


def embed(text: str, dimensions: int = 256) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return clamp(sum(a * b for a, b in zip(left, right)), -1.0, 1.0)


def freshness(created_at: float, half_life_days: float, at: float | None = None) -> float:
    age_days = max(0.0, ((at or now_ts()) - created_at) / 86400.0)
    return math.pow(0.5, age_days / max(0.1, half_life_days))


@dataclass(slots=True)
class Fact:
    kind: str
    subject: str
    predicate: str
    object: str
    text: str
    importance: float
    valence: float = 0.0
    intensity: float = 0.0
    confidence: float = 0.8
    pinned: bool = False
    owner_id: str | None = None
    visibility: str = "personal"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Extraction:
    facts: list[Fact] = field(default_factory=list)
    valence: float = 0.0
    intensity: float = 0.0
    emotion: str = "平静"
    interaction: str = "neutral"
    summary: str = ""
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": [fact.to_dict() for fact in self.facts],
            "valence": self.valence,
            "intensity": self.intensity,
            "emotion": self.emotion,
            "interaction": self.interaction,
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(slots=True)
class RecallHit:
    memory_id: str
    text: str
    kind: str
    importance: float
    similarity: float
    graph_score: float
    freshness: float
    affinity_factor: float
    score: float
    forgotten: bool
    created_at: float
    valence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def affect_label(score: float) -> str:
    if score <= -20:
        return "疏远"
    if score < 10:
        return "普通"
    if score < 30:
        return "熟悉"
    return "亲近"

