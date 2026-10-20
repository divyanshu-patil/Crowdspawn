# Audience check

Does Qloo's audience skew match an independent survey? For 10 genres we compare Qloo's female index (`urn:demographics`, over- or under-index vs average) for a panel of well-known games with the female share of each genre's players in Quantic Foundry's 2017 survey of about 270,000 gamers, as [reported by Game Informer](https://gameinformer.com/b/news/archive/2017/01/21/study-breaks-down-game-genre-playerbases-by-gender.aspx). The genres, panels and metric were fixed before any call. Qloo data collected 2026-10-20; `apps/api/scripts/audience_check.py` regenerates this page.

**Spearman ρ between Qloo's female index and the survey: 0.997** (10 genres; Qloo orders them as the survey does, with only the survey's 69/69 tie split). An LLM's guess of each share (gemma4:31b, no Qloo data): ρ 0.991.

| Genre | Survey: % female | Qloo female index | Qloo panel | LLM guess % |
|---|---|---|---|---|
| Match 3 | 69 | +0.37 | Candy Crush Saga, Bejeweled 3 | 70.0 |
| Family/Farm Sim | 69 | +0.50 | Stardew Valley, The Sims 4, Unpacking, Spiritfarer | 75.0 |
| Casual Puzzle | 42 | +0.10 | Cut the Rope, Monument Valley | 65.0 |
| Atmospheric Exploration | 41 | +0.10 | Journey, Firewatch, Gone Home | 45.0 |
| High Fantasy MMO | 36 | -0.08 | World of Warcraft, Final Fantasy XIV Online, Lost Ark, Black Desert Online | 35.0 |
| Sci-Fi MMO | 16 | -0.28 | EVE Online, Star Wars: The Old Republic, Star Trek Online | 20.0 |
| Fighting | 13.4 | -0.29 | Tekken 7, Street Fighter 6, Mortal Kombat 11, Dragon Ball FighterZ | 15.0 |
| Racing | 6 | -0.39 | Forza Horizon 5, Gran Turismo 7, Need for Speed Heat, Asphalt 9: Legends | 15.0 |
| Tactical Shooter | 4 | -0.43 | Tom Clancy's Rainbow Six Siege, Counter-Strike: Global Offensive, Arma 3 | 10.0 |
| Sports | 2 | -0.48 | EA Sports FC 24, NBA 2K24, Rocket League | 10.0 |

## Caveats

- Ten genres, one survey. The survey is from 2017, self-selected, and Game Informer lists 10 of its 23 genres.
- Qloo's index is relative to its average audience, not a share; only the order is compared.
- The panels are a few famous games per genre, not the survey's own definition of each genre. Qloo found no match for Farm Heroes Saga, Two Dots, so those panels have two games.
- An LLM may have read this survey; a match there is recall, not measurement. Qloo's index is measured for whatever comp set a studio picks, including combinations no survey covers.
