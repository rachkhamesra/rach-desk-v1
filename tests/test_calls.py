import unittest
from unittest.mock import patch
import json, os

import pandas as pd

import calls
import webpage


class CallIntelligenceTest(unittest.TestCase):
    def test_bundled_static_intelligence_contains_priority_and_requested_names(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "call_intelligence_seed.json")
        with open(path, encoding="utf-8") as f: seed = json.load(f)
        requested = {
            "TVSMOTOR", "EICHERMOT", "PGEL", "INDHOTEL", "BAJAJ-AUTO", "UNOMINDA",
            "BHARATFORG", "MOTHERSON", "AUBANK", "INFY", "SRF", "HINDPETRO", "GODREJPROP",
            "ETERNAL", "NAM-INDIA", "ULTRACEMCO", "SHRIRAMFIN",
        }
        self.assertTrue(set(calls.PRIORITY_SYMBOLS).issubset(seed))
        self.assertTrue(requested.issubset(seed))
        self.assertTrue(all(x.get("analysis", {}).get("next_quarter_outlook") for x in seed.values()))
        self.assertTrue(all(x.get("analysis", {}).get("analyst_focus") for x in seed.values()))

    def test_call_library_reuses_stored_summary_fields(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "call_intelligence_seed.json")
        with open(path, encoding="utf-8") as f: seed = json.load(f)
        html = webpage.tab_call_library({"calls": seed, "unresolved": set(), "results": [], "dates": [pd.Timestamp("2026-10-29")]})
        self.assertIn("Conference Call Library", html)
        self.assertIn("NEXT QUARTER OUTLOOK", html)
        self.assertIn("TOP ANALYST CONCERNS", html)
        self.assertIn("IMPORTANT TAKEAWAYS", html)
        self.assertIn("CONGRATULATIONS", html)
        self.assertIn("transcript", html)

    @patch("calls.results._get")
    def test_discover_keeps_latest_transcript_for_fo_only(self, get):
        get.return_value = [
            {"symbol": "AAA", "an_dt": "20-Oct-2026 10:00:00", "desc": "Con Call Updates", "attchmntText": "Transcript", "attchmntFile": "https://x/old.pdf"},
            {"symbol": "AAA", "an_dt": "21-Oct-2026 10:00:00", "desc": "Con Call Updates", "attchmntText": "Transcript", "attchmntFile": "https://x/new.pdf"},
            {"symbol": "BBB", "an_dt": "22-Oct-2026 10:00:00", "desc": "Con Call Updates", "attchmntText": "Transcript", "attchmntFile": "https://x/b.pdf"},
            {"symbol": "AAA", "an_dt": "23-Oct-2026 10:00:00", "desc": "Investor meet", "attchmntText": "Presentation", "attchmntFile": "https://x/slides.pdf"},
        ]
        got = calls.discover(pd.Timestamp("2026-10-27"), ["AAA"])
        self.assertEqual(set(got), {"AAA"})
        self.assertEqual(got["AAA"]["source_url"], "https://x/new.pdf")

    def test_response_text(self):
        payload = {"output": [{"content": [{"type": "output_text", "text": "{\"ok\":true}"}]}]}
        self.assertEqual(calls._response_text(payload), '{"ok":true}')

    def test_priority_calls_take_first_five_slots_then_newest(self):
        latest = {}
        for i, symbol in enumerate(calls.PRIORITY_SYMBOLS):
            latest[symbol] = {"symbol": symbol, "filed_at": f"2026-01-0{i + 1}T00:00:00", "source_url": f"https://x/{symbol}.pdf"}
        for i in range(10):
            symbol = f"LATEST{i}"
            latest[symbol] = {"symbol": symbol, "filed_at": f"2026-10-{i + 1:02d}T00:00:00", "source_url": f"https://x/{symbol}.pdf"}
        got = calls.select_pending(latest, {}, limit=12)
        self.assertEqual([x["symbol"] for x in got[:5]], list(calls.PRIORITY_SYMBOLS))
        self.assertEqual([x["symbol"] for x in got[5:]], [f"LATEST{i}" for i in range(9, 2, -1)])


if __name__ == "__main__":
    unittest.main()
