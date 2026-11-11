# Desk

A searchable stock screen on GitHub Pages, rebuilt every weekday evening from NSE and BSE end-of-day files.

Main screen: search a ticker, see its adjusted price as candlesticks (adjusted open, high, low and close) with moving averages, delivered-share bars (green = up on above-average delivery, red = down on above-average delivery, faded green/red = ordinary days, grey = a move under 0.5 standard deviations), its relative strength against the Nifty, and the futures open-interest build-up. Other tabs combine delivery, relative strength and moving-average proximity into one Signal Confluence view, track cash accumulation and conference calls, and monitor BSE and MCX options-premium turnover.

## Set up (once)
1. Create a GitHub repo and push this folder.
2. Settings, Pages, Source: **GitHub Actions**.
3. Actions tab, run **Daily desk** once ("Run workflow"). The first run downloads about 14 months of files (a few minutes). After that it runs by itself.

The bundled F&O conference-call summaries work without an API key. A future automated refresh can be enabled by adding an OpenAI API key at **Settings → Secrets and variables → Actions → New repository secret** with the name `OPENAI_API_KEY`; the current prototype does not require it.

The page is at `https://<you>.github.io/<repo>/`. Locally: `pip install -r requirements.txt`, then `python run.py` (writes `site/index.html`). `--asof 2026-10-23` rebuilds for an earlier date; `--days 1100` pulls about three years.

## What happens automatically
A small Cloudflare Worker in `scheduler/` is the primary clock: GitHub's own `schedule:` trigger is best-effort and has started jobs hours late or not at all. The Worker starts the **Daily desk** workflow through the API every day at 06:00, 06:30 and 07:00 IST (until a build has run that day, or MCX or the newest session has something new), on weekday evenings every 30 minutes from 19:00 to 22:00 IST (only when the newest NSE/BSE session, with its BSE delivery, or MCX has something new), and on Saturday and Sunday at 20:00 IST as a backup. See `scheduler/README.md` to set it up. The workflow's own crons remain as a backstop and skip in seconds when a build has already covered them. A run restores the small cached history (about 77 MB) and asks NSE and BSE for every trading day it does not yet have (one day of files on a normal evening). Manual runs build unless you choose another mode. City temperatures are downloaded at most once a week per city (they trail real time by about five days anyway), and a build spends at most a few minutes on temperature and power downloads. The user's computer does not need to be on.
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

What it shows, all against the same days of earlier years and the 1991–2020 normal (a 15-day smoothed daily average): region cards (year to date, last 30 days, versus the previous two years and the share of warmer days); cooling-season (March to June) and heating-season (December to February) tables for each region against the previous season, with a "tailwind or headwind" read; six large cities (Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata) always shown as a 3-by-2 grid of year-versus-year charts (14 or 30-day trailing mean of the daily mean or maximum, Feb 29 removed); and an 18-month heat grid of all 25 cities. Regions are simple averages of their cities. Values are ERA5 grid-cell estimates, not station readings, about a week old, and temperature is one input to demand, not a forecast. Open-Meteo's free tier is for non-commercial use.

### Power generation (second view of Alternative Data)
`power.py` and the `nppdgr/` package read the CEA Daily Generation Report, sub-report 2 (station and unit level generation, coal stock days, outages) from npp.gov.in. Each file is parsed, checked against the file's own region totals (a mismatch fails that day and is recorded), then reduced to two small tables in `data/power/`: `fleet.csv` (by region, sector and fuel) and `owner.csv` (by plant owner). Files appear one to two days late; the newest 6 days are downloaded again every run because the portal revises them, and gaps in the last 12 days are retried. Wind and solar are not in this report, so totals are conventional generation, not national supply. Layouts before Nov 2019 are not supported; history starts at 1 Jan 2023 (`FIRST_DAY` in `power.py`). The first build downloads history newest-first within a time budget (`POWER_BUDGET_S`, 900 seconds by default) and carries on at the next build.

