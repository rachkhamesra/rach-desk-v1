# Desk

A searchable stock screen on GitHub Pages, rebuilt every weekday evening from NSE and BSE end-of-day files.

Main screen: search a ticker, see its adjusted price with moving averages, delivered-share bars (green = up on above-average delivery, red = down on above-average delivery, faded green/red = ordinary days, grey = a move under 0.5 standard deviations), its relative strength against the Nifty, and the futures open-interest build-up. Other tabs combine delivery, relative strength and moving-average proximity into one Signal Confluence view, track cash accumulation and conference calls, and monitor BSE and MCX options-premium turnover.

## Set up (once)
1. Create a GitHub repo and push this folder.
2. Settings, Pages, Source: **GitHub Actions**.
3. Settings, Secrets and variables, Actions, **New repository secret**: name `SITE_PASSWORD`, value a passphrase of 12+ characters (longer is better). Every build is encrypted with it, and the deploy fails if the secret is missing, so the site is never published unlocked.
4. Actions tab, run **Daily desk** once ("Run workflow"). The first run downloads about 14 months of files (a few minutes). After that it runs by itself.

The bundled F&O conference-call summaries work without an API key. A future automated refresh can be enabled by adding an OpenAI API key at **Settings → Secrets and variables → Actions → New repository secret** with the name `OPENAI_API_KEY`; the current prototype does not require it.

The page is at `https://<you>.github.io/<repo>/`. Locally: `pip install -r requirements.txt`, then `python run.py` (writes `site/index.html`). `--asof 2026-10-23` rebuilds for an earlier date; `--days 1100` pulls about three years.

## What happens automatically
Monday to Friday at about 06:00 IST the workflow refreshes MCX's prior-session report, the results calendar and the other slow-moving data, and redeploys. From 19:00 IST every 30 minutes until about 01:00 IST it restores the small cached history (about 77 MB) and asks NSE and BSE for every trading day it does not yet have (one day of files on a normal evening); it exits without building when the newest session is already published with its BSE delivery, so the retries cost nothing once the day is complete. On Saturday and Sunday it rebuilds at about 07:47 and 19:47 IST (the second is a backup) to refresh the city temperatures, results calendar, call transcripts and exchange trackers. Manual runs always build. GitHub starts scheduled jobs on a best-effort basis and can be hours late, which is why there are several. The user's computer does not need to be on.
- If the newest NSE/BSE files are not out yet, the run immediately keeps the last complete market session rather than publishing partial data. The later scheduled run checks again automatically.
- On an exchange holiday NSE serves the previous day's file; the job notices and rebuilds on the last real session.
- GitHub can start scheduled jobs a few minutes late. In a public repo GitHub switches scheduled workflows off after 60 days without any repository activity; re-enable them in the Actions tab, or keep the repo private.
- NSE and BSE sometimes block GitHub's servers. If the run fails on downloads, run `python run.py` from cron on your own machine and push `site/` to a `gh-pages` branch; nothing else changes.

## Conference-call intelligence
The repository bundles the latest researched transcript analysis directly in `call_intelligence_seed.json`, so it renders as ordinary website text without a model call at build time. The current [Transcript Intelligence Research Snapshot](TRANSCRIPT_INTELLIGENCE_README.md) contains exactly Eternal, Shriram Finance, Infosys, Punjab National Bank, PG Electroplast and Indian Hotels, provided each has a verified exchange-served transcript. Cached call data is filtered to this publication scope.

Every published fact and evidence passage comes from the latest qualifying NSE/BSE transcript. Guidance changes are shown only when management explicitly states an increase, improvement, reduction, downgrade or upgrade in that same transcript. Old → new figures appear only when both figures are stated there. The main stock tab places the most material validated change in a green or red row above the chart and opens the contextual Call Intelligence evidence; the row stays hidden when no change qualifies.

The STOCKS page shows the result below the charts: next-quarter outlook, the subjects receiving the most analyst questions, a congratulations index, short supporting excerpts, and sector-specific metrics. Manufacturers focus on revenue and volume growth, order inflow, demand, margin outlook and EBITDA margin. Banks and lenders focus on credit growth, credit–deposit ratio, disbursements, NIM, asset quality and credit costs. These are model-generated reading aids; the linked exchange transcript remains the source of record.

## Alternative data (experimental)
The amber **Alternative Data** tab reads whether the season is running hotter or cooler than before, as a pointer to demand for ACs, coolers, fans, heaters and geysers. `heat.py` pulls daily mean and maximum temperature for the 25 cities in `config/cities.json` (edit that file to add or change a city; regions are North, East, West and South, with central India under West) from the Open-Meteo archive (ERA5 reanalysis) and the Niño 3.4 index from NOAA. The first run downloads 1991 onward for each city and takes several minutes; after that a run refreshes the last 40 days once a day. Cached data lives in `data/heat/`, and a city that fails to download keeps its last good data.

