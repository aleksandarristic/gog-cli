"""Shared fuzzy title matching, used by `list --search`, `search`, and game selectors."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any


def search_key(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def best_fuzzy_ratio(query: str, candidate: str) -> float:
    choices = [candidate, *candidate.split()]
    words = candidate.split()
    if len(words) > 1:
        choices.extend(
            f"{left} {right}" for left, right in zip(words, words[1:], strict=False)
        )
    return max(SequenceMatcher(None, query, choice).ratio() for choice in choices)


def title_search_score(query: str, game: dict[str, Any]) -> int:
    normalized_query = search_key(query)
    if not normalized_query:
        return 0

    title = search_key(game.get("title", ""))
    slug = search_key(str(game.get("slug", "")).replace("_", " ").replace("-", " "))
    candidates = [candidate for candidate in (title, slug) if candidate]
    if not candidates:
        return 0

    scores: list[int] = []
    for candidate in candidates:
        if candidate == normalized_query:
            scores.append(1000)
        elif candidate.startswith(normalized_query):
            scores.append(900 - min(len(candidate) - len(normalized_query), 100))
        elif normalized_query in candidate:
            scores.append(800 - min(candidate.index(normalized_query), 100))
        else:
            ratio = best_fuzzy_ratio(normalized_query, candidate)
            if ratio >= 0.78:
                scores.append(int(ratio * 700))
    return max(scores, default=0)
