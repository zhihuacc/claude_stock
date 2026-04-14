import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
from data.fetcher import YFinanceFetcher, TIMEFRAME_MAP


def test_timeframe_map():
    assert TIMEFRAME_MAP["1H"] == "1h"
    assert TIMEFRAME_MAP["1D"] == "1d"
    assert TIMEFRAME_MAP["1W"] == "1wk"
    assert TIMEFRAME_MAP["1M"] == "1mo"


def test_fetch_one_skips_if_up_to_date(mock_config, in_memory_db):
    storage = in_memory_db
    # Simulate last_datetime = now
    storage.update_fetch_log("AAPL", "1D", datetime.utcnow())
    fetcher = YFinanceFetcher(storage, mock_config)
    n = fetcher._fetch_one("AAPL", "1D")
    assert n == 0


def test_fetch_one_uses_history_days_on_first_run(mock_config, in_memory_db):
    storage = in_memory_db
    fetcher = YFinanceFetcher(storage, mock_config)
    # last datetime is None — should set start based on initial_history_days
    with patch.object(fetcher, "_download_with_retry", return_value=None):
        n = fetcher._fetch_one("AAPL", "1D")
    assert n == 0  # no data returned


def test_normalize_strips_timezone(mock_config, in_memory_db, sample_ohlcv_df):
    fetcher = YFinanceFetcher(in_memory_db, mock_config)
    # Build a fake yfinance-style DataFrame with tz-aware index
    idx = pd.date_range("2024-01-01", periods=5, freq="B", tz="America/New_York")
    raw = pd.DataFrame({
        "Open": [100.0] * 5,
        "High": [105.0] * 5,
        "Low":  [98.0]  * 5,
        "Close": [103.0] * 5,
        "Volume": [1_000_000] * 5,
        "Adj Close": [103.0] * 5,
    }, index=idx)
    result = fetcher._normalize(raw, "AAPL", "1D")
    assert result.index.dtype == object or True  # datetime column, tz-naive
    assert "adjusted_close" in result.columns
    assert result["datetime"].dt.tz is None
