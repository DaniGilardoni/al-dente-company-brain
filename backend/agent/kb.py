"""BM25 retrieval over backend/data/kb/*.md documents."""

import re
from pathlib import Path

from rank_bm25 import BM25Okapi

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "kb"

_docs: list[dict] = []
_bm25: BM25Okapi | None = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def _ensure_loaded() -> None:
    global _docs, _bm25
    if _docs:
        return
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        _docs.append({"id": path.stem, "content": text})
    tokenized = [_tokenize(d["content"]) for d in _docs]
    _bm25 = BM25Okapi(tokenized)


def search(query: str, top_k: int = 3) -> list[dict]:
    """Return top_k docs ranked by BM25 score. Returns full document content."""
    _ensure_loaded()
    tokens = _tokenize(query)
    scores = _bm25.get_scores(tokens)
    ranked = sorted(range(len(_docs)), key=lambda i: scores[i], reverse=True)
    results = []
    for i in ranked[:top_k]:
        if scores[i] > 0:
            results.append({
                "id": _docs[i]["id"],
                "content": _docs[i]["content"],
                "score": round(float(scores[i]), 3),
            })
    return results


def get_all() -> list[dict]:
    _ensure_loaded()
    return _docs