What it shows, all against the same days of earlier years and the 1991–2020 normal (a 15-day smoothed daily average): region cards (year to date, last 30 days, versus the previous two years and the share of warmer days); cooling-season (March to June) and heating-season (December to February) tables for each region against the previous season, with a "tailwind or headwind" read; a year-versus-year rolling-temperature chart per city (7, 14 or 30-day trailing mean of the daily mean or maximum, Feb 29 removed); an 18-month city heat grid; and a table of all cities. Regions are simple averages of their cities. Values are ERA5 grid-cell estimates, not station readings, about a week old, and temperature is one input to demand, not a forecast. Open-Meteo's free tier is for non-commercial use.

### Power generation (second view of Alternative Data)
`power.py` and the `nppdgr/` package read the CEA Daily Generation Report, sub-report 2 (station and unit level generation, coal stock days, outages) from npp.gov.in. Each file is parsed, checked against the file's own region totals (a mismatch fails that day and is recorded), then reduced to small tables in `data/power/` (`fleet.csv` by region, sector and fuel, `owner.csv` by plant owner, and the newest day's stations and unit outages in full). Files appear one to two days late; the newest 6 days are downloaded again every run because the portal revises them, and gaps in the last 12 days are retried. Wind and solar are not in this report, so totals are conventional generation, not national supply. Layouts before Nov 2019 are not supported; history starts at 1 Jan 2023 (`FIRST_DAY` in `power.py`).

The first build downloads history newest-first within a time budget (`POWER_BUDGET_S`, 900 seconds by default) and carries on at the next build, so the full 2023-onward backfill (about 1,400 files) completes over the first few builds. The view shows generation by fuel and region against the same dates a year earlier, coal plant load factor, MW-weighted coal stock days and coal capacity on outage, a rolling year-versus-year chart for any of these series, listed plant owners ranked over the last 30 days, the lowest-coal-stock stations of 500 MW or more, and the largest unit outages. Plant-to-owner matching is hand-maintained in `config/plant_owner.csv` (edit that file, not the code): unmatched plants and plants marked `REVIEW` are left out of the owner table, and the view states what share of generation that is. A coal stock of 0 may mean "not reported", so it is left out of the averages.

## Management outlook (six labels)
`outlook.py` turns the tagged next-quarter points of a call into one of six labels, shown as a row above the stock chart (and as a Watchlist column): **bullish, optimistic, positive, muted, cautious, bearish**. Each point's tone is scored (positive +1, neutral 0, cautious −0.75, negative −1.5) and averaged; an explicit guidance raise or cut adds or subtracts 0.25 each (capped at ±0.5). Score ≥ 0.9 with strong language ("accelerating", "record", "raised"...) or a guidance raise is bullish (≥ 0.75 needs three strong points or two raises); ≥ 0.5 optimistic; ≥ 0.25 positive; down to −0.1 muted (no clear direction); down to −0.55 cautious; below that bearish, but only if at least one point is explicitly negative. Fewer than three points gives no label. It is a reading aid built from those tags, not an independent view; open the transcript before relying on it. It needs no model call, so new transcript batches are labelled automatically.

## Signal Confluence
The former Persistent Delivery, Relative Performance and At a Moving Average tabs are combined into three mutually exclusive tables: Delivery + Relative Strength + MA, Delivery + Relative Strength, and Delivery + MA. Persistent delivery requires at least three of the last five sessions at 1.25× or more of the prior 20-session average; relative strength requires a top-30 rank on at least one tracked horizon; MA proximity means within 0.5σ of an active moving average.

## Exchange Trackers
The BSE tracker stores daily Options Premium Turnover in ₹ crore from January 2025 onward. It first reads BSE Equity Derivatives Key Statistics and, when that endpoint rejects a cloud runner, derives the identical options-premium value from BSE's official daily UDiFF derivatives file. The page plots the five-session rolling premium turnover against BSE Ltd's adjusted share price, compares the newest observation with all prior occurrences of the same weekday in the year, shows monthly average daily premium turnover, and writes a short factual summary from those calculations.

The Exchange Tracker has BSE and MCX sub-tabs. The MCX tracker starts with the official date-wise OPTFUT Premium Value reports supplied through 28 October 2026 and retains FUTCOM Total Value for later use. It compares the current part of the month with the same bucket in prior months: Week 1 = days 1–8, Week 2 = 9–16, Week 3 = 17–24 and Week 4 = 25–month-end. It attempts an incremental refresh from MCX Historical Data, retains the last verified report if MCX blocks automated retrieval, and labels that state visibly rather than presenting stale data as current. Its Daily Read also retrieves upcoming MCX options expiries from Groww's public commodity calendar.

