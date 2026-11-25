# Notes for working on this repository

## Keep the Timeline up to date
The **Timeline** tab tells how the page evolved. It reads `config/timeline.json` (a written-up story) and the repository's git history (automatic nodes).

When you ship a user-visible change (a tab, a screen, a rule, a removal, a data fix, a speed-up), add a node to `config/timeline.json` in the same change:
- `date` (YYYY-MM-DD), `phase` (an existing phase key, or add a phase when a new chapter begins), `kind` (`added`, `improved`, `fixed`, `removed`, `infra`), `tab` (where it shows), `title`.
- `what`: one or two plain sentences on what changed. `insight`: what it showed or why it matters. Use numbers you measured; say nothing you did not check.
- `prs`: the pull-request number(s). Raise `covered_pr` to the highest number the file now covers; merged pull requests above it appear automatically as dashed "Latest changes" nodes until they are written up.
- Removals matter as much as additions: record what was taken out and why.
