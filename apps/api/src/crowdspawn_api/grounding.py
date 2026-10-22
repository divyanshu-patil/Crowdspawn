"""Validates a brief against the plan's Qloo results (L7). Returns a list of human-readable errors."""

import re

from .pipeline.cities import regions
from .pipeline.resolve import normalize
from .schemas import BriefSection

CITE = re.compile(r"\[(q\d+(?:\s*,\s*q\d+)*)\]")  # [q3] or [q3, q4]
BOLD = re.compile(r"\*\*(.+?)\*\*")
NUMBER = re.compile(r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?")
# Qloo reports indexes, never headcounts: "3 million gamers" is invented even though 3 is a small count.
HEADCOUNT = re.compile(r"\d[\d,.]*\s*(?:million|billion|thousand|mn|bn)\b", re.IGNORECASE)
# Cities outside the candidate list, so an invented one is caught even if not bolded.
EXTRA_CITIES = (
    "Amsterdam",
    "Atlanta",
    "Bangkok",
    "Barcelona",
    "Beijing",
    "Boston",
    "Buenos Aires",
    "Cairo",
    "Copenhagen",
    "Dallas",
    "Delhi",
    "Denver",
    "Dubai",
    "Dublin",
    "Helsinki",
    "Hong Kong",
    "Houston",
    "Istanbul",
    "Jakarta",
    "Kyiv",
    "Lagos",
    "Lima",
    "Lisbon",
    "Madrid",
    "Manila",
    "Melbourne",
    "Miami",
    "Milan",
    "Montreal",
    "Moscow",
    "Mumbai",
    "Munich",
    "Osaka",
    "Oslo",
    "Philadelphia",
    "Portland",
    "Prague",
    "Rome",
    "San Diego",
    "Santiago",
    "Shanghai",
    "Taipei",
    "Vancouver",
    "Vienna",
    "Zurich",
    "Bogota",
    "Brisbane",
    "Auckland",
    "Kuala Lumpur",
    "Hamburg",
)


SENTENCE = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    """Split at sentence ends, but never inside a **bold name** such as **L.A. Noire** or **Where Should We Begin?**."""
    out: list[str] = []
    for part in SENTENCE.split(text):
        if out and out[-1].count("**") % 2:
            out[-1] += " " + part
        else:
            out.append(part)
    return out


def _to_float(token: str) -> float:
    return float(token.replace("$", "").replace(",", "").replace("%", ""))


def mentions(text: str, cities: set[str]) -> set[str]:
    return {c for c in cities if re.search(rf"\b{re.escape(c)}\b", text, re.IGNORECASE)}


def city_numbers(lines: list[str], cities: set[str]) -> dict[float, set[str]]:
    """Number -> the cities Qloo reported it for. Numbers also seen with no city are free and left out."""
    owners: dict[float, set[str]] = {}
    free: set[float] = set()
    for line in lines:
        named = mentions(line, cities)
        for n in NUMBER.findall(line):
            v = round(_to_float(n), 2)
            if named:
                owners.setdefault(v, set()).update(named)
            else:
                free.add(v)
    return {v: c for v, c in owners.items() if v not in free}


def misattributed(text: str, owners: dict[float, set[str]], cities: set[str]) -> list[str]:
    """A sentence that names a city but quotes a number Qloo only reported for other cities."""
    errors = []
    for sentence in sentences(text):
        named = mentions(sentence, cities)
        if not named:
            continue
        for n in NUMBER.findall(sentence):
            v = _to_float(n)
            if v.is_integer() and v <= 10:  # ranks and counts
                continue
            who = owners.get(round(v, 2))
            if who and not who & named:
                errors.append(
                    f"{n} belongs to {', '.join(sorted(who))}, not {', '.join(sorted(named))}"
                )
    return errors


def validate(
    sections: list[BriefSection],
    *,
    trace_ids: set[str],
    plan_cities: set[str],
    known_names: set[str],
    allowed_numbers: set[float],
    city_owners: dict[float, set[str]] | None = None,
    cite: bool = True,  # False where the facts carry no result ids (scout answers)
) -> list[str]:
    errors: list[str] = []
    known = {normalize(n) for n in known_names | plan_cities}
    plan_city_norm = {normalize(c) for c in plan_cities}
    gazetteer = {normalize(r.name) for r in regions().values()} | {
        normalize(c) for c in EXTRA_CITIES
    }

    for s in sections:
        text = f"{s.heading}\n{s.body}"
        cites = [c.strip() for g in CITE.findall(text) for c in g.split(",")]
        errors += [f"unknown citation [{c}]" for c in cites if c not in trace_ids]
        bolds = BOLD.findall(text)
        errors += [f"unknown name **{b}**" for b in bolds if normalize(b) not in known]

        plain = normalize(BOLD.sub(" ", CITE.sub(" ", text)))
        for city in gazetteer - plan_city_norm:
            if re.search(rf"\b{re.escape(city)}\b", plain):
                errors.append(f"city not in results: {city}")

        errors += [f"headcount not in results: {h}" for h in HEADCOUNT.findall(text)]
        if city_owners:
            errors += misattributed(CITE.sub(" ", s.body), city_owners, plan_cities)
        numbers = NUMBER.findall(BOLD.sub(" ", CITE.sub(" ", text)))
        for n in numbers:
            v = _to_float(n)
            small_count = v.is_integer() and v <= 10 and "%" not in n and "$" not in n
            if not small_count and not any(abs(v - a) < 0.006 for a in allowed_numbers):
                errors.append(f"number not in results: {n}")

        if (
            cite
            and (bolds or any(not _to_float(n).is_integer() or _to_float(n) > 10 for n in numbers))
            and not cites
        ):
            errors.append(f"section '{s.heading}' makes claims without a citation")
    return errors
