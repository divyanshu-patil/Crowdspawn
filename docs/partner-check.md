# Partner check: Qloo vs an LLM alone

For 20 games (the 10 tuning games and the first 10 held-out ones) an LLM (gemma4:31b, no Qloo data, temperature 0) and Qloo each name 6 artists, podcasts, films and brands that fans of the game's comps like more than gamers in general. Qloo's lists are built exactly as a plan builds them. Design fixed before any call. Data collected 2026-10-21; `apps/api/scripts/partner_check.py` regenerates this page.

| Type | Generic names: Qloo | Generic names: LLM | LLM names Qloo can find | Median lift: Qloo | Median lift: LLM's names | LLM's names gamers like as much (lift ≤ 1) |
|---|---|---|---|---|---|---|
| artist | 5% | 32% | 115 of 120 | ×1.096 | ×1.006 | 50 of 115 |
| podcast | 20% | 32% | 51 of 103 | ×1.126 | ×0.988 | 30 of 51 |
| movie | 3% | 15% | 107 of 113 | ×1.108 | ×0.998 | 56 of 105 |
| brand | 67% | 51% | 88 of 119 | ×1.023 | ×0.986 | 63 of 88 |

**Generic names** are the share of a method's names that it gives for 3 or more of the 20 games: the same names whatever the game. This measure doesn't use Qloo's scores.

Most repeated by the LLM: artists: aphex twin, mick gordon, carpenter brut; podcasts: hardcore history, radiolab, the daily; movies: mad max: fury road, the martian, blade runner 2049; brands: razer, logitech g, steel series.

Most repeated by Qloo: artists: square enix music, masafumi takada; podcasts: the empty bowl, wonderful!, trends like these; movies: the imposter; brands: mixer, oculus, newegg.

**Where Qloo's lists are more generic:** brands (67% vs 51%).

## Caveats

- Lift for the LLM's names is measured with Qloo's data, and Qloo chose its own list by lift, so Qloo wins that column by construction. It shows how far the LLM's picks sit from the measured audience; it is not an independent test.
- Neither list is checked against real sponsorship results. A generic name can still be a good partner; it just isn't specific to this audience.
- One LLM, one prompt, temperature 0. Names the LLM gave that Qloo couldn't resolve are counted as not found, even if they exist.
