"""The data behind the Timeline tab: how the page evolved.

Two sources are combined.
  config/timeline.json   a curated story: phases, and for each node a date, a kind (added, improved, fixed, removed, infra), what changed and what it taught.
  git history            every merged pull request after the last one the curated file covers becomes an automatic node, so the page grows by itself; a curated
                         node written later takes its place. The same history gives the numbers on the strip (days building, pull requests, commits) and the activity chart.
When git is not available (a copy of the code without its history) the page still shows the curated story.
"""
import json, os, re, subprocess
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CURATED = os.path.join(HERE, "config", "timeline.json")
KINDS = [("added", "ADDED"), ("improved", "IMPROVED"), ("fixed", "FIXED"), ("removed", "REMOVED"), ("infra", "PIPELINE")]
MERGE = re.compile(r"^Merge pull request #(\d+) from")
SQUASH = re.compile(r"\(#(\d+)\)\s*$")


def load_curated(path=CURATED):
    with open(path, encoding="utf-8") as f: return json.load(f)


def parse_log(text):
    """[(date, subject, body)] from `git log --format=%ad%x1f%s%x1f%b%x1e --date=short`."""
    out = []
    for rec in text.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip(): continue
        parts = rec.split("\x1f")
        if len(parts) < 2: continue
        out.append((parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else ""))
    return out


def git_history(repo=HERE, run=subprocess.run):
    """[(date, subject, body)], newest first, or None when there is no history to read."""
    try:
        r = run(["git", "-C", repo, "log", "--format=%ad%x1f%s%x1f%b%x1e", "--date=short"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not r.stdout.strip(): return None
        return parse_log(r.stdout)
    except Exception:
        return None


def pull_requests(log):
    """{number: (date, title)} for every merged pull request in the log: merge commits carry the title on the first line of their body, squash merges end their subject with (#N)."""
    prs = {}
    for date, subject, body in log:
        m = MERGE.match(subject)
        if m:
            title = next((ln.strip() for ln in body.splitlines() if ln.strip()), subject)
            prs[int(m.group(1))] = (date, title)
            continue
        m = SQUASH.search(subject)
        if m: prs[int(m.group(1))] = (date, SQUASH.sub("", subject).strip())
    return prs


def auto_nodes(prs, covered):
    """Nodes for the pull requests after the last one the curated file covers, oldest first."""
    rows = sorted(((n, d, t) for n, (d, t) in prs.items() if n > covered), key=lambda x: (x[1], x[0]))
    return [dict(date=d, phase="latest", kind="improved", tab="", prs=[n], title=t, what="", insight="", auto=True) for n, d, t in rows]


def activity(log):
    """Commits per day, oldest first: [(date, count)]."""
    c = Counter(d for d, _, _ in log)
    return sorted(c.items())


def build(repo=HERE, curated=None, log=None):
    cur = curated if curated is not None else load_curated()
    log = log if log is not None else git_history(repo)
    prs = pull_requests(log) if log else {}
    nodes = sorted(cur["nodes"], key=lambda n: n["date"])                    # stable: the curated order inside a day is kept
    auto = auto_nodes(prs, int(cur.get("covered_pr", 0)))
    phases = [dict(p, nodes=[n for n in nodes if n["phase"] == p["key"]]) for p in cur["phases"]]
    if auto:
        span = f'{auto[0]["date"][8:10].lstrip("0")} {_month(auto[0]["date"])} onwards'
        phases.append(dict(key="latest", label="Latest changes", span=span, blurb="Merged since the story was last written up. These appear automatically from the repository's history; a written-up version replaces each one.", nodes=auto))
    dates = [n["date"] for n in nodes + auto]
    stats = dict(first=min([d for d, _, _ in log] if log else dates), last=max(dates) if dates else "",
                 commits=len(log) if log else None, prs=len(prs) if prs else None, nodes=len(nodes) + len(auto), removed=sum(1 for n in nodes + auto if n["kind"] == "removed"))
    return dict(phases=phases, stats=stats, activity=activity(log) if log else [], repo=cur.get("repo", ""), kinds=KINDS)


def _month(iso):
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(iso[5:7]) - 1]
