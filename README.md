# Desk

A searchable stock screen on GitHub Pages, rebuilt every weekday evening from NSE and BSE end-of-day files.

Main screen: search a ticker, see its adjusted price with moving averages, delivered-share bars (green = up on above-average delivery, red = down on above-average delivery, faded green/red = ordinary days, grey = a move under 0.5 standard deviations), its relative strength against the Nifty, and the futures open-interest build-up. Other tabs combine delivery, relative strength and moving-average proximity into one Signal Confluence view, track cash accumulation and conference calls, and monitor BSE and MCX options-premium turnover.

## Set up (once)
1. Create a GitHub repo and push this folder.
2. Settings, Pages, Source: **GitHub Actions**.
3. Actions tab, run **Daily desk** once ("Run workflow"). The first run downloads about 14 months of files (a few minutes). After that it runs by itself.

The bundled F&O conference-call summaries work without an API key. A future automated refresh can be enabled by adding an OpenAI API key at **Settings → Secrets and variables → Actions → New repository secret** with the name `OPENAI_API_KEY`; the current prototype does not require it.

The page is at `https://<you>.github.io/<repo>/`. Locally: `pip install -r requirements.txt`, then `python run.py` (writes `site/index.html`). `--asof 2026-10-23` rebuilds for an earlier date; `--days 1100` pulls about three years.

## What happens each night
Monday to Friday at 20:00 IST the workflow starts, restores the small cached history (about 77 MB), and asks NSE and BSE for every trading day it does not yet have, so a normal night downloads one day of files (NSE delivery, NSE prices and ISIN, NSE F&O, NSE index, BSE delivery plus BSE prices for the ISIN map). It then rebuilds the page and deploys it.
- If the files are not out yet it waits, for up to two hours. If BSE's delivery file is late it keeps waiting rather than publish a day with NSE-only delivery (which would be wrong by 8% to 89% depending on the stock). If anything is still missing after two hours the run fails and **the previous page stays up**.
- On an exchange holiday NSE serves the previous day's file; the job notices and rebuilds on the last real session.
- GitHub can start scheduled jobs a few minutes late. In a public repo GitHub switches scheduled workflows off after 60 days without any repository activity; re-enable them in the Actions tab, or keep the repo private.
- NSE and BSE sometimes block GitHub's servers. If the run fails on downloads, run `python run.py` from cron on your own machine and push `site/` to a `gh-pages` branch; nothing else changes.

## Conference-call intelligence
The repository bundles the latest researched transcript analysis directly in `call_intelligence_seed.json`, so it renders as ordinary website text without a model call at build time. The one-off [Transcript Intelligence Research Snapshot](TRANSCRIPT_INTELLIGENCE_README.md) preserves every current summary, evidence fragment, analyst-focus count, congratulations index, sector metric and risk panel for future quality comparison. The optional nightly automation can later look back 150 days for new NSE transcript filings and refresh only changed calls.

The STOCKS page shows the result below the charts: next-quarter outlook, the subjects receiving the most analyst questions, a congratulations index, short supporting excerpts, and sector-specific metrics. Manufacturers focus on revenue and volume growth, order inflow, demand, margin outlook and EBITDA margin. Banks and lenders focus on credit growth, credit–deposit ratio, disbursements, NIM, asset quality and credit costs. These are model-generated reading aids; the linked exchange transcript remains the source of record.

## Signal Confluence
The former Persistent Delivery, Relative Performance and At a Moving Average tabs are combined into three mutually exclusive tables: Delivery + Relative Strength + MA, Delivery + Relative Strength, and Delivery + MA. Persistent delivery requires at least three of the last five sessions at 1.25× or more of the prior 20-session average; relative strength requires a top-30 rank on at least one tracked horizon; MA proximity means within 0.5σ of an active moving average.

## Exchange Trackers
The BSE tracker stores daily Options Premium Turnover in ₹ crore from January 2025 onward. It first reads BSE Equity Derivatives Key Statistics and, when that endpoint rejects a cloud runner, derives the identical options-premium value from BSE's official daily UDiFF derivatives file. The page plots the five-session rolling premium turnover against BSE Ltd's adjusted share price, compares the newest observation with all prior occurrences of the same weekday in the year, shows monthly average daily premium turnover, and writes a short factual summary from those calculations.

The MCX tracker starts with the official date-wise OPTFUT Premium Value reports supplied through 28 October 2026 and retains FUTCOM Total Value for later use. It attempts an incremental refresh from MCX Historical Data, retains the last verified report if MCX blocks automated retrieval, and labels that state visibly rather than presenting stale data as current. Its Daily Read also retrieves upcoming MCX options expiries from Groww's public commodity calendar.

## Corporate actions (automatic)
NSE and BSE do not adjust the previous close, so a split or bonus looks like a crash. A one-day jump is treated as a corporate action when
1. it is confirmed by an exchange signal: the ISIN changed, or the futures lot size moved the opposite way; or
2. it has no such signal (the stock was not in F&O then) but rupee turnover stayed normal. A split changes the share count, not the rupees traded; a crash or news gap comes with a turnover spike (3x the prior 20-day average or more).

Otherwise it is a real move and is left alone. Prices before the date are multiplied by the factor and delivered shares and open interest divided by it, so charts, averages and the 20-day baseline stay on one share basis. Each adjustment shows as a green dashed line on the stock's chart, and `site/corporate_actions.csv` is an audit log. On the 14 events in the first year: 13 adjusted (KOTAKBANK 5:1 split, LICI and PIDILITIND bonuses, ANGELONE 10:1, the VEDL demerger, among them) and POLICYBZR's -36% crash left alone. Nothing needs maintaining by hand; `corp_actions.csv` exists only as an override if you ever disagree with a call (symbol,date,action,ratio,note).

## Results dates and pre-result activity
The nightly run scans NSE's all-equity board-meeting filings for scheduled dates and its corporate-announcement filings for the actual declaration timestamp. There is no separate calendar tab: upcoming results appear as dated badges beside the stock on the main Stocks page. The scanner excludes press releases, call transcripts and newspaper notices. The feeds are cached and merged on each run, so temporary NSE downtime leaves the most recent dates in place and does not stop the rest of the desk from publishing.

For each result it examines the three completed trading sessions before the declaration date. `PRE-RESULT ACTIVITY` means that, on at least one of those sessions, delivered shares were above the prior 20-session average and the absolute price move was greater than 0.8 times the stock's prior-60-session daily-return standard deviation. Both baselines are shifted, so the signal uses no future data.

## Definitions
- Delivered shares = NSE + BSE (mapped through the ISIN). Delivery % is shown for reference, never used to rank.
- 20-day average = mean of the previous 20 sessions' delivered shares; ratio = today / average.
- "Above-average delivery" on the chart is a selector (1.0x, 1.25x default, 1.5x, 2.0x). "Under 0.5 standard deviations" = |daily move| below half the stock's prior-60-session standard deviation.
- OI build-up: price up and OI up = long build-up; price down and OI up = short build-up; price up and OI down = short covering; price down and OI down = long unwinding.
- Relative strength: stock / Nifty, rebased to 100 at the start of the range, with its 50-day average. Relative performance = (1 + stock) / (1 + Nifty) - 1.
- Persistent delivery: at least 3 of the last 5 sessions at 1.25x or more. At a moving average: within 0.5 sigma of the average (sigma = 60-session daily standard deviation).
- Moving averages 32, 50, 100, 200, 233, 377, 610; each switches on when there are enough sessions. Percentile columns read 1Y until about three years of history exist.
