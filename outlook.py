"""Six-way read of management's near-term outlook, from the tagged next-quarter points of a call.

Each next-quarter point in the bundled transcript analysis carries a tone (positive, neutral, cautious,
negative). They are averaged, nudged by explicit guidance raises or cuts, and bucketed:

    BULLISH     nearly all points positive, with strong language (accelerating, record, raised...) or a lot of it
    OPTIMISTIC  clearly upbeat
    POSITIVE    leaning favourable
    MUTED       no clear direction: flat, mixed or neutral commentary
    CAUTIOUS    leaning unfavourable: hedged, headwinds acknowledged
    BEARISH     clearly negative, with at least one explicitly negative point

It is a reading aid built from those tags, not an independent view of the company. Fewer than three
near-term points is too little to call, so no label is given.
"""
import re

LABELS = ("bullish", "optimistic", "positive", "muted", "cautious", "bearish")
WEIGHT = {"positive": 1.0, "neutral": 0.0, "cautious": -.75, "negative": -1.5}
MIN_POINTS = 3
STRONG = re.compile(r"accelerat|record|step[- ]?up|upgrad|rais(?:ed|ing)|higher than|ahead of|robust|strong|surge|ramp|significant|momentum|"
                    r"outperform|more aggressive|beat|best ", re.I)


def classify(analysis, changes=()):
    """Return {label, score, counts, n, strong, guidance} or None when there is too little to judge."""
    points = [p for p in (analysis or {}).get("next_quarter_outlook") or [] if p.get("tone") in WEIGHT]
    if len(points) < MIN_POINTS: return None
    counts = {t: sum(1 for p in points if p["tone"] == t) for t in WEIGHT}
    base = sum(WEIGHT[p["tone"]] for p in points) / len(points)
    strong = sum(1 for p in points if p["tone"] == "positive" and STRONG.search(p.get("summary", "")))
    ups = sum(1 for c in changes if str(c.get("direction", "")).lower() in ("upgrade", "increase", "improvement"))
    downs = sum(1 for c in changes if str(c.get("direction", "")).lower() in ("downgrade", "reduction", "decrease"))
    guidance = max(-.5, min(.5, .25 * (ups - downs)))
    score = base + guidance
    if score >= .9 and (strong >= 1 or ups) or score >= .75 and (strong >= 3 or ups >= 2): label = "bullish"
    elif score >= .5: label = "optimistic"
    elif score >= .25: label = "positive"
    elif score > -.1: label = "muted"
    elif score > -.55 or not counts["negative"]: label = "cautious"
    else: label = "bearish"
    return dict(label=label, score=round(score, 2), counts=counts, n=len(points), strong=strong, guidance=ups - downs)
