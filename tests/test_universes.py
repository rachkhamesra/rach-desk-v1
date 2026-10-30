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


if __name__ == "__main__":
    unittest.main()
