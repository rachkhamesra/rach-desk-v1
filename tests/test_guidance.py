import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

import calls
import guidance
import webpage


def sample_change(direction="upgrade", old="12%–14%", new="15%–17%", materiality=3):
    return {
        "direction": direction, "topic": "Synthetic current guidance", "old_guidance": old,
        "new_guidance": new, "magnitude": "3 percentage points", "materiality": materiality,
        "explicit_statement": "Management explicitly revises guidance in this transcript.",
        "source_verified": True, "evidence_verified": True,
        "evidence": {
            "speaker": "Example Manager", "role": "CEO", "location": "Transcript page 3",
            "quote": '"We are revising our guidance upwards from 12% to 15%."',
            "source_url": "https://nsearchives.nseindia.com/corporate/fixture.pdf",
            "filing_date": "2026-10-28", "call_period": "Q2 FY2027",
        },
    }


class GuidanceTests(unittest.TestCase):
    def test_gate_requires_current_exchange_evidence_and_paired_figures(self):
        self.assertTrue(guidance.valid_change(sample_change(), "Q2 FY2027", sample_change()["evidence"]["source_url"]))
        for key in sample_change():
            broken = sample_change(); del broken[key]
            self.assertFalse(guidance.valid_change(broken), key)
        broken = sample_change(); broken["evidence"]["source_url"] = "https://company.example/transcript.pdf"
        self.assertFalse(guidance.valid_change(broken))
        broken = sample_change(); broken["evidence"]["call_period"] = "Q1 FY2027"
        self.assertFalse(guidance.valid_change(broken, "Q2 FY2027"))
        broken = sample_change(); broken["new_guidance"] = None
        self.assertFalse(guidance.valid_change(broken))
        no_pair = sample_change("improvement", None, None)
        self.assertTrue(guidance.valid_change(no_pair))

    def test_exact_seed_changes_use_only_latest_transcript(self):
        seed = json.loads(Path("call_intelligence_seed.json").read_text())
        expected = {"ETERNAL": 0, "SHRIRAMFIN": 1, "INFY": 1, "PNB": 1, "PGEL": 0, "INDHOTEL": 1}
        for symbol, count in expected.items():
            entry = seed[symbol]
            changes = guidance.validated_changes(entry["analysis"], entry["source_url"])
            self.assertEqual(len(changes), count, symbol)
            for item in changes:
                self.assertEqual(item["evidence"]["source_url"], entry["source_url"])
                self.assertEqual(item["evidence"]["call_period"], entry["analysis"]["call_period"])
                self.assertTrue(item["evidence"]["quote"].startswith('"'))
                self.assertNotIn("prior_evidence", item)

    @patch("calls._pdf_text")
    def test_parser_rejects_off_exchange_and_cover_letters(self, pdf):
        pdf.return_value = "Cover letter transcript https://company.example/transcript.pdf"
        with self.assertRaises(ValueError):
            calls.extract_pdf("https://nsearchives.nseindia.com/corporate/x.pdf")
        self.assertEqual(pdf.call_count, 1)
        with self.assertRaises(ValueError):
            calls.extract_pdf("https://company.example/transcript.pdf")
        self.assertEqual(pdf.call_count, 1)

    @patch("calls.discover", side_effect=RuntimeError("offline"))
    @patch("calls._load_json")
    def test_cache_is_filtered_to_published_symbols(self, load, discover):
        allowed = {symbol: {"analysis": {"material_guidance_changes": []}} for symbol in calls.PUBLISHED_SYMBOLS}
        load.side_effect = [dict(allowed, AUBANK={"analysis": {}}), allowed]
        got = calls.load("/unused", "2026-10-29", [], log=lambda _: None)
        self.assertEqual(set(got), set(calls.PUBLISHED_SYMBOLS))

    def test_row_above_chart_hides_without_change_and_opens_evidence(self):
        html = webpage.tab_stocks({})
        self.assertLess(html.index('id="guidance-row"'), html.index('id="chartbox"'))
        node = shutil.which("node") or os.environ.get("TEST_NODE")
        self.assertTrue(node, "Set TEST_NODE to run JavaScript interaction checks")
        script = webpage.JS
        start = script.index("function escH(")
        end = script.index("function callPanel(", start)
        fixture = json.dumps(sample_change())
        checks = '''
const assert=require('node:assert/strict');
const detail={open:false,scrollIntoView(){this.scrolled=true},focus(){this.focused=true}};
const button={};const row={hidden:true,innerHTML:'',className:'',querySelector(){return button}};
global.document={getElementById(id){return id==='guidance-row'?row:detail}};
guidanceRow({});assert.equal(row.hidden,true);assert.equal(row.innerHTML,'');
const g=FIXTURE;guidanceRow({call:{analysis:{material_guidance_changes:[g]}}});
assert.equal(row.hidden,false);assert.match(row.className,/upgrade/);assert.match(row.innerHTML,/12%–14%/);
button.onclick();assert.equal(detail.open,true);assert.equal(detail.focused,true);assert.equal(detail.scrolled,true);
g.direction='downgrade';guidanceRow({call:{analysis:{material_guidance_changes:[g]}}});assert.match(row.className,/downgrade/);
g.old_guidance=null;g.new_guidance=null;g.magnitude='minimum 7 basis points';guidanceRow({call:{analysis:{material_guidance_changes:[g]}}});assert.match(row.innerHTML,/minimum 7 basis points/);assert.ok(!row.innerHTML.includes('null'));
guidanceRow({call:{analysis:{material_guidance_changes:[]}}});assert.equal(row.hidden,true);assert.equal(row.innerHTML,'');
'''.replace('FIXTURE', fixture)
        subprocess.run([node, "-e", script[start:end] + checks], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
