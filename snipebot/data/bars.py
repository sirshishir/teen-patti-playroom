"""
bars.py — One bar factory: session-aligned RTH resampling from 1-minute bars.

Problem this solves (FIX-7): Alpaca native hour bars are clock-aligned
(09:00–10:00 ET) and include pre/post-market, while the yfinance 1h fallback is
09:30-anchored RTH-only. Primary vs fallback therefore produce *different*
candles → different swings / order blocks / sweeps depending on which source
answered. Resampling both through this single function guarantees identical
candle boundaries: RTH-only (09:30–15:59 ET), anchored to 09:30.
"""

import pandas as pd
import pytz

_ET = pytz.timezone("US/Eastern")


def resample_rth(df_1min: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample 1-minute bars to *rule* ('1h' / '4h' / '1D'), RTH-only, anchored
    to 09:30 ET. Input index must be tz-aware; output is returned in UTC.
    """
    if df_1min is None or df_1min.empty:
        return df_1min

    df = df_1min.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.tz_convert(_ET).between_time("09:30", "15:59")
    if df.empty:
        return df.tz_convert("UTC")

    # Anchor the resample origin to 09:30 ET of the first session in the frame.
    origin = df.index.normalize()[0] + pd.Timedelta(hours=9, minutes=30)
    out = (df.resample(rule, origin=origin)
             .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
             .dropna())
    return out.tz_convert("UTC")