The view is about companies, not regions or states: three year-versus-year charts in one row (all conventional, coal and lignite, hydro), a company chart below them with a selector (NTPC, Adani Power, Tata Power and the other matched owners, all fuels together), a shared 14 or 30-day trailing-mean control, and a table of companies over the last 30 days (capacity, generation, change against the same weekdays a year earlier, coal plant load factor and coal stock days). State-owned and imported generation, unmatched plants and plants marked `REVIEW` are left out of the company table and the view states what share of generation that is. Plant-to-owner matching is hand-maintained in `config/plant_owner.csv` (edit that file, not the code). A coal stock of 0 may mean "not reported", so it is left out of the averages.

Under the company chart, two bar charts total the selected company's generation by calendar month (last 24 months) and by Indian fiscal quarter (Q1 is April to June, last 12 quarters). A month's total is its observed daily mean times its calendar days, so a missing day or Feb 29 cannot skew it. The month or quarter in progress is drawn in orange: solid for generation so far, dashed for an estimate that assumes the remaining days run at the average of the last 14 or 30 days (the smoothing control), and a white tick marks the same period a year earlier. The estimate is a straight run-rate; it ignores seasonality, outages and holidays, so treat it as a pace check, not a forecast.

**IEX day-ahead price (merchant power price).** `iex.py` reads the daily table on IEX's Market Snapshot page (`iexindia.com/market-data/day-ahead-market/market-snapshot`, any range of up to 31 days from April 2022): purchase and sell bids, cleared volume (MCV), and the simple and volume-weighted market clearing price (MCP), stored in `data/power/iex_dam.csv`. It is an HTML table, not an API, so a layout change makes the parse return nothing and the last good data stays. The power view shows two year-versus-year charts (weighted price in Rs per kWh, cleared volume in MU a day) with the same 14 or 30-day smoothing, and a line with the latest day. The first run fetches month by month from 2023 within a 150-second budget (about 47 requests); after that the two newest months are fetched once a day. If IEX refuses automated requests from GitHub's servers the section simply does not appear, and the build log says `iex:` with the reason.

## Management outlook (six labels)
`outlook.py` turns the tagged next-quarter points of a call into one of six labels, shown as a row above the stock chart (and as a Watchlist column): **bullish, optimistic, positive, muted, cautious, bearish**. Each point's tone is scored (positive +1, neutral 0, cautious −0.75, negative −1.5) and averaged; an explicit guidance raise or cut adds or subtracts 0.25 each (capped at ±0.5). Score ≥ 0.9 with strong language ("accelerating", "record", "raised"...) or a guidance raise is bullish (≥ 0.75 needs three strong points or two raises); ≥ 0.5 optimistic; ≥ 0.25 positive; down to −0.1 muted (no clear direction); down to −0.55 cautious; below that bearish, but only if at least one point is explicitly negative. Fewer than three points gives no label. It is a reading aid built from those tags, not an independent view; open the transcript before relying on it. It needs no model call, so new transcript batches are labelled automatically.

## Signal Confluence
The former Persistent Delivery, Relative Performance and At a Moving Average tabs are combined into three mutually exclusive tables: Delivery + Relative Strength + MA, Delivery + Relative Strength, and Delivery + MA. Persistent delivery requires at least three of the last five sessions at 1.25× or more of the prior 20-session average; relative strength requires a top-30 rank on at least one tracked horizon; MA proximity means within 0.5σ of an active moving average.

## Exchange Trackers
The BSE tracker stores daily Options Premium Turnover in ₹ crore from January 2025 onward. It first reads BSE Equity Derivatives Key Statistics and, when that endpoint rejects a cloud runner, derives the identical options-premium value from BSE's official daily UDiFF derivatives file. The page plots the five-session rolling premium turnover against BSE Ltd's adjusted share price, compares the newest observation with all prior occurrences of the same weekday in the year, shows monthly average daily premium turnover, and writes a short factual summary from those calculations.

