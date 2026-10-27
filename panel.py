"""Wide (date x symbol) panels from the parsed daily files."""
import numpy as np, pandas as pd


def universe(parsed, requested=None):
    last = [d for d in sorted(parsed) if parsed[d]["cm"] is not None][-1]
    available = set(parsed[last]["cm"].index)
    return [s for s in (requested or sorted(available)) if s in available]


def wide(parsed, dates, symbols, part, col):
    cols = {}
    for d in dates:
        df = parsed[d].get(part)
        cols[d] = df[col].reindex(symbols) if df is not None else pd.Series(np.nan, index=symbols)
    return pd.DataFrame(cols).T.reindex(dates)
