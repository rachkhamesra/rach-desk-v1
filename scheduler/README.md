# Scheduler

GitHub's own `schedule:` trigger is best-effort: it has started the desk's jobs hours late or not at all. This folder is a small Cloudflare Worker that does the timing instead. It has one cron trigger (every 30 minutes) and, at the right moments, calls GitHub's `workflow_dispatch` API to start **Daily desk**. The workflow's own crons stay in place as a backstop, and every one of them skips in seconds when a build has already covered it, so running both costs almost nothing.

## When it starts a build (IST)

| When | Mode | Meaning |
|---|---|---|
| Mon-Fri 06:00 to 09:30, every 30 min | `daily` | Build unless a build already ran today and nothing is new (MCX, results calendar, transcripts) |
| Mon-Fri 19:00 to 01:00, every 30 min | `retry` | Build only if the newest NSE/BSE session (with BSE delivery) or MCX has something new |
| Sat and Sun 08:00 and 20:00 | `daily` | Weekly-moving data; the 20:00 run is a backup |

The decision is the `plan` function in `worker.mjs` (change the times there; `worker.test.mjs` shows what each moment does). `always` exists only for starting a build by hand.

## One-time setup (about 10 minutes)

1. **A GitHub token that can start the workflow.** GitHub, Settings, Developer settings, Personal access tokens, Fine-grained tokens, Generate new token. Resource owner: you. Repository access: **only** `rach-desk-v1`. Repository permissions: **Actions: Read and write** (Metadata read is added automatically). Expiry: up to one year; put a reminder in your calendar, because a lapsed token silently stops the Worker (the GitHub backstop keeps running, just late).
2. **A Cloudflare account** (the free plan is enough: one cron trigger, 48 invocations a day) and `wrangler`. From this folder:
   ```bash
   cd scheduler
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN    # paste the token from step 1
   npx wrangler deploy
   ```
3. **Check it.** In the Cloudflare dashboard, Workers, rach-desk-scheduler, Settings, Triggers, you will see the cron `*/30 * * * *`. At the next 06:00 to 09:30 or 19:00 to 01:00 IST slot, the Actions tab shows a **Daily desk** run with the event `workflow_dispatch` and a `mode: daily` or `mode: retry` line in the build step's log. To test right away, run `npx wrangler dev --test-scheduled` and open `http://localhost:8787/__scheduled?cron=*/30+*+*+*+*` during a slot (it starts a real run), or start a build by hand from the Actions tab.
4. **Logs.** Dashboard, Workers, rach-desk-scheduler, Logs, shows one line per firing: `started daily.yml in retry mode`, `nothing to start`, or the error GitHub returned (a 401 or 403 usually means the token expired or lacks Actions write).

## Without Cloudflare

Any service that can send a scheduled HTTP request works, for example cron-job.org. Create jobs that `POST https://api.github.com/repos/rachkhamesra/rach-desk-v1/actions/workflows/daily.yml/dispatches` with headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28` and the body `{"ref":"main","inputs":{"mode":"daily"}}` (use `"retry"` for the evening jobs), at the times in the table above (IST). The token is the same as in step 1 and is stored with that service instead.

## Tests

```bash
node --test scheduler/worker.test.mjs     # no packages needed
```
