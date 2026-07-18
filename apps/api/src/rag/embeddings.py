import hashlib
import math
import re
import unicodedata
from collections.abc import Sequence

_TOKEN = re.compile(r"\w+", re.UNICODE)


class HashingEmbedding:
    """Deterministic, dependency-free lexical embedding suitable for offline RAG."""

    name = "hashing-v1"

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 32:
            raise ValueError("dimension must be at least 32")
        self.dimension = dimension

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        tokens = _TOKEN.findall(normalized)
        features = tokens + [
            f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False)
        ]
        vector = [0.0] * self.dimension
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector
