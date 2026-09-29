# Hosting all six sections

The Vercel deployment shows three sections. This is how to get all six online,
free.

---

## Why Vercel only shows three

Vercel runs **serverless functions**. A function wakes up when a request
arrives, must answer quickly, and is then destroyed — including anything it
wrote to disk.

The three hosted sections fit that perfectly: *Market data*, *Does timing beat
holding?* and *SIP simulator* each do one calculation and return in a second or
two.

The three missing sections do not fit it at all:

| Section | What it needs | What Vercel gives |
|---|---|---|
| **Run analysis** | 2–10 minutes of chained LLM calls | killed at 60s (Hobby) / 300s (Pro) |
| **Reports** | a connection held open, streaming each agent as it finishes | functions can't hold connections |
| **Past decisions** | files that survive between visits (decision log, reflections) | disk wiped after every request |

The third one is the quiet killer: the reflection loop only works because run #2
can read what run #1 wrote. On serverless those writes vanish, so it would look
like it worked and silently never learn.

**This is not a configuration problem.** No `vercel.json` setting fixes it —
it is what serverless is.

---

## The fix: a container host instead

Containers stay running, hold connections, and keep a filesystem. The agent
pipeline works on them. The image is ready — `Dockerfile` now supports both
modes:

* `APP_MODE=web` → the full dashboard, all six sections
* unset → the interactive CLI (unchanged, what `docker-compose` uses)

### Option A — Hugging Face Spaces (recommended: free, 16 GB RAM, no card)

1. Add this to the very top of `README.md`, before everything else:

   ```
   ---
   title: TradingAgents Dashboard
   emoji: 📈
   colorFrom: blue
   colorTo: green
   sdk: docker
   app_port: 7860
   ---
   ```

2. Create a Space at <https://huggingface.co/new-space> → SDK **Docker** → Blank.
3. Push this repo to it:

   ```powershell
   cd D:\git\trading\TradingAgents
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```

4. In the Space → **Settings** → **Variables and secrets**, add:
   * Variable `APP_MODE` = `web`
   * Secret `GOOGLE_API_KEY` = your key
   * Secret `FRED_API_KEY` = your key
   * Secret `WEBUI_PASSWORD` = a password of your choice (**required**: the
     container refuses to start on a public address without it)

Secrets are not visible in the repo or to visitors.

**Caveat:** a free Space sleeps after ~48 h idle and its disk resets on rebuild,
so the decision log survives normal use but not a restart. Everything else works.

**Your Space is public by default.** `WEBUI_PASSWORD` makes the browser ask for
a password before any page or API call; without it, anyone who found the URL
could run analyses on your Gemini quota and read your decision history. Setting
the Space to **Private** as well does no harm.

### Option B — Render (connects straight to GitHub)

1. <https://dashboard.render.com/> → New → **Web Service** → connect
   `JatinMangla/TradingAgents`.
2. Runtime **Docker**. Render reads the `Dockerfile` automatically.
3. Environment: `APP_MODE=web`, `GOOGLE_API_KEY`, `FRED_API_KEY`, `WEBUI_PASSWORD`.

**Caveats:** the free tier is 512 MB RAM, which is tight for this dependency
set — if it restarts mid-run, that is why. It also sleeps after 15 minutes idle,
so the first visit takes ~1 minute to wake. No persistent disk on free, so the
decision log resets.

### Option C — keep it local (what you have)

```powershell
.\.venv\Scripts\python.exe -m webui
```

Free, fast, nothing sleeps, decision log persists properly, and your API key
never leaves the machine. The only limitation is that the URL is not shareable.

---

## Which to choose

| | Vercel | HF Spaces | Render | Local |
|---|---|---|---|---|
| All six sections | ❌ | ✅ | ✅ | ✅ |
| Free | ✅ | ✅ | ✅ | ✅ |
| Shareable URL | ✅ | ✅ | ✅ | ❌ |
| Always instant | ✅ | sleeps 48 h | sleeps 15 min | ✅ |
| Decision log survives | ❌ | mostly | ❌ | ✅ |
| Key exposure risk | none | Space secret | env var | none |

Reasonable setup: **keep Vercel** for the evidence tools (instant, no key, safe
to share) and add **HF Spaces** when you want the AI analysis reachable from
your phone. They can both point at the same repo.

---

## Not verified locally

Docker is not installed on this machine, so the image could not be built and run
here. The pieces were checked individually: `pip install ".[webui]"` resolves,
and the dashboard serves correctly with the exact environment the entrypoint
sets (`WEBUI_HOST=0.0.0.0 WEBUI_PORT=7860` → HTTP 200). If the first Space build
fails, its build log will say why — usually a missing dependency.
