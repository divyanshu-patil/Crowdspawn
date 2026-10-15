# How Crowdspawn works

## What it's for

You're a small indie studio about to launch a game with a small marketing budget. You need to know **where to spend it** (which cities for ads, meetups and events) and **who to team up with** (which musicians, podcasts and brands your future players already like).

Store tags like "roguelike" or "cozy" describe your game, not the people who'd play it. Crowdspawn answers the people question using **Qloo**, a "taste" database that knows, from real consumption data, what fans of one thing also like and where they are.

The idea in one line: **find where your players already are, and who else they love, before launch day.**

## How you use it

1. **Describe your game:** title, a short description, a few genre tags.
2. **Pick 1–5 comparable games ("comps"):** existing games your players probably love, like Stardew Valley for a cozy farming game. Your new game usually isn't in Qloo yet, so the app works through these. You can search for them, or click "Suggest for me" and an AI proposes some.
3. **Pick cities and an optional budget,** for example 12 cities and $3,000. You can also add your previous game to see how your current players differ from the new target audience.
4. **Watch it build.** A live progress log ticks through the steps, with a counter of Qloo calls.
5. **Get your plan:** a map and ranked list of cities, the audience profile, partners, a budget split, and a written brief.

## What happens behind the scenes

The API runs eight steps in order, each using the previous step's results:

| Step | What it does | In plain words |
|---|---|---|
| S1 | Checks your comps exist in Qloo | Makes sure the games are real |
| S2 | Asks Qloo for ~20 similar games | "Fans of these also love Loop Hero, Hollow Knight…", with Qloo's reasons |
| S3 | Scores every city, twice | Once for fans of your games, once for fans of mainstream hits (Minecraft, Fortnite, GTA V, Warzone) |
| S4 | Gets the audience's age and gender | e.g. "skews female, 25–29" |
| S5 | Finds partners | Artists, podcasts, films and brands this audience over-indexes on, worldwide and in the top 3 cities |
| S6 | Compares with your last game (optional) | Tastes you share vs. new ground |
| S7 | Splits the budget | Plain math: more money to cities with higher lift and confidence |
| S8 | Writes the brief | An AI turns the results into readable advice |

### The key idea: lift

Big cities have lots of gamers of every kind, so a raw count would always put New York first. Crowdspawn divides your fans' score by ordinary gamers' score in the same city:

- **1.86 in Tokyo** means fans of your comps show up there far more than ordinary gamers do.
- **1.00** means no special interest.
- **Below 1** means they're under-represented.

That's what the crowd size on the map shows: one lit tile per +0.02 lift.

## The rules that make it trustworthy

- **Qloo is the only source of facts.** Every city, number and partner traces back to a specific Qloo call. Small chips like `q21` in the brief link to the trace page, which lists every call the plan made.
- **The AI only writes words.** It never invents cities or numbers. A checker reads the brief and rejects anything not in Qloo's results, such as an invented city, a made-up percentage or a missing citation. If the AI fails twice, a plain template brief is shown instead.
- **It fails safely.** Without a Qloo key (or with a wrong one) the app refuses to make a plan rather than guess, and shows an error screen. This is the "kill switch" you can show in the demo.
- **It's honest about accuracy.** The rankings were tested against real Steam review languages for 6 well-known indie games. The city ranking beat a simple "where gamers are" ranking in only **1 of 6** (details in [`backtest-results.md`](backtest-results.md)). The app says so on the page and calls its results a "starting hypothesis", not a prediction.

## The pieces

```
Your browser  ──>  Website (Next.js, port 3000)  ──>  API (Python FastAPI, port 8000)
                                                         ├─> Qloo (the taste data)
                                                         ├─> Ollama Cloud AI (writes the brief)
                                                         └─> SQLite (saves plans, cached Qloo answers)
```

- **Website** (`apps/web`): the pages and the game look (pixel map, progress bar, rarity cards).
- **API** (`apps/api`): all the logic, plus your secret keys, which never reach the browser.
- **Cache:** repeating a plan costs zero Qloo calls (the hackathon plan allows 10,000 a month).
- **AI provider:** switch between Ollama, Gemini and others by changing `LLM_PROVIDER` in `apps/api/.env`; the facts stay the same, only the wording changes.

## Where to look

- `pnpm dev` starts everything; open http://localhost:3000.
- **/sample** shows a finished plan and works without any keys.
- **New plan** runs the full live flow.
- [`../README.md`](../README.md) has the setup; [`progress.md`](progress.md) tracks which requirements pass; [`qloo-contract.md`](qloo-contract.md) lists the verified Qloo calls.
