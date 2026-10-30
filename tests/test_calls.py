import unittest
from unittest.mock import patch
import json, os

import pandas as pd

import calls
import webpage


class CallIntelligenceTest(unittest.TestCase):
    def test_bundled_static_intelligence_contains_exact_requested_scope(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "call_intelligence_seed.json")
        with open(path, encoding="utf-8") as f: seed = json.load(f)
        requested = {"ETERNAL", "SHRIRAMFIN", "INFY", "PNB", "PGEL", "INDHOTEL", "DRREDDY", "APLAPOLLO", "CGPOWER", "TATACONSUM", "JSWSTEEL", "KEI", "SBICARD", "SHREECEM", "SWIGGY", "MAHABANK", "SAGILITY", "AXISBANK", "TORNTPHARM", "OBEROIRLTY", "FEDERALBNK", "RBLBANK", "AUBANK", "GODREJPROP", "NAM-INDIA", "ULTRACEMCO", "LTF", "VMM", "ADANIGREEN", "CROMPTON", "HAVELLS", "HDFCBANK", "YESBANK", "PERSISTENT", "ICICIBANK", "HDFCLIFE", "HINDZINC"}
        self.assertEqual(set(seed), requested)
        self.assertEqual(set(calls.PUBLISHED_SYMBOLS), requested)
        analysed = [x for x in seed.values() if x.get("analysis")]
        self.assertTrue(all(x["analysis"].get("next_quarter_outlook") for x in analysed))
        self.assertTrue(all(x["analysis"].get("analyst_focus") for x in analysed))
        self.assertEqual(seed["DRREDDY"]["transcript_status"], "missing")
        self.assertEqual(seed["CGPOWER"]["transcript_status"], "missing")
        self.assertEqual(seed["JSWSTEEL"]["transcript_status"], "missing")
        self.assertEqual(seed["APLAPOLLO"]["analysis"]["analysis_profile"], "forward_only_v1")
        self.assertEqual(len(seed["APLAPOLLO"]["analysis"]["analyst_focus"]), 2)
        self.assertNotIn("congratulations", seed["APLAPOLLO"]["analysis"])
        self.assertNotIn("key_actuals", seed["APLAPOLLO"]["analysis"])
        self.assertEqual(seed["PGEL"]["analysis"]["call_period"], "Q1 FY2027")
        refreshed = {"MAHABANK", "SAGILITY", "AXISBANK", "TORNTPHARM", "OBEROIRLTY", "FEDERALBNK", "RBLBANK", "AUBANK", "GODREJPROP", "NAM-INDIA", "ULTRACEMCO", "LTF", "VMM", "ADANIGREEN", "CROMPTON", "HAVELLS", "HDFCBANK", "YESBANK", "PERSISTENT", "ICICIBANK", "HDFCLIFE", "HINDZINC"}
        self.assertTrue(all(len(seed[s]["analysis"]["next_quarter_outlook"]) == 6 for s in refreshed))
        self.assertTrue(all(len(seed[s]["analysis"]["analyst_focus"]) == 4 for s in refreshed))
        self.assertTrue(all(seed[s]["analysis"]["analyst_focus_scope"] == "top_themes_by_question_count" for s in refreshed))
        batch_02 = {"AUBANK", "GODREJPROP", "NAM-INDIA", "ULTRACEMCO", "LTF", "VMM", "ADANIGREEN", "CROMPTON", "HAVELLS", "HDFCBANK", "YESBANK", "PERSISTENT", "ICICIBANK", "HDFCLIFE", "HINDZINC"}
        self.assertTrue(all(len(seed[s]["analysis"]["next_quarter_outlook"]) == 6 for s in batch_02))
        self.assertTrue(all(len(seed[s]["analysis"]["analyst_focus"]) == 4 for s in batch_02))
        self.assertTrue(all(seed[s]["analysis"]["analyst_focus_scope"] == "top_themes_by_question_count" for s in batch_02))

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
        self.assertIn("34 STATIC TRANSCRIPT SUMMARIES", html)
        self.assertIn("Does drought/El Nino in Maharashtra threaten asset quality?", html)
        self.assertIn("3 MISSING TRANSCRIPT", html)
        self.assertIn("FORWARD RISKS &amp; WATCHPOINTS", html)

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
