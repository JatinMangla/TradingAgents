# Using this project to actually make money

You asked for a system that tells you when to buy and sell, and which SIP is
most profitable. This document is the honest answer, backed by numbers this
project measured from real market data — not opinions.

---

## 1. The thing you need to know first

**No system can reliably predict short-term price moves.** Not this one, not a
paid subscription, not a hedge fund's. If prediction worked, the people with it
would use it rather than sell it.

So I did not build a buy/sell oracle. A dashboard printing "BUY at ₹88.50" in
confident language would feel valuable and cost you money. Instead I built tools
that let **real history answer your questions**, including when the answer is
"this doesn't work."

Here is what those tools measured.

---

## 2. Market timing lost. Repeatedly.

Backtest, 10 years, realistic 0.1% cost per trade, signals acted on the next day
(never the same close):

**NIFTY 50 (^NSEI)**

| Strategy | Total return | CAGR | Worst fall | Trades |
|---|---|---|---|---|
| **Buy and hold** | **+180.4%** | **10.9%** | -38.4% | 1 |
| 50/200 moving-average trend | +32.7% | 2.9% | -42.2% | 14 |
| RSI 30/70 mean reversion | +24.3% | 2.2% | -32.7% | 15 |

**RELIANCE.NS**

| Strategy | Total return | CAGR | Worst fall | Trades |
|---|---|---|---|---|
| **Buy and hold** | **+497.2%** | **18.4%** | -45.1% | 1 |
| 50/200 moving-average trend | +140.8% | 8.6% | -45.5% | 14 |
| RSI 30/70 mean reversion | +174.9% | 10.0% | -41.2% | 23 |

Timing did not just underperform — it destroyed most of the return. On the
NIFTY, trading turned a 180% gain into 33%.

**One honest exception.** On TCS.NS the trend rule beat holding (+141% vs +128%)
*and* cut the worst fall from -53% to -28%. That is real, and it is also the
trap: a rule that wins on one stock and loses on two others is **luck, not
edge**. Run the backtest on several instruments before believing any rule. The
tool exists so you can check rather than hope.

---

## 3. Your SIP question, answered with data

₹5,000/month for 10 years (₹6,05,000 invested):

| Instrument | Value now | Total gain | **XIRR** | Worst fall |
|---|---|---|---|---|
| RELIANCE.NS | ₹11,96,535 | +97.8% | **13.03%** | -27.6% |
| **^NSEI (index)** | ₹10,38,488 | +71.7% | **10.38%** | -27.4% |
| HDFCBANK.NS | ₹7,69,409 | +27.2% | **4.69%** | -31.1% |
| TCS.NS | ₹7,12,844 | +17.8% | **3.21%** | -46.7% |

Three things worth absorbing:

1. **The index beat two of three blue-chip stocks.** These were not bad
   companies — they are among India's largest. Stock picking is genuinely hard,
   and "obvious" choices underperformed a fund that requires no skill at all.
2. **Read XIRR, not total gain.** "+71.7%" sounds better than "10.38%", but they
   describe the same result. Money you invested last month has not compounded
   for ten years. XIRR is the real annual rate and the only fair comparison.
   Anyone quoting you a total-return number is flattering their product.
3. **Look at the worst-fall column.** A TCS SIP was down 46.7% at one point.
   The return only happened for someone who did not sell there.

### On SIP vs lump sum

A NIFTY SIP since 2016 returned **10.75% XIRR**. The same total money invested
once at the start returned **+212.96%** — far more. In a mostly-rising market,
lump sum wins.

SIP is not a return-maximiser. It is a **behaviour tool**: it removes the need
to time entry, and it matches how salaries arrive. That is a real benefit. Just
do not expect it to beat lump sum when markets rise.

---

## 4. What the evidence actually supports

None of this is exciting, which is why it is undersold:

- **Low-cost index funds, held for a long time.** The index beat most individual
  stocks above with zero research effort.
- **Costs compound against you.** 0.1% per trade turned winning strategies into
  losers. A 1.5% expense-ratio active fund fights the same drag every year. When
  comparing funds, the expense ratio is one of the few numbers that reliably
  predicts future relative performance — lower is better.