## Password lock
`lock.py` runs in the workflow after the build and replaces `site/index.html` with an unlock screen holding the encrypted page (gzip, then AES-256-GCM, key from PBKDF2-HMAC-SHA256 with 600,000 rounds, decrypted in the browser with WebCrypto). Tick "Remember" to skip the prompt on that device for 30 days; the fixed salt in `lock.py` keeps that working across nightly rebuilds. It keeps casual visitors out, but the encrypted file is still public, so pick a long passphrase. Changing the password locks out remembered devices until they enter the new one. The repository is not hidden by this: keep it private if the code and data should not be public. `site/corporate_actions.csv` is dropped from the deployed site. Locally, `python run.py` still produces an unlocked page; lock it with `SITE_PASSWORD=... python lock.py site/index.html`. Needs a current browser over https (or localhost).

## Watchlist
Press ☆ next to a stock's name to add it, or type a ticker on the Watchlist view (Stocks tab, Watchlist button). The list lives in the browser's local storage on that device only; Export and Import copy it as comma-separated tickers to move it between devices. The ★ button beside the search box narrows the Stocks list to watched stocks.

## Base follow-through
It is the Follow-Through view of the Breakout Bases tab, and uses that tab's filter buttons.
`metrics.base_followthrough` replays the Breakout Bases scan on every past session in the loaded history and records what happened after each signal. A signal is the first day a stock reaches a stage (building, near, fresh) after at least 10 sessions out of it. Returns are measured from that day's close at 5, 10 and 20 sessions, with the excess over the Nifty, the worst dip, and whether the low undercut the base support within 20 sessions. Only data up to the signal day feeds the signal. The tab recomputes win rate, average and median from the signals using the same five filters as the Breakout Bases tab. With the default 420 days of history the sample is small (about 190 replayed sessions); run with `--days 1100` for three years. Results are historical and say nothing certain about the next trade.

## Corporate actions (automatic)
NSE and BSE do not adjust the previous close, so a split or bonus looks like a crash. A one-day jump is treated as a corporate action when
1. it is confirmed by an exchange signal: the ISIN changed, or the futures lot size moved the opposite way; or
2. it has no such signal (the stock was not in F&O then) but rupee turnover stayed normal. A split changes the share count, not the rupees traded; a crash or news gap comes with a turnover spike (3x the prior 20-day average or more).

Otherwise it is a real move and is left alone. Prices before the date are multiplied by the factor and delivered shares and open interest divided by it, so charts, averages and the 20-day baseline stay on one share basis. Each adjustment shows as a green dashed line on the stock's chart, and `site/corporate_actions.csv` is an audit log. On the 14 events in the first year: 13 adjusted (KOTAKBANK 5:1 split, LICI and PIDILITIND bonuses, ANGELONE 10:1, the VEDL demerger, among them) and POLICYBZR's -36% crash left alone. Nothing needs maintaining by hand; `corp_actions.csv` exists only as an override if you ever disagree with a call (symbol,date,action,ratio,note).

## Results calendar and pre-result activity
Each build asks NSE's board-meetings feed for every meeting from a week back to 120 days ahead (without a date range NSE returns only its latest 20, so the range is essential) and keeps the ones that consider financial results. A re-announced date replaces the older one. The workflow runs three times a day, so new intimations appear within hours. The feeds are cached and merged, so temporary NSE downtime leaves the last known dates in place. NSE's feed covers every NSE-listed stock in the universe; BSE's own calendar API refuses automated requests from cloud servers, so BSE is not read separately.

Where it shows:
- **Call Library, Upcoming Results:** every announced result meeting in the universe, with filters for Top 500 by market cap, F&O, five market-cap bands (market caps are NSE's last half-yearly average, so a size band, not a live value), date window (today, 3, 7, 14 days) and a ticker or company search.
- **Stocks chart:** a "Result in N days" banner above the chart with the date, meeting type, period and the NSE filing, and a dated badge beside the stock name.

For each result the scan examines the three completed trading sessions before the declaration date. `PRE-RESULT ACTIVITY` means that, on at least one of those sessions, delivered shares were above the prior 20-session average and the absolute price move was greater than 0.8 times the stock's prior-60-session daily-return standard deviation. Both baselines are shifted, so the signal uses no future data.

## Definitions
- Delivered shares = NSE + BSE (mapped through the ISIN). Delivery % is shown for reference, never used to rank.
- 20-day average = mean of the previous 20 sessions' delivered shares; ratio = today / average.
- "Above-average delivery" on the chart is a selector (1.0x, 1.25x default, 1.5x, 2.0x). "Under 0.5 standard deviations" = |daily move| below half the stock's prior-60-session standard deviation.
- OI build-up: price up and OI up = long build-up; price down and OI up = short build-up; price up and OI down = short covering; price down and OI down = long unwinding.
- Relative strength: stock / Nifty, rebased to 100 at the start of the range, with its 50-day average. Relative performance = (1 + stock) / (1 + Nifty) - 1.
- Persistent delivery: at least 3 of the last 5 sessions at 1.25x or more. At a moving average: within 0.5 sigma of the average (sigma = 60-session daily standard deviation).
- Moving averages 32, 50, 100, 200, 233, 377, 610; each switches on when there are enough sessions. Percentile columns read 1Y until about three years of history exist.
