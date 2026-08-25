# Publishing to GitHub and deploying to Vercel

Everything is committed and ready. The two steps below need **your** GitHub and
Vercel accounts — this machine has no `gh` CLI, no `vercel` CLI, and no stored
credentials, so I could not create the repo or deploy on your behalf.

---

## Step 1 — Push to GitHub  ✅ DONE

Pushed to **<https://github.com/JatinMangla/TradingAgents>** (commits `0c5ac52`
and `2d3f3a5`).

The earlier failure was a wrong remote URL: `origin` pointed at
`trading-agents-dashboard`, which does not exist. Your actual repo is
`JatinMangla/TradingAgents`, an existing fork of the upstream project. Repointing
`origin` there made it a clean fast-forward — **nothing on the fork was lost and
no force-push was needed**.

Remotes now:

* `origin`   → `https://github.com/JatinMangla/TradingAgents.git`
* `upstream` → `https://github.com/TauricResearch/TradingAgents.git`

Verified after the push: `.env` is **not** in the repo, and no API key appears in
any pushed file. Future pushes are just:

```powershell
cd D:\git\trading\TradingAgents
git push
```

## Step 2 — Deploy to Vercel

1. Go to <https://vercel.com/new> and sign in with GitHub.
2. Import `JatinMangla/TradingAgents`.
3. Framework preset: **Other**. Leave build and output settings empty —
   `vercel.json` already configures everything.
4. Deploy.

**No environment variables are needed.** The deployed tools use public price
data only, so there is no key to leak. Do not add `GOOGLE_API_KEY` — nothing in
the serverless build uses it.

You get a URL like `https://trading-agents.vercel.app`.

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
