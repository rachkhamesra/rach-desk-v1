"""Wide (date x symbol) panels from the parsed daily files."""
import numpy as np, pandas as pd


def universe(parsed):
    last = [d for d in sorted(parsed) if parsed[d]["fo"] is not None][-1]
    return list(parsed[last]["fo"].index)


def wide(parsed, dates, symbols, part, col):
    cols = {}
    for d in dates:
        df = parsed[d].get(part)
        cols[d] = df[col].reindex(symbols) if df is not None else pd.Series(np.nan, index=symbols)
    return pd.DataFrame(cols).T.reindex(dates)
