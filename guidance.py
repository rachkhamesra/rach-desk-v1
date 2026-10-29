"""Fail-closed validation for guidance changes stated in one current transcript."""
from urllib.parse import urlparse


EXCHANGE_HOSTS = {
    "nseindia.com", "www.nseindia.com", "nsearchives.nseindia.com",
    "archives.nseindia.com", "bseindia.com", "www.bseindia.com",
}

EVIDENCE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {key: {"type": "string", "minLength": 1} for key in
                   ("speaker", "role", "location", "quote", "source_url", "filing_date", "call_period")},
    "required": ["speaker", "role", "location", "quote", "source_url", "filing_date", "call_period"],
}

CHANGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "direction": {"type": "string", "enum": ["upgrade", "increase", "improvement", "reduction", "downgrade"]},
        "topic": {"type": "string", "minLength": 1},
        "old_guidance": {"type": ["string", "null"]},
        "new_guidance": {"type": ["string", "null"]},
        "magnitude": {"type": "string", "minLength": 1},
        "materiality": {"type": "number", "exclusiveMinimum": 0},
        "explicit_statement": {"type": "string", "minLength": 1},
        "source_verified": {"type": "boolean", "const": True},
        "evidence_verified": {"type": "boolean", "const": True},
        "evidence": EVIDENCE_SCHEMA,
    },
    "required": ["direction", "topic", "old_guidance", "new_guidance", "magnitude", "materiality",
                 "explicit_statement", "source_verified", "evidence_verified", "evidence"],
}


def exchange_source(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and parsed.hostname in EXCHANGE_HOSTS and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def valid_change(change, call_period=None, source_url=None):
    if not isinstance(change, dict) or set(change) != set(CHANGE_SCHEMA["required"]):
        return False
    if change.get("direction") not in CHANGE_SCHEMA["properties"]["direction"]["enum"]:
        return False
    if change.get("source_verified") is not True or change.get("evidence_verified") is not True:
        return False
    score = change.get("materiality")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 < score < float("inf"):
        return False
    for key in ("topic", "magnitude", "explicit_statement"):
        if not isinstance(change.get(key), str) or not change[key].strip():
            return False
    old, new = change.get("old_guidance"), change.get("new_guidance")
    if (old is None) != (new is None) or (old is not None and (not old.strip() or not new.strip() or old == new)):
        return False
    evidence = change.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE_SCHEMA["required"]):
        return False
    if not all(isinstance(value, str) and value.strip() for value in evidence.values()):
        return False
    quote = evidence["quote"]
    if not (quote.startswith('"') and quote.endswith('"')) or len(quote) < 20:
        return False
    if not exchange_source(evidence["source_url"]):
        return False
    if call_period and evidence["call_period"] != call_period:
        return False
    if source_url and evidence["source_url"] != source_url:
        return False
    return True


def validated_changes(analysis, source_url=None):
    changes = analysis.get("material_guidance_changes", [])
    if not isinstance(changes, list):
        return []
    period = analysis.get("call_period")
    unique = {}
    for item in changes:
        if valid_change(item, period, source_url):
            key = (item["direction"], item["topic"], item["old_guidance"], item["new_guidance"], item["magnitude"])
            unique.setdefault(key, item)
    return sorted(unique.values(), key=lambda item: item["materiality"], reverse=True)
