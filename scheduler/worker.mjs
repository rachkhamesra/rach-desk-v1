// External scheduler for the desk build: a Cloudflare Worker with one cron trigger that fires every 30 minutes
// and starts the GitHub workflow at the right moments. GitHub's own `schedule:` is best-effort and has started jobs
// hours late or not at all, so this is the primary clock; the workflow's own crons stay as a backstop.
//
// All times are IST (UTC+5:30). wrangler.toml lists cron triggers only for the moments below, so the Worker does not wake
// at any other time. `mode` is a workflow input:
//   daily - build if nothing has been published yet today, or the newest session or MCX has something new
//   retry - build only if the newest session (with its BSE delivery) or MCX has something new
// (the workflow also accepts "always", for starting a build by hand)

const IST_OFFSET_MIN = 330;

/** Which mode, if any, to start at this moment (epoch milliseconds, on the :00 / :30 UTC grid). */
export function plan(ms) {
  const ist = new Date(ms + IST_OFFSET_MIN * 60000);
  const day = ist.getUTCDay();                                   // 0 = Sunday
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const weekday = day >= 1 && day <= 5;
  // Morning, every day, 06:00 to 07:00 IST: MCX, results calendar and transcripts. Retries until a build has run today.
  if (mins >= 6 * 60 && mins <= 7 * 60) return "daily";
  // Weekday evenings, 19:00 to 22:00 IST: the new NSE/BSE session, with its BSE delivery.
  if (weekday && mins >= 19 * 60 && mins <= 22 * 60) return "retry";
  // Weekend evening: one backup for the weekly-moving data.
  if (!weekday && mins === 20 * 60) return "daily";
  return null;
}

/** Start the workflow. Throws with GitHub's reply on any failure so Cloudflare logs it. */
export async function dispatch(env, mode, fetchImpl = fetch) {
  if (!env.GITHUB_TOKEN) throw new Error("GITHUB_TOKEN secret is not set (see scheduler/README.md)");
  const url = `https://api.github.com/repos/${env.REPO}/actions/workflows/${env.WORKFLOW}/dispatches`;
  const init = {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "rach-desk-scheduler",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.REF || "main", inputs: { mode } }),
  };
  let res = await fetchImpl(url, init);
  if (res.status >= 500) res = await fetchImpl(url, init);        // one retry on a GitHub-side error
  if (res.status !== 204) throw new Error(`GitHub dispatch failed: ${res.status} ${await res.text()}`);
  return res.status;
}

export default {
  async scheduled(event, env) {
    const mode = plan(event.scheduledTime);
    const at = new Date(event.scheduledTime).toISOString();
    if (!mode) { console.log(`${at}: nothing to start`); return; }
    await dispatch(env, mode);
    console.log(`${at}: started ${env.WORKFLOW} in ${mode} mode`);
  },
  async fetch() {
    return new Response("rach-desk scheduler: runs on a cron trigger only\n", { status: 200 });
  },
};