The Exchange Tracker has BSE and MCX sub-tabs. The MCX tracker starts with the official date-wise OPTFUT Premium Value reports supplied through 28 October 2026 and retains FUTCOM Total Value for later use. It compares the current part of the month with the same bucket in prior months: Week 1 = days 1–8, Week 2 = 9–16, Week 3 = 17–24 and Week 4 = 25–month-end. It attempts an incremental refresh from MCX Historical Data, retains the last verified report if MCX blocks automated retrieval, and labels that state visibly rather than presenting stale data as current. Its Daily Read also retrieves upcoming MCX options expiries from Groww's public commodity calendar.

## Password lock (off by default)
`lock.py` can replace `site/index.html` with an unlock screen holding the encrypted page (gzip, AES-256-GCM, key from PBKDF2-HMAC-SHA256 with 600,000 rounds, decrypted in the browser with WebCrypto). The workflow runs it only when the repository variable `SITE_LOCK` is set to `on` (Settings, Secrets and variables, Actions, Variables), and then it needs the `SITE_PASSWORD` secret (12+ characters) and fails the deploy rather than publishing an unlocked page. With the variable unset or anything else, the site is published as a plain page, including `site/corporate_actions.csv`. It keeps casual visitors out, but the encrypted file is still public and the repository is not hidden by it. Changing the password locks out remembered devices until they enter the new one. Locally, `SITE_PASSWORD=... python lock.py site/index.html` locks a built page. Needs a current browser over https (or localhost).

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

## Backtest panels (very experimental)
Four small panels at the bottom of Alternative Data, Power generation: what works, what held in more than one year, what doesn't, and whether there is a threshold. The question is whether generation or IEX day-ahead price moves have ever predicted the share price of NTPC, Adani Power, Adani Green, NHPC and JSW Energy.

**It is run on a local machine, not in the daily build.** From the repo root, with the power data in `data/power`:

```bash
python backtest.py
```

That downloads share prices (Yahoo Finance's unofficial API, cached in `data/backtest/`), scores everything, and writes `config/backtest_results.json`, which you commit. The build only reads that file, so a blocked or changed price source can never break the site. Re-run it when you want fresher results.

- **Signals:** generation 30-day average vs a year earlier; generation 14-day vs 60-day; the same two for IEX weighted price; and "both rising". Generation is lagged 2 days and price 1 day, as they would be published.
- **Scoring:** every 5th trading day, the forward 10- and 20-day return minus Nifty, scored per calendar year (2024, 2025, 2026). Verdicts: works, sometimes works, could work, doesn't work, inverse.
- **Threshold panel:** each signal is turned into standard deviations from its own past year and pooled over the five stocks. The bars show the average 20-day excess return by band; a cut-off only counts if the gap is more than about two standard errors.
- **NHPC** uses all-India hydro generation as a stand-in. **Adani Green** has no generation data (wind and solar are not in the CEA report), so only its price tests run.
- A screen for ideas: about a dozen independent observations per test per year, no costs, hand-matched ownership.

## Exchange tracker: any weekday
Under the BSE and MCX charts, an "Any weekday" card with two dropdowns, Day (Monday to Friday) and Window (YTD, last 6 months, all history). It charts every session on that weekday with a dashed average line, and states the count, average, median, highest, lowest and the latest session against the earlier average, plus the average for each weekday in the same window.

## Short ideas tab (experimental)
F&O stocks only, from `shorts.py`. Six yes/no screens on the existing price, delivery and open-interest data: cash selling (down day, below the 50 and 100-day averages, delivery above its 20-session average), laggards (behind Nifty by 5 points over 20 days and 10 over 3 months, below the 50-day), breakdown below the prior 40-day low on delivery, rejected at the 50-day average, short build-up (down 3% in three sessions with OI up 5%), and near the 52-week low while lagging. The overview lists stocks flagged by two or more screens.

Each screen carries a **replay**: the same rule applied to every held session, then the stock's move against Nifty over the next 10 sessions (one flag per stock per 10 sessions), shown next to the average F&O stock. On the current history (about 280 sessions) none of the screens shows an edge over that baseline, and the page says so. Treat the lists as things to look at, not signals.
