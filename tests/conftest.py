import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from data.storage import StorageManager


def make_ohlcv_df(n=300, start="2023-01-01", symbol="AAPL") -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    dates = pd.date_range(start=start, periods=n, freq="B")
    np.random.seed(42)
    close = 150 + np.cumsum(np.random.randn(n) * 2)
    open_ = close + np.random.randn(n) * 0.5
    high = np.maximum(close, open_) + np.abs(np.random.randn(n))
    low  = np.minimum(close, open_) - np.abs(np.random.randn(n))
    volume = np.random.randint(30_000_000, 80_000_000, size=n)
    return pd.DataFrame({
        "datetime": dates,
        "symbol": symbol,
        "timeframe": "1D",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "adjusted_close": close,
    })


@pytest.fixture
def sample_ohlcv_df():
    return make_ohlcv_df()


@pytest.fixture
def in_memory_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    storage = StorageManager(db_path)
    yield storage
    storage.close()


@pytest.fixture
def mock_config():
    return {
        "watchlist": [{"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"}],
        "data": {
            "timeframes": ["1D"],
            "initial_history_days": 730,
            "initial_history_hours": 60,
            "db_path": ":memory:",
            "timezone": "America/New_York",
        },
        "indicators": {
            "trend": {"sma_periods": [20, 50, 200], "ema_periods": [9, 21],
                      "macd": {"fast": 12, "slow": 26, "signal": 9}, "adx_period": 14},
            "momentum": {"rsi_period": 14,
                         "stochastic": {"k_period": 14, "d_period": 3, "smooth_k": 3},
                         "roc_period": 12, "williams_r_period": 14},
            "volatility": {"bollinger_bands": {"period": 20, "std_dev": 2.0},
                           "atr_period": 14,
                           "keltner_channel": {"ema_period": 20, "atr_period": 10, "multiplier": 2.0}},
            "volume": {"obv": True, "vwap": True, "volume_sma_period": 20},
            "support_resistance": {"pivot_type": "standard", "week_high_low_periods": 52},
        },
        "signals": {
            "enabled": True,
            "timeframes": ["1D"],
            "rules": {
                "rsi_oversold": {"enabled": True, "threshold": 30, "severity": "warning"},
                "rsi_overbought": {"enabled": True, "threshold": 70, "severity": "warning"},
                "golden_cross": {"enabled": True, "fast_period": 50, "slow_period": 200, "severity": "alert"},
                "death_cross": {"enabled": True, "fast_period": 50, "slow_period": 200, "severity": "alert"},
                "macd_bullish_crossover": {"enabled": True, "severity": "info"},
                "macd_bearish_crossover": {"enabled": True, "severity": "info"},
                "near_52w_high": {"enabled": True, "proximity_pct": 5.0, "severity": "info"},
                "near_52w_low": {"enabled": True, "proximity_pct": 5.0, "severity": "alert"},
                "bb_squeeze": {"enabled": True, "bandwidth_threshold": 0.05, "severity": "info"},
                "bb_breakout_upper": {"enabled": True, "severity": "warning"},
                "bb_breakout_lower": {"enabled": True, "severity": "warning"},
                "volume_spike": {"enabled": True, "multiplier": 2.0, "severity": "info"},
            },
        },
        "output": {
            "terminal": {"enabled": True},
            "html_report": {"enabled": False},
            "logging": {"enabled": False},
        },
    }


@pytest.fixture
def mock_fetcher():
    m = MagicMock()
    m.fetch_all.return_value = {("AAPL", "1D"): 10}
    return m
