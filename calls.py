"""Latest F&O earnings-call transcripts and narrowly scoped call intelligence."""
import hashlib
import io
import json
import os
import re
from datetime import timedelta
from urllib.parse import urlparse

import pandas as pd
import requests
from pypdf import PdfReader

import results


MODEL = os.environ.get("CALLS_MODEL", "gpt-6-luna")
MAX_NEW = int(os.environ.get("CALLS_MAX_NEW", "12"))
LOOKBACK_DAYS = int(os.environ.get("CALLS_LOOKBACK_DAYS", "150"))
PRIORITY_SYMBOLS = ("CUMMINSIND", "ABB", "PNB", "PNBHOUSING", "HEROMOTOCO")


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "company_type": {"type": "string", "enum": ["manufacturer", "bank_lender", "other"]},
        "call_period": {"type": "string"},
        "next_quarter_outlook": {"type": "array", "items": {"$ref": "#/$defs/outlook"}},
        "analyst_focus": {"type": "array", "items": {"$ref": "#/$defs/focus"}},
        "congratulations": {"$ref": "#/$defs/congratulations"},
        "manufacturer": {"$ref": "#/$defs/manufacturer"},
        "bank_lender": {"$ref": "#/$defs/bank"},
        "key_risks": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": ["company_type", "call_period", "next_quarter_outlook", "analyst_focus", "congratulations", "manufacturer", "bank_lender", "key_risks"],
    "$defs": {
        "outlook": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "topic": {"type": "string"}, "summary": {"type": "string"},
                "tone": {"type": "string", "enum": ["positive", "neutral", "cautious", "negative"]},
                "evidence": {"type": "string"},
            },
            "required": ["topic", "summary", "tone", "evidence"],
        },
        "focus": {
            "type": "object", "additionalProperties": False,
            "properties": {"topic": {"type": "string"}, "why_it_mattered": {"type": "string"}, "question_count": {"type": "integer", "minimum": 1}},
            "required": ["topic", "why_it_mattered", "question_count"],
        },
        "congratulations": {
            "type": "object", "additionalProperties": False,
            "properties": {"count": {"type": "integer", "minimum": 0}, "analyst_turns": {"type": "integer", "minimum": 0}, "index_pct": {"type": "number", "minimum": 0, "maximum": 100}},
            "required": ["count", "analyst_turns", "index_pct"],
        },
        "manufacturer": {
            "type": ["object", "null"], "additionalProperties": False,
            "properties": {k: {"type": ["string", "null"]} for k in ["revenue_growth", "volume_growth", "order_inflow", "demand_outlook", "margin_outlook", "ebitda_margin"]},
            "required": ["revenue_growth", "volume_growth", "order_inflow", "demand_outlook", "margin_outlook", "ebitda_margin"],
        },
        "bank": {
            "type": ["object", "null"], "additionalProperties": False,
            "properties": {k: {"type": ["string", "null"]} for k in ["credit_growth", "credit_deposit_ratio", "disbursements", "nim_outlook", "asset_quality", "credit_cost_outlook"]},
            "required": ["credit_growth", "credit_deposit_ratio", "disbursements", "nim_outlook", "asset_quality", "credit_cost_outlook"],
        },
    },
}


INSTRUCTIONS = """You are a disciplined Indian-equity earnings-call analyst. Analyse only the supplied transcript; never fill gaps from general knowledge.
The user chiefly wants evidence about the next one or two quarters. Keep every summary short, concrete and decision-useful. Distinguish management guidance from analyst questions. Do not treat historical performance as outlook unless management explicitly connects it to the future.

For next_quarter_outlook, return at most six genuinely forward-looking items. Evidence must be a short verbatim fragment of at most 18 words. If there is no usable outlook, return an empty list.
For analyst_focus, group repeated questions by topic, estimate the number of analyst question turns on that topic, and return at most six topics in descending attention.
Congratulations count means analyst turns that explicitly congratulate, compliment, or say well done to management. analyst_turns is the total substantive analyst question turns. index_pct = 100 * count / analyst_turns, or 0 when there are none.
Classify automobile OEMs, auto ancillaries, capital goods, defence and industrial producers as manufacturer. For them extract only revenue growth, volume growth, order inflow, demand outlook, margin outlook and EBITDA margin. Classify banks and lenders as bank_lender and extract only credit growth, credit-deposit ratio, disbursements, NIM outlook, asset quality and credit-cost outlook. Use null where a requested metric is absent. For all others set both sector metric objects to null.
Do not provide investment advice or invent numerical precision."""


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def discover(asof, fo_symbols):
    """Return the newest transcript filing for each requested F&O symbol."""
    start = pd.Timestamp(asof) - timedelta(days=LOOKBACK_DAYS)
    raw = results._get("/api/corporate-announcements", {
        "index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{asof:%d-%m-%Y}",
    })
    wanted = set(fo_symbols); latest = {}
    for x in raw:
        symbol = str(x.get("symbol") or "").upper()
        text = " ".join(str(x.get(k) or "") for k in ("desc", "attchmntText")).lower()
        url = str(x.get("attchmntFile") or "")
        if symbol not in wanted or "transcript" not in text or not url.lower().endswith(".pdf"): continue
        filed_at = pd.to_datetime(x.get("an_dt"), dayfirst=True, errors="coerce")
        row = {"symbol": symbol, "filed_at": "" if pd.isna(filed_at) else filed_at.isoformat(), "source_url": url,
               "description": str(x.get("attchmntText") or x.get("desc") or "Transcript")}
        if symbol not in latest or row["filed_at"] > latest[symbol]["filed_at"]: latest[symbol] = row
    return latest


