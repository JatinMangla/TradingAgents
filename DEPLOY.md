# Publishing to GitHub and deploying to Vercel

Everything is committed and ready. The two steps below need **your** GitHub and
Vercel accounts — this machine has no `gh` CLI, no `vercel` CLI, and no stored
credentials, so I could not create the repo or deploy on your behalf.

---

## Step 1 — Create the GitHub repo and push

The local repo is already prepared:

* commit `0c5ac52` contains all the work
* `origin` → `https://github.com/JatinMangla/trading-agents-dashboard.git`
* `upstream` → the original TauricResearch repo (kept, so you can pull updates)
* `.env` is gitignored and was **verified not staged** — your API keys stay local

**1a.** Create an empty repo at <https://github.com/new>

* Owner: `JatinMangla`
* Name: `trading-agents-dashboard` (or change it — see note below)
* **Do not** tick "Add a README", ".gitignore" or "license" — the push provides them

**1b.** Push:

```powershell
cd D:\git\trading\TradingAgents
git push -u origin main
```

Git will prompt for credentials. Use a **personal access token** as the password
(GitHub stopped accepting account passwords): <https://github.com/settings/tokens>
→ Generate new token (classic) → scope `repo`.

*Chose a different repo name?* Update the remote first:

```powershell
git remote set-url origin https://github.com/JatinMangla/<your-name>.git
```

### About the licence

The upstream project is Apache-2.0, which permits republishing. `LICENSE` and
the original attribution are preserved in the commit — keep them.

---

## Step 2 — Deploy to Vercel

1. Go to <https://vercel.com/new> and sign in with GitHub.
2. Import `JatinMangla/trading-agents-dashboard`.
3. Framework preset: **Other**. Leave build and output settings empty —
   `vercel.json` already configures everything.
4. Deploy.

**No environment variables are needed.** The deployed tools use public price
data only, so there is no key to leak. Do not add `GOOGLE_API_KEY` — nothing in
the serverless build uses it.

You get a URL like `https://trading-agents-dashboard.vercel.app`.

### What gets deployed

| Tool | Deployed? |
|---|---|
| SIP simulator (with fund name search) | ✅ |
| Strategy backtester vs buy-and-hold | ✅ |
| Market data and instrument search | ✅ |
| **Multi-agent LLM analysis** | ❌ — local only |

### Why the AI analysis is not deployed

This is a deliberate design decision, not an unfinished piece. Three properties
of serverless make it unworkable:

1. **Duration.** One analysis chains many LLM calls and takes minutes. Vercel
   functions cap at 60s (Hobby) / 300s (Pro), so a run is killed partway.
2. **Streaming.** The live agent-by-agent progress is a Server-Sent Events
   connection held open for the whole run. Serverless functions do not hold
   connections that way.
3. **Persistence.** The decision log, the reflection loop that scores past calls
   against the benchmark, the checkpoints and the saved reports are files under
   `~/.tradingagents`. A serverless filesystem is discarded between requests, so
   those writes would vanish and the learning loop would **silently never work** —
   which is worse than not shipping it.

Deploying it anyway would produce a page that looks functional and times out.

### If you want the AI analysis hosted too

It needs an always-on host with a disk, not serverless. Options:

* **Local** — `python -m webui`, which is what you have now, and is free.
* **GitHub Codespaces** — free tier, ~60 h/month on a 2-core box; the
  `.devcontainer/` config is already committed. Put `GOOGLE_API_KEY` in
  Codespaces **Secrets**, never in the repo.
* **Any small VM** (Fly.io, Railway, Render, a VPS) — needs a persistent volume
  mounted at `~/.tradingagents` for the decision log to survive restarts.

---

## Verified before shipping

Run locally against `api/index.py` (the exact app Vercel serves):

* `GET /api/health` → ok
* `GET /` → the dashboard page renders (18 KB)
* `GET /api/sip/search?q=bandhan small cap` → six share classes, plan labels
* `GET /api/sip/compare?tickers=^NSEI&monthly=5000&years=10` → ₹6,05,000 → ₹10,38,583, XIRR 10.38%
* `GET /api/backtest?ticker=^NSEI&years=10` → hold +182.3%, SMA +32.5%, RSI +24.3%

The serverless app imports **no** LLM libraries, so the bundle stays well inside
Vercel's size limit.

## One change to be aware of

Root `requirements.txt` previously contained `.` (install this project). Vercel
reads that file to build the function, so it now lists the lean serverless
dependencies instead. **For local development use `pip install -e .`**, which is
what `RUN_LOCAL.md` already tells you to do.
