"""S1: resolve comp names to Qloo video game entities."""

import re
import unicodedata
from difflib import SequenceMatcher

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9"}
MATCH_THRESHOLD = 0.9


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    tokens = re.sub(r"[^a-z0-9]+", " ", s).split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    return " ".join(ROMAN.get(t, t) for t in tokens)


def name_matches(query: str, candidate: str) -> bool:
    a, b = normalize(query), normalize(candidate)
    return a == b or SequenceMatcher(None, a, b).ratio() >= MATCH_THRESHOLD
