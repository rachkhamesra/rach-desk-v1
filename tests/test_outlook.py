import outlook


def pts(*tones, summary="steady demand"):
    return {"next_quarter_outlook": [{"tone": t, "summary": summary} for t in tones]}


def label(*tones, changes=(), summary="steady demand"):
    return outlook.classify(pts(*tones, summary=summary), changes)["label"]


def test_six_labels_from_tones():
    assert label(*["positive"] * 6, summary="record order inflow, accelerating") == "bullish"
    assert label(*["positive"] * 5, "cautious") == "optimistic"
    assert label(*["positive"] * 4, "neutral", "neutral") == "optimistic"
    assert label("positive", "positive", "positive", "neutral", "neutral", "negative") == "positive"
    assert label("positive", "neutral", "neutral", "neutral", "neutral", "cautious") == "muted"
    assert label("positive", "cautious", "cautious", "cautious", "neutral", "neutral") == "cautious"
    assert label("positive", "neutral", "negative", "negative", "negative", "neutral") == "bearish"


def test_all_positive_without_strong_language_is_optimistic_not_bullish():
    assert label(*["positive"] * 6) == "optimistic"


def test_cautious_only_never_reads_bearish():
    assert label("cautious", "cautious", "cautious", "cautious") == "cautious"


def test_guidance_raise_or_cut_moves_the_score():
    up = [{"direction": "upgrade"}, {"direction": "increase"}]
    assert label(*["positive"] * 5, "neutral", changes=up) == "bullish"
    assert label("positive", "positive", "neutral", "neutral", "neutral", "neutral", changes=[{"direction": "downgrade"}]) == "muted"
    assert outlook.classify(pts(*["positive"] * 4), [{"direction": "reduction"}])["guidance"] == -1


def test_too_few_points_gives_no_label():
    assert outlook.classify(pts("positive", "positive")) is None
    assert outlook.classify({}) is None
    assert outlook.classify(pts("positive", "weird", "positive")) is None
