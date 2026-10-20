# How Crowdspawn works

## What it's for

You're a small indie studio about to launch a game with a small marketing budget. You need to know **where to spend it** (which cities for ads, meetups and events) and **who to team up with** (which musicians, podcasts and brands your future players already like).

Store tags like "roguelike" or "cozy" describe your game, not the people who'd play it. Crowdspawn answers the people question using **Qloo**, a "taste" database that knows, from real consumption data, what fans of one thing also like and where they are.

The idea in one line: **find where your players already are, and who else they love, before launch day.**

## How you use it

1. **Describe your game:** title, a short description, a few genre tags.
2. **Pick 1–5 comparable games ("comps"):** existing games your players probably love, like Stardew Valley for a cozy farming game. Your new game usually isn't in Qloo yet, so the app works through these. You can search for them, or click "Suggest for me" and an AI proposes some.
3. **Say where it's set (optional):** if your game draws on a real place, add a few films, shows or artists from there (Gully Boy, Sacred Games, Divine for a game set in Delhi). "Suggest from my description" proposes some; Qloo must find each one. Also pick your platforms (PC, console, mobile).
4. **Pick cities and an optional budget,** for example the 18 default cities and $5,000. You can also add your previous game to see how your current players differ from the new target audience.
5. **Watch it build.** A live progress log ticks through the steps, with a counter of Qloo calls.
6. **Get your plan:** a map and ranked list of cities, the audience profile, partners, a budget split, and a written brief.

## What happens behind the scenes

The API runs eight steps in order, each using the previous step's results:

| Step | What it does | In plain words |
|---|---|---|
| S1 | Checks your comps exist in Qloo | Makes sure the games are real |
| S2 | Asks Qloo for ~20 similar games | "Fans of these also love Loop Hero, Hollow Knight…", with Qloo's reasons |
| S3 | Scores every city on three things | Taste (fans of your games vs gamers in general), platform (how big your platforms are there) and culture (where fans of your setting's films and music are) |
| S4 | Gets the audience's age and gender | e.g. "skews female, 25–29" |
| S5 | Finds partners | Artists, podcasts, films and brands this audience over-indexes on, worldwide and in the top 3 cities |
| S6 | Compares with your last game (optional) | Tastes you share vs. new ground |
| S7 | Splits the budget | Plain math: more money to cities with a higher spawn score and confidence |
| S8 | Writes the brief | An AI turns the results into readable advice |

### The key idea: the spawn score

Big cities have lots of gamers of every kind, so a raw count would always put New York first. Crowdspawn multiplies three ratios, each around 1.0:

- **Taste lift:** fans of your comps in the city ÷ gamers in general there (the average of PC, console and mobile player panels). 1.05 means slightly more fans than usual.
- **Platform fit:** how strong your platforms are in the city compared with gaming overall. Console games drop in PC- and mobile-first markets.
- **Culture fit:** how concentrated fans of your setting's films, shows and artists are in the city, compared with the average city. Only used when you name a setting.

**Mumbai at 2.49** for Delhi Gullies = taste 1.05 × platform 0.97 × culture 2.45. Below 1 means under-represented. The map's crowd size shows it: one lit tile per +0.02.

On 23 held-out games with no home-country setting, frozen before scoring, Google Trends' top country for a real shipped game like each one was Crowdspawn's #1 in 1 of 23; an LLM with no Qloo data got 4 of 23 and plain popularity 0 of 23. The ranking has a city bias (Stockholm came first for 9 of the 23 games). It does better when a game has a real-world setting, where culture anchors carry the signal. Details: [`scenario-results.md`](scenario-results.md).

## The launch agent

`/agent` is the same engine run by an agent. You describe your game and your question; the agent decides what to do next, one Qloo tool at a time: search for comparable games, look up the culture your game draws on, rank cities, scout the top one, read the audience, find partners, then answer. You watch every step live. It can only use what the tools returned, so it can't invent a city or a number, and it can hand its picks straight to a full launch plan.

## The region scout

`/scout` answers the reverse question: given a place, what works there?

- **Hover a country** for its gamer taste match: how strongly people in its main cities match well-known PC, console and mobile games in Qloo's data, out of 100. It is a taste score, not a player count (Qloo has no player counts).
- **Click a spot or search a town.** A ring marks a 40 km area (widened to 120 km between towns). You get the genres whose fans over-index there, the games locals love, and the platform mix.
- **Check your game:** add comps and platforms to get a verdict for that exact spot.

## The rules that make it trustworthy

- **Qloo is the only source of facts.** Every city, number and partner traces back to a specific Qloo call. Small chips like `q21` in the brief link to the trace page, which lists every call the plan made.
- **The AI only writes words.** It never invents cities or numbers. A checker reads the brief and rejects anything not in Qloo's results, such as an invented city, a made-up percentage or a missing citation. If the AI fails twice, a plain template brief is shown instead.
- **It fails safely.** Without a Qloo key (or with a wrong one) the app refuses to make a plan rather than guess, and shows an error screen. This is the "kill switch" you can show in the demo.
- **It's honest about accuracy.** On 23 held-out games with no home-country setting, frozen before scoring, Google Trends' top country for a real shipped game like each one was Crowdspawn's #1 in 1 of 23; an LLM with no Qloo data got 4 of 23 and plain popularity 0 of 23. The ranking has a city bias (Stockholm came first for 9 of the 23 games). It does better when a game has a real-world setting, where culture anchors carry the signal. A Steam-review backtest on 6 shipped games also lost to popularity ([`backtest-results.md`](backtest-results.md)). The app shows these numbers on its "How accurate is it?" page and calls its ranking a starting hypothesis, not a prediction.

## The pieces

```
Your browser  ──>  Website (Next.js, port 3000)  ──>  API (Python FastAPI, port 8000)
                                                         ├─> Qloo (the taste data)
                                                         ├─> Ollama Cloud AI (writes the brief)
                                                         └─> SQLite (saves plans, cached Qloo answers)
```

- **Website** (`apps/web`): the pages and the game look (pixel maps, rising grid tiles, synthesized 8-bit sounds, progress bar, rarity cards).
- **API** (`apps/api`): all the logic, plus your secret keys, which never reach the browser.
- **Cache:** repeating a plan costs zero Qloo calls (the hackathon plan allows 10,000 a month).
- **AI provider:** switch between Ollama, Gemini and others by changing `LLM_PROVIDER` in `apps/api/.env`; the facts stay the same, only the wording changes.

## Where to look

- `pnpm dev` starts everything; open http://localhost:3000.
- **/sample** shows a finished plan and works without any keys.
- **New plan** runs the full live flow.
- **/scout** explores any place on the map.
- **/agent** lets the launch agent plan for you, step by step.
- [`../README.md`](../README.md) has the setup; [`qloo-contract.md`](qloo-contract.md) lists the verified Qloo calls.
