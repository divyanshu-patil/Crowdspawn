# Accuracy scenarios

Qloo data collected 2026-10-16; Google Trends truth fetched 2026-10-16 (interest by country, last 5 years). Scripts: `apps/api/scripts/scenarios.py`, `fetch_trends_truth.py`.

**Method.** Ten independent hypothetical games, each with its own comps and, when the game has a setting, culture anchors (films, shows, artists) resolved through Qloo search. Each truth is a *real shipped game* that is never used as a comp and is removed from the expanded signal. Every candidate city is scored; country score = mean of its cities. Truth = Google Trends interest for the analogue, restricted to candidate countries. ρ = Spearman over candidate countries with Trends data (needs ≥ 5).

## Scorers compared

| Scorer | What it ranks by | Truth #1 is our #1 | Truth #1 in our top 3 | Mean ρ |
|---|---|---|---|---|
| `original` | comp fans ÷ mainstream gamers (Minecraft, Fortnite, GTA V, Warzone): the old ranking | 2/10 | 5/10 | 0.5 |
| `presence` | comp-fan affinity alone | 1/10 | 5/10 | 0.35 |
| `lift` | comp fans ÷ all gamers (mean of PC, mobile, console panels) | 2/10 | 5/10 | 0.57 |
| `lift×platform` | lift × platform fit | 3/10 | 6/10 | 0.55 |
| `lift×culture` | lift × culture fit | 5/10 | 8/10 | 0.43 |
| `spawn score` (shipped) | lift × platform fit × culture fit | 6/10 | 8/10 | 0.45 |

## Per scenario (`spawn score`)

| Scenario | Platforms | Comps | Culture anchors | Truth analogue | Truth top 3 | Our top 3 | Our #1 city | Top-3 hit | ρ |
|---|---|---|---|---|---|---|---|---|---|
| Delhi Gullies: open-world crime game set in the streets of Delhi | pc, console | Grand Theft Auto V, Sleeping Dogs, Watch Dogs 2, Mafia III, Saints Row | Gully Boy, 3 Idiots, Arijit Singh, Sacred Games | Mumbai Gullies | IN, US, CA | IN, AE, SG | Mumbai | yes | n/a |
| Neon Kabukicho: a story-driven street brawler set in Tokyo's nightlife district | console, pc | Judgment, Shenmue III, SIFU | Spirited Away, Attack on Titan | Yakuza (series) | JP, KR, SG | JP, KR, SG | Tokyo | yes | 0.53 |
| Leshy: a dark fantasy RPG built on Slavic folklore | pc, console | Gothic, Dragon Age: Inquisition, The Elder Scrolls V: Skyrim | Dawid Podsiadło, Sanah, Corpus Christi | The Witcher 3: Wild Hunt | PL, CZ, SE | PL, JP, CA | Warsaw | yes | 0.1 |
| Hanok Online: a fantasy MMORPG from a Seoul studio | pc | Guild Wars 2, The Elder Scrolls Online | BTS, Parasite, Squid Game | Lost Ark | KR, CA, SG | PH, SG, KR | Manila | yes | 0.6 |
| Sultan's March: a medieval sandbox of battles and politics in Anatolia | pc | Total War: Three Kingdoms, Chivalry 2, Crusader Kings III | Tarkan, Resurrection: Ertugrul, The Magnificent Century | Mount & Blade II: Bannerlord | TR, KR, SE | TR, AE, IN | Istanbul | yes | 0.18 |
| Moss Hollow: a cozy farming and village life sim | pc, console, mobile | Story of Seasons: Friends of Mineral Town, Animal Crossing: New Horizons, Rune Factory 4 | none | Stardew Valley | CA, KR, PH | JP, GB, CA | Tokyo | yes | 0.38 |
| Swarmline: a cheap, fast bullet-heaven roguelite | pc, console, mobile | Brotato, Risk of Rain 2, Enter the Gungeon | none | Vampire Survivors | JP, KR, CA | JP, SE, GB | Tokyo | yes | 0.58 |
| Lane Legends: a 5v5 mobile MOBA with 10-minute matches | mobile | League of Legends, Dota 2, Arena of Valor | none | Mobile Legends: Bang Bang | PH, ID, SG | TR, PL, CZ | Istanbul | no | 0.87 |
| Touchline: a deep football club management sim | pc | Out of the Park Baseball 24, Motorsport Manager, EA Sports FC 24 | none | Football Manager (series) | KR, TR, GB | TR, IN, ID | Delhi | no | 0.26 |
| Long Haul: a relaxing long-distance trucking sim | pc | Farming Simulator 22, SnowRunner, BeamNG.drive | none | Euro Truck Simulator 2 | TR, PL, CZ | TR, PL, IN | Istanbul | yes | 0.56 |

## Caveats

- Google Trends measures search interest share per country, not downloads or sales.
- Truth is country level; cities within a country are averaged.
- Candidate countries are the app's 21 markets, so places like Russia, Pakistan or Romania that top some Trends lists are outside the ranking.
- Ten scenarios is a small sample, and the scorer weights were chosen on these same scenarios: treat the numbers as a sanity check, not a validation.
