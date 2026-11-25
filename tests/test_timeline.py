import json
import timeline


LOG = ("2026-11-23\x1fMerge pull request #93 from rachkhamesra/claude/x\x1fNifty trend flag\n\nmore text\x1e"
       "2026-11-23\x1fNifty trend flag: banner on Today\x1f\x1e"
       "2026-11-25\x1fMerge pull request #95 from rachkhamesra/claude/y\x1fA new screen\x1e"
       "2026-11-26\x1fAdd the thing (#96)\x1f\x1e"
       "2026-10-27\x1fAdd Cash Accumulation Watch (#4)\x1f\x1e")


def test_pull_requests_are_read_from_merge_commits_and_squash_subjects():
    prs = timeline.pull_requests(timeline.parse_log(LOG))
    assert prs[93] == ("2026-11-23", "Nifty trend flag") and prs[95] == ("2026-11-25", "A new screen") and prs[96] == ("2026-11-26", "Add the thing") and prs[4][1] == "Add Cash Accumulation Watch"


def test_only_pull_requests_after_the_curated_ones_become_automatic_nodes():
    prs = timeline.pull_requests(timeline.parse_log(LOG))
    nodes = timeline.auto_nodes(prs, covered=94)
    assert [n["prs"] for n in nodes] == [[95], [96]] and all(n["auto"] and n["phase"] == "latest" for n in nodes)


def test_build_joins_the_curated_story_to_the_history_and_survives_no_history():
    cur = dict(covered_pr=94, repo="a/b", phases=[dict(key="p", label="P", span="x", blurb="b")],
               nodes=[dict(date="2026-11-23", phase="p", kind="added", tab="T", prs=[93], title="One", what="w", insight="i")])
    T = timeline.build(curated=cur, log=timeline.parse_log(LOG))
    assert [p["key"] for p in T["phases"]] == ["p", "latest"] and T["stats"]["prs"] == 4 and T["stats"]["commits"] == 5 and T["activity"][0] == ("2026-10-27", 1)
    none = timeline.build(curated=cur, log=[])
    assert [p["key"] for p in none["phases"]] == ["p"] and none["stats"]["commits"] is None and none["activity"] == []


def test_the_curated_file_is_well_formed():
    cur = timeline.load_curated(); keys = {p["key"] for p in cur["phases"]}; kinds = {k for k, _ in timeline.KINDS}
    assert cur["nodes"] and all(n["phase"] in keys and n["kind"] in kinds and len(n["date"]) == 10 and n["title"] for n in cur["nodes"])
    assert all(n["prs"] == sorted(set(n["prs"])) for n in cur["nodes"])                      # no repeated pull-request numbers inside a node
    assert max(p for n in cur["nodes"] for p in n["prs"]) <= cur["covered_pr"]
