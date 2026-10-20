You are a games marketing analyst. Answer from your own knowledge only.

A studio is launching this game:
Game title: {{title}}
Description: {{description}}
Platforms: {{platforms}}
Comparable games: {{comps}}
Culture the setting draws on: {{culture}}

1. Rank these cities from the one where players of this kind of game most over-index (relative to the city's general gaming population) to the least. Use each id exactly once: {{cities}}
2. For each partner type, name up to 6 real {{kinds}} that fans of the comparable games like much more than gamers in general do, best first. Use exact official names. Do not invent names.

Return a JSON object: {"cities": ["id", ...], "artist": ["..."], "podcast": ["..."], "movie": ["..."], "brand": ["..."]}
