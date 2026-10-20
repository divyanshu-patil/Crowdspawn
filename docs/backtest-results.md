# Backtest results

Two runs on six shipped indie games. Both lose to plain popularity; the second, with the scorer the app ships today, loses more clearly. The held-out scenario test in [`scenario-results.md`](scenario-results.md) points to the same cause: a city-level bias in taste lift (Polish and Swedish cities lead almost every list here).

Run on 2026-10-20 with `apps/api/scripts/backtest.py`. City-level truth is not public, so this tests **language-level** signal only.

**Proxy:** each game's Steam review share per language, divided by the mean share for mainstream Steam hits (GTA V, Elden Ring, Cyberpunk 2077), so it measures over-indexing like Qloo's lift. **Qloo ranking:** mean city spawn score per language (taste lift × PC platform fit, the shipped scorer). **Baseline-only ranking:** mean all-gamers heatmap score per language (PC, mobile and console panels: what you'd get from popularity alone). Languages compared: brazilian, english, french, german, japanese, koreana, latam, polish, swedish (9); English is the mean of 10 cities.

| Game | Comps used | Proxy top 3 | Qloo top 3 | Qloo hits in top 3 / top 5 | Qloo ρ | Baseline hits top 3 / top 5 | Baseline ρ |
|---|---|---|---|---|---|---|---|
| Hades | Dead Cells, Bastion, Transistor | latam, french, english | polish, swedish, german | 0/3 · 1/3 | -0.6 | 1/3 · 3/3 | 0.78 |
| Stardew Valley | Story of Seasons, Animal Crossing: New Horizons, Terraria | brazilian, latam, koreana | swedish, latam, koreana | 2/3 · 3/3 | 0.55 | 3/3 · 3/3 | 0.78 |
| Hollow Knight | Ori and the Blind Forest, Dead Cells, Celeste | latam, brazilian, french | polish, swedish, german | 0/3 · 1/3 | -0.53 | 2/3 · 3/3 | 0.82 |
| Celeste | Super Meat Boy, Hollow Knight, Shovel Knight | latam, brazilian, french | polish, koreana, swedish | 0/3 · 1/3 | -0.72 | 2/3 · 3/3 | 0.72 |
| Vampire Survivors | Brotato, Risk of Rain 2, Enter the Gungeon | japanese, koreana, latam | polish, swedish, german | 0/3 · 1/3 | -0.8 | 2/3 · 2/3 | 0.33 |
| Disco Elysium | Planescape: Torment, Pillars of Eternity, Divinity: Original Sin II | english, latam, polish | polish, swedish, german | 1/3 · 1/3 | -0.4 | 1/3 · 2/3 | 0.3 |

**Averages:** Qloo top-3 hits 0.5/3, top-5 1.33/3, Spearman -0.42. Baseline-only top-3 hits 1.83/3, top-5 2.67/3, Spearman 0.62. Qloo's Spearman beat the baseline in 0 of 6 games. For reference, the raw comp-set heatmap score (no baseline division) averaged top-3 hits 0.83/3 and Spearman 0.02.

## Caveats

- Steam review language is a rough proxy for where players are: it misses console players, people who review in English from non-English countries, and markets where Steam is small.
- 9 languages is a small ranking; one swap moves Spearman a lot.
- Qloo's lift compares against all gamers (PC, mobile and console panels), not Steam users specifically.
- This says nothing about city-level accuracy. Treat the city ranking as a taste-informed starting hypothesis.

## Earlier run (2026-10-16, older scorer)

Same games, comps and proxy, before the spawn score shipped: the Qloo ranking was the mean city lift against four mainstream games (Minecraft, Fortnite, GTA V, Warzone), and the baseline was that mainstream heatmap.

| Game | Comps used | Proxy top 3 | Qloo top 3 | Qloo hits in top 3 / top 5 | Qloo ρ | Baseline hits top 3 / top 5 | Baseline ρ |
|---|---|---|---|---|---|---|---|
| Hades | Dead Cells, Bastion, Transistor | latam, french, english | japanese, koreana, swedish | 0/3 · 1/3 | -0.63 | 2/3 · 3/3 | 0.65 |
| Stardew Valley | Story of Seasons, Animal Crossing: New Horizons, Terraria | brazilian, latam, koreana | japanese, english, koreana | 1/3 · 2/3 | 0.32 | 2/3 · 2/3 | 0.37 |
| Hollow Knight | Ori and the Blind Forest, Dead Cells, Celeste | latam, brazilian, french | japanese, swedish, german | 0/3 · 1/3 | -0.7 | 3/3 · 3/3 | 0.72 |
| Celeste | Super Meat Boy, Hollow Knight, Shovel Knight | latam, brazilian, french | japanese, koreana, swedish | 0/3 · 0/3 | -0.48 | 3/3 · 3/3 | 0.58 |
| Vampire Survivors | Brotato, Risk of Rain 2, Enter the Gungeon | japanese, koreana, latam | japanese, swedish, koreana | 2/3 · 2/3 | 0.27 | 1/3 · 1/3 | -0.23 |
| Disco Elysium | Planescape: Torment, Pillars of Eternity, Divinity: Original Sin II | english, latam, polish | japanese, polish, swedish | 1/3 · 2/3 | -0.05 | 1/3 · 3/3 | 0.33 |

**Averages:** Qloo top-3 hits 0.67/3, top-5 1.33/3, Spearman -0.21. Baseline-only top-3 hits 2.0/3, top-5 2.5/3, Spearman 0.4. Qloo's Spearman beat the baseline in 1 of 6 games. For reference, the raw comp-set heatmap score (no baseline division) averaged top-3 hits 0.83/3 and Spearman 0.02.