def _pdf_text(url):
    r = requests.get(url, headers=results.HEADERS, timeout=90)
    r.raise_for_status()
    if len(r.content) > 35_000_000: raise ValueError("transcript PDF is too large")
    reader = PdfReader(io.BytesIO(r.content))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def extract_pdf(url):
    text = _pdf_text(url)
    # Some NSE attachments are one-page covering letters containing the actual
    # company-hosted transcript link rather than the transcript itself.
    if len(text) < 4000:
        links = re.findall(r"https://[^\s<>]+?\.pdf", text, flags=re.I)
        for link in links:
            link = link.rstrip(".,);]")
            host = (urlparse(link).hostname or "").lower()
            if not host or host in {"localhost", "127.0.0.1", "::1"}: continue
            if "transcript" not in link.lower() and "concall" not in link.lower() and "earning" not in link.lower(): continue
            linked = _pdf_text(link)
            if len(linked) > len(text): text = linked
            if len(text) >= 1500: break
    if len(text) < 1500: raise ValueError("transcript contains too little extractable text")
    return text[:600_000]


def _response_text(payload):
    for item in payload.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text": return part.get("text", "")
    raise ValueError("model response had no output_text")


def analyse(symbol, transcript, api_key):
    r = requests.post("https://api.openai.com/v1/responses", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    }, json={
        "model": MODEL,
        "instructions": INSTRUCTIONS,
        "input": f"Company symbol: {symbol}\n\nTRANSCRIPT\n{transcript}",
        "text": {"format": {"type": "json_schema", "name": "call_intelligence", "strict": True, "schema": SCHEMA}},
    }, timeout=300)
    r.raise_for_status()
    return json.loads(_response_text(r.json()))


def select_pending(latest, cache, limit=MAX_NEW):
    """Reserve the first slots for the user's priority names, then take newest calls."""
    changed = {s: x for s, x in latest.items() if x["source_url"] != cache.get(s, {}).get("source_url")}
    chosen = [changed.pop(s) for s in PRIORITY_SYMBOLS if s in changed]
    newest = sorted(changed.values(), key=lambda x: x["filed_at"], reverse=True)
    return (chosen + newest)[:limit]


def load(root, asof, fo_symbols, log=print):
    """Refresh transcript intelligence without ever blocking the market build."""
    path = os.path.join(root, "call_intelligence.json")
    bundled = _load_json(os.path.join(os.path.dirname(__file__), "call_intelligence_seed.json"), {})
    cache = {**_load_json(path, {}), **bundled}
    if bundled: log(f"call intelligence: {len(bundled)} bundled transcript analyses loaded")
    try:
        latest = discover(asof, fo_symbols)
        log(f"call transcripts: {len(latest)} latest F&O filings found")
    except Exception as e:
        log(f"call-transcript discovery failed ({e}); using cached analysis")
        return cache

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    all_pending = [x for x in latest.values() if x["source_url"] != cache.get(x["symbol"], {}).get("source_url")]
    pending = select_pending(latest, cache)
    if pending and not api_key:
        log(f"call intelligence: {len(all_pending)} transcript(s) pending; OPENAI_API_KEY is not configured")
        return cache

    done = 0
    for meta in pending:
        symbol = meta["symbol"]
        try:
            transcript = extract_pdf(meta["source_url"])
            analysis = analyse(symbol, transcript, api_key)
            cache[symbol] = {**meta, "model": MODEL, "content_sha256": hashlib.sha256(transcript.encode()).hexdigest(), "analysis": analysis}
            _save_json(path, cache)
            done += 1
            log(f"call intelligence: analysed {symbol} ({len(transcript):,} characters)")
        except Exception as e:
            log(f"call intelligence: {symbol} failed ({e})")
    if done: log(f"call intelligence: {done} new transcript(s) cached; {max(0, len(all_pending) - len(pending))} remain queued")
    return cache
