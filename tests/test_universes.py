import io, unittest
import pandas as pd
import universes


class UniverseParsingTest(unittest.TestCase):
    def test_index_symbols_are_normalised(self):
        raw = b"Company Name,Industry,Symbol,Series,ISIN Code\nA,X, abc ,EQ,1\nB,X,DEF,EQ,2\n"
        self.assertEqual(universes._symbols_csv(raw), ["ABC", "DEF"])

    def test_market_cap_list_uses_rank_order_and_caps_at_1000(self):
        df = pd.DataFrame({"Rank": [1001, 2, 1], "Symbol": ["LOW", "two", "one"],
                           "Average Market Capitalization (Rs. Cr)": [500, 22000, 9000]})
        buf = io.BytesIO(); df.to_excel(buf, index=False)
        symbols, caps = universes._top1000(buf.getvalue())
        self.assertEqual(symbols, ["ONE", "TWO"])
        self.assertEqual(caps, {"ONE": 9000.0, "TWO": 22000.0})

    def test_market_cap_lakh_values_are_converted_to_crore(self):
        df = pd.DataFrame({"Rank": [1, 2, 3], "Symbol": ["SMALL", "MID", "LARGE"],
                           "Average Market Capitalization (Rs. Lakhs)": [900000, 2000000, 4100000]})
        buf = io.BytesIO(); df.to_excel(buf, index=False)
        _, caps = universes._top1000(buf.getvalue())
        self.assertEqual(caps, {"SMALL": 9000.0, "MID": 20000.0, "LARGE": 41000.0})


if __name__ == "__main__":
    unittest.main()


class CompleteTop1000Test(unittest.TestCase):
    def test_a_stock_in_an_index_but_missing_from_the_ranking_is_added_after_it(self):
        raw = {"top1000": ["A", "B"], "nifty500": ["B", "MCX"], "nifty100": ["A"], "midcap150": ["MCX", "C"], "smallcap250": [], "fo": ["D"]}
        out = universes.complete_top1000(raw)
        self.assertEqual(out["top1000"], ["A", "B", "MCX", "C", "D"])             # ranking order kept, no duplicates