- **Time in the market beats timing it.** Every table above says this.
- **Diversify.** TCS fell 46.7%. If that had been your only holding, the plan
  would have ended there.
- **Only invest money you will not need soon.** A -38% NIFTY fall is normal, not
  exceptional. If you might need the money during one, do not put it in equity.

### On taxes and fees in India (check current rules — these change)

Returns above are before tax and brokerage. Equity held over a year is taxed
more favourably than short-term trades, which is another quiet argument against
frequent trading. Confirm current rates with a qualified advisor.

---

## 4b. Mutual funds and share classes

The SIP tool takes fund names. Typing "bandhan small cap" returns all six share
classes, because they are **not** interchangeable:

| Scheme | Plan | Option |
|---|---|---|
| Bandhan Small Cap **Dir Gr** | Direct | Growth |
| Bandhan Small Cap Reg Gr | Regular | Growth |
| Bandhan Small Cap Dir/Reg IDCW-T/P | either | IDCW |

- **Direct vs Regular**: Direct skips distributor commission, so its expense
  ratio is lower and it compounds faster. Same fund, same manager, same
  portfolio. If you buy through a platform that pays itself commission, you get
  Regular. Over decades the difference is large.
- **Growth vs IDCW**: Growth reinvests; IDCW pays income out. For long-term
  wealth building, Growth.

For a long SIP, **Direct + Growth** is the usual answer. The dropdown marks it.

### A worked example of the trap

Bandhan Small Cap Direct Growth, ₹5,000/month, against the NIFTY:

| Comparison | Fund XIRR | NIFTY XIRR | Note |
|---|---|---|---|
| "10 years" | **26.87%** (6.5y) | 10.38% (10y) | **Not comparable** |
| Same 6 years | **24.89%** | 8.14% | Fair comparison |

The first row is the mistake almost everyone makes. The fund launched in 2021,
so its "10-year" number is really 6.5 years — and those years were a strong
small-cap run. The tool warns you when periods differ.

Over the matched window the fund genuinely did beat the index — with a -18.4%
worst fall against the index's -10.2%. That is the trade: higher returns, and
roughly double the pain. Small caps are cyclical, and six good years is a short
and flattering record. Do not assume it repeats.

## 5. What to do with the tools

```powershell
cd D:\git\trading\TradingAgents
.\.venv\Scripts\python.exe -m webui
```

**"Does timing beat holding?"** — put in any stock, pick a period, run it. Use
this before believing any strategy, including one from the AI agents.

**SIP simulator** — compare an index against whatever you are considering. Add
`^NSEI` to every comparison as your baseline. If a pick cannot beat the index
over 10 years, that is your answer.

**The AI analysis** — treat its output as one researched opinion to argue with,
not a signal. It cannot see the future, and it does not know your finances,
taxes, or when you need the money. Its own reflection log scores past calls
against the benchmark, so watch whether it actually adds value over time.

---

## 6. What this project cannot do for you

Stated plainly so you don't rely on it for these:

- It cannot predict prices or tell you when to buy or sell.
- **Mutual funds are supported** (this corrects an earlier note in this file).
  Yahoo does carry Indian MF NAVs, under opaque codes like `0P0001J6FU.BO`. The
  SIP tool searches them by name and labels the share class. **Bonds and FDs are
  not covered.**
- Expense ratios are **not** in this data. Check them on the AMFI site or the
  fund factsheet — for two funds tracking the same thing, the cheaper one wins
  over time, and that is one of the few reliable predictors available.
- It does not know your tax position, income, debts, or goals — all of which
  matter more than any stock pick.
- It places no orders and connects to no broker.
- **It is not financial advice.** It is a research and measurement tool. For
  decisions about your actual money, a fee-only (not commission-earning)
  advisor is worth more than any dashboard.

---

## 7. The honest summary

The most profitable thing this project can do for you is **stop you from losing
money on strategies that look clever and aren't**. The tables above are worth
more than a buy signal, because they are true.

If you want the shortest evidence-backed version: buy a low-cost index fund
regularly, hold it for many years, don't trade it, and don't check it daily.
The measurements in this repo support that, and nothing in them supports
frequent trading.
