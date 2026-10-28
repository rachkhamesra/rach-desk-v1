/Users/rachitkhamesra/.zprofile:2: no such file or directory: /opt/homebrew/bin/brew
import unittest
from unittest.mock import patch

import pandas as pd

import calls


class CallIntelligenceTest(unittest.TestCase):
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
